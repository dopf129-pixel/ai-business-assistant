from datetime import datetime, timezone

from period_profit_comparison_bridge import (
    build_period_profit_comparison_bridge,
)
from period_profit_comparison_contract import (
    build_period_profit_comparison_contract,
)


def _result(date_from, date_to, **overrides):
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


def _external(result, expense_total, profit_after):
    result["external_expense_evidence"] = {
        "error": False,
        "status": "PERIOD_PROFIT_EXTERNAL_EXPENSE_EVIDENCE_READY",
        "coverage_complete": True,
        "observed_expense_total": expense_total,
        "complete_expense_total": expense_total,
    }
    result["external_expense_adjustment"] = {
        "error": False,
        "profit_adjustment_complete": True,
        "complete_profit_after_external_expenses": profit_after,
        "complete_margin_percent": profit_after / 1000,
    }
    return result


def _bridge(current, previous):
    contract = build_period_profit_comparison_contract(
        current,
        previous,
        tenant_scope="owner-1::store-1",
        generated_at=datetime(2026, 10, 15, tzinfo=timezone.utc),
    )
    assert contract["error"] is False
    return build_period_profit_comparison_bridge(contract)


def test_reference_b_bridge_reconciles_profit_and_nests_revenue_detail():
    previous = _result("2026-08-25", "2026-08-31")
    current = _result(
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
    )

    bridge = _bridge(current, previous)

    assert bridge["B"]["status"] == "CONFIRMED"
    assert bridge["B"]["authoritative_delta"] == 4100
    assert bridge["B"]["contributions"] == {
        "net_accrual_change": 11000,
        "product_cost_contribution": -6000,
        "return_cogs_contribution": 0,
        "tax_contribution": -900,
        "rounding_adjustment": 0,
    }
    assert bridge["B"]["net_accrual_detail"] == {
        "status": "CONFIRMED",
        "meaning": "NET_ACCRUAL_SPLIT_ONLY_NOT_ADDITIONAL_EXPENSE",
        "revenue_change": 20000,
        "other_net_accrual_change": -9000,
        "net_accrual_change": 11000,
        "reconciled": True,
    }
    assert bridge["B"]["reconciled"] is True


def test_e_bridge_subtracts_complete_external_expense_delta_once():
    previous = _external(
        _result("2026-08-25", "2026-08-31"),
        expense_total=1000.0,
        profit_after=14200.0,
    )
    current = _external(
        _result(
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
        ),
        expense_total=2000.0,
        profit_after=17300.0,
    )

    bridge = _bridge(current, previous)

    assert bridge["B"]["authoritative_delta"] == 4100
    assert bridge["E"]["status"] == "CONFIRMED"
    assert bridge["E"]["authoritative_delta"] == 3100
    assert bridge["E"]["contributions"] == {
        "profit_before_external_expenses_delta": 4100,
        "external_expenses_contribution": -1000,
        "rounding_adjustment": 0,
    }


def test_one_cent_authoritative_rounding_is_explicit_and_reconciles():
    previous = _result("2026-08-25", "2026-08-31")
    current = _result(
        "2026-09-01",
        "2026-09-07",
        revenue=120000.0,
        discount_points=25000.0,
        revenue_tax_base=95000.0,
        net_accrual=51000.0,
        product_cost=26000.0,
        tax=5700.0,
        profit=19300.01,
        margin_percent=16.08,
    )

    bridge = _bridge(current, previous)

    assert bridge["B"]["status"] == "CONFIRMED"
    assert bridge["B"]["authoritative_delta"] == 4100.01
    assert bridge["B"]["contributions"]["rounding_adjustment"] == 0.01
    assert bridge["B"]["reconciled"] is True


def test_difference_over_one_cent_is_not_hidden_as_rounding():
    previous = _result("2026-08-25", "2026-08-31")
    current = _result(
        "2026-09-01",
        "2026-09-07",
        revenue=120000.0,
        discount_points=25000.0,
        revenue_tax_base=95000.0,
        net_accrual=51000.0,
        product_cost=26000.0,
        tax=5700.0,
        profit=19300.02,
        margin_percent=16.08,
    )

    bridge = _bridge(current, previous)

    assert bridge["B"]["status"] == "UNAVAILABLE"
    assert bridge["code"] == "PERIOD_PROFIT_COMPARISON_BRIDGE_RECONCILIATION_FAILED"
    assert bridge["B"]["unreconciled_difference"] == 0.02


def test_each_period_must_match_authoritative_formula_not_only_the_delta():
    previous = _result(
        "2026-08-25",
        "2026-08-31",
        profit=15200.02,
    )
    current = _result(
        "2026-09-01",
        "2026-09-07",
        profit=15200.02,
    )

    bridge = _bridge(current, previous)

    assert bridge["B"]["status"] == "UNAVAILABLE"
    assert bridge["B"]["authoritative_delta"] == 0
    assert bridge["B"]["current_period_difference"] == 0.02
    assert bridge["B"]["previous_period_difference"] == 0.02


def test_applied_return_cogs_and_recomputed_tax_use_final_values_once():
    previous = _result("2026-08-25", "2026-08-31")
    current = _result(
        "2026-09-01",
        "2026-09-07",
        net_accrual=51000.0,
        product_cost=26000.0,
        return_cogs_profit_applied=True,
        return_cogs_profit_tax_recomputed=True,
        return_cogs_profit_application_amount=100.0,
        tax=5706.0,
        profit=19394.0,
        margin_percent=19.394,
    )

    bridge = _bridge(current, previous)

    assert bridge["B"]["status"] == "CONFIRMED"
    assert bridge["B"]["authoritative_delta"] == 4194
    assert bridge["B"]["contributions"]["return_cogs_contribution"] == 100
    assert bridge["B"]["contributions"]["tax_contribution"] == -906


def test_partial_external_coverage_does_not_block_b_bridge():
    previous = _result("2026-08-25", "2026-08-31")
    current = _result(
        "2026-09-01",
        "2026-09-07",
        net_accrual=41000.0,
        profit=16200.0,
    )
    current["external_expense_evidence"] = {
        "error": False,
        "status": "PERIOD_PROFIT_EXTERNAL_EXPENSE_EVIDENCE_PARTIAL",
        "coverage_complete": False,
        "observed_expense_total": 200.0,
        "complete_expense_total": None,
    }
    current["external_expense_adjustment"] = {
        "error": False,
        "profit_adjustment_complete": False,
        "observed_profit_after_external_expenses": 16000.0,
        "observed_margin_percent": 16.0,
    }

    bridge = _bridge(current, previous)

    assert bridge["B"]["status"] == "CONFIRMED"
    assert bridge["E"]["status"] == "UNAVAILABLE"
    assert bridge["status"] == "PERIOD_PROFIT_COMPARISON_BRIDGE_PARTIAL"


def test_unconfirmed_return_cogs_blocks_b_bridge_instead_of_assuming_zero():
    previous = _result("2026-08-25", "2026-08-31")
    current = _result(
        "2026-09-01",
        "2026-09-07",
        return_cogs_profit_applied=None,
        return_cogs_profit_tax_recomputed=None,
    )

    bridge = _bridge(current, previous)

    assert bridge["B"]["status"] == "UNAVAILABLE"
    assert "PERIOD_PROFIT_COMPARISON_FINAL_RESULT_UNCONFIRMED" in bridge["reason_codes"]


def test_unsupported_profit_scope_refuses_to_claim_formula_reconciliation():
    previous = _result(
        "2026-08-25",
        "2026-08-31",
        profit_scope="LEGACY_UNKNOWN_SCOPE",
    )
    current = _result(
        "2026-09-01",
        "2026-09-07",
        profit_scope="LEGACY_UNKNOWN_SCOPE",
    )

    bridge = _bridge(current, previous)

    assert bridge["B"]["status"] == "UNAVAILABLE"
    assert bridge["code"] == "PERIOD_PROFIT_COMPARISON_BRIDGE_SCOPE_UNSUPPORTED"


def test_external_adjustment_mismatch_disables_only_e_bridge():
    previous = _external(
        _result("2026-08-25", "2026-08-31"),
        expense_total=1000.0,
        profit_after=14200.0,
    )
    current = _external(
        _result("2026-09-01", "2026-09-07"),
        expense_total=2000.0,
        profit_after=13000.0,
    )

    bridge = _bridge(current, previous)

    assert bridge["B"]["status"] == "CONFIRMED"
    assert bridge["E"]["status"] == "UNAVAILABLE"
    assert bridge["E"]["reason_code"] == "PERIOD_PROFIT_COMPARISON_BRIDGE_EXTERNAL_RECONCILIATION_FAILED"


def test_invalid_contract_shape_returns_controlled_error():
    result = build_period_profit_comparison_bridge({"error": True})

    assert result["error"] is True
    assert result["code"] == "PERIOD_PROFIT_COMPARISON_BRIDGE_CONTRACT_INVALID"
