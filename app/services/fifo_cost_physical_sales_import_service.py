"""Strict parser for the bot-owned physical-sales CSV evidence format."""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from hashlib import sha256
from io import StringIO
import json
import re

from services.fifo_cost_transition_contracts import (
    ScopeIdentity,
    normalize_date_only,
)


@dataclass(frozen=True, slots=True)
class FifoPhysicalSalesRow:
    """Validated source row. Exact posting and row references are sensitive."""

    posting_number: str = field(repr=False)
    finance_sku: str
    quantity: int
    physical_effective_date: str
    row_reference: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class FifoPhysicalSalesDocument:
    """Verified full document; raw row identifiers are excluded from repr."""

    file_sha256: str
    document_fingerprint: str
    normalized_fingerprint: str
    row_references_fingerprint: str
    identity_fingerprint: str
    row_count: int
    unit_count: int
    period_from: str
    period_to: str
    rows: tuple[FifoPhysicalSalesRow, ...] = field(repr=False)

    def to_worker_summary_payload(self) -> dict[str, object]:
        """Return only bounded, non-row identifiers for the worker response."""
        return {
            "file_sha256": self.file_sha256,
            "document_fingerprint": self.document_fingerprint,
            "normalized_fingerprint": self.normalized_fingerprint,
            "row_references_fingerprint": self.row_references_fingerprint,
            "identity_fingerprint": self.identity_fingerprint,
            "row_count": self.row_count,
            "unit_count": self.unit_count,
            "period_from": self.period_from,
            "period_to": self.period_to,
        }


@dataclass(frozen=True, slots=True)
class FifoPhysicalSalesParseResult:
    status: str
    document: FifoPhysicalSalesDocument | None
    issue_codes: tuple[str, ...]


class FifoCostPhysicalSalesImportService:
    """Parse the exact UTF-8 semicolon CSV; do not guess Ozon XLSX formats."""

    MAX_FILE_BYTES = 10 * 1024 * 1024
    MAX_FILENAME_CHARS = 255
    MAX_ROWS = 50_000
    MAX_TOTAL_UNITS = 1_000_000
    MAX_POSTING_NUMBER_CHARS = 128
    MAX_ROW_REFERENCE_CHARS = 128
    TEMPLATE_HEADER = (
        "posting_number;finance_sku;quantity;physical_effective_date;row_reference"
    )
    _POSTING_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,127}$")
    _SKU_RE = re.compile(r"^[0-9]{1,40}$")
    _QUANTITY_RE = re.compile(r"^[0-9]{1,7}$")
    _ROW_REFERENCE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")

    @classmethod
    def template_bytes(cls) -> bytes:
        """Return a header-only safe template, without formulas or sample data."""
        return (cls.TEMPLATE_HEADER + "\r\n").encode("utf-8")

    def parse_csv(self, *, payload, filename, scope) -> FifoPhysicalSalesParseResult:
        if not isinstance(scope, ScopeIdentity):
            return self._error("FIFO_REPORT_SCOPE_INVALID")
        if (
            not isinstance(filename, str) or not filename.strip()
            or len(filename) > self.MAX_FILENAME_CHARS
            or not filename.lower().endswith(".csv")
        ):
            return self._error("FIFO_PHYSICAL_SALES_DOCUMENT_INVALID")
        if isinstance(payload, memoryview):
            if payload.nbytes > self.MAX_FILE_BYTES:
                return self._error("FIFO_REPORT_FILE_SIZE_INVALID")
            payload = payload.tobytes()
        if not isinstance(payload, (bytes, bytearray)):
            return self._error("FIFO_REPORT_PAYLOAD_INVALID")
        raw = bytes(payload)
        if not raw or len(raw) > self.MAX_FILE_BYTES:
            return self._error("FIFO_REPORT_FILE_SIZE_INVALID")
        if b"\x00" in raw:
            return self._error("FIFO_PHYSICAL_SALES_DOCUMENT_INVALID")
        try:
            text = raw.decode("utf-8-sig", errors="strict")
        except UnicodeDecodeError:
            return self._error("FIFO_PHYSICAL_SALES_ENCODING_INVALID")
        try:
            reader = csv.reader(StringIO(text, newline=""), delimiter=";", strict=True)
            header = next(reader, None)
            if header != self.TEMPLATE_HEADER.split(";"):
                return self._error("FIFO_PHYSICAL_SALES_HEADER_INVALID")
            rows: list[FifoPhysicalSalesRow] = []
            for raw_row in reader:
                if len(rows) >= self.MAX_ROWS:
                    return self._error("FIFO_PHYSICAL_SALES_ROW_LIMIT_EXCEEDED")
                if len(raw_row) != 5:
                    return self._error("FIFO_PHYSICAL_SALES_ROW_INVALID")
                row = self._normalize_row(raw_row, expected_sku=scope.sku)
                rows.append(row)
        except csv.Error:
            return self._error("FIFO_PHYSICAL_SALES_CSV_INVALID")
        except ValueError as error:
            code = str(error)
            if not code.startswith("FIFO_"):
                code = "FIFO_PHYSICAL_SALES_ROW_INVALID"
            return self._error(code)
        except UnicodeError:
            return self._error("FIFO_PHYSICAL_SALES_ENCODING_INVALID")
        if not rows:
            return self._error("FIFO_PHYSICAL_SALES_EMPTY")
        try:
            document = self.build_document(payload=raw, scope=scope, rows=rows)
        except ValueError as error:
            code = str(error)
            if not code.startswith("FIFO_"):
                code = "FIFO_PHYSICAL_SALES_DOCUMENT_INVALID"
            return self._error(code)
        return FifoPhysicalSalesParseResult("COMPLETE", document, ())

    @classmethod
    def build_document(cls, *, payload, scope, rows) -> FifoPhysicalSalesDocument:
        """Revalidate worker output in the parent and recompute all manifests."""
        if not isinstance(scope, ScopeIdentity):
            raise ValueError("FIFO_REPORT_SCOPE_INVALID")
        if isinstance(payload, memoryview):
            payload = payload.tobytes()
        if not isinstance(payload, (bytes, bytearray)):
            raise ValueError("FIFO_REPORT_PAYLOAD_INVALID")
        raw = bytes(payload)
        if not raw or len(raw) > cls.MAX_FILE_BYTES:
            raise ValueError("FIFO_REPORT_FILE_SIZE_INVALID")
        if b"\x00" in raw:
            raise ValueError("FIFO_PHYSICAL_SALES_DOCUMENT_INVALID")
        if not isinstance(rows, (tuple, list)) or not 1 <= len(rows) <= cls.MAX_ROWS:
            raise ValueError("FIFO_PHYSICAL_SALES_ROW_LIMIT_EXCEEDED")
        normalized_rows = []
        seen_references: dict[str, FifoPhysicalSalesRow] = {}
        seen_identities: dict[tuple[str, str], FifoPhysicalSalesRow] = {}
        total_units = 0
        for value in rows:
            if isinstance(value, FifoPhysicalSalesRow):
                if type(value.quantity) is not int:
                    raise ValueError("FIFO_PHYSICAL_SALES_QUANTITY_INVALID")
                row = cls._normalize_row(
                    [value.posting_number, value.finance_sku, str(value.quantity),
                     value.physical_effective_date, value.row_reference],
                    expected_sku=scope.sku,
                )
            elif isinstance(value, dict) and set(value) == {
                "posting_number", "finance_sku", "quantity",
                "physical_effective_date", "row_reference",
            }:
                if type(value["quantity"]) is not int:
                    raise ValueError("FIFO_PHYSICAL_SALES_QUANTITY_INVALID")
                row = cls._normalize_row(
                    [
                        value["posting_number"], value["finance_sku"],
                        str(value["quantity"]), value["physical_effective_date"],
                        value["row_reference"],
                    ],
                    expected_sku=scope.sku,
                )
            else:
                raise ValueError("FIFO_REPORT_WORKER_RESULT_INVALID")
            if row.finance_sku != scope.sku:
                raise ValueError("FIFO_PHYSICAL_SALES_IDENTITY_MISMATCH")
            previous = seen_references.get(row.row_reference)
            if previous is not None:
                code = (
                    "FIFO_PHYSICAL_SALES_DUPLICATE_ROW_REFERENCE"
                    if previous == row
                    else "FIFO_PHYSICAL_SALES_ROW_REFERENCE_CONFLICT"
                )
                raise ValueError(code)
            seen_references[row.row_reference] = row
            identity = (row.posting_number, row.finance_sku)
            previous_identity = seen_identities.get(identity)
            if previous_identity is not None:
                code = (
                    "FIFO_PHYSICAL_SALES_DUPLICATE_IDENTITY"
                    if previous_identity == row
                    else "FIFO_PHYSICAL_SALES_IDENTITY_CONFLICT"
                )
                raise ValueError(code)
            seen_identities[identity] = row
            total_units += row.quantity
            if total_units > cls.MAX_TOTAL_UNITS:
                raise ValueError("FIFO_PHYSICAL_SALES_UNIT_LIMIT_EXCEEDED")
            normalized_rows.append(row)
        canonical_rows = [
            {
                "posting_number": row.posting_number,
                "finance_sku": row.finance_sku,
                "quantity": row.quantity,
                "physical_effective_date": row.physical_effective_date,
                "row_reference": row.row_reference,
            }
            for row in sorted(normalized_rows, key=lambda item: item.row_reference)
        ]
        canonical = json.dumps(
            canonical_rows, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")
        raw_sha = sha256(raw).hexdigest()
        rowrefs_json = json.dumps(
            sorted(row.row_reference for row in normalized_rows),
            ensure_ascii=True, separators=(",", ":"),
        ).encode("ascii")
        scope_json = json.dumps(
            {
                "owner_id": scope.owner_id,
                "store_id": scope.store_id,
                "product_id": scope.product_id,
                "offer_id": scope.offer_id,
                "sku": scope.sku,
            },
            ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")
        dates = [row.physical_effective_date for row in normalized_rows]
        return FifoPhysicalSalesDocument(
            file_sha256=raw_sha,
            document_fingerprint=raw_sha,
            normalized_fingerprint=sha256(canonical).hexdigest(),
            row_references_fingerprint=sha256(rowrefs_json).hexdigest(),
            identity_fingerprint=sha256(scope_json).hexdigest(),
            row_count=len(normalized_rows),
            unit_count=total_units,
            period_from=min(dates),
            period_to=max(dates),
            rows=tuple(normalized_rows),
        )

    @classmethod
    def _normalize_row(cls, raw_row, *, expected_sku):
        posting, finance_sku, quantity_text, date_text, row_reference = raw_row
        values = [item.strip() if isinstance(item, str) else item for item in raw_row]
        if any(not isinstance(item, str) for item in values):
            raise ValueError("FIFO_PHYSICAL_SALES_ROW_INVALID")
        posting, finance_sku, quantity_text, date_text, row_reference = values
        if (
            len(posting) > cls.MAX_POSTING_NUMBER_CHARS
            or cls._POSTING_RE.fullmatch(posting) is None
        ):
            raise ValueError("FIFO_PHYSICAL_SALES_POSTING_NUMBER_INVALID")
        if cls._SKU_RE.fullmatch(finance_sku) is None or int(finance_sku) <= 0:
            raise ValueError("FIFO_PHYSICAL_SALES_FINANCE_SKU_INVALID")
        if finance_sku != expected_sku:
            raise ValueError("FIFO_PHYSICAL_SALES_IDENTITY_MISMATCH")
        if cls._QUANTITY_RE.fullmatch(quantity_text) is None:
            raise ValueError("FIFO_PHYSICAL_SALES_QUANTITY_INVALID")
        quantity = int(quantity_text)
        if not 1 <= quantity <= 1_000_000:
            raise ValueError("FIFO_PHYSICAL_SALES_QUANTITY_INVALID")
        try:
            effective_date = normalize_date_only(date_text)
        except ValueError as error:
            raise ValueError("FIFO_PHYSICAL_SALES_DATE_INVALID") from error
        if (
            len(row_reference) > cls.MAX_ROW_REFERENCE_CHARS
            or cls._ROW_REFERENCE_RE.fullmatch(row_reference) is None
        ):
            raise ValueError("FIFO_PHYSICAL_SALES_ROW_REFERENCE_INVALID")
        return FifoPhysicalSalesRow(
            posting_number=posting,
            finance_sku=finance_sku,
            quantity=quantity,
            physical_effective_date=effective_date,
            row_reference=row_reference,
        )

    @staticmethod
    def _error(code):
        return FifoPhysicalSalesParseResult("ERROR", None, (code,))
