"""Managed subprocess boundary for allowlisted FIFO report/document parsers."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
import json
import sys
from collections.abc import Mapping

from services.fifo_cost_report_import_service import FifoCostReportImportService
from services.fifo_cost_stock_management_import_service import (
    FifoCostStockManagementImportService,
)
from services.fifo_cost_physical_sales_import_service import (
    FifoCostPhysicalSalesImportService,
)
from services.fifo_cost_transition_contracts import ScopeIdentity


MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_HEADER_BYTES = 4096
MAX_OUTPUT_BYTES = 384 * 1024
MAX_PHYSICAL_OUTPUT_BYTES = 64 * 1024
_ALLOWED_REPORTS = {
    "TURNOVER": "parse_turnover_workbook",
    "STOCK_MANAGEMENT": "parse_stock_management_workbook",
}


def _json_value(value):
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key.value if isinstance(key, Enum) else key): _json_value(item)
                for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_value(item) for item in value]
    if value is None or type(value) in (str, int, float, bool):
        return value
    raise TypeError("unsupported worker result value")


def _read_request(stream):
    header_bytes = stream.readline(MAX_HEADER_BYTES + 1)
    if not header_bytes or len(header_bytes) > MAX_HEADER_BYTES or not header_bytes.endswith(b"\n"):
        raise ValueError("FIFO_REPORT_WORKER_HEADER_INVALID")
    header = json.loads(header_bytes.decode("utf-8"))
    if not isinstance(header, dict):
        raise ValueError("FIFO_REPORT_WORKER_HEADER_INVALID")
    expected = header.get("payload_bytes")
    if type(expected) is not int or not 1 <= expected <= MAX_FILE_BYTES:
        raise ValueError("FIFO_REPORT_FILE_SIZE_INVALID")
    payload = stream.read(expected + 1)
    if len(payload) != expected:
        raise ValueError("FIFO_REPORT_WORKER_PAYLOAD_INVALID")
    scope_value = header.get("scope")
    if not isinstance(scope_value, dict):
        raise ValueError("FIFO_REPORT_SCOPE_INVALID")
    scope = ScopeIdentity(**scope_value)
    filename = header.get("filename")
    if not isinstance(filename, str) or len(filename) > 255:
        raise ValueError("FIFO_REPORT_FILENAME_INVALID")
    document_kind = header.get("document_kind")
    if document_kind is not None:
        if document_kind != "PHYSICAL_SALES_CSV":
            raise ValueError("FIFO_REPORT_FORMAT_UNSUPPORTED")
        return document_kind, None, filename, payload, scope
    report_type = header.get("report_type")
    method_name = _ALLOWED_REPORTS.get(report_type)
    if method_name is None:
        raise ValueError("FIFO_REPORT_FORMAT_UNSUPPORTED")
    return report_type, method_name, filename, payload, scope


def _run():
    try:
        parser_kind, method_name, filename, payload, scope = _read_request(sys.stdin.buffer)
        if parser_kind == "PHYSICAL_SALES_CSV":
            parsed = FifoCostPhysicalSalesImportService().parse_csv(
                payload=payload, filename=filename, scope=scope,
            )
            if parsed.document is None:
                code = parsed.issue_codes[0] if parsed.issue_codes else "FIFO_PHYSICAL_SALES_PARSE_FAILED"
                encoded = json.dumps(
                    {"error": True, "code": code}, separators=(",", ":"),
                ).encode("utf-8")
                sys.stdout.buffer.write(encoded)
                sys.stdout.buffer.flush()
                return 0
            response = {
                "error": False,
                "document_kind": parser_kind,
                "document": parsed.document.to_worker_summary_payload(),
            }
            encoded = json.dumps(
                response, ensure_ascii=False, separators=(",", ":"),
            ).encode("utf-8")
            if len(encoded) > MAX_PHYSICAL_OUTPUT_BYTES:
                raise ValueError("FIFO_PHYSICAL_SALES_WORKER_RESULT_TOO_LARGE")
            sys.stdout.buffer.write(encoded)
            sys.stdout.buffer.flush()
            return 0
        parser = (
            FifoCostReportImportService()
            if parser_kind == "TURNOVER"
            else FifoCostStockManagementImportService()
        )
        result = getattr(parser, method_name)(
            payload=payload, filename=filename, scope=scope,
        )
        report = result.report_evidence
        if report is None:
            code = result.issue_codes[0] if result.issue_codes else "FIFO_REPORT_PARSE_FAILED"
            encoded = json.dumps(
                {"error": True, "code": code}, separators=(",", ":"),
            ).encode("utf-8")
            sys.stdout.buffer.write(encoded)
            sys.stdout.buffer.flush()
            return 0
        response = {
            "error": False,
            "status": result.status,
            "issue_codes": list(result.issue_codes),
            "report": None,
        }
        if report is not None:
            response["report"] = {
                "report_type": report.report_type.value,
                "period_from": report.period_from,
                "period_to": report.period_to,
                "period_provenance": report.period_provenance.value,
                "captured_at": report.captured_at,
                "file_sha256": report.file_sha256,
                "parser_version": report.parser_version,
                "cell_references": list(report.cell_references),
                "normalized_fields": _json_value(report.normalized_fields),
                "completeness": report.metadata.completeness.value,
                "source_fingerprint": report.metadata.source_fingerprint,
            }
        encoded = json.dumps(
            response, ensure_ascii=False, separators=(",", ":"),
        ).encode("utf-8")
        if len(encoded) > MAX_OUTPUT_BYTES:
            raise ValueError("FIFO_TRANSITION_PAYLOAD_TOO_LARGE")
        sys.stdout.buffer.write(encoded)
        sys.stdout.buffer.flush()
        return 0
    except Exception as error:
        code = str(error) if str(error).startswith("FIFO_") else "FIFO_REPORT_WORKER_FAILED"
        encoded = json.dumps({"error": True, "code": code}, separators=(",", ":")).encode()
        sys.stdout.buffer.write(encoded[:MAX_OUTPUT_BYTES])
        sys.stdout.buffer.flush()
        return 0


if __name__ == "__main__":
    raise SystemExit(_run())
