from copy import deepcopy
from decimal import Decimal

import pytest

from services.tax_service import TaxService
from services.unit_price_scenario_service import UnitPriceScenarioService
from services.unit_price_tariff_resolver import UnitPriceTariffResolver
from services.unit_price_tariff_snapshot_adapter import UnitPriceTariffSnapshotAdapter
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


_TARIFF_IDENTITY = {
    "owner_id": "owner-1", "user_id": "owner-1", "store_id": "store-1",
    "product_id": "product-1", "offer_id": "offer-1", "sku": "sku-1",
}


def _frozen_manual_tariff(bands=None, *, origin="MANUAL_SELLER_ASSUMPTION"):
    profile = {
        "profile_id": "profile-1", "revision": 1, "state_revision": 1,
        "owner_id": "owner-1", "store_id": "store-1",
        "identity": {key: _TARIFF_IDENTITY[key] for key in ("product_id", "offer_id", "sku")},
        "sale_schema": "FBO", "price_basis": "SELLER_PRICE_RUB", "currency": "RUB",
        "origin": origin,
        "source_ref": "synthetic-test" if origin == "MANUAL_SELLER_ASSUMPTION" else "current-price-api",
        "recorded_at": "2026-10-27T10:00:00+00:00",
        "observed_at": "2026-10-27T10:00:00+00:00" if origin != "MANUAL_SELLER_ASSUMPTION" else None,
        "effective_from": "2026-10-01", "effective_to": None,
        "confirmed_by_owner": True if origin == "MANUAL_SELLER_ASSUMPTION" else None,
        "bands": bands or [
            {"price_from_cents": 1, "price_to_cents": 10_000, "commission_rate": "11"},
            {"price_from_cents": 10_001, "price_to_cents": 30_000, "commission_rate": "22"},
        ],
    }
    price_cents = 10_000
    resolved = UnitPriceTariffResolver().resolve(
        seller_price_cents=price_cents, identity=_TARIFF_IDENTITY,
        sale_schema="FBO", effective_date="2026-10-27", profiles=[profile],
    )
    assert resolved["available"] is True
    return UnitPriceTariffSnapshotAdapter.freeze(
        resolved, profile, candidate_profiles=[profile], effective_date="2026-10-27",
    )


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


def test_target_and_break_even_prices_keep_historical_cross_docking_cost_fixed():
    planner, _ = _planner()
    values = _inputs(cross_docking_per_unit="12")

    result = planner.solve(values, "20")

    assert result["break_even"]["forward_result"]["calculated"]["cross_docking"] == 12.0
    assert result["target"]["forward_result"]["calculated"]["cross_docking"] == 12.0
    baseline = _planner()[0].solve(_inputs(), "20")
    assert Decimal(result["target"]["price"]) > Decimal(baseline["target"]["price"])


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
    [("50", "0", "0.02"), ("0", "50", None), ("49.99", "0.01", "0.02")],
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


def test_solver_prefers_a_small_verified_price_when_maximum_price_also_passes():
    planner, service = _planner(counting=True)
    values = _inputs(
        price="500",
        cost="0",
        commission_rate="50",
        logistics_per_unit="0",
        last_mile_per_unit="0",
        acquiring_per_unit="0",
        advertising_rate="0",
        discount_points_rate="0",
        tax_mode="NONE",
        tax_rate=None,
        minimum_tax_rate=None,
    )

    result = planner.solve(values, "50")

    outcome = result["target"]
    assert outcome["status"] == "FOUND"
    assert outcome["price"] == "0.02"
    assert Decimal(outcome["price"]) <= Decimal(values["price"])
    assert outcome["goal_reached"] is True
    assert result["evaluation_count"] == service.calls
    assert result["evaluation_count"] <= 127


def test_current_price_probe_accepts_calculator_decimal_comma_and_grouped_spaces():
    planner, _ = _planner()

    assert planner._current_price_cents({"price": "500,00"}) == 50_000
    assert planner._current_price_cents({"price": "1 234,56"}) == 123_456
    assert planner._current_price_cents({"price": "1\u00a0234,56"}) == 123_456
    assert planner._current_price_cents({"price": "5e2"}) == 50_000
    assert planner._current_price_cents({"price": "1.234,56"}) is None


@pytest.mark.parametrize(
    "price,expected_cents",
    [
        ("11.11", 1_111),
        ("11.110", 1_111),
        (Decimal("11.110"), 1_111),
        ("1.0000", 100),
        ("11.111", None),
    ],
)
def test_current_price_probe_normalizes_only_insignificant_trailing_zeros(
    price, expected_cents
):
    planner, _ = _planner()

    assert planner._current_price_cents({"price": price}) == expected_cents


def test_comparison_uses_candidate_specific_frozen_tariff_and_ranks_rounded_unit_profit():
    planner, service = _planner(counting=True)
    inputs = _inputs(
        price="100", cost="0", commission_rate="11", logistics_per_unit="0",
        last_mile_per_unit="0", acquiring_per_unit="0", advertising_rate="0",
        discount_points_rate="0", tax_mode="NONE", tax_rate=None,
        minimum_tax_rate=None,
    )
    frozen = _frozen_manual_tariff()

    result = planner.compare_prices(
        inputs, "99,99; 100,00; 100,01", identity=_TARIFF_IDENTITY,
        frozen_tariff_snapshot=frozen,
    )

    rows = result["rows"]
    assert [row["commission_rate"] for row in rows] == ["11", "11", "22"]
    assert [row["commission"] for row in rows] == [11.0, 11.0, 22.0]
    assert [row["profit"] for row in rows] == [88.99, 89.0, 78.01]
    assert result["baseline"]["price"] == "100.00"
    assert result["baseline"]["profit"] == 89.0
    assert [row["profit_delta_vs_baseline"] for row in rows] == ["-0.01", "0.00", "-10.99"]
    assert result["best_prices"] == ["100.00"]
    assert result["best_profit"] == "89.00"
    assert result["evidence_basis"] == "SCENARIO_ASSUMPTIONS"
    assert result["advertising_basis"]["mode"] == "SAME_DRR"
    assert result["advertising_basis"]["revenue_basis"] == "SELLER_REVENUE"
    assert result["advertising_basis"]["rate"] == "0"
    assert result["evaluation_count"] == service.calls
    assert 3 <= result["evaluation_count"] <= result["evaluation_limit"] == 1_024
    assert result["candidate_count"] == 3
    assert all(row["compensation_thresholds"]["status"] in {"COMPLETED", "PARTIAL"}
               for row in rows)


def test_target_search_checks_each_tariff_segment_and_keeps_lower_band_minimum():
    planner, _service = _planner(counting=True)
    inputs = _inputs(
        price="100", cost="50", commission_rate="11", logistics_per_unit="0",
        last_mile_per_unit="0", acquiring_per_unit="0", advertising_rate="0",
        discount_points_rate="0", tax_mode="NONE", tax_rate=None,
        minimum_tax_rate=None,
    )
    frozen = _frozen_manual_tariff()

    result = planner.solve(
        inputs, "30", identity=_TARIFF_IDENTITY,
        frozen_tariff_snapshot=frozen, tariff_resolution_required=True,
    )

    assert result["target"]["status"] == "FOUND"
    assert result["target"]["price"] == "84.75"
    assert result["target"]["commission_rate"] == "11"
    assert result["target"]["commission_origin"] == "MANUAL_SELLER_ASSUMPTION"
    assert result["target"]["previous_cent_check"] == "CALCULATED"
    assert result["target"]["previous_cent_goal_reached"] is False
    assert result["tariff_search"]["scope"] == "MINIMUM_AMONG_COVERED_TARIFF_SEGMENTS"
    assert result["tariff_search"]["global_minimum_claimed"] is False
    assert result["evaluation_count"] <= result["evaluation_limit"] == 1_024

    after_jump = planner.scenario_service.calculate({
        **inputs, "price": "100.01", "commission_rate": "22",
    })
    later_reachable = planner.scenario_service.calculate({
        **inputs, "price": "104.18", "commission_rate": "22",
    })
    assert after_jump["calculated"]["profit"] * 100 < 30 * 100.01
    assert later_reachable["calculated"]["profit"] * 100 >= 30 * 104.18


def test_target_search_continues_to_a_later_tariff_band_when_earlier_band_cannot_reach_goal():
    planner, _service = _planner(counting=True)
    inputs = _inputs(
        price="100", cost="1000", commission_rate="11", logistics_per_unit="0",
        last_mile_per_unit="0", acquiring_per_unit="0", advertising_rate="0",
        discount_points_rate="0", tax_mode="NONE", tax_rate=None,
        minimum_tax_rate=None,
    )
    frozen = _frozen_manual_tariff(bands=[
        {"price_from_cents": 1, "price_to_cents": 10_000, "commission_rate": "11"},
        {"price_from_cents": 10_001, "price_to_cents": 300_000, "commission_rate": "22"},
    ])

    result = planner.solve(
        inputs, "20", identity=_TARIFF_IDENTITY,
        frozen_tariff_snapshot=frozen, tariff_resolution_required=True,
    )

    assert result["target"]["status"] == "FOUND"
    assert Decimal(result["target"]["price"]) > Decimal("100.00")
    assert result["target"]["commission_rate"] == "22"
    assert result["target"]["goal_reached"] is True
    assert result["target"]["previous_cent_check"] == "CALCULATED"
    assert result["target"]["previous_cent_goal_reached"] is False
    assert result["evaluation_count"] <= result["evaluation_limit"] == 1_024


def test_target_search_reports_uncovered_price_gaps_instead_of_filling_them():
    planner, _service = _planner()
    inputs = _inputs(
        price="100", cost="50", commission_rate="11", logistics_per_unit="0",
        last_mile_per_unit="0", acquiring_per_unit="0", advertising_rate="0",
        discount_points_rate="0", tax_mode="NONE", tax_rate=None,
        minimum_tax_rate=None,
    )
    frozen = _frozen_manual_tariff(bands=[
        {"price_from_cents": 1, "price_to_cents": 10_000, "commission_rate": "11"},
        {"price_from_cents": 20_000, "price_to_cents": 30_000, "commission_rate": "22"},
    ])

    result = planner.solve(
        inputs, "30", identity=_TARIFF_IDENTITY,
        frozen_tariff_snapshot=frozen, tariff_resolution_required=True,
    )

    assert result["target"]["price"] == "84.75"
    assert { (gap["from"], gap["to"]) for gap in result["tariff_search"]["gaps"] } >= {
        ("100.01", "199.99"),
        ("300.01", format(planner.max_price, ".2f")),
    }
    assert result["tariff_search"]["coverage_complete"] is False
    assert result["tariff_search"]["global_minimum_claimed"] is False


def test_target_search_marks_profile_conflict_as_gap_and_does_not_pick_first_profile():
    planner, _service = _planner()
    inputs = _inputs(
        price="100", cost="50", commission_rate="11", logistics_per_unit="0",
        last_mile_per_unit="0", acquiring_per_unit="0", advertising_rate="0",
        discount_points_rate="0", tax_mode="NONE", tax_rate=None,
        minimum_tax_rate=None,
    )
    frozen = _frozen_manual_tariff()
    conflicting_profile = deepcopy(frozen["profiles"][0])
    conflicting_profile.update({
        "profile_id": "profile-conflict", "revision": 2, "state_revision": 2,
        "bands": [{
            "price_from_cents": 25_000, "price_to_cents": 26_000,
            "commission_rate": "10",
        }],
    })
    frozen["profiles"].append(conflicting_profile)

    result = planner.solve(
        inputs, "30", identity=_TARIFF_IDENTITY,
        frozen_tariff_snapshot=frozen, tariff_resolution_required=True,
    )

    assert result["error"] is False
    assert result["target"]["price"] == "84.75"
    assert {
        (gap["from"], gap["to"], gap["reason"])
        for gap in result["tariff_search"]["gaps"]
    } >= {("250.00", "260.00", "TARIFF_PROFILE_CONFLICT")}


def test_target_search_rejects_more_than_twenty_frozen_tariff_rules():
    planner, service = _planner(counting=True)
    inputs = _inputs(price="100", commission_rate="11")
    frozen = _frozen_manual_tariff()
    additional_profile = deepcopy(frozen["profiles"][0])
    additional_profile.update({
        "profile_id": "profile-many-rules", "revision": 2, "state_revision": 2,
        "bands": [{
            "price_from_cents": 31_000 + (index * 100),
            "price_to_cents": 31_099 + (index * 100),
            "commission_rate": "22",
        } for index in range(19)],
    })
    frozen["profiles"].append(additional_profile)

    result = planner.solve(
        inputs, "20", identity=_TARIFF_IDENTITY,
        frozen_tariff_snapshot=frozen, tariff_resolution_required=True,
    )

    assert result["error"] is True
    assert result["code"] == "TARIFF_RULE_LIMIT_EXCEEDED"
    assert service.calls == 0


def test_target_search_stays_within_budget_for_twenty_tariff_rules_and_gaps():
    planner, service = _planner(counting=True)
    inputs = _inputs(
        price="100", cost="100000000", commission_rate="11",
        logistics_per_unit="0", last_mile_per_unit="0", acquiring_per_unit="0",
        advertising_rate="0", discount_points_rate="0", tax_mode="NONE",
        tax_rate=None, minimum_tax_rate=None,
    )
    frozen = _frozen_manual_tariff(bands=[
        {
            "price_from_cents": 1 + (index * 20_000),
            "price_to_cents": 10_000 + (index * 20_000),
            "commission_rate": "11" if index % 2 == 0 else "22",
        }
        for index in range(20)
    ])

    result = planner.solve(
        inputs, "20", identity=_TARIFF_IDENTITY,
        frozen_tariff_snapshot=frozen, tariff_resolution_required=True,
    )

    assert result["target"]["status"] == "NOT_FOUND_IN_COVERED_SEGMENTS"
    assert result["tariff_search"]["rule_count"] == result["tariff_search"]["rule_limit"] == 20
    assert result["evaluation_count"] == service.calls
    assert result["evaluation_count"] <= result["evaluation_limit"] == 1_024


def test_target_search_stops_when_frozen_tariff_source_is_unavailable():
    planner, service = _planner(counting=True)
    inputs = _inputs(price="100", commission_rate=None)
    frozen = UnitPriceTariffSnapshotAdapter.freeze(
        {"available": False, "status": "SOURCE_UNAVAILABLE", "reason": "SOURCE_UNAVAILABLE",
         "seller_price_cents": 10_000, "price_basis": "SELLER_PRICE_RUB",
         "effective_date": "2026-10-27"},
        candidate_profiles=[], effective_date="2026-10-27",
    )

    result = planner.solve(
        inputs, "20", identity=_TARIFF_IDENTITY,
        frozen_tariff_snapshot=frozen, tariff_resolution_required=True,
    )

    assert result["error"] is False
    assert result["break_even"]["status"] == "SOURCE_UNAVAILABLE"
    assert result["target"]["status"] == "SOURCE_UNAVAILABLE"
    assert service.calls == 0


def test_target_search_refuses_a_segment_with_observed_non_monotonic_goal_predicate():
    class NonMonotonicScenario:
        MAX_INPUT_DIGITS = UnitPriceScenarioService.MAX_INPUT_DIGITS
        MAX_INPUT_ADJUSTED_EXPONENT = UnitPriceScenarioService.MAX_INPUT_ADJUSTED_EXPONENT

        @staticmethod
        def calculate(inputs, **_kwargs):
            price = Decimal(str(inputs["price"]))
            profit = price if price < Decimal("50") else Decimal("0")
            return {
                "error": False,
                "available": True,
                "calculated": {
                    "profit": float(profit),
                    "margin_percent": 100.0 if profit else 0.0,
                    "tax": 0.0,
                },
                "missing_inputs": [],
                "invalid_inputs": [],
            }

    planner = UnitPriceTargetPlanningService(NonMonotonicScenario())
    inputs = _inputs(
        price="100", cost="0", commission_rate="11", logistics_per_unit="0",
        last_mile_per_unit="0", acquiring_per_unit="0", advertising_rate="0",
        discount_points_rate="0", tax_mode="NONE", tax_rate=None,
        minimum_tax_rate=None,
    )

    result = planner.solve(
        inputs, "30", identity=_TARIFF_IDENTITY,
        frozen_tariff_snapshot=_frozen_manual_tariff(bands=[{
            "price_from_cents": 1, "price_to_cents": 10_000,
            "commission_rate": "11",
        }]),
        tariff_resolution_required=True,
    )

    assert result["target"]["status"] == "NON_MONOTONIC_SEGMENT"
    assert result["target"]["available"] is False


def test_target_search_returns_earliest_cent_when_rounded_goal_predicate_flickers():
    planner, service = _planner(counting=True)
    inputs = _inputs(
        price="100", cost="25", commission_rate="22",
        logistics_per_unit="0", last_mile_per_unit="0", acquiring_per_unit="0",
        advertising_rate="20", discount_points_rate="0", tax_mode="USN_INCOME",
        tax_rate="6", minimum_tax_rate="1",
    )
    frozen = _frozen_manual_tariff(bands=[{
        "price_from_cents": 1, "price_to_cents": 10_000,
        "commission_rate": "22",
    }])

    result = planner.solve(
        inputs, "10", identity=_TARIFF_IDENTITY,
        frozen_tariff_snapshot=frozen, tariff_resolution_required=True,
    )

    assert result["target"]["status"] == "FOUND"
    assert result["target"]["price"] == "59.52"
    assert result["evaluation_count"] == service.calls
    assert result["evaluation_count"] <= result["evaluation_limit"]
    at_candidate = UnitPriceScenarioService(TaxService()).calculate(
        {**inputs, "price": "59.52", "commission_rate": "22"},
    )
    previous_cent = UnitPriceScenarioService(TaxService()).calculate(
        {**inputs, "price": "59.51", "commission_rate": "22"},
    )
    assert planner._reached(at_candidate, Decimal("59.52"), Decimal("10"))
    assert not planner._reached(previous_cent, Decimal("59.51"), Decimal("10"))


def test_target_search_fails_closed_without_frozen_tariff_or_saved_exact_point():
    planner, service = _planner(counting=True)

    result = planner.solve(
        _inputs(price="100", commission_rate="11"), "20",
        identity=_TARIFF_IDENTITY, tariff_resolution_required=True,
    )

    assert result["target"]["status"] == "COMMISSION_UNKNOWN"
    assert result["break_even"]["status"] == "COMMISSION_UNKNOWN"
    assert result["evaluation_count"] == service.calls == 0
    assert result["tariff_search"]["global_minimum_claimed"] is False


def test_target_search_legacy_saved_rate_is_usable_only_at_its_exact_price():
    planner, _service = _planner(counting=True)
    inputs = _inputs(
        price="100", cost="0", commission_rate="11", logistics_per_unit="0",
        last_mile_per_unit="0", acquiring_per_unit="0", advertising_rate="0",
        discount_points_rate="0", tax_mode="NONE", tax_rate=None,
        minimum_tax_rate=None,
    )

    result = planner.solve(
        inputs, "80", identity=_TARIFF_IDENTITY,
        tariff_resolution_required=True, exact_price_rate_cents=10_000,
    )

    assert result["target"]["status"] == "FOUND"
    assert result["target"]["price"] == "100.00"
    assert result["target"]["commission_rate"] == "11"
    assert result["tariff_search"]["scope"] == "EXACT_SAVED_PRICE_ONLY"
    assert result["tariff_search"]["covered_segment_count"] == 1
    assert result["tariff_search"]["global_minimum_claimed"] is False


def test_current_price_point_does_not_create_numeric_profit_for_neighboring_prices():
    planner, _ = _planner()
    point_profile = {
        "profile_id": "point-1", "revision": 1, "state_revision": 1,
        "owner_id": "owner-1", "store_id": "store-1",
        "identity": {key: _TARIFF_IDENTITY[key] for key in ("product_id", "offer_id", "sku")},
        "sale_schema": "FBO", "price_basis": "SELLER_PRICE_RUB", "currency": "RUB",
        "origin": "CURRENT_PRICE_POINT", "source_ref": "current-price-api",
        "recorded_at": "2026-10-27T10:00:00+00:00",
        "observed_at": "2026-10-27T10:00:00+00:00",
        "effective_from": "2026-10-27", "effective_to": "2026-10-27",
        "confirmed_by_owner": None,
        "bands": [{"price_from_cents": 10_000, "price_to_cents": 10_000, "commission_rate": "14"}],
    }
    point = UnitPriceTariffResolver().resolve(
        seller_price_cents=10_000, identity=_TARIFF_IDENTITY, sale_schema="FBO",
        effective_date="2026-10-27", profiles=[point_profile],
    )
    frozen = UnitPriceTariffSnapshotAdapter.freeze(
        point, point_profile, candidate_profiles=[point_profile], effective_date="2026-10-27",
    )
    inputs = _inputs(
        price="100", cost="0", commission_rate="14", logistics_per_unit="0",
        last_mile_per_unit="0", acquiring_per_unit="0", advertising_rate="0",
        discount_points_rate="0", tax_mode="NONE", tax_rate=None,
        minimum_tax_rate=None,
    )

    result = planner.compare_prices(
        inputs, "99,99; 100; 100,01", identity=_TARIFF_IDENTITY,
        frozen_tariff_snapshot=frozen,
    )

    assert [row["available"] for row in result["rows"]] == [False, True, False]
    assert result["rows"][0]["profit"] is None
    assert result["rows"][2]["profit"] is None
    assert [row["status"] for row in result["rows"]] == [
        "COMMISSION_UNKNOWN", "CALCULATED", "COMMISSION_UNKNOWN",
    ]
    assert result["best_prices"] == ["100.00"]


def test_comparison_keeps_legacy_rate_only_at_its_exact_frozen_price():
    planner, _ = _planner()
    inputs = _inputs(
        price="100", commission_rate="14", cost="0", logistics_per_unit="0",
        last_mile_per_unit="0", acquiring_per_unit="0", advertising_rate="0",
        discount_points_rate="0", tax_mode="NONE", tax_rate=None,
        minimum_tax_rate=None,
    )

    result = planner.compare_prices(
        inputs, "100; 100,01", identity=_TARIFF_IDENTITY,
        tariff_resolution_required=True, exact_price_rate_cents=10_000,
    )

    assert result["rows"][0]["available"] is True
    assert result["rows"][1]["available"] is False
    assert result["rows"][0]["commission_status"] == "LEGACY_EXACT_PRICE_ONLY"
    assert result["rows"][1]["profit"] is None


def test_comparison_marks_all_equal_rounded_unit_profit_candidates_as_best():
    planner, _ = _planner()
    inputs = _inputs(
        price="100", cost="0", commission_rate="100", logistics_per_unit="0",
        last_mile_per_unit="0", acquiring_per_unit="0", advertising_rate="0",
        discount_points_rate="0", tax_mode="NONE", tax_rate=None,
        minimum_tax_rate=None,
    )

    result = planner.compare_prices(inputs, "99,99; 100")

    assert [row["profit"] for row in result["rows"]] == [0.0, 0.0]
    assert [row["is_best"] for row in result["rows"]] == [True, True]
    assert result["best_prices"] == ["99.99", "100.00"]
    assert result["best_profit"] == "0.00"


def test_price_list_parser_accepts_ten_candidates_and_rejects_eleven():
    planner, _ = _planner()

    ten = planner.parse_price_list("; ".join(str(price) for price in range(100, 110)))
    eleven = planner.parse_price_list("; ".join(str(price) for price in range(100, 111)))

    assert ten["valid"] is True
    assert len(ten["prices"]) == 10
    assert eleven["valid"] is False


def test_per_price_drr_reproduces_n01_compensation_example_and_distinct_n02_thresholds():
    planner, service = _planner(counting=True)
    inputs = _inputs(
        price="100", cost="20", commission_rate="24.2",
        logistics_per_unit="20", last_mile_per_unit="0",
        acquiring_per_unit="4.06", advertising_rate="16.5",
        discount_points_rate="0", tax_mode="NONE", tax_rate=None,
        minimum_tax_rate=None,
    )

    result = planner.compare_prices(
        inputs, "100; 95", advertising_mode="PER_PRICE_DRR",
        advertising_rates=["16.50", "12"],
    )

    assert [row["advertising_per_unit"] for row in result["rows"]] == [16.5, 11.4]
    assert [row["profit"] for row in result["rows"]] == [15.24, 16.55]
    assert result["baseline"]["profit"] == 15.24
    assert result["rows"][1]["profit_delta_vs_baseline"] == "1.31"
    assert result["advertising_basis"]["mode"] == "PER_PRICE_DRR"
    assert result["advertising_basis"]["revenue_basis"] == "SELLER_REVENUE"
    thresholds = result["rows"][1]["compensation_thresholds"]
    assert thresholds["non_worse"]["advertising_rate"] == "13.38"
    assert thresholds["non_worse"]["advertising_per_unit"] == "12.71"
    assert thresholds["strictly_better"]["advertising_rate"] == "13.37"
    assert thresholds["strictly_better"]["advertising_per_unit"] == "12.70"
    assert thresholds["non_worse"]["profit_per_unit"] == "15.24"
    assert thresholds["strictly_better"]["profit_per_unit"] == "15.25"
    assert result["evaluation_count"] == service.calls <= 1_024


def test_advertising_cost_is_weighted_by_successful_units_and_exact_denominator_is_returned():
    planner, _ = _planner()
    inputs = _inputs(
        price="100", cost="20", commission_rate="24.2",
        logistics_per_unit="20", last_mile_per_unit="0",
        acquiring_per_unit="4.06", advertising_rate="0",
        discount_points_rate="0", tax_mode="NONE", tax_rate=None,
        minimum_tax_rate=None,
    )
    basis = planner.parse_advertising_cost_basis("200; 40")
    result = planner.compare_prices(
        inputs, "100; 95", advertising_mode="MANUAL_COST_PER_SUCCESSFUL_UNIT",
        advertising_cost_basis=basis["basis"],
    )

    assert basis["valid"] is True
    assert basis["basis"]["amount_per_unit"] == "5.00"
    assert basis["basis"]["denominator"] == "SUCCESSFUL_UNITS"
    assert [row["advertising_per_unit"] for row in result["rows"]] == [5.0, 5.0]
    assert [row["advertising_rate"] for row in result["rows"]] == [None, None]
    assert result["advertising_basis"]["total_spend"] == "200.00"
    assert result["advertising_basis"]["successful_units"] == 40
    assert result["advertising_basis"]["amount_per_unit"] == "5.00"
    assert result["advertising_basis"]["revenue_basis"] == "NOT_APPLICABLE"


def test_absolute_advertising_above_price_stays_fixed_across_candidate_prices():
    planner, _ = _planner()
    inputs = _inputs(
        price="100", cost="20", commission_rate="10",
        logistics_per_unit="5", last_mile_per_unit="1", acquiring_per_unit="1",
        advertising_rate="0", discount_points_rate="0", tax_mode="NONE",
        tax_rate=None, minimum_tax_rate=None,
    )
    basis = planner.parse_advertising_cost_basis("2400; 20")
    result = planner.compare_prices(
        inputs, "100; 95", advertising_mode="MANUAL_COST_PER_SUCCESSFUL_UNIT",
        advertising_cost_basis=basis["basis"],
    )

    assert result["status"] == "COMPLETED"
    assert [row["available"] for row in result["rows"]] == [True, True]
    assert [row["advertising_per_unit"] for row in result["rows"]] == [120.0, 120.0]
    assert [row["advertising_rate"] for row in result["rows"]] == [None, None]
    assert [row["profit"] for row in result["rows"]] == [-57.0, -61.5]
    assert result["baseline"]["advertising_per_unit"] == 120.0
    assert result["advertising_basis"]["amount_per_unit"] == "120.00"
    assert [row["compensation_thresholds"]["status"] for row in result["rows"]] == [
        "FIXED_COST_BASIS_NOT_SOLVED", "FIXED_COST_BASIS_NOT_SOLVED",
    ]


@pytest.mark.parametrize("text", [
    "100", "100;0", "100;-1", "100;10001", "NaN;20", "100.001;20",
])
def test_advertising_cost_basis_rejects_missing_invalid_or_unbounded_denominators(text):
    planner, _ = _planner()

    result = planner.parse_advertising_cost_basis(text)

    assert result["valid"] is False


def test_compensation_threshold_uses_canonical_tax_dependent_on_ad_spend_and_checks_next_tick():
    planner, _ = _planner()
    inputs = _inputs(
        price="100", cost="20", commission_rate="24.2",
        logistics_per_unit="20", last_mile_per_unit="0",
        acquiring_per_unit="4.06", advertising_rate="16.5",
        discount_points_rate="0", tax_mode="USN_INCOME_MINUS_EXPENSES",
        tax_rate="15", minimum_tax_rate="1",
    )

    result = planner.compare_prices(
        inputs, "100; 95", advertising_mode="PER_PRICE_DRR",
        advertising_rates=["16.5", "12"],
    )

    baseline_profit = Decimal(str(result["baseline"]["profit"]))
    candidate = result["rows"][1]
    thresholds = candidate["compensation_thresholds"]
    assert candidate["available"] is True
    assert thresholds["non_worse"]["available"] is True
    assert thresholds["strictly_better"]["available"] is True
    for kind, predicate in (
        ("non_worse", lambda profit: profit >= baseline_profit),
        ("strictly_better", lambda profit: profit > baseline_profit),
    ):
        outcome = thresholds[kind]
        rate = Decimal(outcome["advertising_rate"])
        direct_inputs = dict(inputs)
        direct_inputs.update({
            "price": candidate["price"],
            "commission_rate": candidate["commission_rate"],
            "advertising_rate": outcome["advertising_rate"],
        })
        direct = planner.scenario_service.calculate(direct_inputs)
        next_inputs = dict(direct_inputs)
        next_inputs["advertising_rate"] = format(rate + Decimal("0.01"), ".2f")
        next_direct = planner.scenario_service.calculate(next_inputs)
        assert predicate(Decimal(str(direct["calculated"]["profit"])))
        assert not predicate(Decimal(str(next_direct["calculated"]["profit"])))
        assert outcome["tax_per_unit"] == format(
            Decimal(str(direct["calculated"]["tax"])), ".2f",
        )


def test_compensation_threshold_reports_non_worse_target_unreachable_at_zero_drr():
    planner, _ = _planner()
    inputs = _inputs(
        price="100", cost="20", commission_rate="24.2",
        logistics_per_unit="20", last_mile_per_unit="0",
        acquiring_per_unit="4.06", advertising_rate="16.5",
        discount_points_rate="0", tax_mode="NONE", tax_rate=None,
        minimum_tax_rate=None,
    )

    result = planner.compare_prices(
        inputs, "100;70", advertising_mode="PER_PRICE_DRR",
        advertising_rates=["16.5", "0"],
    )

    candidate = result["rows"][1]
    assert candidate["available"] is True
    assert candidate["profit"] < result["baseline"]["profit"]
    assert candidate["compensation_thresholds"]["non_worse"]["status"] == "NOT_REACHABLE"
    assert candidate["compensation_thresholds"]["strictly_better"]["status"] == "NOT_REACHABLE"


def test_price_grid_inserts_tariff_boundary_and_neighboring_cents_without_threshold_per_point():
    planner, service = _planner(counting=True)
    values = _inputs(
        price="100", commission_rate="11", cost="20",
        logistics_per_unit="20", last_mile_per_unit="0",
        acquiring_per_unit="4.06", advertising_rate="0",
        discount_points_rate="0", tax_mode="NONE", tax_rate=None,
        minimum_tax_rate=None,
    )
    snapshot = _frozen_manual_tariff()

    grid = planner.build_price_grid(
        "99.98;100.03;0.03", frozen_tariff_snapshot=snapshot,
        identity=_TARIFF_IDENTITY, inputs=values,
    )
    result = planner.compare_prices(
        values, grid["prices"], frozen_tariff_snapshot=snapshot,
        tariff_resolution_required=True, identity=_TARIFF_IDENTITY,
        price_grid_metadata=grid["metadata"],
    )

    assert grid["valid"] is True
    assert grid["normalized"] == ["99.98", "100.00", "100.01", "100.03"]
    assert grid["metadata"]["inserted_tariff_boundary_prices"] == ["100.00"]
    assert [row["commission_rate"] for row in result["rows"]] == ["11", "11", "22", "22"]
    assert [row["is_tariff_boundary"] for row in result["rows"]] == [False, True, True, False]
    assert result["global_optimum_claimed"] is False
    assert result["evaluation_count"] == service.calls == 5
    assert all(row["compensation_thresholds"]["status"] == "DEFERRED_UNTIL_CANDIDATE_SELECTED"
               for row in result["rows"])
    assert all("forward_result" not in row for row in result["rows"])


def test_price_grid_accepts_exact_two_hundred_candidates_with_bounded_forward_calls():
    planner, service = _planner(counting=True)
    values = _inputs(
        price="100", cost="0", commission_rate="10",
        logistics_per_unit="0", last_mile_per_unit="0",
        acquiring_per_unit="0", advertising_rate="0",
        discount_points_rate="0", tax_mode="NONE", tax_rate=None,
        minimum_tax_rate=None,
    )
    grid = planner.build_price_grid("1;2.99;0.01")

    result = planner.compare_prices(values, grid["prices"], price_grid_metadata=grid["metadata"])

    assert grid["valid"] is True
    assert len(result["rows"]) == result["candidate_count"] == 200
    assert result["evaluation_count"] == service.calls == 201  # Includes the separate baseline.
    assert result["evaluation_count"] <= result["evaluation_limit"] == 1_024
    assert all("forward_result" not in row for row in result["rows"])


def test_price_grid_keeps_profit_unknown_when_no_tariff_is_confirmed():
    planner, service = _planner(counting=True)
    grid = planner.build_price_grid("99;101;1")

    result = planner.compare_prices(
        _inputs(price="100", commission_rate="15"), grid["prices"],
        tariff_resolution_required=True, price_grid_metadata=grid["metadata"],
    )

    assert grid["valid"] is True
    assert result["available"] is False
    assert result["best_profit"] is None
    assert all(row["commission_status"] == "UNKNOWN" for row in result["rows"])
    assert all(row["profit"] is None for row in result["rows"])
    assert result["evaluation_count"] == service.calls == 0


def test_price_grid_comparison_rejects_metadata_that_omits_required_grid_points():
    planner, service = _planner(counting=True)
    values = _inputs(price="100", commission_rate="11")
    snapshot = _frozen_manual_tariff()
    grid = planner.build_price_grid(
        "99.98;100.03;0.03", frozen_tariff_snapshot=snapshot,
        identity=_TARIFF_IDENTITY, inputs=values,
    )
    truncated_metadata = dict(grid["metadata"])
    truncated_metadata["base_grid_count"] = 2
    truncated_metadata["candidate_count"] = 2
    truncated_metadata["searched_prices"] = ["99.98", "100.03"]
    truncated_metadata["tariff_boundary_prices"] = []
    truncated_metadata["inserted_tariff_boundary_prices"] = []

    result = planner.compare_prices(
        values, [Decimal("99.98"), Decimal("100.03")],
        frozen_tariff_snapshot=snapshot, tariff_resolution_required=True,
        identity=_TARIFF_IDENTITY, price_grid_metadata=truncated_metadata,
    )

    assert result["error"] is True
    assert result["code"] == "INVALID_PRICE_GRID"
    assert service.calls == 0


def test_price_grid_does_not_silently_truncate_when_base_or_tariff_points_exceed_limit():
    planner, _ = _planner()
    values = _inputs(price="100", commission_rate="11")
    too_many_base_points = planner.build_price_grid("1;3;0.01")

    bands = [{
        "price_from_cents": 1, "price_to_cents": 10_000,
        "commission_rate": "11",
    }]
    bands.extend({
        "price_from_cents": 10_001 + (index * 5),
        "price_to_cents": 10_002 + (index * 5),
        "commission_rate": "22",
    } for index in range(19))
    snapshot = _frozen_manual_tariff(bands=bands)
    too_many_boundary_points = planner.build_price_grid(
        "99;104;0.03", frozen_tariff_snapshot=snapshot,
        identity=_TARIFF_IDENTITY, inputs=values,
    )

    assert too_many_base_points == {
        "valid": False, "code": "PRICE_GRID_LIMIT",
        "required_candidates_at_least": 201, "candidate_limit": 200,
    }
    assert too_many_boundary_points["valid"] is False
    assert too_many_boundary_points["code"] == "PRICE_GRID_LIMIT"
    assert too_many_boundary_points["required_candidates"] > 200
    assert "prices" not in too_many_boundary_points


def test_price_grid_rejects_more_than_twenty_rules_across_frozen_profiles():
    planner, _ = _planner()
    values = _inputs(price="100", commission_rate="11")
    bands = [
        {"price_from_cents": 1, "price_to_cents": 9_999, "commission_rate": "11"},
        {"price_from_cents": 10_000, "price_to_cents": 10_000, "commission_rate": "11"},
    ]
    bands.extend({
        "price_from_cents": 10_000 + index * 10,
        "price_to_cents": 10_009 + index * 10,
        "commission_rate": "22",
    } for index in range(1, 10))
    snapshot = _frozen_manual_tariff(bands=bands)
    second_profile = dict(snapshot["profiles"][0])
    second_profile["profile_id"] = "profile-2"
    second_profile["revision"] = 2
    snapshot["profiles"].append(second_profile)

    result = planner.build_price_grid(
        "99;101;0.50", frozen_tariff_snapshot=snapshot,
        identity=_TARIFF_IDENTITY, inputs=values,
    )

    assert result == {
        "valid": False,
        "code": "PRICE_GRID_TARIFF_RULE_LIMIT",
        "tariff_rule_count": 22,
        "tariff_rule_limit": 20,
    }


def test_price_grid_parser_rejects_reversed_zero_step_or_excess_precision():
    planner, _ = _planner()

    for text in ("10;10;1", "11;10;1", "10;20;0", "10;20;0.001", "10;20", "NaN;20;1"):
        assert planner.parse_price_grid(text)["valid"] is False


def test_target_search_is_invariant_to_insignificant_trailing_price_zeros():
    outcomes = []
    for price in ("11.11", "11.110"):
        planner, _ = _planner()
        values = _inputs(
            price=price,
            cost="0",
            commission_rate="68.18",
            logistics_per_unit="0",
            last_mile_per_unit="0",
            acquiring_per_unit="0",
            advertising_rate="31.81",
            discount_points_rate="0",
            tax_mode="NONE",
            tax_rate=None,
            minimum_tax_rate=None,
        )
        direct = planner.scenario_service.calculate(values)
        result = planner.solve(values, "0.01")

        assert direct["available"] is True
        assert direct["calculated"]["profit"] == 0.01
        outcomes.append(result["target"])

    assert [outcome["price"] for outcome in outcomes] == ["11.08", "11.08"]
    assert all(outcome["goal_reached"] is True for outcome in outcomes)


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
    "500;600;700;800;900;1000;1100;1200;1300;1400;1500",
    "500; ;600",
])
def test_invalid_price_list_is_rejected_as_a_whole(text):
    planner, _ = _planner()

    result = planner.parse_price_list(text)

    assert result["error"] is True
    assert result["valid"] is False
    assert "prices" not in result


def test_comparison_preserves_input_order_and_keeps_compensation_work_bounded():
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
    assert result["evaluation_count"] == service.calls
    assert result["evaluation_count"] == 2
    assert result["evaluation_count"] <= result["evaluation_limit"] == 1_024
    assert all(row["compensation_thresholds"]["status"] == "BASELINE_UNAVAILABLE"
               for row in result["rows"])
    assert all(row["compensation_thresholds"] for row in result["rows"])
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


def test_caller_can_tighten_solver_forward_evaluation_budget():
    planner, service = _planner(counting=True)

    result = planner.solve(_inputs(), "30", max_evaluations=4)

    assert result["evaluation_count"] == service.calls <= 4
    assert result["evaluation_limit"] == 4
    assert result["target"]["status"] == "SEARCH_BUDGET_EXHAUSTED"


def test_comparison_keeps_unavailable_scenarios_distinct_from_target_failure():
    planner, _ = _planner()
    values = _inputs()
    values["acquiring_per_unit"] = None

    result = planner.compare_prices(values, "450; 500", target_margin_percent="20")

    assert all(not row["available"] for row in result["rows"])
    assert all(row["goal_reached"] is None for row in result["rows"])
    assert {row["status"] for row in result["rows"]} == {"MISSING_INPUTS"}
    assert all(row["missing_inputs"] == ["acquiring_per_unit"] for row in result["rows"])
