from services.tax_service import TaxService
from services.unit_price_scenario_service import UnitPriceScenarioService


def _inputs(**overrides):
    values = {
        "price": "100",
        "cost": "20",
        "commission_rate": "10",
        "logistics_per_unit": "5",
        "last_mile_per_unit": "1",
        "acquiring_per_unit": "1",
        "advertising_rate": "12",
        "discount_points_rate": "0",
        "tax_mode": "NONE",
        "tax_rate": None,
        "minimum_tax_rate": None,
    }
    values.update(overrides)
    return values


def _contract(*, components=None, keys=None, units=100, completeness="COMPLETE", mode="WINDOW_COST_ALLOCATION"):
    components = components if components is not None else [
        {"component_key": "EXTRA_SERVICE", "numerator_rub": "500.00", "ownership": "ADDITIONAL"},
    ]
    component_keys = [item["component_key"] for item in components]
    if keys is None:
        keys = sorted(component_keys)
    return {
        "schema_version": 1,
        "calculation_mode": mode,
        "expense_snapshot_ref": "a" * 64,
        "quantity_evidence_ref": "b" * 64,
        "expense_policy_revision": "unit-economics-v1",
        "included_component_keys": keys,
        "excluded_component_statuses": {},
        "numerator_and_denominator_basis": {
            "numerator": "WINDOW_EXPENSE_RUB" if mode == "WINDOW_COST_ALLOCATION" else "STRICT_COHORT_LOSS_RUB",
            "denominator": "SOLD_UNITS_WINDOW" if mode == "WINDOW_COST_ALLOCATION" else "RETAINED_UNITS_EXACT_COHORT",
        },
        "source_completeness": completeness,
        "assumed_inputs": [],
        "scope": {
            "scope_kind": "REFERENCE_56_COMPLETED_LOCAL_DAYS",
            "from_date": "2026-01-01",
            "to_date": "2026-02-25",
            "date_basis": "LOCAL_CALENDAR_DAY",
            "timezone": "Europe/Moscow",
        },
        "denominator_units": units,
        "components": components,
    }


class _TaxSpy:
    SUPPORTED_MODES = TaxService.SUPPORTED_MODES

    def __init__(self):
        self.calls = []
        self._service = TaxService()

    def calculate(self, **kwargs):
        self.calls.append(dict(kwargs))
        return self._service.calculate(**kwargs)


def test_legacy_calculation_is_identical_when_extended_contract_is_absent():
    service = UnitPriceScenarioService(TaxService())
    inputs = _inputs()
    identity = {"scenario_id": "scenario-test"}
    assert service.calculate(inputs, identity=identity) == service.calculate(
        inputs, identity=identity, extended_scenario=None,
    )
    assert "extended_calculation" not in service.calculate(inputs)
    assert "additional_unit_expenses" not in service.calculate(inputs)["calculated"]


def test_extended_evidence_is_not_marked_applied_when_base_scenario_is_unavailable():
    result = UnitPriceScenarioService(TaxService()).calculate(
        _inputs(price=None), extended_scenario=_contract(),
    )
    assert result["available"] is False
    assert result["extended_calculation"]["status"] == "UNAVAILABLE"


def test_n01_applies_additional_window_expense_before_tax_exactly_once():
    tax = _TaxSpy()
    service = UnitPriceScenarioService(tax)
    result = service.calculate(_inputs(), extended_scenario=_contract())

    assert result["available"] is True
    assert result["calculated"]["fees"] == 7.0
    assert result["calculated"]["profit_before_tax"] == 46.0
    assert result["calculated"]["additional_unit_expenses"] == 5.0
    assert result["calculated"]["profit"] == 46.0
    assert tax.calls == [{
        "mode": "NONE", "revenue": 100.0, "gross_profit": 46.0,
        "tax_rate": None, "minimum_tax_rate": None, "discount_points": 0.0,
    }]
    assert result["extended_calculation"]["status"] == "APPLIED"
    assert result["extended_calculation"]["denominator_kind"] == "SOLD_UNITS_WINDOW"
    assert result["extended_calculation"]["additional_expense_per_unit_rub"] == "5.00"


def test_n09_existing_tax_service_receives_adjusted_gross_profit_once():
    tax = _TaxSpy()
    service = UnitPriceScenarioService(tax)
    result = service.calculate(
        _inputs(tax_mode="USN_INCOME", tax_rate="6", discount_points_rate="20"),
        extended_scenario=_contract(),
    )

    assert result["calculated"]["profit_before_tax"] == 46.0
    assert result["calculated"]["tax"] == 4.8
    assert result["calculated"]["profit"] == 41.2
    assert len(tax.calls) == 1
    assert tax.calls[0]["gross_profit"] == 46.0
    assert tax.calls[0]["discount_points"] == 20.0


def test_components_are_summed_then_divided_and_rounded_once():
    components = [
        {"component_key": "EXTRA_A", "numerator_rub": "0.01", "ownership": "ADDITIONAL"},
        {"component_key": "EXTRA_B", "numerator_rub": "0.01", "ownership": "ADDITIONAL"},
    ]
    result = UnitPriceScenarioService(TaxService()).calculate(
        _inputs(), extended_scenario=_contract(components=components, units=3),
    )
    assert result["extended_calculation"]["total_numerator_rub"] == "0.02"
    assert result["extended_calculation"]["additional_expense_per_unit_rub"] == "0.01"
    assert result["calculated"]["additional_unit_expenses"] == 0.01
    assert result["calculated"]["profit_before_tax"] == 50.99


def test_complete_empty_snapshot_is_an_explicit_confirmed_zero():
    result = UnitPriceScenarioService(TaxService()).calculate(
        _inputs(), extended_scenario=_contract(components=[], keys=[]),
    )
    assert result["available"] is True
    assert result["extended_calculation"]["total_numerator_rub"] == "0.00"
    assert result["calculated"]["additional_unit_expenses"] == 0.0
    assert result["calculated"]["profit_before_tax"] == 51.0


def test_partial_source_does_not_fall_back_to_legacy_profit_or_call_tax():
    tax = _TaxSpy()
    result = UnitPriceScenarioService(tax).calculate(
        _inputs(), extended_scenario=_contract(completeness="PARTIAL"),
    )
    assert result["available"] is False
    assert result["calculated"]["profit"] is None
    assert result["extended_calculation"]["status"] == "UNAVAILABLE"
    assert result["extended_calculation"]["reason"] == "SOURCE_EVIDENCE_PARTIAL"
    assert tax.calls == []


def test_strict_retained_mode_is_explicitly_unavailable_until_w12():
    result = UnitPriceScenarioService(TaxService()).calculate(
        _inputs(), extended_scenario=_contract(mode="STRICT_RETAINED_COHORT"),
    )
    assert result["available"] is False
    assert result["extended_calculation"]["reason"] == "STRICT_RETAINED_COHORT_NOT_IMPLEMENTED"


def test_zero_or_invalid_denominator_fails_closed_without_a_tax_call():
    tax = _TaxSpy()
    result = UnitPriceScenarioService(tax).calculate(
        _inputs(), extended_scenario=_contract(units=0),
    )
    assert result["available"] is False
    assert result["extended_calculation"]["reason"] == "ZERO_OR_INVALID_DENOMINATOR"
    assert tax.calls == []


def test_extended_contract_never_mixes_cross_docking_supplied_units_with_sale_units():
    tax = _TaxSpy()
    result = UnitPriceScenarioService(tax).calculate(
        _inputs(cross_docking_per_unit="2"), extended_scenario=_contract(),
    )
    assert result["available"] is False
    assert result["extended_calculation"]["reason"] == "CROSS_DOCKING_DENOMINATOR_INCOMPATIBLE"
    assert tax.calls == []


def test_duplicate_component_key_and_wrong_included_key_list_fail_closed():
    duplicate = [
        {"component_key": "EXTRA_A", "numerator_rub": "1.00", "ownership": "ADDITIONAL"},
        {"component_key": "EXTRA_A", "numerator_rub": "1.00", "ownership": "ADDITIONAL"},
    ]
    result = UnitPriceScenarioService(TaxService()).calculate(
        _inputs(), extended_scenario=_contract(components=duplicate, keys=["EXTRA_A"]),
    )
    assert result["available"] is False
    assert result["extended_calculation"]["reason"] == "EXTENDED_COMPONENT_DUPLICATE"

    mismatch = UnitPriceScenarioService(TaxService()).calculate(
        _inputs(), extended_scenario=_contract(keys=[]),
    )
    assert mismatch["available"] is False
    assert mismatch["extended_calculation"]["reason"] == "EXTENDED_COMPONENT_KEYS_MISMATCH"


def test_excluded_components_cannot_also_be_included():
    contract = _contract()
    contract["excluded_component_statuses"] = {"EXTRA_SERVICE": "EXCLUDED"}
    result = UnitPriceScenarioService(TaxService()).calculate(_inputs(), extended_scenario=contract)
    assert result["available"] is False
    assert result["extended_calculation"]["reason"] == "EXTENDED_EXCLUDED_COMPONENTS_INVALID"


def test_component_with_base_included_ownership_cannot_be_added_again():
    contract = _contract(components=[
        {"component_key": "BASE_FEE", "numerator_rub": "5.00", "ownership": "BASE_ALREADY_INCLUDED"},
    ])
    result = UnitPriceScenarioService(TaxService()).calculate(_inputs(), extended_scenario=contract)
    assert result["available"] is False
    assert result["extended_calculation"]["reason"] == "EXTENDED_COMPONENT_INVALID"


def test_invalid_schema_and_free_text_contract_fields_are_not_echoed():
    contract = _contract()
    contract["schema_version"] = 99
    result = UnitPriceScenarioService(TaxService()).calculate(_inputs(), extended_scenario=contract)
    assert result["extended_calculation"]["reason"] == "EXTENDED_SCHEMA_UNSUPPORTED"
    assert "500.00" not in repr(result)

    contract = _contract()
    contract["unexpected"] = "private data"
    result = UnitPriceScenarioService(TaxService()).calculate(_inputs(), extended_scenario=contract)
    assert result["extended_calculation"]["reason"] == "EXTENDED_CONTRACT_INVALID"
    assert "private data" not in repr(result)


def test_invalid_or_overlapping_scope_is_rejected():
    contract = _contract()
    contract["scope"]["to_date"] = "2026-02-24"
    result = UnitPriceScenarioService(TaxService()).calculate(_inputs(), extended_scenario=contract)
    assert result["extended_calculation"]["reason"] == "EXTENDED_SCOPE_INVALID"


def test_calculate_components_only_and_compare_use_the_same_canonical_extension():
    service = UnitPriceScenarioService(TaxService())
    contract = _contract()
    component_result = service.calculate_components_only(_inputs(), extended_scenario=contract)
    compare = service.compare(
        _inputs(), current_price="100", extended_scenario=contract,
    )
    assert component_result["available"] is True
    assert component_result["calculated"]["profit_before_tax"] == 46.0
    assert compare["calculated"]["profit"] == 46.0
    assert compare["comparison"]["profit"] == 46.0


def test_amount_bound_and_timezone_fail_closed():
    huge = _contract(components=[
        {"component_key": "EXTRA_SERVICE", "numerator_rub": "10000000000000", "ownership": "ADDITIONAL"},
    ])
    assert UnitPriceScenarioService(TaxService()).calculate(
        _inputs(), extended_scenario=huge,
    )["extended_calculation"]["reason"] == "EXTENDED_COMPONENT_AMOUNT_INVALID"

    bad_zone = _contract()
    bad_zone["scope"]["timezone"] = "Not/A_Timezone"
    assert UnitPriceScenarioService(TaxService()).calculate(
        _inputs(), extended_scenario=bad_zone,
    )["extended_calculation"]["reason"] == "EXTENDED_SCOPE_INVALID"


def test_malformed_nested_types_fail_closed_without_exceptions():
    mutations = [
        lambda contract: contract.update(calculation_mode={}),
        lambda contract: contract.update(source_completeness=[]),
        lambda contract: contract.update(assumed_inputs=[{}]),
        lambda contract: contract["scope"].update(scope_kind=[]),
        lambda contract: contract["excluded_component_statuses"].update(EXTRA={}),
    ]
    for mutate in mutations:
        contract = _contract(components=[])
        mutate(contract)
        result = UnitPriceScenarioService(TaxService()).calculate(
            _inputs(), extended_scenario=contract,
        )
        assert result["available"] is False
        assert result["extended_calculation"]["status"] == "UNAVAILABLE"
        assert "{}" not in repr(result["extended_calculation"])


def test_extended_calculation_reports_model_only_and_keeps_identity_data_out_of_contract():
    contract = _contract()
    result = UnitPriceScenarioService(TaxService()).calculate(
        _inputs(), identity={"user_id": "owner-1", "sku": "secret-sku"},
        extended_scenario=contract,
    )
    assert result["read_only"] is True
    assert result["executed"] is False
    assert result["extended_calculation"]["included_component_keys"] == ["EXTRA_SERVICE"]
    assert result["extended_calculation"]["expense_snapshot_ref"] == "a" * 64
    assert "secret-sku" not in repr(result["extended_calculation"])

