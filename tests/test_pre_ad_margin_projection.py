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
            "included_expense_keys": [
                "ACQUIRING",
                "COGS",
                "EXTRA_SERVICE",
                "LAST_MILE",
                "LOGISTICS",
                "OZON_COMMISSION",
            ],
            "confirmed_zero_expense_keys": [],
            "unknown_non_ad_expense_keys": [
                "CROSS_DOCKING",
                "PLACEMENT",
                "RETURNS_AND_CANCELLATIONS",
                "STORAGE",
                "UNMAPPED_NON_AD_EXPENSES",
            ],
            "excluded_expense_keys": ["ADVERTISING", "FIXED_STORE_OVERHEAD"],
            "excluded_expense_reasons": {
                "ADVERTISING": "EXCLUDED_BY_DEFINITION",
                "FIXED_STORE_OVERHEAD": "OUTSIDE_SKU_CONTRIBUTION_SCOPE",
            },
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
    assert result["advertising_tax_bridge"]["status"] == "UNAVAILABLE"
    assert result["advertising_tax_bridge"]["tax_before_ad_rub"] == 4.5
    assert result["advertising_tax_bridge"]["reason"] == "AFTER_AD_SCENARIO_UNAVAILABLE"
    assert result["pre_ad_margin"]["revenue_basis"] == "SELLER_REVENUE_BEFORE_DISCOUNT_POINTS"
    assert result["pre_ad_margin"]["price_per_unit_rub"] == 100.0


def test_pre_ad_projection_is_invariant_across_ad_modes_zero_unknown_and_invalid_credit():
    service = UnitPriceScenarioService(TaxService())
    base = _inputs(tax_mode="USN_INCOME", discount_points_rate="25")
    cases = {}

    percent_zero = dict(base, advertising_rate="0")
    cases["percent_zero"] = service.calculate(percent_zero)

    percent_twelve = dict(base, advertising_rate="12")
    cases["percent_twelve"] = service.calculate(percent_twelve)

    absolute_zero = dict(base)
    absolute_zero.pop("advertising_rate")
    absolute_zero.update({
        "advertising_mode": "ABSOLUTE_PER_SUCCESSFUL_UNIT",
        "advertising_cost_per_unit": "0",
    })
    cases["absolute_zero"] = service.calculate(absolute_zero)

    absolute_over_price = dict(base)
    absolute_over_price.pop("advertising_rate")
    absolute_over_price.update({
        "advertising_mode": "ABSOLUTE_PER_SUCCESSFUL_UNIT",
        "advertising_cost_per_unit": "120",
    })
    cases["absolute_over_price"] = service.calculate(absolute_over_price)

    unknown = dict(base)
    unknown.pop("advertising_rate")
    cases["unknown"] = service.calculate(unknown)

    invalid_negative = dict(base)
    invalid_negative.pop("advertising_rate")
    invalid_negative.update({
        "advertising_mode": "ABSOLUTE_PER_SUCCESSFUL_UNIT",
        "advertising_cost_per_unit": "-5",
    })
    cases["invalid_negative"] = service.calculate(invalid_negative)

    before_values = {
        (
            result["pre_ad_margin"]["profit_per_unit_rub"],
            result["pre_ad_margin"]["margin_percent"],
            result["pre_ad_margin"]["tax_per_unit_rub"],
        )
        for result in cases.values()
    }
    assert len(before_values) == 1
    assert cases["percent_zero"]["available"] is True
    assert cases["percent_zero"]["calculated"]["advertising"] == 0.0
    assert cases["absolute_zero"]["available"] is True
    assert cases["absolute_zero"]["calculated"]["advertising"] == 0.0
    assert cases["percent_twelve"]["calculated"]["advertising"] == 12.0
    assert cases["absolute_over_price"]["calculated"]["advertising"] == 120.0
    assert cases["unknown"]["available"] is False
    assert cases["unknown"]["pre_ad_margin"]["status"] == "AVAILABLE"
    assert cases["invalid_negative"]["available"] is False
    assert cases["invalid_negative"]["pre_ad_margin"]["status"] == "AVAILABLE"
    assert "advertising_cost_per_unit" in cases["invalid_negative"]["invalid_inputs"]
    components_only = service.calculate_components_only(invalid_negative)
    assert components_only["available"] is False
    assert components_only["calculated"]["profit_before_tax"] is None
    assert components_only["calculated"]["pre_ad_profit_before_tax"] == 41.0


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
    bridge = result["advertising_tax_bridge"]
    assert bridge["status"] == "AVAILABLE"
    assert bridge["tax_before_ad_rub"] == 5.7
    assert bridge["tax_after_ad_rub"] == 3.9
    assert bridge["advertising_per_unit_rub"] == 12.0
    assert bridge["tax_effect_of_advertising_rub"] == 1.8
    assert bridge["expected_profit_after_ad_rub"] == 22.1
    assert bridge["reconciliation_delta_rub"] == 0.0


def test_usn_income_bridge_uses_equal_tax_bases_and_reconciles_profit():
    result = UnitPriceScenarioService(TaxService()).calculate(
        _inputs(),
        extended_scenario=_additional_expense_contract(),
    )

    bridge = result["advertising_tax_bridge"]
    assert bridge["status"] == "AVAILABLE"
    assert bridge["tax_before_ad_rub"] == 4.5
    assert bridge["tax_after_ad_rub"] == 4.5
    assert bridge["advertising_per_unit_rub"] == 12.0
    assert bridge["tax_effect_of_advertising_rub"] == 0.0
    assert bridge["profit_before_ad_rub"] == 33.5
    assert bridge["profit_after_ad_rub"] == 21.5
    assert bridge["expected_profit_after_ad_rub"] == 21.5
    assert bridge["reconciliation_delta_rub"] == 0.0


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
    assert result["advertising_tax_bridge"]["status"] == "AVAILABLE"
    assert result["advertising_tax_bridge"]["advertising_per_unit_rub"] == 120.0
    assert result["advertising_tax_bridge"]["reconciliation_delta_rub"] == 0.0


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


def test_complete_zero_storage_evidence_is_not_reported_as_unknown():
    contract = _additional_expense_contract()
    contract["included_component_keys"] = ["FINANCE_PAID_STORAGE"]
    contract["components"] = [{
        "component_key": "FINANCE_PAID_STORAGE",
        "numerator_rub": "0.00",
        "ownership": "ADDITIONAL",
    }]
    inputs = _inputs()
    inputs.pop("advertising_rate")

    result = UnitPriceScenarioService(TaxService()).calculate(
        inputs,
        extended_scenario=contract,
    )

    scope = result["pre_ad_margin"]["expense_scope"]
    assert result["pre_ad_margin"]["status"] == "AVAILABLE"
    assert scope["status"] == "PARTIAL"
    assert "STORAGE" in scope["included_expense_keys"]
    assert scope["confirmed_zero_expense_keys"] == ["STORAGE"]
    assert scope["known_non_ad_expenses_rub"]["STORAGE"] == 0.0
    assert "CONFIRMED_ADDITIONAL_EXPENSES" not in scope["known_non_ad_expenses_rub"]
    assert "STORAGE" not in scope["unknown_non_ad_expense_keys"]
    assert "RETURNS_AND_CANCELLATIONS" in scope["unknown_non_ad_expense_keys"]


def test_explicitly_excluded_storage_is_not_mislabeled_as_zero_or_unknown():
    contract = _additional_expense_contract()
    contract["excluded_component_statuses"] = {"STORAGE": "EXCLUDED"}
    inputs = _inputs()
    inputs.pop("advertising_rate")

    result = UnitPriceScenarioService(TaxService()).calculate(
        inputs,
        extended_scenario=contract,
    )

    scope = result["pre_ad_margin"]["expense_scope"]
    assert "STORAGE" in scope["excluded_expense_keys"]
    assert scope["excluded_expense_reasons"]["STORAGE"] == "EXPLICITLY_EXCLUDED_BY_SOURCE_SCOPE"
    assert "STORAGE" not in scope["confirmed_zero_expense_keys"]
    assert "STORAGE" not in scope["unknown_non_ad_expense_keys"]


def test_zero_price_has_no_pre_ad_profit_percentage_instead_of_fabricated_zero():
    inputs = _inputs(price="0")
    inputs.pop("advertising_rate")

    result = UnitPriceScenarioService(TaxService()).calculate(inputs)

    assert result["pre_ad_margin"]["status"] == "UNAVAILABLE"
    assert result["pre_ad_margin"]["price_per_unit_rub"] is None
    assert result["pre_ad_margin"]["profit_per_unit_rub"] is None
    assert result["pre_ad_margin"]["margin_percent"] is None
    assert result["pre_ad_margin"]["reason"] == "NO_AD_INPUTS_INVALID"


def test_negative_and_out_of_range_prices_are_rejected_by_existing_bounds():
    service = UnitPriceScenarioService(TaxService())

    for price in ("-1", "10000000000000"):
        inputs = _inputs(price=price)
        inputs.pop("advertising_rate")
        result = service.calculate(inputs)

        assert result["pre_ad_margin"]["status"] == "UNAVAILABLE"
        assert result["pre_ad_margin"]["price_per_unit_rub"] is None
        assert result["pre_ad_margin"]["profit_per_unit_rub"] is None
        assert result["pre_ad_margin"]["margin_percent"] is None
        assert result["pre_ad_margin"]["invalid_inputs"] == ["price"]


def test_confirmed_zero_expenses_are_not_treated_as_missing():
    inputs = _inputs(
        cost="0",
        commission_rate="0",
        logistics_per_unit="0",
        last_mile_per_unit="0",
        acquiring_per_unit="0",
        discount_points_rate="0",
        tax_mode="NONE",
    )
    inputs.pop("advertising_rate")

    result = UnitPriceScenarioService(TaxService()).calculate(inputs)

    assert result["pre_ad_margin"]["status"] == "AVAILABLE"
    assert result["pre_ad_margin"]["profit_per_unit_rub"] == 100.0
    assert result["pre_ad_margin"]["margin_percent"] == 100.0
    assert result["pre_ad_margin"]["missing_inputs"] == []
    assert result["pre_ad_margin"]["invalid_inputs"] == []


def test_negative_pre_ad_profit_and_margin_are_preserved_without_clipping():
    inputs = _inputs(
        cost="76",
        discount_points_rate="0",
        tax_mode="NONE",
    )
    inputs.pop("advertising_rate")

    result = UnitPriceScenarioService(TaxService()).calculate(inputs)

    assert result["pre_ad_margin"]["status"] == "AVAILABLE"
    assert result["pre_ad_margin"]["profit_per_unit_rub"] == -5.0
    assert result["pre_ad_margin"]["margin_percent"] == -5.0


def test_discount_points_do_not_reduce_pre_ad_seller_revenue_denominator_or_profit_before_tax():
    service = UnitPriceScenarioService(TaxService())
    without_points = _inputs(tax_mode="NONE", discount_points_rate="0")
    with_points = _inputs(tax_mode="NONE", discount_points_rate="25")
    without_points.pop("advertising_rate")
    with_points.pop("advertising_rate")

    zero_points_result = service.calculate(without_points)
    points_result = service.calculate(with_points)

    assert zero_points_result["pre_ad_margin"]["profit_per_unit_rub"] == 41.0
    assert points_result["pre_ad_margin"]["profit_per_unit_rub"] == 41.0
    assert zero_points_result["pre_ad_margin"]["margin_percent"] == 41.0
    assert points_result["pre_ad_margin"]["margin_percent"] == 41.0
    assert points_result["pre_ad_margin"]["price_per_unit_rub"] == 100.0
    assert points_result["pre_ad_margin"]["revenue_basis"] == "SELLER_REVENUE_BEFORE_DISCOUNT_POINTS"


def test_discount_points_reduce_usn_tax_basis_but_margin_percentage_uses_seller_price():
    service = UnitPriceScenarioService(TaxService())
    without_points = _inputs(tax_mode="USN_INCOME", discount_points_rate="0")
    with_points = _inputs(tax_mode="USN_INCOME", discount_points_rate="25")
    without_points.pop("advertising_rate")
    with_points.pop("advertising_rate")

    zero_points_result = service.calculate(without_points)
    points_result = service.calculate(with_points)

    assert zero_points_result["pre_ad_margin"]["tax_per_unit_rub"] == 6.0
    assert points_result["pre_ad_margin"]["tax_per_unit_rub"] == 4.5
    assert zero_points_result["pre_ad_margin"]["profit_per_unit_rub"] == 35.0
    assert points_result["pre_ad_margin"]["profit_per_unit_rub"] == 36.5
    assert points_result["pre_ad_margin"]["price_per_unit_rub"] == 100.0
    assert points_result["pre_ad_margin"]["margin_percent"] == 36.5
    assert points_result["pre_ad_margin"]["revenue_basis"] == "SELLER_REVENUE_BEFORE_DISCOUNT_POINTS"


def test_money_rounding_remains_canonical_at_half_cent_boundary():
    inputs = _inputs(
        cost="30.005",
        tax_mode="NONE",
        discount_points_rate="0",
    )
    inputs.pop("advertising_rate")

    result = UnitPriceScenarioService(TaxService()).calculate(inputs)

    assert result["pre_ad_margin"]["status"] == "AVAILABLE"
    assert result["pre_ad_margin"]["profit_per_unit_rub"] == 41.0
    assert result["pre_ad_margin"]["margin_percent"] == 41.0


def test_components_only_exposes_separate_pre_ad_contribution_without_changing_legacy_field():
    inputs = _inputs()
    inputs.pop("advertising_rate")

    result = UnitPriceScenarioService(TaxService()).calculate_components_only(inputs)

    assert result["available"] is False
    assert result["calculated"]["profit_before_tax"] is None
    assert result["calculated"]["pre_ad_profit_before_tax"] == 41.0


def test_components_only_keeps_aggregate_tax_calculation_outside_per_sku_loop():
    class TaxSpy:
        SUPPORTED_MODES = TaxService.SUPPORTED_MODES

        def __init__(self):
            self.calls = []

        def calculate(self, **kwargs):
            self.calls.append(dict(kwargs))
            return TaxService().calculate(**kwargs)

    tax = TaxSpy()
    inputs = _inputs()
    inputs.pop("advertising_rate")

    result = UnitPriceScenarioService(tax).calculate_components_only(inputs)

    assert result["calculated"]["pre_ad_profit_before_tax"] == 41.0
    assert tax.calls == []
