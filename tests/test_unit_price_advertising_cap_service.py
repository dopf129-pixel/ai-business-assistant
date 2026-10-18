from copy import deepcopy

from services.tax_service import TaxService
from services.unit_price_advertising_cap_service import UnitPriceAdvertisingCapService
from services.unit_price_scenario_service import UnitPriceScenarioService


def _inputs(**overrides):
    values = {
        "price": "500", "cost": "150", "commission_rate": "20",
        "advertising_rate": "10", "discount_points_rate": "20",
        "logistics_per_unit": "25", "last_mile_per_unit": "5",
        "acquiring_per_unit": "5", "tax_mode": "USN_INCOME",
        "tax_rate": "6", "minimum_tax_rate": "1",
    }
    values.update(overrides)
    return values


def _service():
    return UnitPriceAdvertisingCapService(UnitPriceScenarioService(TaxService()))


def test_matches_required_grid_example_and_confirms_neighboring_ticks():
    inputs = _inputs()
    original = deepcopy(inputs)
    result = _service().solve(inputs, "25")

    assert result["error"] is False
    assert result["break_even"]["status"] == "FOUND"
    assert result["break_even"]["advertising_rate"] == "38.20"
    assert result["break_even"]["advertising_per_unit"] == "191.00"
    assert result["break_even"]["profit_per_unit"] == "0.00"
    assert result["break_even"]["next_tick_rate"] == "38.21"
    assert result["target"]["advertising_rate"] == "13.20"
    assert result["target"]["advertising_per_unit"] == "66.00"
    assert result["target"]["next_tick_rate"] == "13.21"
    assert result["target"]["headroom_percentage_points"] == "3.20"
    assert result["target"]["headroom_per_unit"] == "16.00"
    assert result["evaluation_count"] <= 128
    assert inputs == original
    assert result["read_only"] is True and result["executed"] is False


def test_supports_no_tax_and_upper_bound_and_handles_zero_targets():
    result = _service().solve(_inputs(
        cost="0", commission_rate="0", logistics_per_unit="0",
        last_mile_per_unit="0", acquiring_per_unit="0",
        discount_points_rate="0", tax_mode="NONE", tax_rate=None,
        minimum_tax_rate=None, advertising_rate="100",
    ), "0")

    assert result["error"] is False
    assert result["break_even"]["status"] == "UPPER_BOUND_REACHED"
    assert result["break_even"]["advertising_rate"] == "100.00"
    assert result["target"]["status"] == "UPPER_BOUND_REACHED"
    assert result["target"]["advertising_rate"] == "100.00"
    assert result["evaluation_count"] <= 128


def test_tax_minimum_switch_is_evaluated_through_canonical_forward_calculator():
    result = _service().solve(_inputs(
        tax_mode="USN_INCOME_MINUS_EXPENSES", tax_rate="15",
        minimum_tax_rate="1", discount_points_rate="0",
    ), "20")

    assert result["error"] is False
    assert result["break_even"]["available"] is True
    assert result["target"]["available"] is True
    assert result["evaluation_count"] <= 128


def test_negative_profit_without_advertising_reports_unreachable_limits():
    result = _service().solve(_inputs(cost="1000"), "0")

    assert result["error"] is False
    assert result["break_even"]["status"] == "NOT_REACHABLE"
    assert result["target"]["status"] == "NOT_REACHABLE"


def test_missing_inputs_and_invalid_targets_do_not_return_a_limit():
    missing = _service().solve(_inputs(advertising_rate=None), "20")
    invalid_target = _service().solve(_inputs(), "100.01")

    assert missing["status"] == "MISSING_INPUTS"
    assert "advertising_rate" in missing["missing_inputs"]
    assert invalid_target["code"] == "INVALID_TARGET"


class _NonMonotonicScenario:
    def calculate(self, inputs, **_kwargs):
        rate = float(inputs["advertising_rate"])
        # Deliberately non-monotonic at middle rates; a binary search must not
        # claim an advertising cap on this unverified forward function.
        profit = 10 - rate if rate < 50 else rate - 40
        return {"available": True, "calculated": {
            "revenue": 100, "profit": profit, "margin_percent": profit,
            "advertising": rate,
        }}


def test_non_monotonic_forward_results_fail_closed():
    result = UnitPriceAdvertisingCapService(_NonMonotonicScenario()).solve(
        _inputs(), "5",
    )

    assert result["code"] == "LIMIT_NOT_CONFIRMED"
    assert result["available"] is False
    assert "break_even" not in result
