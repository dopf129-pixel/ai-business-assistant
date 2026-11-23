"""Strict, redacting CSV importer for owner-supplied provisional movements."""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import date
from hashlib import sha256
from io import StringIO
import json
import re
from types import MappingProxyType
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from services.fifo_cost_provisional_fbo_csv_import_service import (
    FifoCostProvisionalFboCsvImportService,
)
from services.fifo_cost_provisional_timeline_contracts import (
    ProvisionalEventSource,
    ProvisionalStockZone,
    ProvisionalTimelineEvent,
    ProvisionalTimelineEventKind,
    scope_fingerprint,
)
from services.fifo_cost_transition_contracts import ScopeIdentity, normalize_store_timezone


@dataclass(frozen=True, slots=True)
class ProvisionalMovementsDocument:
    file_sha256: str
    document_fingerprint: str
    normalized_fingerprint: str
    scope_fingerprint: str
    timezone_name: str
    row_count: int
    total_units: int
    event_counts: object
    events: tuple[ProvisionalTimelineEvent, ...] = field(repr=False)


@dataclass(frozen=True, slots=True)
class ProvisionalMovementsParseResult:
    status: str
    document: ProvisionalMovementsDocument | None
    issue_codes: tuple[str, ...]


class FifoCostProvisionalMovementsImportService:
    MAX_FILE_BYTES = 10 * 1024 * 1024
    MAX_ROWS = 50_000
    MAX_TOTAL_UNITS = 1_000_000
    MAX_FILENAME_CHARS = 255
    MAX_REFERENCE_CHARS = 100
    MAX_POSTING_CHARS = 128
    HEADER = (
        "event_kind", "event_reference", "effective_at", "sku", "quantity",
        "posting_number", "stock_zone", "resellable", "source_reference",
    )
    _SAFE_REFERENCE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:#/-]{0,99}$")
    _SKU = re.compile(r"^[0-9]{1,40}$")
    _QUANTITY = re.compile(r"^[0-9]{1,7}$")
    _POSTING = FifoCostProvisionalFboCsvImportService._POSTING_RE
    _KINDS = {kind.value: kind for kind in ProvisionalTimelineEventKind if kind not in {
        ProvisionalTimelineEventKind.BUYER_DISPATCH,
        ProvisionalTimelineEventKind.BUYOUT,
    }}
    _ZONE_ALIASES = {zone.value: zone for zone in ProvisionalStockZone}

    def parse_csv(self, *, payload, filename, scope, timezone_name):
        if not isinstance(scope, ScopeIdentity):
            return self._error("FIFO_PROVISIONAL_SCOPE_INVALID")
        if (not isinstance(filename, str) or not filename.strip()
                or len(filename) > self.MAX_FILENAME_CHARS
                or not filename.lower().endswith(".csv")):
            return self._error("FIFO_PROVISIONAL_MOVEMENTS_FILENAME_INVALID")
        if isinstance(payload, memoryview):
            if payload.nbytes > self.MAX_FILE_BYTES:
                return self._error("FIFO_PROVISIONAL_MOVEMENTS_FILE_SIZE_INVALID")
            payload = payload.tobytes()
        if not isinstance(payload, (bytes, bytearray)):
            return self._error("FIFO_PROVISIONAL_MOVEMENTS_PAYLOAD_INVALID")
        raw = bytes(payload)
        if not raw or len(raw) > self.MAX_FILE_BYTES or b"\0" in raw:
            return self._error("FIFO_PROVISIONAL_MOVEMENTS_FILE_SIZE_INVALID")
        try:
            timezone_name = normalize_store_timezone(timezone_name)
            zone = ZoneInfo(timezone_name)
        except (TypeError, ValueError, ZoneInfoNotFoundError):
            return self._error("FIFO_PROVISIONAL_MOVEMENTS_TIMEZONE_INVALID")
        try:
            text = raw.decode("utf-8-sig", errors="strict")
        except UnicodeDecodeError:
            return self._error("FIFO_PROVISIONAL_MOVEMENTS_ENCODING_INVALID")

        scope_digest = scope_fingerprint(scope, timezone_name)
        event_by_reference = {}
        events = []
        event_counts = {}
        total_units = 0
        try:
            reader = csv.reader(StringIO(text, newline=""), delimiter=";", strict=True)
            header = next(reader, None)
            if header is None or tuple(self._header_name(v) for v in header) != self.HEADER:
                return self._error("FIFO_PROVISIONAL_MOVEMENTS_HEADER_INVALID")
            for row_number, cells in enumerate(reader, start=1):
                if not cells or all(not str(cell).strip() for cell in cells):
                    continue
                if row_number > self.MAX_ROWS or len(cells) != len(self.HEADER):
                    return self._error("FIFO_PROVISIONAL_MOVEMENTS_ROW_INVALID")
                value = {name: str(cells[index]).strip() for index, name in enumerate(self.HEADER)}
                kind = self._KINDS.get(value["event_kind"].upper())
                if kind is None:
                    return self._error("FIFO_PROVISIONAL_MOVEMENTS_KIND_INVALID")
                if not self._SAFE_REFERENCE.fullmatch(value["event_reference"]):
                    return self._error("FIFO_PROVISIONAL_MOVEMENTS_REFERENCE_INVALID")
                if (not self._SAFE_REFERENCE.fullmatch(value["source_reference"])
                        or not any(char.isdigit() for char in value["source_reference"])
                        or "://" in value["source_reference"]):
                    return self._error("FIFO_PROVISIONAL_MOVEMENTS_SOURCE_REFERENCE_INVALID")
                reference = value["event_reference"]
                reference_key = self._digest("event-ref-v1", reference)
                if reference_key in event_by_reference:
                    return self._error("FIFO_PROVISIONAL_MOVEMENTS_DUPLICATE_REFERENCE")
                sku = value["sku"]
                if not self._SKU.fullmatch(sku) or sku != scope.sku:
                    return self._error("FIFO_PROVISIONAL_MOVEMENTS_SKU_MISMATCH")
                quantity_text = value["quantity"]
                if not self._QUANTITY.fullmatch(quantity_text):
                    return self._error("FIFO_PROVISIONAL_MOVEMENTS_QUANTITY_INVALID")
                quantity = int(quantity_text)
                if quantity <= 0:
                    return self._error("FIFO_PROVISIONAL_MOVEMENTS_QUANTITY_INVALID")
                total_units += quantity
                if total_units > self.MAX_TOTAL_UNITS:
                    return self._error("FIFO_PROVISIONAL_MOVEMENTS_UNIT_LIMIT_EXCEEDED")
                moment = FifoCostProvisionalFboCsvImportService._parse_moment(
                    value["effective_at"], zone,
                )
                if moment is None or moment.precision != "INSTANT":
                    return self._error("FIFO_PROVISIONAL_MOVEMENTS_TIME_INVALID")
                posting = value["posting_number"]
                posting_key = None
                if posting:
                    if (len(posting) > self.MAX_POSTING_CHARS
                            or not self._POSTING.fullmatch(posting)):
                        return self._error("FIFO_PROVISIONAL_MOVEMENTS_POSTING_INVALID")
                    posting_key = sha256(posting.encode("utf-8")).hexdigest()
                zone_value = value["stock_zone"]
                stock_zone = self._ZONE_ALIASES.get(zone_value.casefold()) if zone_value else None
                if zone_value and stock_zone is None:
                    return self._error("FIFO_PROVISIONAL_MOVEMENTS_ZONE_INVALID")
                resellable_text = value["resellable"].casefold()
                if resellable_text in {"true", "false"}:
                    resellable = resellable_text == "true"
                elif not resellable_text:
                    resellable = None
                else:
                    return self._error("FIFO_PROVISIONAL_MOVEMENTS_RESELLABLE_INVALID")
                if not self._valid_fields(kind, posting_key, stock_zone, resellable):
                    return self._error("FIFO_PROVISIONAL_MOVEMENTS_FIELDS_INVALID")
                source_key = self._digest("source-ref-v1", value["source_reference"])
                event = ProvisionalTimelineEvent(
                    event_key=self._digest("owner-event-v1", scope_digest, reference),
                    source_key=source_key,
                    scope_fingerprint=scope_digest,
                    event_kind=kind,
                    finance_sku=sku,
                    quantity=quantity,
                    local_date=moment.local_date,
                    effective_at_utc=moment.utc_timestamp,
                    time_precision=moment.precision,
                    source=ProvisionalEventSource.OWNER_MOVEMENTS_CSV,
                    posting_key=posting_key,
                    stock_zone=stock_zone,
                    resellable=resellable,
                )
                event_by_reference[reference_key] = event
                events.append(event)
                event_counts[kind.value] = event_counts.get(kind.value, 0) + 1
        except (csv.Error, UnicodeError):
            return self._error("FIFO_PROVISIONAL_MOVEMENTS_CSV_INVALID")
        except (TypeError, ValueError) as error:
            code = str(error)
            if not code.startswith(("FIFO_PROVISIONAL_MOVEMENTS_", "FIFO_PROVISIONAL_FBO_TIME_")):
                code = "FIFO_PROVISIONAL_MOVEMENTS_ROW_INVALID"
            return self._error(code)
        if not events:
            return self._error("FIFO_PROVISIONAL_MOVEMENTS_EMPTY")
        safe_rows = [event.safe_payload() for event in events]
        normalized_bytes = json.dumps(
            safe_rows, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        ).encode("ascii")
        raw_digest = sha256(raw).hexdigest()
        normalized_digest = sha256(normalized_bytes).hexdigest()
        document_digest = self._digest(
            "provisional-owner-movements-v1", raw_digest, scope_digest, timezone_name,
        )
        document = ProvisionalMovementsDocument(
            file_sha256=raw_digest,
            document_fingerprint=document_digest,
            normalized_fingerprint=normalized_digest,
            scope_fingerprint=scope_digest,
            timezone_name=timezone_name,
            row_count=len(events),
            total_units=total_units,
            event_counts=MappingProxyType(dict(sorted(event_counts.items()))),
            events=tuple(sorted(events, key=lambda item: (
                item.effective_at_utc, item.event_key,
            ))),
        )
        return ProvisionalMovementsParseResult("COMPLETE", document, ())

    @staticmethod
    def _header_name(value):
        return " ".join(str(value or "").replace("\ufeff", "").strip().casefold().split())

    @staticmethod
    def _digest(*parts):
        return sha256("\0".join(parts).encode("utf-8")).hexdigest()

    @staticmethod
    def _valid_fields(kind, posting_key, stock_zone, resellable):
        if kind is ProvisionalTimelineEventKind.SUPPLY_RECEIVED:
            return posting_key is None and stock_zone is not None and resellable is None
        if kind is ProvisionalTimelineEventKind.OPENING_TRANSIT_LINK:
            return posting_key is not None and stock_zone is None and resellable is None
        if kind in {ProvisionalTimelineEventKind.NON_BUYOUT_RESTOCK,
                    ProvisionalTimelineEventKind.SALE_RETURN_RESTOCK}:
            return posting_key is not None and stock_zone is None and type(resellable) is bool
        if kind in {ProvisionalTimelineEventKind.RELEASE_HOLD,
                    ProvisionalTimelineEventKind.NON_SALE_REMOVE}:
            return posting_key is None and stock_zone is not None and resellable is None
        return False

    @staticmethod
    def _error(code):
        return ProvisionalMovementsParseResult("ERROR", None, (code,))
