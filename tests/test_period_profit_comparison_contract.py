from datetime import datetime, timezone

from period_profit_comparison_contract import (
    build_period_profit_comparison_contract,
)


def _result(date_from, date_to, **summary_overrides):
    summary = {
        "error": False,
        "status": "PERIOD_PROFIT_SUMMARY_READY",
        "date_from": date_from,
        "date_to": date_to,
        "profit_scope": "OZON_ACCOUNT_ACCRUALS_COST_AND_CONFIGURED_TAX_V3",
        "returns_included": False,
        "advertising_included": False,
        "storage_included": False,
        "revenue": 1000.0,
        "discount_points": 100.0,
        "revenue_tax_base": 900.0,
        "net_accrual": 600.0,
        "product_cost": 100.0,
        "tax": 54.0,
        "profit": 446.0,
        "margin_percent": 44.6,
        "units_sold": 10,
        "tax_mode": "USN_INCOME",
        "tax_rate_percent": 6.0,
        "minimum_tax_rate_percent": None,
        "return_cogs_profit_applied": False,
        "return_cogs_profit_tax_recomputed": False,
        "return_cogs_profit_application_amount": None,
    }
    summary.update(summary_overrides)
    return {
        "error": False,
        "status": "PERIOD_PROFIT_QUERY_READY",
        "request": {
            "error": False,
            "status": "PERIOD_PROFIT_REQUEST_READY",
            "date_from": date_from,
            "date_to": date_to,
        },
        "summary": summary,
        "coverage": {
            "coverage_status": "COMPLETE",
            "included_components": ["returns", "advertising"],
            "missing_components": [],
        },
        "external_expense_evidence": None,
        "external_expense_adjustment": None,
    }


def _external_result(date_from, date_to, *, expenses, profit_after, margin):
    result = _result(date_from, date_to)
    total = expenses
    result["external_expense_evidence"] = {
        "error": False,
        "status": "PERIOD_PROFIT_EXTERNAL_EXPENSE_EVIDENCE_READY",
        "coverage_complete": True,
        "observed_expense_total": total,
        "complete_expense_total": total,
    }
    result["external_expense_adjustment"] = {
        "error": False,
        "profit_adjustment_complete": True,
        "complete_profit_after_external_expenses": profit_after,
        "complete_margin_percent": margin,
    }
    return result


def _build(current, previous, **kwargs):
    return build_period_profit_comparison_contract(
        current,
        previous,
        tenant_scope="user-1::store-1",
        generated_at=datetime(2026, 10, 15, 12, tzinfo=timezone.utc),
        **kwargs,
    )


def test_contract_projects_finalized_values_without_recalculating_and_marks_read_only():
    current = _result("2026-09-01", "2026-09-07", profit=123.45)
    previous = _result("2026-08-25", "2026-08-31", profit=100.0)

    contract = _build(current, previous)

    assert contract["error"] is False
    assert contract["generated_at"] == "2026-10-15T12:00:00Z"
    assert contract["current"]["period"]["inclusive_days"] == 7
    assert contract["current"]["metrics"]["profit"]["value"] == 123.45
    assert contract["profit_bases"]["B"]["status"] == "CONFIRMED"
    assert contract["profit_bases"]["E"]["status"] == "UNAVAILABLE"
    assert contract["read_only"] is True
    assert contract["executed"] is False
    assert current["summary"]["profit"] == 123.45


def test_complete_external_coverage_confirms_e_and_zero_is_a_known_amount():
    current = _external_result(
        "2026-09-01", "2026-09-07", expenses=0.0, profit_after=446.0, margin=44.6
    )
    previous = _external_result(
        "2026-08-25", "2026-08-31", expenses=0.0, profit_after=400.0, margin=40.0
    )

    contract = _build(current, previous)

    assert contract["profit_bases"]["E"]["status"] == "CONFIRMED"
    assert contract["current"]["metrics"]["external_expenses"] == {
        "value": 0.0,
        "unit": "RUB",
        "status": "CONFIRMED",
        "source": "external_expense_evidence",
    }


def test_external_coverage_on_only_one_side_keeps_b_but_disables_e_delta():
    current = _external_result(
        "2026-09-01", "2026-09-07", expenses=25.0, profit_after=421.0, margin=42.1
    )
    previous = _result("2026-08-25", "2026-08-31")

    contract = _build(current, previous)

    assert contract["profit_bases"]["B"]["status"] == "CONFIRMED"
    assert contract["profit_bases"]["E"]["status"] == "UNAVAILABLE"
    assert contract["current"]["metrics"]["profit_after_external_expenses"]["status"] == "CONFIRMED"
    assert contract["previous"]["metrics"]["profit_after_external_expenses"]["status"] == "UNKNOWN"


def test_partial_external_data_never_becomes_confirmed_e():
    current = _result("2026-09-01", "2026-09-07")
    current["external_expense_evidence"] = {
        "error": False,
        "status": "PERIOD_PROFIT_EXTERNAL_EXPENSE_EVIDENCE_PARTIAL",
        "coverage_complete": False,
        "observed_expense_total": 20.0,
        "complete_expense_total": None,
    }
    current["external_expense_adjustment"] = {
        "error": False,
        "profit_adjustment_complete": False,
        "observed_profit_after_external_expenses": 426.0,
        "observed_margin_percent": 42.6,
    }

    contract = _build(
        current,
        _external_result(
            "2026-08-25", "2026-08-31", expenses=10.0, profit_after=390.0, margin=39.0
        ),
    )

    assert contract["profit_bases"]["B"]["status"] == "CONFIRMED"
    assert contract["profit_bases"]["E"]["status"] == "UNAVAILABLE"
    assert contract["current"]["metrics"]["profit_after_external_expenses"]["status"] == "PARTIAL"


def test_tax_policy_mismatch_disables_profit_comparison_but_keeps_independent_metrics():
    current = _result("2026-09-01", "2026-09-07", tax_rate_percent=6.0)
    previous = _result("2026-08-25", "2026-08-31", tax_rate_percent=5.0)

    contract = _build(current, previous)

    assert contract["profit_bases"]["B"]["status"] == "UNAVAILABLE"
    assert contract["profit_bases"]["E"]["status"] == "UNAVAILABLE"
    assert contract["current"]["metrics"]["revenue"]["value"] == 1000.0
    assert "PERIOD_PROFIT_COMPARISON_TAX_POLICY_MISMATCH" in contract["profit_compatibility"]["reason_codes"]


def test_profit_scope_mismatch_disables_only_profit_comparison():
    current = _result("2026-09-01", "2026-09-07")
    previous = _result(
        "2026-08-25",
        "2026-08-31",
        profit_scope="OZON_ACCOUNT_ACCRUALS_COST_COMMITTED_RETURN_COGS_AND_CONFIGURED_TAX_V4",
    )

    contract = _build(current, previous)

    assert contract["profit_bases"]["B"]["status"] == "UNAVAILABLE"
    assert "PERIOD_PROFIT_COMPARISON_SCOPE_MISMATCH" in contract["profit_compatibility"]["reason_codes"]
    assert contract["current"]["metrics"]["net_accrual"]["status"] == "CONFIRMED"


def test_period_length_and_adjacency_mismatches_are_reported():
    current = _result("2026-09-01", "2026-09-07")
    shorter = _result("2026-08-25", "2026-08-30")
    contract = _build(current, shorter)
    assert "PERIOD_PROFIT_COMPARISON_PERIOD_LENGTH_MISMATCH" in contract["profit_compatibility"]["reason_codes"]

    gap = _build(current, _result("2026-08-23", "2026-08-29"))
    assert "PERIOD_PROFIT_COMPARISON_PERIODS_NOT_ADJACENT" in gap["profit_compatibility"]["reason_codes"]


def test_missing_tenant_does_not_confirm_cross_period_profit_comparison():
    contract = build_period_profit_comparison_contract(
        _result("2026-09-01", "2026-09-07"),
        _result("2026-08-25", "2026-08-31"),
        generated_at=datetime(2026, 10, 15, tzinfo=timezone.utc),
    )

    assert contract["profit_bases"]["B"]["status"] == "UNAVAILABLE"
    assert "PERIOD_PROFIT_COMPARISON_TENANT_SCOPE_UNKNOWN" in contract["profit_compatibility"]["reason_codes"]


def test_return_cogs_zero_requires_explicit_not_applied_flag():
    current = _result("2026-09-01", "2026-09-07", return_cogs_profit_applied=False)
    previous = _result("2026-08-25", "2026-08-31")
    contract = _build(current, previous)
    assert contract["current"]["metrics"]["return_cogs_adjustment"]["status"] == "CONFIRMED"
    assert contract["current"]["metrics"]["return_cogs_adjustment"]["value"] == 0.0

    unknown = _build(
        _result("2026-09-01", "2026-09-07", return_cogs_profit_applied=None),
        previous,
    )
    assert unknown["current"]["metrics"]["return_cogs_adjustment"]["status"] == "UNKNOWN"
    assert unknown["current"]["metrics"]["profit"]["status"] == "UNKNOWN"


def test_unfinalized_base_summary_cannot_be_promoted_to_confirmed_profit():
    current = _result(
        "2026-09-01",
        "2026-09-07",
        return_cogs_profit_tax_recomputed=None,
    )

    contract = _build(
        current,
        _result("2026-08-25", "2026-08-31"),
    )

    assert contract["profit_bases"]["B"]["status"] == "UNAVAILABLE"
    assert contract["current"]["metrics"]["profit"]["status"] == "UNKNOWN"
    assert contract["current"]["metrics"]["revenue"]["status"] == "CONFIRMED"
    assert "PERIOD_PROFIT_COMPARISON_FINAL_RESULT_UNCONFIRMED" in contract["profit_compatibility"]["reason_codes"]


def test_invalid_shapes_and_malformed_metrics_are_controlled_unknowns():
    invalid = build_period_profit_comparison_contract(
        {"error": True},
        _result("2026-08-25", "2026-08-31"),
        tenant_scope="tenant",
        generated_at=datetime(2026, 10, 15, tzinfo=timezone.utc),
    )
    assert invalid["error"] is True
    assert invalid["code"] == "PERIOD_PROFIT_COMPARISON_CURRENT_RESULT_INVALID"

    malformed = _build(
        _result("2026-09-01", "2026-09-07", profit=True),
        _result("2026-08-25", "2026-08-31"),
    )
    assert malformed["current"]["metrics"]["profit"]["status"] == "UNKNOWN"
    assert malformed["profit_bases"]["B"]["status"] == "UNAVAILABLE"


def test_summary_must_match_its_original_request_period():
    current = _result("2026-09-01", "2026-09-07")
    current["request"]["date_to"] = "2026-09-08"

    contract = _build(
        current,
        _result("2026-08-25", "2026-08-31"),
    )

    assert contract["error"] is True
    assert contract["code"] == "PERIOD_PROFIT_COMPARISON_CURRENT_RESULT_INVALID"
