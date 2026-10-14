from services.tax_service import TaxService
from services.unit_price_scenario_service import UnitPriceScenarioService


def _inputs(**overrides):
    values = {
        "price": "500",
        "cost": "120",
        "commission_rate": "15",
        "logistics_per_unit": "40",
        "last_mile_per_unit": "10",
        "acquiring_per_unit": "5",
        "advertising_rate": "8",
        "discount_points_rate": "20",
        "tax_mode": "USN_INCOME",
        "tax_rate": "6",
        "minimum_tax_rate": "1",
    }
    values.update(overrides)
    return values


def test_scenario_matches_signed_control_fixture_and_uses_seller_price_tax_base():
    service = UnitPriceScenarioService(TaxService())

    result = service.calculate(
        _inputs(),
        identity={
            "user_id": "u1",
            "store_id": "s1",
            "sku": "123",
            "offer_id": "offer-1",
        },
    )

    assert result["available"] is True
    assert result["kind"] == "PRICE_PLANNING_SCENARIO"
    assert result["read_only"] is True
    assert result["executed"] is False
    assert result["identity"]["sku"] == "123"
    assert result["calculated"] == {
        "revenue": 500.0,
        "discount_points": 100.0,
        "taxable_revenue": 400.0,
        "commission": 75.0,
        "advertising": 40.0,
        "fees": 55.0,
        "profit_before_tax": 210.0,
        "tax": 24.0,
        "effective_tax_rate": 4.8,
        "profit": 186.0,
        "margin_percent": 37.2,
    }


def test_reprice_recalculates_variable_costs_but_preserves_fixed_fees():
    service = UnitPriceScenarioService(TaxService())
    base = _inputs()
    baseline = service.calculate(base)
    repriced = service.calculate({**base, "price": "600"})

    assert baseline["calculated"]["profit"] == 186.0
    assert repriced["calculated"]["discount_points"] == 120.0
    assert repriced["calculated"]["commission"] == 90.0
    assert repriced["calculated"]["advertising"] == 48.0
    assert repriced["calculated"]["fees"] == 55.0
    assert repriced["calculated"]["tax"] == 28.8
    assert repriced["calculated"]["profit"] == 258.2
    assert repriced["calculated"]["margin_percent"] == 43.03


def test_margin_is_not_markup_and_loss_is_valid():
    service = UnitPriceScenarioService(TaxService())
    result = service.calculate(_inputs(cost="600"))

    assert result["available"] is True
    assert result["calculated"]["profit"] < 0
    assert result["calculated"]["margin_percent"] < 0
    assert result["calculated"]["margin_percent"] != round(
        result["calculated"]["profit"] / 600 * 100,
        2,
    )


def test_explicit_zero_assumptions_are_valid_and_not_confused_with_missing():
    service = UnitPriceScenarioService(TaxService())
    values = _inputs(
        cost="0",
        advertising_rate="0",
        discount_points_rate="0",
        logistics_per_unit="0",
        last_mile_per_unit="0",
        acquiring_per_unit="0",
    )

    result = service.calculate(values)

    assert result["available"] is True
    assert result["calculated"]["discount_points"] == 0.0
    assert result["calculated"]["advertising"] == 0.0


def test_missing_required_inputs_produce_unavailable_profit_with_named_fields():
    service = UnitPriceScenarioService(TaxService())
    values = _inputs()
    del values["advertising_rate"]
    del values["tax_mode"]

    result = service.calculate(values)

    assert result["available"] is False
    assert result["calculated"]["profit"] is None
    assert result["calculated"]["margin_percent"] is None
    assert set(result["missing_inputs"]) == {"advertising_rate", "tax_mode"}


def test_invalid_prices_rates_and_non_finite_values_fail_closed():
    service = UnitPriceScenarioService(TaxService())

    for invalid in ("0", "-1", "NaN", "Infinity", True, "not-money"):
        result = service.calculate(_inputs(price=invalid))
        assert result["available"] is False
        assert "price" in result["invalid_inputs"]

    for invalid_rate in ("-0.1", "100.01", "NaN", True):
        result = service.calculate(_inputs(advertising_rate=invalid_rate))
        assert result["available"] is False
        assert "advertising_rate" in result["invalid_inputs"]


def test_tax_policy_none_is_explicit_and_missing_tax_configuration_is_not_zero():
    service = UnitPriceScenarioService(TaxService())

    no_tax = service.calculate(_inputs(tax_mode="NONE", tax_rate=None))
    missing = service.calculate(_inputs(tax_mode=None, tax_rate=None))

    assert no_tax["available"] is True
    assert no_tax["calculated"]["tax"] == 0.0
    assert missing["available"] is False
    assert "tax_mode" in missing["missing_inputs"]


def test_income_minus_expenses_uses_existing_tax_service_minimum_tax_rule():
    service = UnitPriceScenarioService(TaxService())
    result = service.calculate(
        _inputs(
            tax_mode="USN_INCOME_MINUS_EXPENSES",
            tax_rate="15",
            minimum_tax_rate="1",
            cost="400",
        )
    )

    assert result["available"] is True
    assert result["calculated"]["tax"] == 4.0


def test_unsupported_decimal_magnitude_and_precision_fail_closed_before_quantize():
    service = UnitPriceScenarioService(TaxService())

    for value in ("1e100", "1e-100", "12345678901234567890"):
        result = service.calculate(_inputs(price=value))
        assert result["available"] is False
        assert "price" in result["invalid_inputs"]
        assert result["calculated"]["tax"] is None
        assert result["calculated"]["profit"] is None
        assert result["calculated"]["margin_percent"] is None


def test_bounded_weighted_percentage_accepts_decimal_context_precision_only():
    service = UnitPriceScenarioService(TaxService())
    recurring = service.calculate(_inputs(
        logistics_per_unit="0",
        last_mile_per_unit="0",
        acquiring_per_unit="0",
        advertising_rate="0",
        discount_points_rate="16.66666666666666666666666667",
    ))
    excessive = service.calculate(_inputs(
        discount_points_rate="16.666666666666666666666666671",
    ))

    assert recurring["available"] is True
    assert recurring["calculated"]["tax"] == 25
    assert recurring["calculated"]["profit"] == 280
    assert recurring["calculated"]["margin_percent"] == 56
    assert excessive["available"] is False
    assert "discount_points_rate" in excessive["invalid_inputs"]


def test_large_finite_tax_service_output_never_marks_empty_profit_as_available():
    class InvalidTaxService:
        SUPPORTED_MODES = TaxService.SUPPORTED_MODES

        def calculate(self, **_kwargs):
            return {"error": False, "configured": True, "tax_amount": "Infinity"}

    service = UnitPriceScenarioService(InvalidTaxService())
    result = service.calculate(_inputs())

    assert result["available"] is False
    assert "tax_calculation" in result["invalid_inputs"]
    assert result["calculated"]["tax"] is None
    assert result["calculated"]["profit"] is None
    assert result["calculated"]["margin_percent"] is None


def test_localized_money_input_is_still_accepted_with_spaces_and_decimal_comma():
    service = UnitPriceScenarioService(TaxService())
    result = service.calculate(_inputs(price="1 200,50"))

    assert result["available"] is True
    assert result["inputs"]["price"]["value"] == 1200.5
