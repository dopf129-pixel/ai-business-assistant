from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor

import pytest

from services.tax_service import TaxService
from services.unit_price_scenario_service import UnitPriceScenarioService
from services.unit_price_sensitivity_service import UnitPriceSensitivityService


def _context(inputs=None):
    snapshot = {
        "identity": {
            "user_id": "user-1",
            "store_id": "store-a",
            "tenant_scope": "user-1::ozon::store-a",
            "product_id": "product-1",
            "offer_id": "offer-1",
            "sku": "sku-1",
        },
        "source_periods": {"seller_price_as_of": "2026-10-17T00:00:00Z"},
        "source_completeness": {"commission": {"complete": True}},
    }
    return {
        "snapshot": snapshot,
        "identity": deepcopy(snapshot["identity"]),
        "inputs": inputs or {
            "price": "500",
            "cost": "200",
            "commission_rate": "15",
            "advertising_rate": "10",
            "discount_points_rate": "20",
            "logistics_per_unit": "40",
            "last_mile_per_unit": "10",
            "acquiring_per_unit": "5",
            "tax_mode": "USN_INCOME",
            "tax_rate": "6",
            "minimum_tax_rate": "1",
        },
        "provenance": {"cost": "confirmed_store_cost"},
        "sources": {
            "periods": snapshot["source_periods"],
            "completeness": snapshot["source_completeness"],
        },
        "source_age_seconds": 10,
        "source_ttl_seconds": 600,
        "source_version": "scenario-v3",
        "source_as_of": snapshot["source_periods"],
    }


def _service():
    return UnitPriceSensitivityService(UnitPriceScenarioService(TaxService()))


def test_parser_accepts_absolute_decimal_values_and_bounds_axis_count():
    service = _service()

    parsed = service.parse_axis_values("500; 550,50\n600", "price")
    seven = service.parse_axis_values("100;200;300;400;500;600;700", "cost")
    zero = service.parse_axis_values("0;5;10", "advertising_rate")

    assert parsed["values"] == ["500", "550.50", "600"]
    assert len(seven["values"]) == 7
    assert zero["values"][0] == "0"
    assert service.parse_axis_values("0;50;100", "advertising_rate")["error"] is False


@pytest.mark.parametrize("value", ["1;1.0;2", "+1;2;3", "1;;3", "NaN;2;3", "Infinity;2;3", "0;1;2", "1e13;2;3", "1;2"])
def test_parser_rejects_duplicate_ambiguous_invalid_or_out_of_range_inputs(value):
    result = _service().parse_axis_values(value, "price")
    assert result["error"] is True


@pytest.mark.parametrize("axis,value", [
    ("cost", "0;1;2"),
    ("advertising_rate", "-1;10;20"),
    ("advertising_rate", "0;50;100.01"),
    ("unknown", "1;2;3"),
])
def test_parser_applies_axis_specific_money_and_rate_rules(axis, value):
    result = _service().parse_axis_values(value, axis)
    if axis == "cost":
        assert result["error"] is False
    else:
        assert result["error"] is True


def test_one_axis_sweep_matches_direct_forward_calculator_and_preserves_base():
    scenario = UnitPriceScenarioService(TaxService())
    service = UnitPriceSensitivityService(scenario)
    context = _context()
    before = deepcopy(context)
    result = service.build_sweep(context, {"price": ["500", "550", "564.16"]}, target_margin_percent="25")

    assert result["error"] is False
    assert result["cell_count"] == 3
    assert result["available_cell_count"] == 3
    assert context == before
    assert [cell["inputs"]["price"] for cell in result["cells"]] == ["500", "550", "564.16"]
    for cell in result["cells"]:
        direct = scenario.calculate(
            cell["inputs"],
            identity=cell["scenario"]["identity"],
            provenance=cell["provenance"],
            sources=context["sources"],
        )
        assert cell["scenario"]["calculated"] == direct["calculated"]
    assert result["cells"][0]["scenario"]["calculated"]["profit"] == 96.0
    assert result["cells"][2]["target_reached"] is True
    assert result["best_worst_basis"] == "among_checked_scenarios_only"


def test_each_axis_value_is_an_absolute_assumption_and_cost_zero_is_known():
    service = _service()
    result = service.build_sweep(
        _context(),
        {"cost": ["0", "200", "220"]},
    )
    assert [cell["inputs"]["cost"] for cell in result["cells"]] == ["0", "200", "220"]
    assert result["cells"][0]["provenance"]["cost"] == "sensitivity_absolute_value"
    assert result["cells"][0]["status"] == "AVAILABLE"


def test_two_axis_matrix_caps_at_49_and_records_exact_coordinates_and_indexes():
    service = _service()
    values = [str(index * 10) for index in range(1, 8)]
    result = service.build_sweep(
        _context(),
        {"advertising_rate": values, "cost": values},
        target_margin_percent="0",
    )

    assert result["cell_count"] == 49
    assert result["available_cell_count"] == 49
    assert result["cells"][0]["coordinate_indexes"] == {"advertising_rate": 0, "cost": 0}
    assert result["cells"][-1]["coordinate_indexes"] == {"advertising_rate": 6, "cost": 6}
    assert result["cells"][-1]["coordinates"] == {"advertising_rate": "70", "cost": "70"}
    assert len({cell["input_signature"] for cell in result["cells"]}) == 49
    assert any(cell["target_reached"] is False for cell in result["cells"])
    assert all(
        cell["target_reached"] is (
            cell["scenario"]["calculated"]["profit"] >= 0
        )
        for cell in result["cells"]
    )


def test_invalid_axes_target_and_context_fail_closed():
    service = _service()
    context = _context()
    assert service.build_sweep(context, {})["code"] == "SENSITIVITY_AXES_INVALID"
    assert service.build_sweep(context, {"price": ["1", "2"]})["code"] == "SENSITIVITY_VALUE_COUNT_INVALID"
    assert service.build_sweep(context, {"price": ["1", "2", "3"] * 3})["code"] == "SENSITIVITY_VALUE_COUNT_INVALID"
    assert service.build_sweep(context, {"price": ["1", "2", "3"]}, target_margin_percent=True)["code"] == "SENSITIVITY_TARGET_INVALID"
    mismatch = _context()
    mismatch["identity"]["sku"] = "different"
    assert service.build_sweep(mismatch, {"price": ["1", "2", "3"]})["code"] == "SENSITIVITY_IDENTITY_MISMATCH"


def test_unknown_inputs_remain_unknown_and_stale_source_performs_no_calculation():
    class _SpyScenario:
        def __init__(self):
            self.calls = 0

        def calculate(self, *args, **kwargs):
            self.calls += 1
            return {"available": False, "missing_inputs": ["cost"], "invalid_inputs": [], "calculated": {}}

    spy = _SpyScenario()
    service = UnitPriceSensitivityService(spy)
    missing = _context({**_context()["inputs"], "cost": None})
    incomplete = service.build_sweep(missing, {"price": ["450", "500", "550"]})
    assert [cell["status"] for cell in incomplete["cells"]] == ["INCOMPLETE_INPUTS"] * 3
    assert all(cell["scenario"]["calculated"] == {} for cell in incomplete["cells"])

    stale_context = _context()
    stale_context["source_age_seconds"] = 600
    before_calls = spy.calls
    stale = service.build_sweep(stale_context, {"price": ["450", "500", "550"]})
    assert [cell["status"] for cell in stale["cells"]] == ["SOURCE_STALE"] * 3
    assert spy.calls == before_calls


def test_sweep_uses_existing_minimum_tax_branch_and_matches_direct_result():
    scenario = UnitPriceScenarioService(TaxService())
    service = UnitPriceSensitivityService(scenario)
    context = _context({
        **_context()["inputs"],
        "tax_mode": "USN_INCOME_MINUS_EXPENSES",
        "tax_rate": "15",
        "minimum_tax_rate": "1",
        "cost": "400",
    })
    result = service.build_sweep(context, {"cost": ["400", "450", "500"]})

    assert result["error"] is False
    for cell in result["cells"]:
        direct = scenario.calculate(
            cell["inputs"], identity=cell["scenario"]["identity"],
            provenance=cell["provenance"], sources=context["sources"],
        )
        assert cell["scenario"]["calculated"] == direct["calculated"]
    assert result["cells"][0]["scenario"]["calculated"]["tax"] == 4.0


def test_parallel_sweeps_are_isolated_and_do_not_mutate_shared_snapshot():
    service = _service()
    context = _context()
    before = deepcopy(context)
    with ThreadPoolExecutor(max_workers=2) as pool:
        price_future = pool.submit(service.build_sweep, context, {"price": ["450", "500", "550"]})
        cost_future = pool.submit(service.build_sweep, context, {"cost": ["100", "200", "300"]})
        price_result = price_future.result()
        cost_result = cost_future.result()

    assert price_result["error"] is False
    assert cost_result["error"] is False
    assert price_result["sensitivity_id"] != cost_result["sensitivity_id"]
    assert [cell["coordinates"] for cell in price_result["cells"]] != [
        cell["coordinates"] for cell in cost_result["cells"]
    ]
    assert context == before


def test_source_age_that_cannot_be_represented_safely_is_rejected():
    context = _context()
    context["source_age_seconds"] = "1e999999"
    assert _service().build_sweep(context, {"price": ["450", "500", "550"]})[
        "code"
    ] == "SENSITIVITY_SOURCE_FRESHNESS_UNKNOWN"
