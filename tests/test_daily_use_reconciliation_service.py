from datetime import date

from services.daily_use_reconciliation_service import DailyUseReconciliationService


HEADERS = ["ID начисления", "Дата начисления", "Тип начисления", "SKU", "Сумма итого, руб."]
PERIOD = {"from": "2026-08-01", "to": "2026-08-31"}


def _reference(rows, **kwargs):
    options = {
        "sheet_name": "Начисления",
        "header_row": 2,
        "headers": HEADERS,
        "rows": rows,
        "period_from": "2026-08-01",
        "period_to": "2026-08-31",
        "source_period_from": "2026-08-01",
        "source_period_to": "2026-08-31",
        "scope_alias": "shop-a",
        "coverage_assertion": "USER_CONFIRMED_FULL_PERIOD",
    }
    options.update(kwargs)
    result = DailyUseReconciliationService().normalize_accrual_table(**options)
    assert result["error"] is False
    return result["reference"]


def _snapshot(value="12.30", *, period=None, scope_alias="shop-a", coverage="COMPLETE", status="CONFIRMED", dimension=None):
    return {
        "schema": "daily_use_canonical_snapshot",
        "schema_version": 1,
        "scope_alias": scope_alias,
        "dimension": dimension or {"kind": "store", "alias": scope_alias},
        "application_revision": "synthetic-test",
        "period": period or PERIOD,
        "date_basis": "accrual_date",
        "coverage": {"status": coverage},
        "metrics": {
            "net_accrual": {
                "value": value,
                "status": status,
                "unit": "RUB",
                "semantic": "signed_leaf_accrual_amount_sum",
                "date_basis": "accrual_date",
            }
        },
    }


def test_signed_rows_and_correction_are_summed_as_decimal_and_exposed_without_ids():
    reference = _reference([
        ["synthetic-id-1", date(2026, 8, 3), "sale", "synthetic-sku-a", 20.10],
        ["synthetic-id-2", date(2026, 8, 3), "adjustment", "synthetic-sku-a", -7.80],
        ["synthetic-id-2", date(2026, 8, 3), "another-line", "synthetic-sku-a", 0.00],
    ])

    assert reference["metrics"]["net_accrual"]["value"] == "12.30"
    assert reference["coverage"]["rows_in_period"] == 3
    assert "synthetic-id-1" not in str(reference)
    assert "synthetic-sku-a" not in str(reference)


def test_matching_canonical_snapshot_returns_safe_comparison_row():
    reference = _reference([["id", date(2026, 8, 1), "sale", "sku", 12.30]])

    result = DailyUseReconciliationService().compare(reference, _snapshot())

    assert result["error"] is False
    assert result["rows"] == [{
        "metric": "net_accrual",
        "expected": "12.30",
        "actual": "12.30",
        "difference": "0.00",
        "source_basis": "ozon_accruals_xlsx_v1/accrual_date vs period_profit/net_accrual",
        "coverage": "COMPLETE/COMPLETE",
        "status": "MATCH",
        "reason": None,
    }]


def test_unknown_column_and_duplicate_header_fail_with_explainable_profile_errors():
    service = DailyUseReconciliationService()
    base = {
        "sheet_name": "Начисления",
        "header_row": 2,
        "headers": HEADERS,
        "rows": [],
        "period_from": "2026-08-01",
        "period_to": "2026-08-31",
        "source_period_from": "2026-08-01",
        "source_period_to": "2026-08-31",
        "scope_alias": "shop-a",
    }
    unknown = service.normalize_accrual_table(**{**base, "headers": ["Дата", "Сумма"]})
    duplicate = service.normalize_accrual_table(**{**base, "headers": HEADERS + ["SKU"]})

    assert unknown["code"] == "DAILY_USE_REPORT_PROFILE_COLUMNS_UNSUPPORTED"
    assert duplicate["code"] == "DAILY_USE_REPORT_PROFILE_DUPLICATE_COLUMN"


def test_wrong_sheet_and_header_row_are_not_guessed():
    service = DailyUseReconciliationService()
    options = {
        "sheet_name": "Other",
        "header_row": 3,
        "headers": HEADERS,
        "rows": [],
        "period_from": "2026-08-01",
        "period_to": "2026-08-31",
        "source_period_from": "2026-08-01",
        "source_period_to": "2026-08-31",
        "scope_alias": "shop-a",
    }

    assert service.normalize_accrual_table(**options)["code"] == "DAILY_USE_REPORT_PROFILE_SHEET_MISMATCH"
    assert service.normalize_accrual_table(**{**options, "sheet_name": "Начисления"})["code"] == "DAILY_USE_REPORT_PROFILE_HEADER_ROW_MISMATCH"


def test_empty_period_is_unavailable_not_zero_and_invalid_amount_is_not_silenced():
    empty = _reference([], coverage_assertion="USER_CONFIRMED_FULL_PERIOD")
    corrupted = DailyUseReconciliationService().normalize_accrual_table(
        sheet_name="Начисления", header_row=2, headers=HEADERS,
        rows=[["synthetic", date(2026, 8, 2), "sale", "sku", "not-money"]],
        period_from="2026-08-01", period_to="2026-08-31",
        source_period_from="2026-08-01", source_period_to="2026-08-31",
        scope_alias="shop-a", coverage_assertion="USER_CONFIRMED_FULL_PERIOD",
    )

    assert empty["coverage"]["status"] == "UNAVAILABLE"
    assert empty["metrics"]["net_accrual"]["value"] is None
    assert corrupted["code"] == "DAILY_USE_RECONCILIATION_AMOUNT_INVALID"
    assert corrupted["row_number"] == 3
    assert "not-money" not in str(corrupted)


def test_wrong_period_store_or_sku_is_not_reported_as_match():
    service = DailyUseReconciliationService()
    reference = _reference([["id", date(2026, 8, 1), "sale", "sku", 12.30]])
    wrong_store = service.compare(reference, _snapshot(scope_alias="shop-b"))
    wrong_period = service.compare(reference, _snapshot(period={"from": "2026-08-02", "to": "2026-08-31"}))
    sku_reference_result = service.normalize_accrual_table(
        sheet_name="Начисления", header_row=2, headers=HEADERS,
        rows=[["id", date(2026, 8, 1), "sale", "synthetic-sku-a", 12.30]],
        period_from="2026-08-01", period_to="2026-08-31",
        source_period_from="2026-08-01", source_period_to="2026-08-31",
        scope_alias="shop-a", coverage_assertion="USER_CONFIRMED_FULL_PERIOD",
        sku_filter_value="synthetic-sku-a", sku_dimension_alias="sku-a",
    )
    wrong_sku = service.compare(
        sku_reference_result["reference"],
        _snapshot(dimension={"kind": "sku", "alias": "sku-b"}),
    )

    assert wrong_store["rows"][0]["status"] == "NOT_COMPARABLE"
    assert wrong_store["rows"][0]["reason"] == "STORE_SCOPE_ALIAS_MISMATCH"
    assert wrong_period["rows"][0]["status"] == "NOT_COMPARABLE"
    assert wrong_period["rows"][0]["reason"] == "PERIOD_MISMATCH"
    assert wrong_sku["rows"][0]["status"] == "NOT_COMPARABLE"
    assert wrong_sku["rows"][0]["reason"] == "SKU_DIMENSION_MISMATCH"


def test_partial_or_unknown_coverage_never_becomes_zero_match():
    reference = _reference([["id", date(2026, 8, 1), "sale", "sku", 0]])
    reference["coverage"]["status"] = "UNVERIFIED"
    result = DailyUseReconciliationService().compare(reference, _snapshot(value="0"))

    assert result["rows"][0]["status"] == "EVIDENCE_REQUIRED"
    assert result["rows"][0]["expected"] is None
    assert result["rows"][0]["actual"] is None


def test_owner_export_is_projected_without_scope_or_sku_identifiers():
    document = {
        "document_kind": "owner_analytics_export",
        "export_kind": "period_profit",
        "schema_version": 1,
        "metadata": {
            "periods": {"current": {"from": "2026-08-01", "to": "2026-08-31"}},
            "coverage_status": "COMPLETE",
            "snapshot_generated_at": "2026-10-25T10:00:00Z",
            "scope": "private-scope-must-not-be-copied",
        },
        "rows": [{
            "section": "comparison_metric", "name": "net_accrual",
            "current_value": "12.30", "current_status": "CONFIRMED", "unit": "RUB",
        }],
    }

    result = DailyUseReconciliationService().canonical_from_period_profit_export(
        document, scope_alias="shop-a", revision="abcdef1"
    )

    assert result["error"] is False
    assert result["snapshot"]["metrics"]["net_accrual"]["value"] == "12.30"
    assert "private-scope-must-not-be-copied" not in str(result)
