from copy import deepcopy
from datetime import datetime, timezone

import pytest

from services.planning_workspace_repository import PlanningWorkspaceRepository
from services.tax_service import TaxService
from services.unit_price_observation_normalizer import UnitPriceObservationNormalizer
from services.unit_price_observation_quality_service import UnitPriceObservationQualityService
from services.unit_price_observation_result_service import UnitPriceObservationResultService
from services.unit_price_scenario_service import UnitPriceScenarioService
from services.unit_price_target_planning_service import UnitPriceTargetPlanningService


_IDENTITY = {
    "store_id": "store-a", "product_id": "product-1",
    "offer_id": "offer-1", "sku": "sku-1", "sale_schema": "FBO",
}
_SCENARIO_IDENTITY = {
    "store_id": "store-a", "product_id": "product-1",
    "offer_id": "offer-1", "sku": "sku-1", "scheme": "FBO",
}


def _inputs(**overrides):
    values = {
        "price": "100.00", "cost": "20.00", "commission_rate": "10",
        "logistics_per_unit": "2.00", "last_mile_per_unit": "3.00",
        "acquiring_per_unit": "1.00", "advertising_rate": "0",
        "discount_points_rate": "0", "tax_mode": "NONE",
    }
    values.update(overrides)
    return values


def _evidence(*, units=4, performance_basis="SHARED_LOCAL_SALE_DATE", mixed=False):
    window = {
        "from": "2026-10-01", "to": "2026-10-07",
        "timezone": "Europe/Moscow", "date_basis": "SOURCE_CALENDAR_DATE",
    }
    sources = [
        {
            "name": "FINANCE", "status": "COMPLETE", "complete": True,
            "row_count": 7, "source_date_basis": "SHARED_LOCAL_SALE_DATE",
            "source_window_start": window["from"], "source_window_end": window["to"],
            "timezone": window["timezone"],
        },
        {
            "name": "ANALYTICS", "status": "COMPLETE", "complete": True,
            "row_count": 7, "source_date_basis": "SHARED_LOCAL_SALE_DATE",
            "source_window_start": window["from"], "source_window_end": window["to"],
            "timezone": window["timezone"],
        },
        {
            "name": "PERFORMANCE", "status": "COMPLETE", "complete": True,
            "row_count": 7, "source_date_basis": performance_basis,
            "source_window_start": window["from"], "source_window_end": window["to"],
            "timezone": window["timezone"],
        },
    ]
    raw = {
        "error": False, "status": "AVAILABLE", "identity": deepcopy(_IDENTITY),
        "seller_price_cents": 10_000, "window": window, "sources": sources,
        "metrics": {
            "gross_seller_revenue": "400.00", "discount_points": "0.00",
            "discount_points_complete": True, "finance_net": "250.00",
            "acquiring": "-4.00", "commission": "-40.00",
            "logistics": "-60.00", "other_fees": "-42.00", "cpc_spend": "12.00",
            "source_row_count": 7, "sample_days": 7,
            "successful_sale_units": units,
        },
        "warnings": [],
    }
    if mixed:
        raw["metrics"]["price_evidence_status"] = "MIXED_PRICES"
    result = UnitPriceObservationNormalizer.normalize_collected(raw)
    result["metrics"]["successful_sale_units"] = units
    result["metrics"]["successful_unit_denominator"] = units
    result["completeness"]["successful_units"] = "CONFIRMED"
    return result


def _service():
    scenario = UnitPriceScenarioService(TaxService())
    planner = UnitPriceTargetPlanningService(scenario)
    return UnitPriceObservationResultService(scenario, planner)


def _extended_cost_contract(*, assumed_inputs=(), amount="7.00", ref="a"):
    return {
        "schema_version": 1, "calculation_mode": "WINDOW_COST_ALLOCATION",
        "expense_snapshot_ref": ref * 64, "quantity_evidence_ref": None,
        "expense_policy_revision": "expense-policy-v1",
        "included_component_keys": ["CROSS_DOCKING"],
        "excluded_component_statuses": {},
        "numerator_and_denominator_basis": {
            "numerator": "WINDOW_EXPENSE_RUB", "denominator": "SOLD_UNITS_WINDOW",
        },
        "source_completeness": "COMPLETE", "assumed_inputs": list(assumed_inputs),
        "scope": {
            "scope_kind": "REFERENCE_56_COMPLETED_LOCAL_DAYS",
            "from_date": "2026-08-01", "to_date": "2026-09-25",
            "date_basis": "LOCAL_CALENDAR_DAY", "timezone": "Europe/Moscow",
        },
        "denominator_units": 10,
        "components": [{
            "component_key": "CROSS_DOCKING", "numerator_rub": amount,
            "ownership": "ADDITIONAL",
        }],
    }


def test_complete_compatible_evidence_builds_only_an_explicit_cpc_model():
    evidence = _evidence()
    # A caller cannot promote the source aggregates by adding an untrusted label.
    evidence["evidence_basis"] = "CANONICAL_FACT_COMPARABLE"

    result = _service().evaluate(
        evidence, scenario_inputs=_inputs(), identity=_SCENARIO_IDENTITY,
        provenance={"cost": "manual_owner_input", "commission_rate": "manual_owner_input"},
    )

    assert result["status"] == "AVAILABLE"
    assert result["evidence_basis"] == "MODELLED_FROM_OBSERVED_INPUTS"
    canonical = UnitPriceScenarioService(TaxService()).calculate(
        _inputs(advertising_rate="3"), identity=_SCENARIO_IDENTITY,
    )
    assert canonical["available"] is True
    assert result["metrics"]["profit_per_unit"] == f"{canonical['calculated']['profit']:.2f}"
    assert result["metrics"]["scenario_profit_per_unit"] == "61.00"
    assert result["metrics"]["observed_profit_per_unit"] is None
    assert result["metrics"]["weighted_ad_spend_numerator"] == "12.00"
    assert result["metrics"]["successful_unit_denominator"] == 4
    assert result["metrics"]["advertising_status"] == "CPC_ONLY_MODEL"
    assert result["metrics"]["tariff_status"] == "MANUAL_ASSUMPTION"
    assert result["completeness"]["tariff"] == "MANUAL_ASSUMPTION"
    assert any("OTHER_ADVERTISING_TYPES_ARE_UNKNOWN" in item for item in result["warnings"])
    assert PlanningWorkspaceRepository._normalize_unit_price_observation_result(result) is not None


def test_absolute_advertising_plan_uses_absolute_observed_cpc_cost():
    inputs = _inputs()
    inputs.pop("advertising_rate")
    inputs.update({
        "advertising_mode": "ABSOLUTE_PER_SUCCESSFUL_UNIT",
        "advertising_cost_per_unit": "3.00",
    })

    result = _service().evaluate(
        _evidence(), scenario_inputs=inputs, identity=_SCENARIO_IDENTITY,
    )

    assert result["status"] == "AVAILABLE"
    assert result["metrics"]["scenario_profit_per_unit"] == "61.00"
    assert result["metrics"]["advertising_status"] == "CPC_ONLY_MODEL"
    assert PlanningWorkspaceRepository._normalize_unit_price_observation_result(result) is not None


def test_confirmed_tariff_provenance_is_preserved_in_result_completeness():
    result = _service().evaluate(
        _evidence(), scenario_inputs=_inputs(), identity=_SCENARIO_IDENTITY,
        provenance={
            "cost": "manual_owner_input",
            "commission_rate": "confirmed_official_source",
        },
    )

    assert result["status"] == "AVAILABLE"
    assert result["metrics"]["tariff_status"] == "CONFIRMED"
    assert result["completeness"]["tariff"] == "CONFIRMED"


def test_extended_cost_basis_is_applied_and_origin_is_recorded_in_result():
    contract = _extended_cost_contract()
    result = _service().evaluate(
        _evidence(), scenario_inputs=_inputs(), identity=_SCENARIO_IDENTITY,
        provenance={"cost": "manual_owner_input", "commission_rate": "manual_owner_input"},
        extended_scenario=contract,
    )

    assert result["status"] == "AVAILABLE"
    assert result["metrics"]["extended_cost_mode"] == "WINDOW_COST_ALLOCATION"
    assert result["metrics"]["extended_cost_origin"] == "CONFIRMED"
    assert result["metrics"]["extended_cost_per_unit"] == "0.70"
    assert len(result["metrics"]["extended_cost_signature"]) == 64
    assert PlanningWorkspaceRepository._normalize_unit_price_observation_result(result) is not None

    manual = _service().evaluate(
        _evidence(), scenario_inputs=_inputs(), identity=_SCENARIO_IDENTITY,
        provenance={"cost": "manual_owner_input", "commission_rate": "manual_owner_input"},
        extended_scenario=_extended_cost_contract(assumed_inputs=["OWNER_COST"]),
    )
    assert manual["metrics"]["extended_cost_origin"] == "MANUAL_ASSUMPTION"
    assert manual["metrics"]["extended_cost_signature"] != result["metrics"]["extended_cost_signature"]


def test_extended_cost_contract_failure_never_silently_drops_its_basis():
    contract = _extended_cost_contract()
    contract["expense_snapshot_ref"] = "invalid-reference"
    result = _service().evaluate(
        _evidence(), scenario_inputs=_inputs(), identity=_SCENARIO_IDENTITY,
        provenance={"cost": "manual_owner_input", "commission_rate": "manual_owner_input"},
        extended_scenario=contract,
    )

    assert result["status"] == "INSUFFICIENT_DATA"
    assert result["evidence_basis"] == "SCENARIO_ASSUMPTIONS"
    assert result["metrics"].get("profit_per_unit") is None


def test_strict_cohort_loss_basis_is_bound_to_exact_owner_sku_and_denominator():
    contract = _extended_cost_contract()
    contract.update({
        "calculation_mode": "STRICT_RETAINED_COHORT",
        "quantity_evidence_ref": "b" * 64,
        "numerator_and_denominator_basis": {
            "numerator": "STRICT_COHORT_LOSS_RUB",
            "denominator": "RETAINED_UNITS_EXACT_COHORT",
        },
        "scope": {
            "scope_kind": "EXPERIMENT_PHASE_WINDOW",
            "from_date": "2026-10-01", "to_date": "2026-10-07",
            "date_basis": "LOCAL_CALENDAR_DAY", "timezone": "Europe/Moscow",
        },
        "denominator_units": 100, "included_component_keys": [], "components": [],
    })
    identity = {**_SCENARIO_IDENTITY, "owner_id": "owner-a"}
    strict_evidence = {
        "error": False, "status": "COMPLETE",
        "identity": {
            "owner_id": "owner-a", "store_id": "store-a",
            "product_id": "product-1", "offer_id": "offer-1",
            "sku": "sku-1", "sale_schema": "FBO",
        },
        "fees": {"status": "COMPLETE", "cohort_matches": True,
                  "additional_exact_cohort_rub": "300.00"},
        "quantity": {"status": "COMPLETE", "cohort_matches": True,
                     "delivered_units": 110,
                     "confirmed_returned_units_from_deliveries": 10,
                     "retained_units": 100},
        "inventory": {"status": "COMPLETE", "disposition_units": 10,
                      "inventory_loss_cogs_rub": "60.00",
                      "compensation_deduction_rub": "10.00"},
        "strict_retained_cohort_loss": {
            "status": "AVAILABLE", "model_scope": "STRICT_RETAINED_COHORT",
            "denominator_kind": "RETAINED_UNITS_EXACT_COHORT",
            "denominator_units": 100, "fee_loss_pool_rub": "300.00",
            "loss_pool_rub": "350.00", "loss_per_retained_unit_rub": "3.50",
        },
        "read_only": True, "executed": False,
    }

    result = _service().evaluate(
        _evidence(), scenario_inputs=_inputs(), identity=identity,
        provenance={"cost": "manual_owner_input", "commission_rate": "manual_owner_input"},
        extended_scenario=contract, strict_return_evidence=strict_evidence,
    )

    assert result["status"] == "AVAILABLE"
    assert result["metrics"]["extended_cost_mode"] == "STRICT_RETAINED_COHORT"
    assert result["metrics"]["extended_cost_origin"] == "CONFIRMED"
    assert result["metrics"]["extended_cost_per_unit"] == "3.50"
    assert PlanningWorkspaceRepository._normalize_unit_price_observation_result(result) is not None


@pytest.mark.parametrize(
    "tariff_origin", ["confirmed_official_source", "current_price_point"],
)
def test_confirmed_tariff_result_remains_ready_in_model_quality_gate(tariff_origin):
    def candidate(price, start, end, commission_provenance):
        evidence = _evidence()
        evidence["seller_price_cents"] = price * 100
        evidence["window"].update({"from": start, "to": end})
        for source in evidence["sources"]:
            source.update({
                "source_window_start": start,
                "source_window_end": end,
                "received_at": "2026-10-27T09:00:00+00:00",
            })
        result = _service().evaluate(
            evidence,
            scenario_inputs=_inputs(price=f"{price:.2f}"),
            identity=_SCENARIO_IDENTITY,
            provenance={
                "cost": "manual_owner_input",
                "commission_rate": commission_provenance,
            },
        )
        assert result["status"] == "AVAILABLE"
        return {
            "owner_id": "owner-a", "store_id": "store-a",
            "result_revision": 1, "assumption_signature": "same-model-inputs",
            "result": result,
        }

    candidates = [
        candidate(100, "2026-10-01", "2026-10-07", tariff_origin),
        candidate(95, "2026-10-08", "2026-10-14", tariff_origin),
    ]
    quality = UnitPriceObservationQualityService().assess(
        candidates, now=datetime(2026, 10, 27, 10, 0, tzinfo=timezone.utc),
    )

    assert all(item["result"]["completeness"]["tariff"] == "CONFIRMED" for item in candidates)
    assert quality["status"] == "COMPARABLE"
    assert quality["verified"] is False
    assert all(item["status"] == "READY" for item in quality["candidates"])


def test_unknown_tariff_result_still_fails_model_quality_gate():
    def candidate(price, start, end, commission_provenance):
        evidence = _evidence()
        evidence["seller_price_cents"] = price * 100
        evidence["window"].update({"from": start, "to": end})
        for source in evidence["sources"]:
            source.update({
                "source_window_start": start,
                "source_window_end": end,
                "received_at": "2026-10-27T09:00:00+00:00",
            })
        result = _service().evaluate(
            evidence,
            scenario_inputs=_inputs(price=f"{price:.2f}"),
            identity=_SCENARIO_IDENTITY,
            provenance={
                "cost": "manual_owner_input",
                "commission_rate": commission_provenance,
            },
        )
        return {
            "owner_id": "owner-a", "store_id": "store-a",
            "result_revision": 1, "assumption_signature": "same-model-inputs",
            "result": result,
        }

    first = candidate(100, "2026-10-01", "2026-10-07", "unknown")
    second = candidate(95, "2026-10-08", "2026-10-14", "unknown")
    quality = UnitPriceObservationQualityService().assess(
        [first, second],
        now=datetime(2026, 10, 27, 10, 0, tzinfo=timezone.utc),
    )

    assert first["result"]["completeness"]["tariff"] == "UNKNOWN"
    assert quality["status"] == "INCOMPARABLE"
    assert "MODEL_TARIFF_BASIS_UNCONFIRMED" in quality["reasons"]


def test_missing_successful_unit_denominator_returns_incomplete_without_profit():
    evidence = _evidence(units=None)
    evidence["metrics"]["successful_unit_denominator"] = None
    evidence["completeness"]["successful_units"] = "UNKNOWN"

    result = _service().evaluate(
        evidence, scenario_inputs=_inputs(), identity=_SCENARIO_IDENTITY,
    )

    assert result["status"] == "INSUFFICIENT_DATA"
    assert result["evidence_basis"] == "SCENARIO_ASSUMPTIONS"
    assert result["metrics"]["observed_profit_per_unit"] is None
    assert "profit_per_unit" not in result["metrics"]
    assert "SUCCESSFUL_UNIT_DENOMINATOR_UNCONFIRMED" in result["reasons"]


def test_mismatched_source_date_basis_blocks_the_model():
    result = _service().evaluate(
        _evidence(performance_basis="PERFORMANCE_REPORT_DATE"),
        scenario_inputs=_inputs(), identity=_SCENARIO_IDENTITY,
    )

    assert result["status"] == "INCOMPARABLE"
    assert "CPC_AND_SUCCESSFUL_UNITS_USE_DIFFERENT_DATE_BASES" in result["reasons"]
    assert "profit_per_unit" not in result["metrics"]


def test_complete_fbo_buyout_cohort_allows_explicit_model_with_date_basis_warning():
    evidence = _evidence(performance_basis="PERFORMANCE_REPORT_DATE")
    evidence["sources"].append({
        "name": "RETURNS", "status": "COMPLETE", "complete": True,
        "row_count": 4, "source_date_basis": "FBO_POSTING_AND_RETURN_CHANGE_WINDOW",
        "source_window_start": evidence["window"]["from"],
        "source_window_end": evidence["window"]["to"],
        "timezone": evidence["window"]["timezone"],
    })
    evidence["metrics"].update({
        "ordered_units": 4, "delivered_units": 3, "cancelled_units": 1,
        "successful_sale_units": 3, "successful_unit_denominator": 3,
        "returned_units": 1, "buyout_rate_percent": "75.00",
        "buyout_sample_size": 4,
    })
    evidence["completeness"]["returns"] = "CONFIRMED"

    result = _service().evaluate(
        evidence, scenario_inputs=_inputs(), identity=_SCENARIO_IDENTITY,
    )

    assert result["status"] == "AVAILABLE"
    assert result["evidence_basis"] == "MODELLED_FROM_OBSERVED_INPUTS"
    assert result["metrics"]["successful_sale_units"] == 3
    assert result["metrics"]["buyout_rate_percent"] == "75.00"
    assert result["metrics"]["observed_profit_per_unit"] is None
    assert any("FBO_BUYOUT_RATE_IS_A_WINDOW_ESTIMATE" in item for item in result["warnings"])
    assert any("RETURN_COSTS_ARE_NOT_NETTED" in item for item in result["warnings"])
    assert any("CPC_REPORT_DATE_AND_FBO_POSTING_COHORT" in item for item in result["warnings"])


def test_incomplete_fbo_buyout_source_cannot_override_date_basis_gate():
    evidence = _evidence(performance_basis="PERFORMANCE_REPORT_DATE")
    evidence["sources"].append({
        "name": "RETURNS", "status": "PARTIAL", "complete": False,
        "row_count": 4, "source_date_basis": "FBO_POSTING_AND_RETURN_CHANGE_WINDOW",
        "source_window_start": evidence["window"]["from"],
        "source_window_end": evidence["window"]["to"],
        "timezone": evidence["window"]["timezone"],
    })

    result = _service().evaluate(
        evidence, scenario_inputs=_inputs(), identity=_SCENARIO_IDENTITY,
    )

    assert result["status"] == "INCOMPARABLE"
    assert "CPC_AND_SUCCESSFUL_UNITS_USE_DIFFERENT_DATE_BASES" in result["reasons"]
    assert "profit_per_unit" not in result["metrics"]


def test_mixed_price_window_blocks_a_single_price_model():
    result = _service().evaluate(
        _evidence(mixed=True), scenario_inputs=_inputs(), identity=_SCENARIO_IDENTITY,
    )

    assert result["status"] == "INCOMPARABLE"
    assert "PRICE_WINDOW_IS_MIXED" in result["reasons"]
    assert "profit_per_unit" not in result["metrics"]


def test_scenario_sku_or_seller_price_mismatch_blocks_modeling():
    wrong_identity = {**_SCENARIO_IDENTITY, "sku": "another-sku"}
    identity_result = _service().evaluate(
        _evidence(), scenario_inputs=_inputs(), identity=wrong_identity,
    )
    price_result = _service().evaluate(
        _evidence(), scenario_inputs=_inputs(price="99.99"), identity=_SCENARIO_IDENTITY,
    )

    assert identity_result["status"] == "INCOMPARABLE"
    assert "SCENARIO_IDENTITY_DOES_NOT_MATCH_OBSERVATION" in identity_result["reasons"]
    assert price_result["status"] == "INCOMPARABLE"
    assert "FROZEN_SCENARIO_SELLER_PRICE_DOES_NOT_MATCH_OBSERVATION" in price_result["reasons"]
