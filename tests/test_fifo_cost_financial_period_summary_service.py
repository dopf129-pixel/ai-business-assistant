from services.fifo_cost_financial_period_summary_service import (
    FifoCostFinancialPeriodSummaryService,
)


def _reconstruction(*, before_complete=True):
    return {
        "error": False,
        "code": "FIFO_LATE_ENTRY_RECONSTRUCTION_READY",
        "before_complete": before_complete,
        "preview_fingerprint": "a" * 64,
        "sale_identity_digests_by_event": {
            "event-1": "b" * 64,
            "event-2": "c" * 64,
        },
        "before_allocations": [
            {"event_id": "event-1", "total_cost_rub": "42.00"},
            {"event_id": "event-2", "total_cost_rub": "10.00"},
        ],
    }


def _period_profit_summary():
    return {
        "error": False,
        "date_from": "2026-11-01",
        "date_to": "2026-11-30",
        "period": "2026-11",
        "revenue": 1000.00,
        "discount_points": 25.00,
        "net_accrual": 750.00,
        "product_cost": 100.00,
        "current_sku_product_cost": 42.00,
        "profit_scope": "OZON_ACCOUNT_ACCRUALS_COST_AND_CONFIGURED_TAX_V3",
        "account_level_ozon_accruals_included": True,
        "product_revenue_reconciled": True,
        "sale_quantity_reconciled": True,
        "effective_cost_reconciled": True,
        "fifo_cogs_reconciliation_required": False,
    }


def test_snapshot_uses_exact_reconstruction_cogs_and_preserves_other_product_costs():
    result = FifoCostFinancialPeriodSummaryService().build_snapshot(
        period_profit_summary=_period_profit_summary(),
        reconstruction=_reconstruction(),
        sale_identity_digests=["b" * 64],
        daily_source_fingerprint="d" * 64,
        tax_policy_fingerprint="e" * 64,
    )

    assert result["error"] is False, result
    summary = result["summary"].as_impact_summary()
    assert summary["period"] == "2026-11"
    assert summary["current_sku_product_cost"] == "42.00"
    assert summary["current_total_product_cost"] == "100.00"
    assert summary["sale_identity_digests"] == ["b" * 64]
    assert summary["net_accrual"] == "750.00"
    assert summary["source_fingerprint"] != "d" * 64


def test_snapshot_stays_unavailable_when_historical_before_cost_is_not_proven():
    result = FifoCostFinancialPeriodSummaryService().build_snapshot(
        period_profit_summary=_period_profit_summary(),
        reconstruction=_reconstruction(before_complete=False),
        sale_identity_digests=["b" * 64],
        daily_source_fingerprint="d" * 64,
        tax_policy_fingerprint="e" * 64,
    )

    assert result["error"] is True
    assert result["code"] == "FIFO_BASELINE_UNAVAILABLE"
    assert "summary" not in result


def test_snapshot_rejects_sale_identity_outside_reconstruction():
    result = FifoCostFinancialPeriodSummaryService().build_snapshot(
        period_profit_summary=_period_profit_summary(),
        reconstruction=_reconstruction(),
        sale_identity_digests=["f" * 64],
        daily_source_fingerprint="d" * 64,
        tax_policy_fingerprint="e" * 64,
    )

    assert result["error"] is True
    assert result["code"] == "FIFO_BASELINE_UNAVAILABLE"


def test_snapshot_requires_whole_store_period_profit_controls():
    summary = _period_profit_summary()
    summary["account_level_ozon_accruals_included"] = False
    result = FifoCostFinancialPeriodSummaryService().build_snapshot(
        period_profit_summary=summary,
        reconstruction=_reconstruction(),
        sale_identity_digests=["b" * 64],
        daily_source_fingerprint="d" * 64,
        tax_policy_fingerprint="e" * 64,
    )

    assert result["error"] is True
    assert result["code"] == "FIFO_PERIOD_SUMMARY_SOURCE_INCOMPLETE"


def test_snapshot_rejects_period_profit_sku_cost_that_disagrees_with_fifo_before():
    summary = _period_profit_summary()
    summary["current_sku_product_cost"] = 41.99
    result = FifoCostFinancialPeriodSummaryService().build_snapshot(
        period_profit_summary=summary,
        reconstruction=_reconstruction(),
        sale_identity_digests=["b" * 64],
        daily_source_fingerprint="d" * 64,
        tax_policy_fingerprint="e" * 64,
    )

    assert result["error"] is True
    assert result["code"] == "FIFO_PERIOD_COGS_BASELINE_MISMATCH"


def test_snapshot_keeps_full_month_sku_cost_when_reconstruction_covers_only_sales_subset():
    summary = _period_profit_summary()
    summary["current_sku_product_cost"] = 52.00
    summary["product_cost"] = 110.00
    result = FifoCostFinancialPeriodSummaryService().build_snapshot(
        period_profit_summary=summary,
        reconstruction=_reconstruction(),
        sale_identity_digests=["b" * 64],
        daily_source_fingerprint="d" * 64,
        tax_policy_fingerprint="e" * 64,
    )

    assert result["error"] is False, result
    snapshot = result["summary"].as_impact_summary()
    assert snapshot["current_sku_product_cost"] == "52.00"
    assert snapshot["current_total_product_cost"] == "110.00"


def test_snapshot_rejects_full_month_sku_cost_below_reconstructed_subset():
    summary = _period_profit_summary()
    summary["current_sku_product_cost"] = 41.99
    result = FifoCostFinancialPeriodSummaryService().build_snapshot(
        period_profit_summary=summary,
        reconstruction=_reconstruction(),
        sale_identity_digests=["b" * 64],
        daily_source_fingerprint="d" * 64,
        tax_policy_fingerprint="e" * 64,
    )

    assert result["error"] is True
    assert result["code"] == "FIFO_PERIOD_COGS_BASELINE_MISMATCH"
