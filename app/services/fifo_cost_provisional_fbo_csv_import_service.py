"""Bounded, owner-scoped parser for provisional Ozon FBO shipment CSVs.

Raw posting numbers and unrelated columns are used only transiently. The public
document contains an opaque per-posting digest and aggregate metadata.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import date, datetime, time, timezone
from hashlib import sha256
from io import StringIO
import json
import re
from types import MappingProxyType
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from services.fifo_cost_transition_contracts import ScopeIdentity


@dataclass(frozen=True, slots=True)
class ProvisionalFboMoment:
    """A calendar-day observation or a timestamp normalized to UTC."""

    local_date: date
    utc_timestamp: datetime | None
    precision: str


@dataclass(frozen=True, slots=True)
class ProvisionalFboRow:
    """Selected-SKU row with no raw posting reference or additional CSV cells."""

    posting_key: str
    finance_sku: str
    quantity: int
    status_kind: str
    dispatch: ProvisionalFboMoment | None
    delivered: ProvisionalFboMoment | None

    def safe_fingerprint_payload(self):
        return {
            "posting_key": self.posting_key,
            "sku": self.finance_sku,
            "quantity": self.quantity,
            "status": self.status_kind,
            "dispatch": _moment_payload(self.dispatch),
            "delivered": _moment_payload(self.delivered),
        }


@dataclass(frozen=True, slots=True)
class ProvisionalFboDocument:
    file_sha256: str
    normalized_fingerprint: str
    document_fingerprint: str
    row_count: int
    selected_units: int
    excluded_other_sku_rows: int
    duplicate_rows: int
    unknown_status_rows: int
    period_from: str
    period_to: str
    timezone_name: str
    status_counts: object
    rows: tuple[ProvisionalFboRow, ...] = field(repr=False)

    def to_worker_summary_payload(self):
        return {
            "file_sha256": self.file_sha256,
            "normalized_fingerprint": self.normalized_fingerprint,
            "document_fingerprint": self.document_fingerprint,
            "row_count": self.row_count,
            "selected_units": self.selected_units,
            "excluded_other_sku_rows": self.excluded_other_sku_rows,
            "duplicate_rows": self.duplicate_rows,
            "unknown_status_rows": self.unknown_status_rows,
            "period_from": self.period_from,
            "period_to": self.period_to,
            "timezone_name": self.timezone_name,
            "status_counts": dict(self.status_counts),
            "rows": [
                {
                    **row.safe_fingerprint_payload(),
                    "dispatch": _moment_payload(row.dispatch, include_utc=True),
                    "delivered": _moment_payload(row.delivered, include_utc=True),
                }
                for row in self.rows
            ],
        }


@dataclass(frozen=True, slots=True)
class ProvisionalFboParseResult:
    status: str
    document: ProvisionalFboDocument | None
    issue_codes: tuple[str, ...]


class FifoCostProvisionalFboCsvImportService:
    MAX_FILE_BYTES = 10 * 1024 * 1024
    MAX_ROWS = 50_000
    MAX_TOTAL_UNITS = 1_000_000
    MAX_FILENAME_CHARS = 255
    MAX_POSTING_CHARS = 128
    _POSTING_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,127}$")
    _SKU_RE = re.compile(r"^[0-9]{1,40}$")
    _QUANTITY_RE = re.compile(r"^[0-9]{1,7}$")
    _HEADER_ALIASES = {
        "posting_number": {"posting_number", "номер отправления"},
        "finance_sku": {"finance_sku", "sku"},
        "quantity": {"quantity", "количество"},
        "status": {"status", "статус"},
        "dispatch_at": {
            "dispatch_at", "дата передачи в доставку",
            "фактическая дата передачи в доставку",
        },
        "delivered_at": {
            "delivered_at", "delivery_date", "дата доставки",
            "фактическая дата доставки",
        },
    }
    _REQUIRED = (
        "posting_number", "finance_sku", "quantity", "status",
        "dispatch_at", "delivered_at",
    )
    _DELIVERED = frozenset({
        "доставлен", "доставлена", "доставлено", "выдан покупателю",
        "delivered", "delivered_to_customer",
    })
    _CANCELLED = frozenset({
        "отменен", "отменена", "отменено", "отменен продавцом",
        "cancelled", "canceled",
    })
    _IN_TRANSIT = frozenset({
        "передан в доставку", "доставляется", "в пути", "ожидает покупателя",
        "awaiting_deliver", "delivering", "in_transit",
    })

    def parse_csv(self, *, payload, filename, scope, timezone_name):
        if not isinstance(scope, ScopeIdentity):
            return self._error("FIFO_PROVISIONAL_SCOPE_INVALID")
        if (
            not isinstance(filename, str) or not filename.strip()
            or len(filename) > self.MAX_FILENAME_CHARS
            or not filename.lower().endswith(".csv")
        ):
            return self._error("FIFO_PROVISIONAL_FBO_FILENAME_INVALID")
        if isinstance(payload, memoryview):
            if payload.nbytes > self.MAX_FILE_BYTES:
                return self._error("FIFO_PROVISIONAL_FBO_FILE_SIZE_INVALID")
            payload = payload.tobytes()
        if not isinstance(payload, (bytes, bytearray)):
            return self._error("FIFO_PROVISIONAL_FBO_PAYLOAD_INVALID")
        raw = bytes(payload)
        if not raw or len(raw) > self.MAX_FILE_BYTES or b"\x00" in raw:
            return self._error("FIFO_PROVISIONAL_FBO_FILE_SIZE_INVALID")
        try:
            zone = ZoneInfo(timezone_name)
        except (TypeError, ZoneInfoNotFoundError):
            return self._error("FIFO_PROVISIONAL_FBO_TIMEZONE_INVALID")
        try:
            text = raw.decode("utf-8-sig", errors="strict")
        except UnicodeDecodeError:
            return self._error("FIFO_PROVISIONAL_FBO_ENCODING_INVALID")

        try:
            reader = csv.reader(StringIO(text, newline=""), delimiter=";", strict=True)
            header = next(reader, None)
            indexes = self._header_indexes(header)
            rows: dict[str, ProvisionalFboRow] = {}
            raw_identities: dict[str, tuple[object, ...]] = {}
            excluded = duplicates = unknown = selected_units = 0
            counts: dict[str, int] = {}
            input_rows = 0
            dates: list[date] = []
            for cells in reader:
                if not cells or all(not str(cell).strip() for cell in cells):
                    continue
                input_rows += 1
                if input_rows > self.MAX_ROWS:
                    return self._error("FIFO_PROVISIONAL_FBO_ROW_LIMIT_EXCEEDED")
                if len(cells) != len(header):
                    return self._error("FIFO_PROVISIONAL_FBO_ROW_INVALID")
                sku = self._cell(cells, indexes["finance_sku"])
                if not self._SKU_RE.fullmatch(sku):
                    return self._error("FIFO_PROVISIONAL_FBO_SKU_INVALID")
                if sku != scope.sku:
                    excluded += 1
                    continue
                posting_number = self._cell(cells, indexes["posting_number"])
                if (
                    len(posting_number) > self.MAX_POSTING_CHARS
                    or not self._POSTING_RE.fullmatch(posting_number)
                ):
                    return self._error("FIFO_PROVISIONAL_FBO_POSTING_INVALID")
                quantity_text = self._cell(cells, indexes["quantity"])
                if not self._QUANTITY_RE.fullmatch(quantity_text):
                    return self._error("FIFO_PROVISIONAL_FBO_QUANTITY_INVALID")
                quantity = int(quantity_text)
                if quantity <= 0:
                    return self._error("FIFO_PROVISIONAL_FBO_QUANTITY_INVALID")
                status_kind = self._status_kind(self._cell(cells, indexes["status"]))
                dispatch = self._parse_moment(
                    self._cell(cells, indexes["dispatch_at"]), zone,
                )
                delivered = self._parse_moment(
                    self._cell(cells, indexes["delivered_at"]), zone,
                )
                if dispatch and delivered:
                    if dispatch.local_date > delivered.local_date:
                        return self._error("FIFO_PROVISIONAL_FBO_DATE_ORDER_INVALID")
                    if (
                        dispatch.utc_timestamp is not None
                        and delivered.utc_timestamp is not None
                        and delivered.utc_timestamp < dispatch.utc_timestamp
                    ):
                        return self._error("FIFO_PROVISIONAL_FBO_DATE_ORDER_INVALID")
                key = sha256(posting_number.encode("utf-8")).hexdigest()
                row = ProvisionalFboRow(
                    posting_key=key, finance_sku=sku, quantity=quantity,
                    status_kind=status_kind, dispatch=dispatch, delivered=delivered,
                )
                identity = (
                    sku, quantity, status_kind,
                    _moment_payload(dispatch, include_utc=True),
                    _moment_payload(delivered, include_utc=True),
                )
                if key in raw_identities:
                    if raw_identities[key] != identity:
                        return self._error("FIFO_PROVISIONAL_FBO_DUPLICATE_CONFLICT")
                    duplicates += 1
                    continue
                raw_identities[key] = identity
                rows[key] = row
                selected_units += quantity
                if selected_units > self.MAX_TOTAL_UNITS:
                    return self._error("FIFO_PROVISIONAL_FBO_UNIT_LIMIT_EXCEEDED")
                counts[status_kind] = counts.get(status_kind, 0) + 1
                unknown += status_kind == "UNKNOWN"
                if dispatch:
                    dates.append(dispatch.local_date)
                if delivered:
                    dates.append(delivered.local_date)
        except (csv.Error, UnicodeError):
            return self._error("FIFO_PROVISIONAL_FBO_CSV_INVALID")
        except ValueError as error:
            code = str(error)
            if not code.startswith("FIFO_"):
                code = "FIFO_PROVISIONAL_FBO_ROW_INVALID"
            return self._error(code)

        if not rows:
            return self._error("FIFO_PROVISIONAL_FBO_TARGET_SKU_EMPTY")
        normalized = [rows[key].safe_fingerprint_payload() for key in sorted(rows)]
        normalized_bytes = json.dumps(
            normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        ).encode("ascii")
        normalized_fingerprint = sha256(normalized_bytes).hexdigest()
        raw_sha = sha256(raw).hexdigest()
        document_fingerprint = sha256(
            f"provisional-fbo-csv-v1:{raw_sha}:{scope.sku}:{timezone_name}".encode(),
        ).hexdigest()
        document = ProvisionalFboDocument(
            file_sha256=raw_sha,
            normalized_fingerprint=normalized_fingerprint,
            document_fingerprint=document_fingerprint,
            row_count=len(rows),
            selected_units=selected_units,
            excluded_other_sku_rows=excluded,
            duplicate_rows=duplicates,
            unknown_status_rows=unknown,
            period_from=min(dates).isoformat() if dates else "",
            period_to=max(dates).isoformat() if dates else "",
            timezone_name=str(timezone_name),
            status_counts=MappingProxyType(dict(sorted(counts.items()))),
            rows=tuple(rows[key] for key in sorted(rows)),
        )
        return ProvisionalFboParseResult("COMPLETE", document, ())

    @classmethod
    def _header_indexes(cls, header):
        if not isinstance(header, list) or not header:
            raise ValueError("FIFO_PROVISIONAL_FBO_HEADER_INVALID")
        aliases = {}
        for field_name, names in cls._HEADER_ALIASES.items():
            for name in names:
                aliases[cls._normalize_header(name)] = field_name
        indexes = {}
        for index, raw_name in enumerate(header):
            name = cls._normalize_header(raw_name)
            mapped = aliases.get(name)
            if mapped is None:
                continue
            if mapped in indexes:
                raise ValueError("FIFO_PROVISIONAL_FBO_HEADER_AMBIGUOUS")
            indexes[mapped] = index
        if any(name not in indexes for name in cls._REQUIRED):
            raise ValueError("FIFO_PROVISIONAL_FBO_HEADER_INVALID")
        return indexes

    @staticmethod
    def _normalize_header(value):
        return " ".join(str(value or "").replace("\ufeff", "").strip().casefold().replace("ё", "е").split())

    @staticmethod
    def _cell(cells, index):
        return str(cells[index] if index < len(cells) else "").strip()

    @classmethod
    def _status_kind(cls, value):
        normalized = " ".join(str(value or "").strip().casefold().replace("ё", "е").split())
        if normalized in cls._DELIVERED:
            return "DELIVERED"
        if normalized in cls._CANCELLED:
            return "CANCELLED"
        if normalized in cls._IN_TRANSIT:
            return "IN_TRANSIT"
        return "UNKNOWN"

    @classmethod
    def _parse_moment(cls, value, zone):
        value = str(value or "").strip()
        if not value:
            return None
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            try:
                parsed_date = date.fromisoformat(value)
            except ValueError as error:
                raise ValueError("FIFO_PROVISIONAL_FBO_TIME_INVALID") from error
            return ProvisionalFboMoment(parsed_date, None, "DAY")
        normalized = value[:-1] + "+00:00" if value.endswith(("Z", "z")) else value
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError as error:
            raise ValueError("FIFO_PROVISIONAL_FBO_TIME_INVALID") from error
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            aware0 = parsed.replace(tzinfo=zone, fold=0)
            aware1 = parsed.replace(tzinfo=zone, fold=1)
            roundtrip0 = aware0.astimezone(timezone.utc).astimezone(zone).replace(tzinfo=None)
            roundtrip1 = aware1.astimezone(timezone.utc).astimezone(zone).replace(tzinfo=None)
            if roundtrip0 != parsed and roundtrip1 != parsed:
                raise ValueError("FIFO_PROVISIONAL_FBO_TIME_NONEXISTENT")
            if aware0.utcoffset() != aware1.utcoffset():
                raise ValueError("FIFO_PROVISIONAL_FBO_TIME_AMBIGUOUS")
            parsed = aware0
        local = parsed.astimezone(zone)
        return ProvisionalFboMoment(
            local.date(), parsed.astimezone(timezone.utc), "INSTANT",
        )

    @staticmethod
    def _error(code):
        return ProvisionalFboParseResult("ERROR", None, (code,))


def _moment_payload(moment, *, include_utc=False):
    if moment is None:
        return None
    payload = {"local_date": moment.local_date.isoformat(), "precision": moment.precision}
    if include_utc:
        payload["utc_timestamp"] = (
            moment.utc_timestamp.isoformat() if moment.utc_timestamp else None
        )
    return payload
