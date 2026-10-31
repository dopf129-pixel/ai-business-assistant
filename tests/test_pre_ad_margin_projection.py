from copy import deepcopy

from services.tax_service import TaxService
from services.unit_price_scenario_service import UnitPriceScenarioService


def _inputs(**overrides):
    values = {
        "price": "100",
        "cost": "30",
        "commission_rate": "14",
        "logistics_per_unit": "10",
        "last_mile_per_unit": "3",
        "acquiring_per_unit": "2",
        "discount_points_rate": "25",
        "tax_mode": "USN_INCOME",
        "tax_rate": "6",
        "minimum_tax_rate": "1",
        "advertising_mode": "PERCENT_OF_SELLER_REVENUE",
        "advertising_rate": "12",
    }
    values.update(overrides)
    return values


def _additional_expense_contract():
    return {
        "schema_version": 1,
        "calculation_mode": "WINDOW_COST_ALLOCATION",
        "expense_snapshot_ref": "a" * 64,
        "quantity_evidence_ref": "b" * 64,
        "expense_policy_revision": "unit-economics-v1",
        "included_component_keys": ["EXTRA_SERVICE"],
        "excluded_component_statuses": {},
        "numerator_and_denominator_basis": {
            "numerator": "WINDOW_EXPENSE_RUB",
            "denominator": "SOLD_UNITS_WINDOW",
        },
        "source_completeness": "COMPLETE",
        "assumed_inputs": [],
        "scope": {
            "scope_kind": "REFERENCE_56_COMPLETED_LOCAL_DAYS",
            "from_date": "2026-01-01",
            "to_date": "2026-02-25",
            "date_basis": "LOCAL_CALENDAR_DAY",
            "timezone": "Europe/Moscow",
        },
        "denominator_units": 100,
        "components": [{
            "component_key": "EXTRA_SERVICE",
            "numerator_rub": "300.00",
            "ownership": "ADDITIONAL",
        }],
    }


def test_pre_ad_scenario_is_available_when_advertising_is_unknown_and_does_not_mutate_inputs():
    inputs = _inputs()
    inputs.pop("advertising_rate")
    original = deepcopy(inputs)

    result = UnitPriceScenarioService(TaxService()).calculate(
        inputs,
        extended_scenario=_additional_expense_contract(),
    )

    assert inputs == original
    assert result["available"] is False
    assert result["calculated"]["profit"] is None
    assert result["pre_ad_margin"] == {
        "schema_version": 1,
        "basis": "PRICE_SCENARIO_NO_AD",
        "tax_basis": "NO_ADVERTISING_SCENARIO",
        "revenue_basis": "SELLER_REVENUE_BEFORE_DISCOUNT_POINTS",
        "currency": "RUB",
        "unit_basis": "ONE_SUCCESSFUL_UNIT",
        "status": "AVAILABLE",
        "price_per_unit_rub": 100.0,
        "profit_per_unit_rub": 33.5,
        "margin_percent": 33.5,
        "tax_per_unit_rub": 4.5,
        "advertising_status": "EXCLUDED_BY_DEFINITION",
        "expense_scope": {
            "status": "PARTIAL",
            "known_non_ad_expenses_rub": {
                "ACQUIRING": 2.0,
                "CONFIRMED_ADDITIONAL_EXPENSES": 3.0,
                "COGS": 30.0,
                "LAST_MILE": 3.0,
                "LOGISTICS": 10.0,
                "OZON_COMMISSION": 14.0,
            },
            "unknown_non_ad_expense_keys": [
                "CROSS_DOCKING",
                "FIXED_STORE_OVERHEAD",
                "RETURNS_AND_CANCELLATIONS",
                "STORAGE",
                "UNMAPPED_NON_AD_EXPENSES",
            ],
            "excluded_expense_keys": ["ADVERTISING"],
        },
        "missing_inputs": [],
        "invalid_inputs": [],
        "source_periods": {},
        "as_of": None,
        "read_only": True,
        "executed": False,
        "reason": "UNMODELED_NON_AD_EXPENSES",
    }
    assert "advertising_rate" in result["missing_inputs"]
    assert result["inputs"]["advertising_rate"]["value"] is None


def test_pre_ad_and_after_ad_tax_bases_are_calculated_separately_for_profit_tax():
    inputs = _inputs(
        discount_points_rate="0",
        tax_mode="USN_INCOME_MINUS_EXPENSES",
        tax_rate="15",
    )

    result = UnitPriceScenarioService(TaxService()).calculate(
        inputs,
        extended_scenario=_additional_expense_contract(),
    )

    assert result["calculated"]["profit_before_tax"] == 26.0
    assert result["calculated"]["tax"] == 3.9
    assert result["calculated"]["profit"] == 22.1
    assert result["pre_ad_margin"]["profit_per_unit_rub"] == 32.3
    assert result["pre_ad_margin"]["tax_per_unit_rub"] == 5.7
    assert result["pre_ad_margin"]["margin_percent"] == 32.3
    assert result["pre_ad_margin"]["tax_basis"] == "NO_ADVERTISING_SCENARIO"


def test_absolute_advertising_above_price_does_not_block_pre_ad_projection():
    inputs = _inputs()
    inputs.pop("advertising_rate")
    inputs.update({
        "advertising_mode": "ABSOLUTE_PER_SUCCESSFUL_UNIT",
        "advertising_cost_per_unit": "120",
        "tax_mode": "NONE",
        "discount_points_rate": "0",
    })

    result = UnitPriceScenarioService(TaxService()).calculate(inputs)

    assert result["available"] is True
    assert result["calculated"]["profit"] == -79.0
    assert result["pre_ad_margin"]["profit_per_unit_rub"] == 41.0
    assert result["pre_ad_margin"]["margin_percent"] == 41.0


def test_no_tax_mode_keeps_pre_ad_available():
    inputs = _inputs(
        tax_mode="NONE",
        discount_points_rate="0",
    )
    inputs.pop("advertising_rate")

    result = UnitPriceScenarioService(TaxService()).calculate(inputs)

    assert result["pre_ad_margin"]["status"] == "AVAILABLE"
    assert result["pre_ad_margin"]["tax_per_unit_rub"] == 0.0
    assert result["pre_ad_margin"]["profit_per_unit_rub"] == 41.0


def test_pre_ad_projection_is_unavailable_when_a_required_non_ad_input_is_missing():
    inputs = _inputs(cost=None)
    inputs.pop("advertising_rate")

    result = UnitPriceScenarioService(TaxService()).calculate(inputs)

    assert result["pre_ad_margin"]["status"] == "UNAVAILABLE"
    assert result["pre_ad_margin"]["reason"] == "NO_AD_REQUIRED_INPUTS_MISSING"
    assert result["pre_ad_margin"]["profit_per_unit_rub"] is None
    assert result["pre_ad_margin"]["missing_inputs"] == ["cost"]


def test_components_only_exposes_separate_pre_ad_contribution_without_changing_legacy_field():
    inputs = _inputs()
    inputs.pop("advertising_rate")

    result = UnitPriceScenarioService(TaxService()).calculate_components_only(inputs)

    assert result["available"] is False
    assert result["calculated"]["profit_before_tax"] is None
    assert result["calculated"]["pre_ad_profit_before_tax"] == 41.0
