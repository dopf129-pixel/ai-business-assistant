from copy import deepcopy
from decimal import Decimal

from services.unit_economics_experiment_recommendation_service import (
    UnitEconomicsExperimentRecommendationService,
)
from test_unit_economics_experiment_phase_comparison_service import _collection, _evaluate


def _result(*, outcome=None, candidate_profit=None, baseline_collection="1" * 64,
            candidate_collection="2" * 64, baseline_revision=2):
    if candidate_profit is not None:
        finance_net = Decimal(candidate_profit) * 30 + Decimal("300.00")
    elif outcome == "BASELINE_BETTER_IN_MODEL":
        finance_net = Decimal("800.00")
    elif outcome == "NO_CLEAR_DIFFERENCE":
        finance_net = Decimal("1000.30")
    else:
        finance_net = Decimal("1100.00")
    experiment = None
    if outcome == "NO_CLEAR_DIFFERENCE":
        experiment = {"config": {
            "calculation_mode": "WINDOW_COST_ALLOCATION", "decision_threshold_rub": "0.02",
        }}
    evaluated = _evaluate(
        candidate=_collection(
            "2026-08-08", "2026-08-14", "2026-08-15T12:00:00Z",
            finance_net=str(finance_net),
        ),
        experiment=experiment,
    )
    if outcome in {"CONTINUE_COLLECTING", "FIX_DATA_OR_CONDITIONS", "INCOMPARABLE"}:
        evaluated.update({
            "outcome": outcome,
            "status": {
                "CONTINUE_COLLECTING": "WAITING_FOR_DATA",
                "FIX_DATA_OR_CONDITIONS": "INSUFFICIENT_DATA",
                "INCOMPARABLE": "INCOMPARABLE",
            }[outcome],
            "quality_gates": [{"gate": "COMPARABILITY_01", "status": "FAIL",
                               "reason_code": "SYNTHETIC_GATE_FAILURE"}],
            "baseline_profit_per_unit_rub": None,
            "candidate_profit_per_unit_rub": None,
            "delta_profit_per_unit_rub": None,
            "quantity_basis": None,
            "comparison": None,
        })
    comparison = deepcopy(evaluated["comparison"])
    if comparison:
        comparison["baseline_collection_hash"] = baseline_collection
        comparison["candidate_collection_hash"] = candidate_collection
        comparison["baseline_readiness_revision"] = baseline_revision
    return {
        "schema_version": 2, "status": evaluated["status"],
        "source_as_of": evaluated["source_as_of"],
        "snapshot_refs": [baseline_collection, candidate_collection],
        "baseline_profit_per_unit_rub": evaluated["baseline_profit_per_unit_rub"],
        "candidate_profit_per_unit_rub": evaluated["candidate_profit_per_unit_rub"],
        "delta_profit_per_unit_rub": evaluated["delta_profit_per_unit_rub"],
        "quantity_basis": evaluated["quantity_basis"],
        "window": comparison["candidate"]["window"] if comparison else None,
        "quality_gates": evaluated["quality_gates"], "limitations": evaluated["limitations"],
        "outcome": evaluated["outcome"], "comparison": comparison,
    }


def test_recommendation_has_explanations_and_next_step_for_every_outcome():
    outcomes = (
        "CONTINUE_COLLECTING", "FIX_DATA_OR_CONDITIONS", "INCOMPARABLE",
        "NO_CLEAR_DIFFERENCE", "CANDIDATE_BETTER_IN_MODEL", "BASELINE_BETTER_IN_MODEL",
    )
    for outcome in outcomes:
        recommendation = UnitEconomicsExperimentRecommendationService.explain_result(
            _result(outcome=outcome),
        )
        assert recommendation.get("error") is not True
        assert recommendation["outcome"] == outcome
        assert recommendation["explanation"]
        assert recommendation["next_step"]
        assert recommendation["changes_ozon_price"] is False


def test_ranking_uses_only_evaluated_compatible_candidate_results_and_keeps_ties():
    baseline_hash = "1" * 64
    candidates = [
        {"phase_id": "a" * 32, "result_revision": 1, "latest_result_revision": 1,
         "payload": _result(candidate_profit="26.67", baseline_collection=baseline_hash)},
        {"phase_id": "b" * 32, "result_revision": 1, "latest_result_revision": 1,
         "payload": _result(candidate_profit="26.67", baseline_collection=baseline_hash,
                            candidate_collection="3" * 64)},
        {"phase_id": "c" * 32, "result_revision": 1, "latest_result_revision": 1,
         "payload": _result(outcome="INCOMPARABLE", baseline_collection=baseline_hash)},
    ]
    ranking = UnitEconomicsExperimentRecommendationService.rank_evaluated_candidates(candidates)
    assert ranking["status"] == "RANKED"
    assert ranking["evaluated_candidate_count"] == 2
    assert ranking["excluded_candidate_count"] == 1
    assert ranking["best_phase_ids"] == ["a" * 32, "b" * 32]
    assert ranking["maximum_profit_per_unit_rub"] == "26.67"


def test_ranking_refuses_candidate_sets_with_different_baseline_evidence():
    candidates = [
        {"phase_id": "a" * 32, "result_revision": 1, "latest_result_revision": 1,
         "payload": _result()},
        {"phase_id": "b" * 32, "result_revision": 1, "latest_result_revision": 1,
         "payload": _result(candidate_profit="30.00", baseline_collection="9" * 64)},
    ]
    ranking = UnitEconomicsExperimentRecommendationService.rank_evaluated_candidates(candidates)
    assert ranking["status"] == "INCOMPARABLE_CANDIDATE_BASES"
    assert "best_phase_ids" not in ranking


def test_ranking_rejects_unbounded_or_duplicate_candidate_input():
    one = {
        "phase_id": "a" * 32, "result_revision": 1,
        "latest_result_revision": 1, "payload": _result(),
    }
    assert UnitEconomicsExperimentRecommendationService.rank_evaluated_candidates(
        [one] * 11,
    )["status"] == "UNAVAILABLE"
    assert UnitEconomicsExperimentRecommendationService.rank_evaluated_candidates(
        [one, one],
    )["status"] == "UNAVAILABLE"


def test_ranking_excludes_superseded_result_revisions():
    phase_id = "a" * 32
    ranking = UnitEconomicsExperimentRecommendationService.rank_evaluated_candidates([
        {"phase_id": phase_id, "result_revision": 1, "latest_result_revision": 2,
         "payload": _result(candidate_profit="40.00")},
        {"phase_id": phase_id, "result_revision": 2, "latest_result_revision": 2,
         "payload": _result(candidate_profit="26.67")},
    ])
    assert ranking["status"] == "RANKED"
    assert ranking["evaluated_candidate_count"] == 1
    assert ranking["maximum_profit_per_unit_rub"] == "26.67"


def test_explanations_return_only_allowlisted_reason_codes():
    payload = _result(outcome="FIX_DATA_OR_CONDITIONS")
    payload["quality_gates"][0]["reason_code"] = "USER_SKU_AND_NAME_SHOULD_NOT_ECHO"
    recommendation = UnitEconomicsExperimentRecommendationService.explain_result(payload)
    assert recommendation["reason_codes"] == ["UNRECOGNIZED_QUALITY_REASON"]
    assert "USER_SKU" not in recommendation["explanation"]
