from copy import deepcopy

from product_decision_user_action_learning_evidence_quality import (
    build_product_decision_user_action_learning_evidence_quality,
)


def _summary(observation_count=3, sku_count=2, **values):
    outcome_counts = {"NO_DECISION_CHANGE": observation_count}
    priority_counts = {"PRIORITY_UNCHANGED": observation_count}
    base = observation_count // sku_count
    remainder = observation_count % sku_count
    sku_counts = {
        "hook-%d" % (index + 1): (
            base + (1 if index < remainder else 0)
        )
        for index in range(sku_count)
    }
    outcome_ids = [
        "product-decision-user-action-post-decision-outcome:obs-%d"
        % index
        for index in range(observation_count)
    ]
    result = {
        "error": False,
        "status": "PRODUCT_DECISION_USER_ACTION_LEARNING_SUMMARY_READY",
        "observation_count": observation_count,
        "sku_count": sku_count,
        "outcome_counts": outcome_counts,
        "priority_change_counts": priority_counts,
        "sku_observation_counts": sku_counts,
        "outcome_ids": outcome_ids,
        "completion_evidence_source": "USER_REPORT",
        "learning_scope": "DESCRIPTIVE_OBSERVATIONS_ONLY",
        "causal_claim_allowed": False,
        "externally_verified": False,
        "persistent": False,
        "decision_rule_update_allowed": False,
        "automatic_execution_allowed": False,
        "execution_allowed": False,
        "execution_ready": False,
        "executed": False,
    }
    result.update(values)
    return result


def test_v931_non_mapping_summary_fails_closed():
    result = build_product_decision_user_action_learning_evidence_quality(
        ["not", "a", "mapping"]
    )

    assert result["error"] is True
    assert result["code"] == "LEARNING_EVIDENCE_QUALITY_SUMMARY_INPUT_INVALID"


def test_v932_missing_explicit_summary_error_marker_is_not_success():
    source = _summary()
    source.pop("error")

    result = build_product_decision_user_action_learning_evidence_quality(
        source
    )

    assert result["code"] == "LEARNING_EVIDENCE_QUALITY_SUMMARY_STATUS_INVALID"


def test_v933_string_observation_count_is_not_coerced():
    result = build_product_decision_user_action_learning_evidence_quality(
        _summary(observation_count="3")
    )

    assert result["code"] == "LEARNING_EVIDENCE_QUALITY_COUNTS_INVALID"


def test_v934_missing_observation_count_is_not_zero():
    source = _summary()
    source.pop("observation_count")

    result = build_product_decision_user_action_learning_evidence_quality(
        source
    )

    assert result["code"] == "LEARNING_EVIDENCE_QUALITY_COUNTS_INVALID"


def test_v935_outcome_count_sum_must_match_observations():
    result = build_product_decision_user_action_learning_evidence_quality(
        _summary(outcome_counts={"NO_DECISION_CHANGE": 2})
    )

    assert (
        result["code"]
        == "LEARNING_EVIDENCE_QUALITY_AGGREGATES_MISMATCH"
    )


def test_v936_sku_count_map_must_match_declared_sku_count():
    result = build_product_decision_user_action_learning_evidence_quality(
        _summary(sku_observation_counts={"hook-1": 3})
    )

    assert (
        result["code"]
        == "LEARNING_EVIDENCE_QUALITY_AGGREGATES_MISMATCH"
    )


def test_v937_duplicate_outcome_ids_cannot_support_quality():
    source = _summary()
    source["outcome_ids"][1] = source["outcome_ids"][0]

    result = build_product_decision_user_action_learning_evidence_quality(
        source
    )

    assert (
        result["code"]
        == "LEARNING_EVIDENCE_QUALITY_AGGREGATES_INVALID"
    )


def test_v938_noncanonical_outcome_count_key_blocks():
    result = build_product_decision_user_action_learning_evidence_quality(
        _summary(outcome_counts={"SOMETHING_HAPPENED": 3})
    )

    assert (
        result["code"]
        == "LEARNING_EVIDENCE_QUALITY_AGGREGATES_INVALID"
    )


def test_v939_zero_evidence_requires_all_aggregate_maps_empty():
    source = _summary()
    source.update(
        {
            "observation_count": 0,
            "sku_count": 0,
            "outcome_counts": {},
            "priority_change_counts": {},
            "sku_observation_counts": {},
            "outcome_ids": [],
        }
    )

    result = build_product_decision_user_action_learning_evidence_quality(
        source
    )

    assert result["error"] is False
    assert result["evidence_quality"] == "NO_EVIDENCE"
    assert result["evidence_quality_score"] == 0


def test_v940_valid_quality_is_deterministic_safe_and_non_mutating():
    source = _summary(observation_count=10, sku_count=2)
    before = deepcopy(source)

    first = build_product_decision_user_action_learning_evidence_quality(
        source
    )
    second = build_product_decision_user_action_learning_evidence_quality(
        source
    )

    assert first == second
    assert first["error"] is False
    assert first["evidence_quality"] == "DESCRIPTIVE_BASELINE"
    assert first["evidence_quality_score"] == 3
    assert first["observation_count"] == 10
    assert first["sku_count"] == 2
    assert sum(first["outcome_counts"].values()) == 10
    assert sum(first["sku_observation_counts"].values()) == 10
    assert len(first["outcome_ids"]) == 10
    assert first["completion_evidence_source"] == "USER_REPORT"
    assert first["quality_scope"] == "DESCRIPTIVE_OBSERVATIONS_ONLY"
    assert first["externally_verified"] is False
    assert first["persistent"] is False
    assert first["causal_inference_supported"] is False
    assert first["decision_rule_update_allowed"] is False
    assert first["automatic_execution_allowed"] is False
    assert first["execution_allowed"] is False
    assert first["execution_ready"] is False
    assert first["executed"] is False
    assert source == before
