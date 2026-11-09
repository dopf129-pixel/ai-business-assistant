from __future__ import annotations

import reprlib
from pathlib import Path

from services.fifo_cost_physical_sales_import_service import (
    FifoCostPhysicalSalesImportService,
)
from services.fifo_cost_transition_contracts import ScopeIdentity


SCOPE = ScopeIdentity(
    owner_id="owner-1", store_id="store-1", product_id="product-1",
    offer_id="hook-2", sku="3921245627",
)
HEADER = FifoCostPhysicalSalesImportService.TEMPLATE_HEADER


def _csv(*rows, bom=False):
    text = HEADER + "\r\n" + "".join(";".join(row) + "\r\n" for row in rows)
    raw = text.encode("utf-8")
    return (b"\xef\xbb\xbf" + raw) if bom else raw


def _row(posting="posting-1", sku="3921245627", quantity="2", day="2026-11-05", ref="row-1"):
    return posting, sku, quantity, day, ref


def test_exact_template_and_utf8_bom_quoted_csv_are_accepted():
    service = FifoCostPhysicalSalesImportService()
    assert service.template_bytes() == (HEADER + "\r\n").encode("utf-8")
    template = Path("docs/templates/fifo_physical_sales_template.csv").read_bytes()
    template = template.replace(b"\r\n", b"\n")
    assert template == (HEADER + "\n").encode("utf-8")
    result = service.parse_csv(
        filename="physical-sales.csv",
        payload=_csv(('"posting-1"', '"3921245627"', '"2"', '"2026-11-05"', '"row-1"'), bom=True),
        scope=SCOPE,
    )
    assert result.status == "COMPLETE", result.issue_codes
    assert result.document.row_count == 1
    assert result.document.unit_count == 2
    assert (result.document.period_from, result.document.period_to) == (
        "2026-11-05", "2026-11-05",
    )
    assert len(result.document.file_sha256) == 64
    worker_summary = result.document.to_worker_summary_payload()
    assert "rows" not in worker_summary
    assert "posting-1" not in repr(worker_summary)
    assert "row-1" not in repr(worker_summary)


def test_wrong_header_missing_extra_fields_and_malformed_quotes_are_rejected():
    service = FifoCostPhysicalSalesImportService()
    cases = (
        ("wrong.csv", (HEADER.replace("quantity", "units") + "\n" + ";".join(_row())).encode()),
        ("missing.csv", _csv(("posting-1", "3921245627", "2", "2026-11-05"))),
        ("extra.csv", (HEADER + "\n" + ";".join((*_row(), "extra"))).encode()),
        ("quote.csv", (HEADER + '\n"posting-1;3921245627;2;2026-11-05;row-1').encode()),
    )
    for filename, payload in cases:
        result = service.parse_csv(filename=filename, payload=payload, scope=SCOPE)
        assert result.status == "ERROR", filename
        assert result.document is None
        assert result.issue_codes
    assert service.parse_csv(
        filename="physical.xlsx", payload=_csv(_row()), scope=SCOPE,
    ).status == "ERROR"


def test_invalid_encoding_nul_empty_and_oversize_are_rejected():
    service = FifoCostPhysicalSalesImportService()
    assert service.parse_csv(
        filename="x.csv", payload=b"\xff", scope=SCOPE,
    ).issue_codes == ("FIFO_PHYSICAL_SALES_ENCODING_INVALID",)
    assert service.parse_csv(
        filename="x.csv", payload=_csv(_row()) + b"\x00", scope=SCOPE,
    ).issue_codes == ("FIFO_PHYSICAL_SALES_DOCUMENT_INVALID",)
    assert service.parse_csv(
        filename="x.csv", payload=(HEADER + "\n").encode(), scope=SCOPE,
    ).issue_codes == ("FIFO_PHYSICAL_SALES_EMPTY",)
    assert service.parse_csv(
        filename="x.csv", payload=b"x" * (service.MAX_FILE_BYTES + 1), scope=SCOPE,
    ).issue_codes == ("FIFO_REPORT_FILE_SIZE_INVALID",)


def test_identity_reference_date_and_quantity_conflicts_fail_closed():
    service = FifoCostPhysicalSalesImportService()
    cases = (
        (_row(sku="999"), "FIFO_PHYSICAL_SALES_IDENTITY_MISMATCH"),
        (_row(quantity="0"), "FIFO_PHYSICAL_SALES_QUANTITY_INVALID"),
        (_row(quantity="1.5"), "FIFO_PHYSICAL_SALES_QUANTITY_INVALID"),
        (_row(day="2026-02-30"), "FIFO_PHYSICAL_SALES_DATE_INVALID"),
        (_row(day="05.11.2026"), "FIFO_PHYSICAL_SALES_DATE_INVALID"),
        (_row(ref="=SUM(A1:A2)"), "FIFO_PHYSICAL_SALES_ROW_REFERENCE_INVALID"),
    )
    for row, code in cases:
        result = service.parse_csv(filename="x.csv", payload=_csv(row), scope=SCOPE)
        assert result.issue_codes == (code,)
    duplicate_reference = service.parse_csv(
        filename="x.csv", payload=_csv(_row(), _row(posting="posting-2")), scope=SCOPE,
    )
    assert duplicate_reference.issue_codes == ("FIFO_PHYSICAL_SALES_ROW_REFERENCE_CONFLICT",)
    exact_duplicate_reference = service.parse_csv(
        filename="x.csv", payload=_csv(_row(), _row()), scope=SCOPE,
    )
    assert exact_duplicate_reference.issue_codes == ("FIFO_PHYSICAL_SALES_DUPLICATE_ROW_REFERENCE",)
    duplicate_identity = service.parse_csv(
        filename="x.csv", payload=_csv(_row(), _row(ref="row-2")), scope=SCOPE,
    )
    assert duplicate_identity.issue_codes == ("FIFO_PHYSICAL_SALES_IDENTITY_CONFLICT",)
    conflicting_identity = service.parse_csv(
        filename="x.csv", payload=_csv(_row(), _row(quantity="3", ref="row-2")), scope=SCOPE,
    )
    assert conflicting_identity.issue_codes == ("FIFO_PHYSICAL_SALES_IDENTITY_CONFLICT",)


def test_document_manifest_rejects_worker_tampering_duplicate_rows_and_unit_overflow():
    service = FifoCostPhysicalSalesImportService()
    payload = _csv(_row())
    parsed = service.parse_csv(filename="x.csv", payload=payload, scope=SCOPE)
    document = parsed.document
    assert document is not None
    worker_payload = document.to_worker_summary_payload()
    worker_payload["unit_count"] = 99
    recomputed = service.build_document(
        payload=payload, scope=SCOPE, rows=document.rows,
    )
    assert worker_payload["unit_count"] != recomputed.unit_count == 2
    duplicate = [document.rows[0], document.rows[0]]
    try:
        service.build_document(payload=payload, scope=SCOPE, rows=duplicate)
    except ValueError as error:
        assert str(error) == "FIFO_PHYSICAL_SALES_DUPLICATE_ROW_REFERENCE"
    else:
        raise AssertionError("duplicate worker row was accepted")
    try:
        service.build_document(
            payload=payload, scope=SCOPE,
            rows=[
                {"posting_number": "posting-1", "finance_sku": SCOPE.sku,
                 "quantity": 600000, "physical_effective_date": "2026-11-05",
                 "row_reference": "one"},
                {"posting_number": "posting-2", "finance_sku": SCOPE.sku,
                 "quantity": 600000, "physical_effective_date": "2026-11-05",
                 "row_reference": "two"},
            ],
        )
    except ValueError as error:
        assert str(error) == "FIFO_PHYSICAL_SALES_UNIT_LIMIT_EXCEEDED"
    else:
        raise AssertionError("unit limit was not enforced")
    try:
        service.build_document(payload=b"a\x00b", scope=SCOPE, rows=[document.rows[0]])
    except ValueError as error:
        assert str(error) == "FIFO_PHYSICAL_SALES_DOCUMENT_INVALID"
    else:
        raise AssertionError("NUL-containing worker input was accepted")


def test_row_cap_and_sensitive_identifiers_are_not_rendered():
    service = FifoCostPhysicalSalesImportService()
    many = (HEADER + "\n" + "posting-1;3921245627;1;2026-11-05;row-1\n" * (service.MAX_ROWS + 1)).encode()
    assert service.parse_csv(filename="x.csv", payload=many, scope=SCOPE).issue_codes == (
        "FIFO_PHYSICAL_SALES_ROW_LIMIT_EXCEEDED",
    )
    result = service.parse_csv(filename="x.csv", payload=_csv(_row()), scope=SCOPE)
    rendered = reprlib.repr(result.document)
    assert "posting-1" not in rendered
    assert "row-1" not in rendered
