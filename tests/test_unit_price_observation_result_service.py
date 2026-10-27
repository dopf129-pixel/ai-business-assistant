from copy import deepcopy

from services.planning_workspace_repository import PlanningWorkspaceRepository
from services.tax_service import TaxService
from services.unit_price_observation_normalizer import UnitPriceObservationNormalizer
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
    assert result["completeness"]["tariff"] == "MANUAL_ASSUMPTION"
    assert any("OTHER_ADVERTISING_TYPES_ARE_UNKNOWN" in item for item in result["warnings"])
    assert PlanningWorkspaceRepository._normalize_unit_price_observation_result(result) is not None


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
