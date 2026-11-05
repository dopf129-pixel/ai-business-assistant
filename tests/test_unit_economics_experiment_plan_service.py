from copy import deepcopy

import pytest

from services.unit_economics_experiment_plan_service import (
    UnitEconomicsExperimentPlanService,
)


def _config():
    return {
        "metric": "MAX_RUB_PER_UNIT",
        "candidate_price_bounds_cents": {
            "min_price_cents": 9500, "max_price_cents": 10500,
        },
        "candidate_prices_cents": [9700, 10000, 10300],
        "decision_threshold_rub": "0.01",
        "planned_duration_days": 7,
        "maturity_min_days": 7,
        "maturity_min_units": 30,
    }


@pytest.mark.parametrize("bounds,expected", [
    (None, None),
    ({"min_price_cents": 1, "max_price_cents": 1},
     {"min_price_cents": 1, "max_price_cents": 1}),
    ({"min_price_cents": 1, "max_price_cents": 99_999_999_999_999},
     {"min_price_cents": 1, "max_price_cents": 99_999_999_999_999}),
])
def test_normalize_price_bounds_accepts_supported_cent_ranges(bounds, expected):
    assert UnitEconomicsExperimentPlanService.normalize_price_bounds(bounds) == expected


@pytest.mark.parametrize("bounds", [
    {},
    {"min_price_cents": True, "max_price_cents": 100},
    {"min_price_cents": 101, "max_price_cents": 100},
    {"min_price_cents": 0, "max_price_cents": 100},
    {"min_price_cents": 1, "max_price_cents": 100_000_000_000_000},
    {"min_price_cents": 1, "max_price_cents": 100, "extra": 1},
])
def test_normalize_price_bounds_rejects_impossible_or_unknown_values(bounds):
    assert UnitEconomicsExperimentPlanService.normalize_price_bounds(bounds) is None


def test_complete_plan_keeps_target_in_rubles_per_unit_and_is_ready():
    result = UnitEconomicsExperimentPlanService.evaluate(_config())

    assert result == {
        "error": False, "status": "READY", "eligible_for_ready": True,
        "target_metric": "MAX_RUB_PER_UNIT", "planned_duration_days": 7,
        "minimum_maturity_days": 7, "minimum_maturity_units": 30,
        "reason_codes": [],
    }


def test_incomplete_draft_is_preserved_as_incomplete_not_ready():
    draft = _config()
    draft["candidate_price_bounds_cents"] = None
    draft["candidate_prices_cents"] = []

    result = UnitEconomicsExperimentPlanService.evaluate(draft)

    assert result["error"] is False
    assert result["status"] == "INCOMPLETE"
    assert result["eligible_for_ready"] is False
    assert result["target_metric"] == "MAX_RUB_PER_UNIT"
    assert result["reason_codes"] == [
        "EXPERIMENT_CANDIDATES_REQUIRED", "EXPERIMENT_PRICE_BOUNDS_REQUIRED",
    ]


@pytest.mark.parametrize("field,value,reason", [
    ("metric", "TOTAL_PROFIT", "EXPERIMENT_TARGET_METRIC_UNSUPPORTED"),
    ("planned_duration_days", 2, "EXPERIMENT_DURATION_OUT_OF_RANGE"),
    ("planned_duration_days", 29, "EXPERIMENT_DURATION_OUT_OF_RANGE"),
    ("decision_threshold_rub", "0", "EXPERIMENT_DECISION_THRESHOLD_INVALID"),
    ("decision_threshold_rub", "NaN", "EXPERIMENT_DECISION_THRESHOLD_INVALID"),
    ("maturity_min_days", 6, "EXPERIMENT_MATURITY_DAYS_INVALID"),
    ("maturity_min_units", 29, "EXPERIMENT_MATURITY_UNITS_INVALID"),
])
def test_impossible_plan_inputs_never_pass_ready_gate(field, value, reason):
    config = deepcopy(_config())
    config[field] = value

    result = UnitEconomicsExperimentPlanService.evaluate(config)

    assert result["error"] is False
    assert result["eligible_for_ready"] is False
    assert reason in result["reason_codes"]


def test_candidate_outside_price_bounds_never_passes_ready_gate():
    config = _config()
    config["candidate_prices_cents"] = [9499, 10000]

    result = UnitEconomicsExperimentPlanService.evaluate(config)

    assert result["eligible_for_ready"] is False
    assert "EXPERIMENT_CANDIDATE_OUTSIDE_BOUNDS" in result["reason_codes"]


def test_duplicate_candidate_prices_do_not_pass_ready_gate():
    config = _config()
    config["candidate_prices_cents"] = [10000, 10000]

    result = UnitEconomicsExperimentPlanService.evaluate(config)

    assert result["eligible_for_ready"] is False
    assert "EXPERIMENT_CANDIDATE_PRICE_INVALID" in result["reason_codes"]


@pytest.mark.parametrize("prices", [[], [10000], [10000] * 11])
def test_candidate_count_requires_two_to_ten_options(prices):
    config = _config()
    config["candidate_prices_cents"] = prices

    result = UnitEconomicsExperimentPlanService.evaluate(config)

    assert result["eligible_for_ready"] is False
    assert "EXPERIMENT_CANDIDATES_REQUIRED" in result["reason_codes"]
