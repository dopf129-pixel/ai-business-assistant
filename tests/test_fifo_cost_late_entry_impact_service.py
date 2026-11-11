from services.fifo_cost_late_entry_impact_service import (
    FifoCostLateEntryImpactService,
)
from calendar import monthrange
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import json
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
        "sale_identity_digests_by_event": {"event-sale-1": "e" * 64},
        "related_return_count": returns,
        "non_sale_outflow_count": 0,
        "candidate_outflows": [],
        "candidate_non_sale_outflow_value_rub": "0.00",
        "return_cogs_authorization_changed": False,
    }


def _tax_policy_fingerprint(mode="USN_INCOME", rate=6.0, minimum=1.0):
    mode = mode.upper()
    if mode == "NONE":
        rate, minimum = 0.0, 1.0
    normalized = {
        "mode": mode,
        "tax_rate": float(rate),
        "minimum_tax_rate": float(minimum),
    }
    encoded = json.dumps(
        normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _summary(
    *, current_sku_cost="100.00", total_cost="200.00", net_accrual="500.00",
    period="2026-10", tax_mode="USN_INCOME", tax_rate=6.0,
    minimum_tax_rate=1.0, reconstruction_fingerprint="c" * 64,
):
    year, month = map(int, period.split("-"))
    return {
        "period": period,
        "complete": True,
        "source_fingerprint": "d" * 64,
        "reconstruction_fingerprint": reconstruction_fingerprint,
        "tax_policy_fingerprint": _tax_policy_fingerprint(
            tax_mode, tax_rate, minimum_tax_rate,
        ),
        "sale_identity_digests": ["e" * 64],
        "revenue": "1000.00",
        "discount_points": "0.00",
        "net_accrual": net_accrual,
        "current_total_product_cost": total_cost,
        "current_sku_product_cost": current_sku_cost,
        "period_from": f"{period}-01",
        "period_to": f"{period}-{monthrange(year, month)[1]:02d}",
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


def _five_unit_reconstruction():
    reconstruction = _reconstruction(before_cost="105.00", after_cost="92.30")
    reconstruction["before_total_cogs_rub"] = "105.00"
    reconstruction["candidate_total_cogs_rub"] = "92.30"
    reconstruction["before_allocations"] = [{
        "event_id": "event-sale-1", "quantity": 5,
        "total_cost_rub": "105.00", "lines": [{
            "layer_id": "layer-old", "rate_change_id": None,
            "quantity": 5, "unit_cost_rub": "21.00", "total_cost_rub": "105.00",
        }],
    }]
    reconstruction["candidate_allocations"] = [{
        "event_id": "event-sale-1", "quantity": 5,
        "total_cost_rub": "92.30", "lines": [
            {
                "layer_id": "layer-old", "rate_change_id": None,
                "quantity": 3, "unit_cost_rub": "21.00", "total_cost_rub": "63.00",
            },
            {
                "layer_id": None, "rate_change_id": "rate-candidate",
                "quantity": 2, "unit_cost_rub": "14.65", "total_cost_rub": "29.30",
            },
        ],
    }]
    return reconstruction


def test_late_entry_impact_calculates_cogs_tax_and_profit_using_income_tax_policy():
    result = FifoCostLateEntryImpactService().preview(
        reconstruction=_reconstruction(),
        period_summaries=[_summary()],
        tax_policy_result=_policy(),
    )

    assert result["code"] == "FIFO_LATE_ENTRY_IMPACT_READY"
    assert result["complete"] is True
    assert result["periods"] == [{
        "period": "2026-10",
        "physical_sale_start_date": "2026-09-12",
        "physical_sale_end_date": "2026-09-12",
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


def test_late_entry_replaces_only_target_sale_subset_and_preserves_earlier_same_sku_cogs():
    result = FifoCostLateEntryImpactService().preview(
        reconstruction=_reconstruction(before_cost="100.00", after_cost="150.00"),
        period_summaries=[_summary(
            current_sku_cost="130.00", total_cost="200.00",
        )],
        tax_policy_result=_policy(),
    )

    assert result["code"] == "FIFO_LATE_ENTRY_IMPACT_READY"
    period = result["periods"][0]
    # 30 ₽ is an earlier same-SKU sale and 70 ₽ belongs to other products;
    # both stay in the 100 ₽ untouched store-cost portion.
    assert period["before_sku_cogs_rub"] == "100.00"
    assert period["after_sku_cogs_rub"] == "150.00"
    assert period["before_total_cogs_rub"] == "200.00"
    assert period["after_total_cogs_rub"] == "250.00"
    assert period["delta_profit_rub"] == "-50.00"


@pytest.mark.parametrize(
    ("mode", "expected_tax", "expected_before_profit", "expected_after_profit"),
    [
        ("NONE", "0.00", "395.00", "407.70"),
        ("USN_INCOME", "60.00", "335.00", "347.70"),
    ],
)
def test_late_entry_numeric_acceptance_five_units_uses_independent_decimal_oracle(
    mode, expected_tax, expected_before_profit, expected_after_profit,
):
    # Independent arithmetic from N21/N24/N25: old COGS=5*21=105;
    # candidate COGS=3*21+2*14.65=92.30; net accrual=500.
    old_cogs = Decimal("5") * Decimal("21.00")
    candidate_cogs = Decimal("3") * Decimal("21.00") + Decimal("2") * Decimal("14.65")
    assert old_cogs == Decimal("105.00")
    assert candidate_cogs == Decimal("92.30")
    assert Decimal("500.00") - old_cogs == Decimal("395.00")
    assert Decimal("500.00") - candidate_cogs == Decimal("407.70")

    reconstruction = _five_unit_reconstruction()
    summary = _summary(
        current_sku_cost="105.00", total_cost="105.00", net_accrual="500.00",
        tax_mode=mode,
    )
    policy = _policy(mode, 6.0, 1.0)

    result = FifoCostLateEntryImpactService().preview(
        reconstruction=reconstruction,
        period_summaries=[summary],
        tax_policy_result=policy,
    )

    assert result["code"] == "FIFO_LATE_ENTRY_IMPACT_READY"
    period = result["periods"][0]
    assert period["units"] == 5
    assert period["before_sku_cogs_rub"] == "105.00"
    assert period["after_sku_cogs_rub"] == "92.30"
    assert period["delta_cogs_rub"] == "-12.70"
    assert period["before_tax_rub"] == expected_tax
    assert period["after_tax_rub"] == expected_tax
    assert period["before_profit_rub"] == expected_before_profit
    assert period["after_profit_rub"] == expected_after_profit
    assert period["delta_profit_rub"] == "12.70"


def test_late_entry_impact_applies_minimum_tax_and_expense_based_policy():
    result = FifoCostLateEntryImpactService().preview(
        reconstruction=_reconstruction(),
        period_summaries=[_summary(
            tax_mode="USN_INCOME_MINUS_EXPENSES", tax_rate=15.0,
        )],
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
        period_summaries=[_summary(
            tax_mode="USN_INCOME_MINUS_EXPENSES", tax_rate=15.0,
        )],
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
    baseline = FifoCostLateEntryImpactService().preview(
        reconstruction=_reconstruction(),
        period_summaries=[_summary()],
        tax_policy_result=_policy(),
    )
    reconstruction = _reconstruction()
    reconstruction["non_sale_outflow_count"] = 1
    reconstruction["candidate_outflows"] = [{
        "event_id": "event-outflow-1", "quantity": 2,
        "reason_code": "HOME_SHORTAGE", "estimated_value_rub": "42.00",
    }]
    reconstruction["candidate_non_sale_outflow_value_rub"] = "42.00"
    result = FifoCostLateEntryImpactService().preview(
        reconstruction=reconstruction,
        period_summaries=[_summary()],
        tax_policy_result=_policy(),
    )

    assert result["code"] == "FIFO_LATE_ENTRY_IMPACT_READY"
    assert result["non_sale_outflow_count"] == 1
    assert result["non_sale_outflow_estimated_value_rub"] == "42.00"
    assert result["non_sale_outflows_included_in_sales_cogs"] is False
    assert result["periods"][0]["units"] == 2
    assert result["periods"][0]["before_sku_cogs_rub"] == "100.00"
    assert result["periods"][0]["after_sku_cogs_rub"] == "150.00"
    assert result["periods"][0]["before_profit_rub"] == "240.00"
    assert result["periods"][0]["after_profit_rub"] == "190.00"
    assert result["periods"][0]["delta_profit_rub"] == "-50.00"
    assert result["periods"][0]["delta_profit_rub"] == baseline["periods"][0][
        "delta_profit_rub"
    ]


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

    assert result["code"] == "FIFO_LATE_ENTRY_IMPACT_CANDIDATE_ONLY"
    assert result["reason_code"] == "FIFO_PERIOD_SUMMARY_COVERAGE_INCOMPLETE"
    assert result["candidate_total_cogs_rub"] == "150.00"
    assert "periods" not in result
    assert "delta_profit_rub" not in repr(result)


def test_late_entry_impact_does_not_infer_zero_from_incomplete_period_source():
    summary = _summary()
    summary["complete"] = False
    result = FifoCostLateEntryImpactService().preview(
        reconstruction=_reconstruction(),
        period_summaries=[summary],
        tax_policy_result=_policy(),
    )

    assert result["code"] == "FIFO_LATE_ENTRY_IMPACT_CANDIDATE_ONLY"
    assert result["reason_code"] == "FIFO_PERIOD_SUMMARY_UNAVAILABLE"


def test_late_entry_impact_rejects_baseline_that_does_not_match_replay():
    result = FifoCostLateEntryImpactService().preview(
        reconstruction=_reconstruction(),
        period_summaries=[_summary(current_sku_cost="99.99")],
        tax_policy_result=_policy(),
    )

    assert result["code"] == "FIFO_LATE_ENTRY_IMPACT_CANDIDATE_ONLY"
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

    assert result["code"] == "FIFO_LATE_ENTRY_IMPACT_BLOCKED"
    assert result["reason_code"] == "FIFO_FINANCIAL_PERIOD_MAPPING_UNAVAILABLE"
    assert result["complete"] is False


def test_late_entry_without_before_baseline_returns_candidate_cost_only_by_financial_period():
    reconstruction = _reconstruction()
    reconstruction["before_complete"] = False
    reconstruction["before_reason_code"] = "HISTORY_GAP"
    reconstruction["before_allocations"] = []
    reconstruction["before_total_cogs_rub"] = None
    result = FifoCostLateEntryImpactService().preview(
        reconstruction=reconstruction,
        period_summaries=[_summary()],
        tax_policy_result={"error": False, "configured": False},
    )

    assert result["code"] == "FIFO_LATE_ENTRY_IMPACT_CANDIDATE_ONLY"
    assert result["reason_code"] == "HISTORY_GAP"
    assert result["candidate_total_cogs_rub"] == "150.00"
    assert result["candidate_periods"] == [{
        "period": "2026-10",
        "units": 2,
        "candidate_cogs_rub": "150.00",
        "candidate_units_by_basis": {"rate:rate-candidate": 2},
        "candidate_cogs_by_basis_rub": {"rate:rate-candidate": "150.00"},
        "physical_sale_start_date": "2026-09-12",
        "physical_sale_end_date": "2026-09-12",
        "completeness": "CANDIDATE_ONLY",
    }]
    assert "delta_cogs_rub" not in result
    assert "tax" not in repr(result)
    assert "profit" not in repr(result)


def test_late_entry_never_treats_physical_date_as_financial_period():
    result = FifoCostLateEntryImpactService().preview(
        reconstruction=_reconstruction(),
        period_summaries=[_summary()],
        tax_policy_result=_policy(),
    )

    assert result["code"] == "FIFO_LATE_ENTRY_IMPACT_READY"
    assert result["periods"][0]["period"] == "2026-10"
    assert result["periods"][0]["physical_sale_start_date"] == "2026-09-12"

    moved_financial_summary = _summary(period="2026-11")
    moved = FifoCostLateEntryImpactService().preview(
        reconstruction=_reconstruction(),
        period_summaries=[moved_financial_summary],
        tax_policy_result=_policy(),
    )
    assert moved["periods"][0]["period"] == "2026-11"
    assert moved["periods"][0]["physical_sale_start_date"] == "2026-09-12"
    assert moved["financial_period_mapping_fingerprint"] != (
        result["financial_period_mapping_fingerprint"]
    )


def test_late_entry_impact_covers_every_financial_period_in_dependent_sale_horizon():
    reconstruction = _reconstruction(before_cost="100.00", after_cost="150.00")
    reconstruction["before_total_cogs_rub"] = "150.00"
    reconstruction["candidate_total_cogs_rub"] = "210.00"
    reconstruction["before_allocations"].append({
        "event_id": "event-sale-2", "quantity": 1,
        "total_cost_rub": "50.00", "lines": [{
            "layer_id": "layer-old", "rate_change_id": None,
            "quantity": 1, "unit_cost_rub": "50.00", "total_cost_rub": "50.00",
        }],
    })
    reconstruction["candidate_allocations"].append({
        "event_id": "event-sale-2", "quantity": 1,
        "total_cost_rub": "60.00", "lines": [{
            "layer_id": None, "rate_change_id": "rate-candidate",
            "quantity": 1, "unit_cost_rub": "60.00", "total_cost_rub": "60.00",
        }],
    })
    reconstruction["sale_effective_dates"]["event-sale-2"] = "2026-10-02"
    reconstruction["sale_identity_digests_by_event"]["event-sale-2"] = "f" * 64
    october = _summary()
    october["current_sku_product_cost"] = "100.00"
    october["current_total_product_cost"] = "200.00"
    november = _summary(
        current_sku_cost="50.00", total_cost="100.00", period="2026-11",
    )
    november["sale_identity_digests"] = ["f" * 64]
    result = FifoCostLateEntryImpactService().preview(
        reconstruction=reconstruction,
        period_summaries=[october, november],
        tax_policy_result=_policy(),
    )

    assert result["code"] == "FIFO_LATE_ENTRY_IMPACT_READY", result.get("reason_code")
    assert [(row["period"], row["units"]) for row in result["periods"]] == [
        ("2026-10", 2), ("2026-11", 1),
    ]
    assert [row["delta_cogs_rub"] for row in result["periods"]] == [
        "50.00", "10.00",
    ]
    assert [row["before_total_cogs_rub"] for row in result["periods"]] == [
        "200.00", "100.00",
    ]
    assert [row["after_total_cogs_rub"] for row in result["periods"]] == [
        "250.00", "110.00",
    ]


def test_late_entry_requires_complete_financial_sale_identity_mapping():
    summary = _summary()
    summary.pop("sale_identity_digests")
    result = FifoCostLateEntryImpactService().preview(
        reconstruction=_reconstruction(),
        period_summaries=[summary],
        tax_policy_result=_policy(),
    )

    assert result["code"] == "FIFO_LATE_ENTRY_IMPACT_CANDIDATE_ONLY"
    assert result["reason_code"] == "FIFO_FINANCIAL_PERIOD_MAPPING_UNAVAILABLE"
    assert result["candidate_total_cogs_rub"] == "150.00"
    assert result["candidate_periods"] == []


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
        period_summaries=[_summary(
            current_sku_cost="800.00", total_cost="800.00", net_accrual="1200.00",
            tax_mode="USN_INCOME_MINUS_EXPENSES", tax_rate=15.0,
        )],
        tax_policy_result=_policy("USN_INCOME_MINUS_EXPENSES", 15.0, 1.0),
    )

    assert income_tax["periods"][0]["delta_cogs_rub"] == "200.00"
    assert income_tax["periods"][0]["delta_tax_rub"] == "0.00"
    assert income_tax["periods"][0]["delta_profit_rub"] == "-200.00"
    assert expense_tax["periods"][0]["delta_cogs_rub"] == "200.00"
    assert expense_tax["periods"][0]["delta_tax_rub"] == "-30.00"
    assert expense_tax["periods"][0]["delta_profit_rub"] == "-170.00"


@pytest.mark.parametrize(
    ("mode", "rate", "minimum", "points", "net", "before_tax", "after_tax",
     "before_profit", "after_profit", "delta_profit"),
    [
        ("NONE", 0.0, 1.0, "0.00", "400.00", "0.00", "0.00",
         "295.00", "307.70", "12.70"),
        ("USN_INCOME", 6.0, 1.0, "200.00", "400.00", "48.00", "48.00",
         "247.00", "259.70", "12.70"),
        ("USN_INCOME_MINUS_EXPENSES", 15.0, 1.0, "0.00", "400.00", "44.25", "46.16",
         "250.75", "261.54", "10.79"),
        ("USN_INCOME_MINUS_EXPENSES", 15.0, 1.0, "0.00", "110.00", "10.00", "10.00",
         "-5.00", "7.70", "12.70"),
    ],
)
def test_late_entry_matches_mr12_to_mr15_canonical_tax_and_profit_matrix(
    mode, rate, minimum, points, net, before_tax, after_tax,
    before_profit, after_profit, delta_profit,
):
    reconstruction = _five_unit_reconstruction()
    summary = _summary(
        current_sku_cost="105.00", total_cost="105.00", net_accrual=net,
        tax_mode=mode, tax_rate=rate, minimum_tax_rate=minimum,
    )
    summary["discount_points"] = points

    result = FifoCostLateEntryImpactService().preview(
        reconstruction=reconstruction,
        period_summaries=[summary],
        tax_policy_result=_policy(mode, rate, minimum),
    )

    assert result["code"] == "FIFO_LATE_ENTRY_IMPACT_READY"
    period = result["periods"][0]
    assert period["before_sku_cogs_rub"] == "105.00"
    assert period["after_sku_cogs_rub"] == "92.30"
    assert period["before_tax_rub"] == before_tax
    assert period["after_tax_rub"] == after_tax
    assert period["before_profit_rub"] == before_profit
    assert period["after_profit_rub"] == after_profit
    assert period["delta_profit_rub"] == delta_profit


@pytest.mark.parametrize(
    ("binding", "expected_reason"),
    [
        ("tax_policy_fingerprint", "FIFO_PERIOD_SUMMARY_TAX_POLICY_MISMATCH"),
        ("reconstruction_fingerprint", "FIFO_PERIOD_SUMMARY_RECONSTRUCTION_MISMATCH"),
    ],
)
def test_late_entry_impact_requires_exact_snapshot_policy_and_reconstruction_bindings(
    binding, expected_reason,
):
    summary = _summary()
    summary[binding] = "f" * 64
    result = FifoCostLateEntryImpactService().preview(
        reconstruction=_reconstruction(),
        period_summaries=[summary],
        tax_policy_result=_policy(),
    )

    assert result["code"] == "FIFO_LATE_ENTRY_IMPACT_CANDIDATE_ONLY"
    assert result["complete"] is False
    assert result["reason_code"] == expected_reason
    assert "periods" not in result
    assert "delta_profit_rub" not in repr(result)


def test_late_entry_snapshot_must_cover_the_complete_financial_month():
    summary = _summary()
    summary["period_to"] = "2026-10-30"
    result = FifoCostLateEntryImpactService().preview(
        reconstruction=_reconstruction(),
        period_summaries=[summary],
        tax_policy_result=_policy(),
    )

    assert result["code"] == "FIFO_LATE_ENTRY_IMPACT_CANDIDATE_ONLY"
    assert result["reason_code"] == "FIFO_PERIOD_SUMMARY_INVALID"
    assert "periods" not in result


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
