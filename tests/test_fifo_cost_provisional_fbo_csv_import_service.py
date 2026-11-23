from __future__ import annotations

import reprlib

from services.fifo_cost_provisional_fbo_csv_import_service import (
    FifoCostProvisionalFboCsvImportService,
)
from services.fifo_cost_transition_contracts import ScopeIdentity


SCOPE = ScopeIdentity(
    owner_id="owner-test", store_id="store-test", product_id="product-test",
    offer_id="hook-2", sku="3921245627",
)
SERVICE = FifoCostProvisionalFboCsvImportService()
HEADER = (
    "Номер отправления;SKU;Количество;Статус;"
    "Дата передачи в доставку;Дата доставки;Адрес покупателя"
)


def _csv(*rows, bom=False, header=HEADER):
    payload = (header + "\r\n" + "".join(
        ";".join(row) + "\r\n" for row in rows
    )).encode("utf-8")
    return b"\xef\xbb\xbf" + payload if bom else payload


def _row(
    posting="posting-1", sku="3921245627", quantity="2",
    status="Доставлен", dispatch="2026-11-06 10:00:00",
    delivered="2026-11-07 12:00:00", address="private-address",
):
    return posting, sku, quantity, status, dispatch, delivered, address


def _parse(payload, *, timezone_name="Europe/Moscow"):
    return SERVICE.parse_csv(
        filename="orders.csv", payload=payload, scope=SCOPE,
        timezone_name=timezone_name,
    )


def test_utf8_bom_exact_sku_and_extra_columns_are_safe_and_scoped():
    result = _parse(_csv(
        _row(),
        _row(posting="other-sku", sku="999999", address="secret-address"),
        bom=True,
    ))
    assert result.status == "COMPLETE", result.issue_codes
    document = result.document
    assert document.row_count == 1
    assert document.selected_units == 2
    assert document.excluded_other_sku_rows == 1
    assert document.status_counts == {"DELIVERED": 1}
    assert document.period_from == "2026-11-06"
    assert document.period_to == "2026-11-07"
    rendered = reprlib.repr(document)
    assert "posting-1" not in rendered
    assert "private-address" not in rendered
    assert "secret-address" not in rendered
    worker_payload = document.to_worker_summary_payload()
    assert len(worker_payload["rows"]) == 1
    assert "posting-1" not in repr(worker_payload)
    assert "private-address" not in repr(worker_payload)
    assert worker_payload["rows"][0]["dispatch"]["utc_timestamp"].endswith("+00:00")


def test_identical_duplicate_is_idempotent_and_conflicting_same_identity_blocks():
    duplicate = _parse(_csv(_row(), _row()))
    assert duplicate.status == "COMPLETE", duplicate.issue_codes
    assert duplicate.document.row_count == 1
    assert duplicate.document.duplicate_rows == 1
    conflict = _parse(_csv(_row(), _row(quantity="3")))
    assert conflict.issue_codes == ("FIFO_PROVISIONAL_FBO_DUPLICATE_CONFLICT",)
    assert conflict.document is None


def test_missing_identity_malformed_quantity_date_and_empty_scope_fail_closed():
    cases = (
        (_csv(_row(posting="")), "FIFO_PROVISIONAL_FBO_POSTING_INVALID"),
        (_csv(_row(quantity="1.5")), "FIFO_PROVISIONAL_FBO_QUANTITY_INVALID"),
        (_csv(_row(quantity="0")), "FIFO_PROVISIONAL_FBO_QUANTITY_INVALID"),
        (_csv(_row(dispatch="2026-02-30")), "FIFO_PROVISIONAL_FBO_TIME_INVALID"),
        (_csv(_row(
            dispatch="2026-11-06T12:00:00+00:00",
            delivered="2026-11-06T11:00:00+00:00",
        )), "FIFO_PROVISIONAL_FBO_DATE_ORDER_INVALID"),
        (_csv(_row(sku="not-a-sku")), "FIFO_PROVISIONAL_FBO_SKU_INVALID"),
        (_csv(_row(sku="999999")), "FIFO_PROVISIONAL_FBO_TARGET_SKU_EMPTY"),
    )
    for payload, code in cases:
        assert _parse(payload).issue_codes == (code,)


def test_status_is_reduced_to_allowlisted_category_without_echoing_source_value():
    result = _parse(_csv(_row(status="Неизвестный статус покупателя")))
    assert result.status == "COMPLETE"
    assert result.document.unknown_status_rows == 1
    assert result.document.status_counts == {"UNKNOWN": 1}
    assert "Неизвестный статус" not in repr(result.document)


def test_timezone_conversion_and_dst_ambiguity_are_explicit():
    offset = _parse(_csv(_row(
        dispatch="2026-11-06T07:00:00+00:00",
        delivered="2026-11-07",
    )))
    assert offset.status == "COMPLETE"
    row = offset.document.rows[0]
    assert row.dispatch.local_date.isoformat() == "2026-11-06"
    assert row.dispatch.utc_timestamp.isoformat() == "2026-11-06T07:00:00+00:00"
    assert row.delivered.precision == "DAY"
    assert row.delivered.utc_timestamp is None

    ambiguous = _parse(_csv(_row(
        dispatch="2026-11-01 01:30:00",
        delivered="2026-11-02",
    )), timezone_name="America/New_York")
    assert ambiguous.issue_codes == ("FIFO_PROVISIONAL_FBO_TIME_AMBIGUOUS",)

    nonexistent = _parse(_csv(_row(
        dispatch="2026-03-08 02:30:00",
        delivered="2026-03-09",
    )), timezone_name="America/New_York")
    assert nonexistent.issue_codes == ("FIFO_PROVISIONAL_FBO_TIME_NONEXISTENT",)


def test_header_format_file_and_unit_limits_are_enforced():
    assert _parse(b"\xff").issue_codes == ("FIFO_PROVISIONAL_FBO_ENCODING_INVALID",)
    assert _parse(_csv(_row()) + b"\x00").issue_codes == (
        "FIFO_PROVISIONAL_FBO_FILE_SIZE_INVALID",
    )
    assert _parse(_csv(_row()), timezone_name="Invalid/Zone").issue_codes == (
        "FIFO_PROVISIONAL_FBO_TIMEZONE_INVALID",
    )
    assert _parse(_csv(_row()),).status == "COMPLETE"

    duplicate_header = HEADER + ";finance_sku"
    assert _parse(
        _csv(_row(), header=duplicate_header),
    ).issue_codes == ("FIFO_PROVISIONAL_FBO_HEADER_AMBIGUOUS",)
    assert _parse(
        _csv(_row(), header="posting_number;sku;quantity;status"),
    ).issue_codes == ("FIFO_PROVISIONAL_FBO_HEADER_INVALID",)
    assert _parse(_csv(_row()),).status == "COMPLETE"
    oversized = SERVICE.parse_csv(
        filename="orders.csv", payload=b"x" * (SERVICE.MAX_FILE_BYTES + 1),
        scope=SCOPE, timezone_name="Europe/Moscow",
    )
    assert oversized.issue_codes == ("FIFO_PROVISIONAL_FBO_FILE_SIZE_INVALID",)

    too_many = HEADER + "\n" + (
        "posting-1;3921245627;1;В пути;2026-11-06;;addr\n"
        * (SERVICE.MAX_ROWS + 1)
    )
    assert _parse(too_many.encode("utf-8")).issue_codes == (
        "FIFO_PROVISIONAL_FBO_ROW_LIMIT_EXCEEDED",
    )
    too_many_units = _parse(_csv(_row(quantity="1000001")))
    assert too_many_units.issue_codes == ("FIFO_PROVISIONAL_FBO_UNIT_LIMIT_EXCEEDED",)
