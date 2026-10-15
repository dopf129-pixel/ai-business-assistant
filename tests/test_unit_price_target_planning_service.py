from decimal import Decimal

import pytest

from services.tax_service import TaxService
from services.unit_price_scenario_service import UnitPriceScenarioService
from services.unit_price_target_planning_service import UnitPriceTargetPlanningService


def _inputs(**overrides):
    values = {
        "price": None,
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


class _CountingScenarioService:
    MAX_INPUT_DIGITS = UnitPriceScenarioService.MAX_INPUT_DIGITS
    MAX_INPUT_ADJUSTED_EXPONENT = UnitPriceScenarioService.MAX_INPUT_ADJUSTED_EXPONENT

    def __init__(self):
        self.delegate = UnitPriceScenarioService(TaxService())
        self.calls = 0

    def calculate(self, *args, **kwargs):
        self.calls += 1
        return self.delegate.calculate(*args, **kwargs)


def _planner(counting=False):
    service = _CountingScenarioService() if counting else UnitPriceScenarioService(TaxService())
    return UnitPriceTargetPlanningService(service), service


def _assert_goal(outcome, target):
    assert outcome["status"] == "FOUND"
    assert outcome["goal_reached"] is True
    price = Decimal(outcome["price"])
    profit = Decimal(str(outcome["profit"]))
    assert profit * 100 >= Decimal(target) * price


def test_solver_uses_real_forward_calculator_for_break_even_and_target_margin():
    planner, _ = _planner()

    result = planner.solve(
        _inputs(),
        Decimal("20"),
        identity={"user_id": "u1", "store_id": "s1", "sku": "123", "scenario_version": 4},
        provenance={"cost": "manual"},
        sources={"as_of": "test snapshot"},
    )

    assert result["error"] is False
    assert result["read_only"] is True
    assert result["executed"] is False
    assert result["identity"]["store_id"] == "s1"
    assert Decimal("242.38") <= Decimal(result["break_even"]["price"]) <= Decimal("242.40")
    assert Decimal("335.25") <= Decimal(result["target"]["price"]) <= Decimal("335.27")
    _assert_goal(result["break_even"], "0")
    _assert_goal(result["target"], "20")


def test_exact_goal_does_not_use_displayed_rounded_margin():
    planner, _ = _planner()
    result = planner.compare_prices(
        _inputs(),
        "414,70; 414,71\n414,72",
        target_margin_percent="30",
    )

    assert [row["margin_percent"] for row in result["rows"]] == [30.0, 30.0, 30.0]
    assert [row["goal_reached"] for row in result["rows"]] == [False, False, True]
    assert [row["profit"] for row in result["rows"]] == [124.4, 124.41, 124.42]


@pytest.mark.parametrize("tax_mode,tax_rate,minimum_rate", [
    ("NONE", None, None),
    ("USN_INCOME", "6", "1"),
    ("USN_INCOME_MINUS_EXPENSES", "15", "1"),
])
def test_solver_uses_tax_service_for_each_supported_tax_mode(tax_mode, tax_rate, minimum_rate):
    planner, _ = _planner()
    values = _inputs(
        tax_mode=tax_mode,
        tax_rate=tax_rate,
        minimum_tax_rate=minimum_rate,
    )

    result = planner.solve(values, "10")

    assert result["break_even"]["status"] == "FOUND"
    _assert_goal(result["break_even"], "0")
    _assert_goal(result["target"], "10")
    for outcome in (result["break_even"], result["target"]):
        assert outcome["forward_result"]["available"] is True


@pytest.mark.parametrize("target", ["0", "99.99", "100"])
def test_zero_cost_no_tax_scenarios_support_target_boundaries(target):
    planner, _ = _planner()
    values = _inputs(
        cost="0",
        commission_rate="0",
        logistics_per_unit="0",
        last_mile_per_unit="0",
        acquiring_per_unit="0",
        advertising_rate="0",
        discount_points_rate="0",
        tax_mode="NONE",
        tax_rate=None,
        minimum_tax_rate=None,
    )

    result = planner.solve(values, target)

    assert result["break_even"]["price"] == "0.01"
    assert result["target"]["price"] == "0.01"
    _assert_goal(result["target"], target)


def test_solver_reports_not_found_without_claiming_that_target_is_impossible():
    planner, _ = _planner()
    values = _inputs(
        cost="10",
        commission_rate="100",
        logistics_per_unit="0",
        last_mile_per_unit="0",
        acquiring_per_unit="0",
        advertising_rate="0",
        discount_points_rate="0",
        tax_mode="NONE",
        tax_rate=None,
        minimum_tax_rate=None,
    )

    result = planner.solve(values, "20")

    assert result["break_even"]["status"] == "NOT_FOUND_IN_TESTED_RANGE"
    assert result["target"]["status"] == "NOT_FOUND_IN_TESTED_RANGE"
    assert result["available"] is False


@pytest.mark.parametrize(
    "target,advertising_rate,expected_price",
    [("50", "0", None), ("0", "50", None), ("49.99", "0.01", "0.02")],
)
def test_solver_finds_verified_price_when_maximum_cent_fails_from_rounding(
    target, advertising_rate, expected_price
):
    planner, service = _planner(counting=True)
    values = _inputs(
        price=None,
        cost="0",
        commission_rate="50",
        logistics_per_unit="0",
        last_mile_per_unit="0",
        acquiring_per_unit="0",
        advertising_rate=advertising_rate,
        discount_points_rate="0",
        tax_mode="NONE",
        tax_rate=None,
        minimum_tax_rate=None,
    )

    result = planner.solve(values, target)

    outcome = result["target"]
    assert outcome["status"] == "FOUND"
    if expected_price is not None:
        assert outcome["price"] == expected_price
    assert outcome["goal_reached"] is True
    assert outcome["forward_result"]["available"] is True
    assert Decimal(outcome["price"]) < planner.max_price
    assert result["evaluation_count"] == service.calls
    assert result["evaluation_count"] <= 127


def test_current_price_probe_accepts_calculator_decimal_comma_and_grouped_spaces():
    planner, _ = _planner()

    assert planner._current_price_cents({"price": "500,00"}) == 50_000
    assert planner._current_price_cents({"price": "1 234,56"}) == 123_456
    assert planner._current_price_cents({"price": "1\u00a0234,56"}) == 123_456
    assert planner._current_price_cents({"price": "5e2"}) == 50_000
    assert planner._current_price_cents({"price": "1.234,56"}) is None


def test_target_and_comparison_candidates_do_not_inherit_observed_price_provenance():
    planner, _ = _planner()
    source_provenance = {
        "price": "ozon_current_seller_price",
        "cost": "manual_seller_assumption",
    }
    values = _inputs(price="500")

    plan = planner.solve(
        values, "20", provenance=source_provenance
    )
    comparison = planner.compare_prices(
        values, "550;600", provenance=source_provenance
    )

    assert plan["source_price_provenance"] == "ozon_current_seller_price"
    assert plan["provenance"]["price"] == "planned_seller_price"
    for outcome in (plan["break_even"], plan["target"]):
        assert (
            outcome["forward_result"]["inputs"]["price"]["provenance"]
            == "planned_seller_price"
        )

    assert comparison["source_price_provenance"] == "ozon_current_seller_price"
    assert comparison["provenance"]["price"] == "manual_seller_assumption"
    for row in comparison["rows"]:
        assert (
            row["forward_result"]["inputs"]["price"]["provenance"]
            == "manual_seller_assumption"
        )
    assert comparison["provenance"]["cost"] == "manual_seller_assumption"


def test_missing_non_price_inputs_remain_unknown_and_do_not_become_zero():
    planner, service = _planner(counting=True)
    values = _inputs()
    del values["last_mile_per_unit"]
    del values["tax_mode"]

    result = planner.solve(values, "20")

    assert result["break_even"]["status"] == "MISSING_INPUTS"
    assert result["target"]["status"] == "MISSING_INPUTS"
    assert set(result["break_even"]["missing_inputs"]) == {"last_mile_per_unit", "tax_mode"}
    assert service.calls == result["evaluation_count"] == 1


def test_target_input_is_validated_without_defaulting_or_float_comparison():
    planner, _ = _planner()

    assert planner.parse_target_margin("0")["value"] == Decimal("0")
    assert planner.parse_target_margin("99,99")["value"] == Decimal("99.99")
    assert planner.parse_target_margin("100")["value"] == Decimal("100")
    for value in ("", "-1", "100.01", "20.001", "NaN", "Infinity", "1e1", "20%", True):
        assert planner.parse_target_margin(value)["valid"] is False
    assert planner.solve(_inputs(), "20.001")["code"] == "INVALID_TARGET"


def test_price_list_parser_accepts_decimal_comma_thousands_spaces_and_windows_newlines():
    planner, _ = _planner()

    parsed = planner.parse_price_list("499,90; 1 200.50\r\n1\u00a0234,00")

    assert parsed["valid"] is True
    assert parsed["normalized"] == ["499.90", "1200.50", "1234.00"]


@pytest.mark.parametrize("text", [
    "",
    "500",
    "500;500.00",
    "500.5;500,50",
    "500;bad;600",
    "500;0",
    "500;1.234",
    "500;600;700;800;900;1000",
    "500; ;600",
])
def test_invalid_price_list_is_rejected_as_a_whole(text):
    planner, _ = _planner()

    result = planner.parse_price_list(text)

    assert result["error"] is True
    assert result["valid"] is False
    assert "prices" not in result


def test_comparison_preserves_input_order_and_uses_one_forward_call_per_price():
    planner, service = _planner(counting=True)

    result = planner.compare_prices(
        _inputs(),
        [Decimal("600"), Decimal("500")],
        target_margin_percent=Decimal("20"),
        identity={"user_id": "u1", "store_id": "s1", "sku": "123"},
        provenance={"cost": "manual"},
        sources={"as_of": "snapshot"},
    )

    assert [row["price"] for row in result["rows"]] == ["600.00", "500.00"]
    assert [row["profit"] for row in result["rows"]] == [258.2, 186.0]
    assert all(row["goal_reached"] is True for row in result["rows"])
    assert result["evaluation_count"] == service.calls == 2
    assert result["identity"]["store_id"] == "s1"
    assert result["read_only"] is True and result["executed"] is False


def test_search_stays_inside_forward_evaluation_budget():
    planner, service = _planner(counting=True)

    result = planner.solve(_inputs(), "30")

    assert result["evaluation_count"] == service.calls
    assert result["evaluation_count"] <= 113
    assert result["evaluation_limit"] == 128
    _assert_goal(result["break_even"], "0")
    _assert_goal(result["target"], "30")
    assert Decimal("414.72") <= Decimal(result["target"]["price"]) <= Decimal("414.74")


def test_comparison_keeps_unavailable_scenarios_distinct_from_target_failure():
    planner, _ = _planner()
    values = _inputs()
    values["acquiring_per_unit"] = None

    result = planner.compare_prices(values, "450; 500", target_margin_percent="20")

    assert all(not row["available"] for row in result["rows"])
    assert all(row["goal_reached"] is None for row in result["rows"])
    assert {row["status"] for row in result["rows"]} == {"MISSING_INPUTS"}
    assert all(row["missing_inputs"] == ["acquiring_per_unit"] for row in result["rows"])
