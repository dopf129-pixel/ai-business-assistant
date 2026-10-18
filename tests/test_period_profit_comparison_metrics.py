from datetime import datetime, timezone

from period_profit_comparison_contract import (
    build_period_profit_comparison_contract,
)
from period_profit_comparison_metrics import (
    build_period_profit_comparison_metrics,
)


def _period(date_from, date_to, **overrides):
    summary = {
        "error": False,
        "status": "PERIOD_PROFIT_SUMMARY_READY",
        "date_from": date_from,
        "date_to": date_to,
        "profit_scope": "OZON_ACCOUNT_ACCRUALS_COST_AND_CONFIGURED_TAX_V3",
        "returns_included": False,
        "advertising_included": False,
        "storage_included": False,
        "revenue": 100000.0,
        "discount_points": 20000.0,
        "revenue_tax_base": 80000.0,
        "net_accrual": 40000.0,
        "product_cost": 20000.0,
        "tax": 4800.0,
        "profit": 15200.0,
        "margin_percent": 15.2,
        "units_sold": 100,
        "tax_mode": "USN_INCOME",
        "tax_rate_percent": 6.0,
        "minimum_tax_rate_percent": None,
        "return_cogs_profit_applied": False,
        "return_cogs_profit_tax_recomputed": False,
        "return_cogs_profit_application_amount": None,
    }
    summary.update(overrides)
    return {
        "error": False,
        "status": "PERIOD_PROFIT_QUERY_READY",
        "request": {
            "status": "PERIOD_PROFIT_REQUEST_READY",
            "date_from": date_from,
            "date_to": date_to,
        },
        "summary": summary,
        "coverage": {
            "coverage_status": "COMPLETE",
            "included_components": [],
            "missing_components": [],
        },
    }


def _contract(current, previous):
    return build_period_profit_comparison_contract(
        current,
        previous,
        tenant_scope="owner-1::store-1",
        generated_at=datetime(2026, 10, 15, 12, tzinfo=timezone.utc),
    )


def _metrics(current, previous):
    return build_period_profit_comparison_metrics(
        _contract(current, previous)
    )


def test_reference_period_example_returns_signed_deltas_and_revenue_shares():
    previous = _period(
        "2026-08-25",
        "2026-08-31",
        revenue=100000.0,
        discount_points=20000.0,
        revenue_tax_base=80000.0,
        net_accrual=40000.0,
        product_cost=20000.0,
        tax=4800.0,
        profit=15200.0,
        margin_percent=15.2,
        units_sold=100,
    )
    current = _period(
        "2026-09-01",
        "2026-09-07",
        revenue=120000.0,
        discount_points=25000.0,
        revenue_tax_base=95000.0,
        net_accrual=51000.0,
        product_cost=26000.0,
        tax=5700.0,
        profit=19300.0,
        margin_percent=16.08,
        units_sold=120,
    )

    result = _metrics(current, previous)

    assert result["error"] is False
    assert result["metrics"]["revenue"]["delta"] == 20000
    assert result["metrics"]["revenue"]["relative_change_percent"] == 20
    assert result["metrics"]["discount_points"]["delta"] == 5000
    assert result["metrics"]["revenue_tax_base"]["delta"] == 15000
    assert result["metrics"]["net_accrual"]["delta"] == 11000
    assert result["metrics"]["product_cost"]["delta"] == 6000
    assert result["metrics"]["tax"]["delta"] == 900
    assert result["metrics"]["profit"]["delta"] == 4100
    assert result["metrics"]["margin_percent"]["delta"] == 0.88
    assert result["metrics"]["margin_percent"]["delta_unit"] == "PERCENTAGE_POINT"
    assert result["metrics"]["margin_percent"]["relative_change_status"] == "NOT_APPLICABLE"
    assert result["metrics"]["revenue"]["current_share_of_revenue_percent"] == 100
    assert result["metrics"]["units_sold"]["current_share_of_revenue_percent"] is None
    assert current["summary"]["profit"] == 19300.0


def test_zero_and_negative_previous_values_have_explicit_relative_semantics():
    zero_previous = _period("2026-08-25", "2026-08-31", profit=0.0)
    positive_current = _period("2026-09-01", "2026-09-07", profit=50.0)
    zero_result = _metrics(positive_current, zero_previous)["metrics"]["profit"]
    assert zero_result["delta"] == 50
    assert zero_result["relative_change_percent"] is None
    assert zero_result["relative_change_status"] == "UNDEFINED_PREVIOUS_ZERO"

    negative_previous = _period("2026-08-25", "2026-08-31", profit=-100.0)
    negative_current = _period("2026-09-01", "2026-09-07", profit=-50.0)
    negative_result = _metrics(negative_current, negative_previous)["metrics"]["profit"]
    assert negative_result["delta"] == 50
    assert negative_result["relative_change_percent"] == 50
    assert negative_result["relative_change_basis"] == "ABSOLUTE_PREVIOUS_VALUE"


def test_tax_policy_mismatch_preserves_independent_deltas_and_hides_profit_delta():
    current = _period("2026-09-01", "2026-09-07", tax_rate_percent=5.0)
    previous = _period("2026-08-25", "2026-08-31", tax_rate_percent=6.0)

    metrics = _metrics(current, previous)["metrics"]

    assert metrics["revenue"]["delta"] == 0
    assert metrics["net_accrual"]["delta"] == 0
    assert metrics["tax"]["delta"] is None
    assert metrics["tax"]["comparison_status"] == "UNAVAILABLE"
    assert metrics["profit"]["delta"] is None


def test_incompatible_period_keeps_values_but_suppresses_all_deltas():
    current = _period("2026-09-01", "2026-09-07")
    previous = _period("2026-08-25", "2026-08-30")

    row = _metrics(current, previous)["metrics"]["revenue"]

    assert row["current_value"] == 100000
    assert row["previous_value"] == 100000
    assert row["delta"] is None
    assert row["comparison_status"] == "UNAVAILABLE"


def test_partial_external_amount_is_visible_as_estimate_but_has_no_delta():
    current = _period("2026-09-01", "2026-09-07")
    current["external_expense_evidence"] = {
        "error": False,
        "status": "PERIOD_PROFIT_EXTERNAL_EXPENSE_EVIDENCE_PARTIAL",
        "coverage_complete": False,
        "observed_expense_total": 75.0,
        "complete_expense_total": None,
    }
    current["external_expense_adjustment"] = {
        "error": False,
        "profit_adjustment_complete": False,
        "observed_profit_after_external_expenses": 15125.0,
        "observed_margin_percent": 15.13,
    }
    previous = _period("2026-08-25", "2026-08-31")

    rows = _metrics(current, previous)["metrics"]

    assert rows["external_expenses"]["current_value"] == 75
    assert rows["external_expenses"]["current_status"] == "PARTIAL"
    assert rows["external_expenses"]["delta"] is None
    assert rows["profit"]["comparison_status"] == "COMPARABLE"
    assert rows["profit_after_external_expenses"]["delta"] is None


def test_large_integer_unit_delta_is_exact():
    previous = _period(
        "2026-08-25",
        "2026-08-31",
        units_sold=9007199254740991,
    )
    current = _period(
        "2026-09-01",
        "2026-09-07",
        units_sold=9007199254740993,
    )

    row = _metrics(current, previous)["metrics"]["units_sold"]

    assert row["current_value"] == 9007199254740993
    assert row["delta"] == 2


def test_overflow_never_emits_a_non_finite_delta():
    previous = _period("2026-08-25", "2026-08-31", revenue=-1.7e308)
    current = _period("2026-09-01", "2026-09-07", revenue=1.7e308)

    row = _metrics(current, previous)["metrics"]["revenue"]

    assert row["comparison_status"] == "UNAVAILABLE"
    assert row["delta"] is None
    assert "PERIOD_PROFIT_COMPARISON_ARITHMETIC_LIMIT" in row["reason_codes"]


def test_invalid_input_contract_returns_controlled_error():
    result = build_period_profit_comparison_metrics({"error": True})

    assert result["error"] is True
    assert result["code"] == "PERIOD_PROFIT_COMPARISON_METRICS_CONTRACT_INVALID"


def test_malformed_ready_shaped_contract_returns_controlled_error():
    contract = _contract(
        _period("2026-09-01", "2026-09-07"),
        _period("2026-08-25", "2026-08-31"),
    )
    contract["profit_bases"].pop("B")

    result = build_period_profit_comparison_metrics(contract)

    assert result["error"] is True
    assert result["code"] == "PERIOD_PROFIT_COMPARISON_METRICS_CONTRACT_INVALID"
