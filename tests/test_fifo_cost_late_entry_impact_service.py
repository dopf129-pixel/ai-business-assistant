from services.fifo_cost_late_entry_impact_service import (
    FifoCostLateEntryImpactService,
)
from decimal import Decimal, ROUND_HALF_UP
import pytest
from services.fifo_cost_repository import FifoCostRepository


def _reconstruction(*, before_cost="100.00", after_cost="150.00", returns=0):
    before_unit = format(
        (Decimal(before_cost) / 2).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        ".2f",
    )
    after_unit = format(
        (Decimal(after_cost) / 2).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        ".2f",
    )
    return {
        "error": False,
        "code": "FIFO_LATE_ENTRY_RECONSTRUCTION_READY",
        "complete": True,
        "draft_id": "late_" + "a" * 40,
        "stream_revision": 4,
        "allocation_revision": 2,
        "source_set_fingerprint": "b" * 64,
        "preview_fingerprint": "c" * 64,
        "before_complete": True,
        "before_total_cogs_rub": before_cost,
        "candidate_total_cogs_rub": after_cost,
        "before_allocations": [{
            "event_id": "event-sale-1", "quantity": 2,
            "total_cost_rub": before_cost, "lines": [{
                "layer_id": "layer-old", "rate_change_id": None,
                "quantity": 2, "unit_cost_rub": before_unit,
                "total_cost_rub": before_cost,
            }],
        }],
        "candidate_allocations": [{
            "event_id": "event-sale-1", "quantity": 2,
            "total_cost_rub": after_cost, "lines": [{
                "layer_id": None, "rate_change_id": "rate-candidate",
                "quantity": 2, "unit_cost_rub": after_unit,
                "total_cost_rub": after_cost,
            }],
        }],
        "sale_effective_dates": {"event-sale-1": "2026-09-12"},
        "related_return_count": returns,
        "non_sale_outflow_count": 0,
        "candidate_outflows": [],
        "candidate_non_sale_outflow_value_rub": "0.00",
        "return_cogs_authorization_changed": False,
    }


def _summary(*, current_sku_cost="100.00", total_cost="200.00", net_accrual="500.00"):
    return {
        "period": "2026-09",
        "complete": True,
        "source_fingerprint": "d" * 64,
        "revenue": "1000.00",
        "discount_points": "0.00",
        "net_accrual": net_accrual,
        "current_total_product_cost": total_cost,
        "current_sku_product_cost": current_sku_cost,
    }


def _policy(mode="USN_INCOME", rate=6.0, minimum=1.0):
    return {
        "error": False,
        "configured": True,
        "policy": {
            "mode": mode,
            "tax_rate": rate,
            "minimum_tax_rate": minimum,
        },
    }


def test_late_entry_impact_calculates_cogs_tax_and_profit_using_income_tax_policy():
    result = FifoCostLateEntryImpactService().preview(
        reconstruction=_reconstruction(),
        period_summaries=[_summary()],
        tax_policy_result=_policy(),
    )

    assert result["code"] == "FIFO_LATE_ENTRY_IMPACT_READY"
    assert result["complete"] is True
    assert result["periods"] == [{
        "period": "2026-09",
        "start_date": "2026-09-12",
        "end_date": "2026-09-12",
        "units": 2,
        "before_units_by_basis": {"layer:layer-old": 2},
        "after_units_by_basis": {"rate:rate-candidate": 2},
        "before_cogs_by_basis_rub": {"layer:layer-old": "100.00"},
        "after_cogs_by_basis_rub": {"rate:rate-candidate": "150.00"},
        "completeness": "COMPLETE",
        "before_sku_cogs_rub": "100.00",
        "after_sku_cogs_rub": "150.00",
        "delta_cogs_rub": "50.00",
        "before_total_cogs_rub": "200.00",
        "after_total_cogs_rub": "250.00",
        "before_tax_rub": "60.00",
        "after_tax_rub": "60.00",
        "delta_tax_rub": "0.00",
        "before_profit_rub": "240.00",
        "after_profit_rub": "190.00",
        "delta_profit_rub": "-50.00",
        "source_fingerprint": "d" * 64,
    }]
    assert len(result["preview_fingerprint"]) == 64
    assert result["read_only"] is True


def test_late_entry_impact_applies_minimum_tax_and_expense_based_policy():
    result = FifoCostLateEntryImpactService().preview(
        reconstruction=_reconstruction(),
        period_summaries=[_summary()],
        tax_policy_result=_policy("USN_INCOME_MINUS_EXPENSES", 15.0, 1.0),
    )

    period = result["periods"][0]
    assert period["before_tax_rub"] == "45.00"
    assert period["after_tax_rub"] == "37.50"
    assert period["delta_tax_rub"] == "-7.50"
    assert period["delta_profit_rub"] == "-42.50"


def test_late_entry_before_old_layer_is_spent_has_zero_cogs_tax_and_profit_delta():
    result = FifoCostLateEntryImpactService().preview(
        reconstruction=_reconstruction(before_cost="100.00", after_cost="100.00"),
        period_summaries=[_summary()],
        tax_policy_result=_policy("USN_INCOME_MINUS_EXPENSES", 15.0, 1.0),
    )

    period = result["periods"][0]
    assert period["delta_cogs_rub"] == "0.00"
    assert period["delta_tax_rub"] == "0.00"
    assert period["delta_profit_rub"] == "0.00"


def test_late_entry_impact_accepts_already_replayed_linked_returns_without_changing_return_cogs():
    reconstruction = _reconstruction(returns=1)
    result = FifoCostLateEntryImpactService().preview(
        reconstruction=reconstruction,
        period_summaries=[_summary()],
        tax_policy_result=_policy(),
    )

    assert result["code"] == "FIFO_LATE_ENTRY_IMPACT_READY"
    assert result["related_return_count"] == 1
    assert result["return_cogs_authorization_changed"] is False
    assert result["periods"][0]["units"] == 2
    assert "linked_return_count" not in result["periods"][0]
    assert result["read_only"] is True


def test_late_entry_impact_keeps_non_sale_outflow_out_of_sales_units_and_cogs():
    reconstruction = _reconstruction()
    reconstruction["non_sale_outflow_count"] = 1
    reconstruction["candidate_outflows"] = [{
        "event_id": "event-outflow-1", "quantity": 3,
        "reason_code": "HOME_SHORTAGE", "estimated_value_rub": "30.00",
    }]
    reconstruction["candidate_non_sale_outflow_value_rub"] = "30.00"
    result = FifoCostLateEntryImpactService().preview(
        reconstruction=reconstruction,
        period_summaries=[_summary()],
        tax_policy_result=_policy(),
    )

    assert result["code"] == "FIFO_LATE_ENTRY_IMPACT_READY"
    assert result["non_sale_outflow_count"] == 1
    assert result["non_sale_outflow_estimated_value_rub"] == "30.00"
    assert result["non_sale_outflows_included_in_sales_cogs"] is False
    assert result["periods"][0]["units"] == 2
    assert result["periods"][0]["before_sku_cogs_rub"] == "100.00"
    assert result["periods"][0]["after_sku_cogs_rub"] == "150.00"


@pytest.mark.parametrize(
    ("field", "value"),
    [("return_cogs_authorization_changed", True),
     ("non_sale_outflows_included_in_sales_cogs", True)],
)
def test_persisted_impact_rejects_return_cogs_or_outflow_sales_cogs_authority_change(
    field, value,
):
    result = FifoCostLateEntryImpactService().preview(
        reconstruction=_reconstruction(returns=1),
        period_summaries=[_summary()],
        tax_policy_result=_policy(),
    )
    assert result["code"] == "FIFO_LATE_ENTRY_IMPACT_READY"
    assert isinstance(FifoCostRepository._normalize_late_entry_correction(result), dict)

    tampered = dict(result)
    tampered[field] = value
    tampered["preview_fingerprint"] = FifoCostLateEntryImpactService._fingerprint({
        key: item for key, item in tampered.items()
        if key not in {"preview_fingerprint", "code", "error"}
    })

    assert FifoCostRepository._normalize_late_entry_correction(tampered) == (
        "FIFO_LATE_ENTRY_IMPACT_INVALID"
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [("related_return_count", -1), ("related_return_count", "1"),
     ("non_sale_outflow_count", -1), ("non_sale_outflow_count", True)],
)
def test_late_entry_impact_rejects_invalid_return_or_outflow_counts(field, value):
    reconstruction = _reconstruction()
    reconstruction[field] = value
    result = FifoCostLateEntryImpactService().preview(
        reconstruction=reconstruction,
        period_summaries=[_summary()],
        tax_policy_result=_policy(),
    )

    assert result["code"] == "FIFO_LATE_ENTRY_IMPACT_BLOCKED"
    assert result["complete"] is False


def test_late_entry_impact_requires_complete_snapshots_for_every_affected_period():
    result = FifoCostLateEntryImpactService().preview(
        reconstruction=_reconstruction(),
        period_summaries=[],
        tax_policy_result=_policy(),
    )

    assert result["reason_code"] == "FIFO_PERIOD_SUMMARY_COVERAGE_INCOMPLETE"


def test_late_entry_impact_does_not_infer_zero_from_incomplete_period_source():
    summary = _summary()
    summary["complete"] = False
    result = FifoCostLateEntryImpactService().preview(
        reconstruction=_reconstruction(),
        period_summaries=[summary],
        tax_policy_result=_policy(),
    )

    assert result["reason_code"] == "FIFO_PERIOD_SUMMARY_UNAVAILABLE"


def test_late_entry_impact_rejects_baseline_that_does_not_match_replay():
    result = FifoCostLateEntryImpactService().preview(
        reconstruction=_reconstruction(),
        period_summaries=[_summary(current_sku_cost="99.99")],
        tax_policy_result=_policy(),
    )

    assert result["reason_code"] == "FIFO_PERIOD_COGS_BASELINE_MISMATCH"


def test_late_entry_impact_rejects_different_sale_coverage_or_quantity():
    reconstruction = _reconstruction()
    reconstruction["candidate_allocations"][0]["event_id"] = "other-sale"
    reconstruction["sale_effective_dates"]["other-sale"] = "2026-09-12"
    result = FifoCostLateEntryImpactService().preview(
        reconstruction=reconstruction,
        period_summaries=[_summary()],
        tax_policy_result=_policy(),
    )

    assert result["reason_code"] == "FIFO_ALLOCATION_EVENT_COVERAGE_MISMATCH"


def test_n10_late_rate_change_reprices_40_units_without_hard_coding_profit_delta():
    reconstruction = _reconstruction(before_cost="800.00", after_cost="1000.00")
    reconstruction["before_allocations"][0]["lines"][0].update(
        quantity=40, unit_cost_rub="20.00", total_cost_rub="800.00",
    )
    reconstruction["before_allocations"][0]["quantity"] = 40
    reconstruction["candidate_allocations"][0]["lines"][0].update(
        quantity=40, unit_cost_rub="25.00", total_cost_rub="1000.00",
    )
    reconstruction["candidate_allocations"][0]["quantity"] = 40
    summary = _summary(
        current_sku_cost="800.00", total_cost="800.00", net_accrual="1200.00",
    )

    income_tax = FifoCostLateEntryImpactService().preview(
        reconstruction=reconstruction,
        period_summaries=[summary],
        tax_policy_result=_policy("USN_INCOME", 6.0, 1.0),
    )
    expense_tax = FifoCostLateEntryImpactService().preview(
        reconstruction=reconstruction,
        period_summaries=[summary],
        tax_policy_result=_policy("USN_INCOME_MINUS_EXPENSES", 15.0, 1.0),
    )

    assert income_tax["periods"][0]["delta_cogs_rub"] == "200.00"
    assert income_tax["periods"][0]["delta_tax_rub"] == "0.00"
    assert income_tax["periods"][0]["delta_profit_rub"] == "-200.00"
    assert expense_tax["periods"][0]["delta_cogs_rub"] == "200.00"
    assert expense_tax["periods"][0]["delta_tax_rub"] == "-30.00"
    assert expense_tax["periods"][0]["delta_profit_rub"] == "-170.00"


def test_late_entry_impact_rejects_signed_money_in_invalid_fields_and_bad_policy():
    summary = _summary()
    summary["current_total_product_cost"] = "NaN"
    result = FifoCostLateEntryImpactService().preview(
        reconstruction=_reconstruction(),
        period_summaries=[summary],
        tax_policy_result=_policy(),
    )
    assert result["reason_code"] == "FIFO_PERIOD_SUMMARY_INVALID"

    result = FifoCostLateEntryImpactService().preview(
        reconstruction=_reconstruction(),
        period_summaries=[_summary()],
        tax_policy_result={"error": False, "configured": False},
    )
    assert result["reason_code"] == "FIFO_TAX_POLICY_UNAVAILABLE"
