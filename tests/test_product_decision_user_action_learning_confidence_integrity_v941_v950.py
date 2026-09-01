from copy import deepcopy

from product_decision_user_action_learning_confidence import (
    build_product_decision_user_action_learning_confidence,
)


def _quality(observation_count=10, sku_count=2, **values):
    if observation_count == 0:
        quality_name = "NO_EVIDENCE"
        quality_score = 0
        outcome_counts = {}
        priority_counts = {}
        sku_counts = {}
        outcome_ids = []
    else:
        if observation_count < 3:
            quality_name = "VERY_LIMITED"
            quality_score = 1
        elif observation_count < 10 or sku_count < 2:
            quality_name = "LIMITED"
            quality_score = 2
        else:
            quality_name = "DESCRIPTIVE_BASELINE"
            quality_score = 3

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
        "status":
            "PRODUCT_DECISION_USER_ACTION_LEARNING_EVIDENCE_QUALITY_READY",
        "evidence_quality": quality_name,
        "evidence_quality_score": quality_score,
        "observation_count": observation_count,
        "sku_count": sku_count,
        "outcome_counts": outcome_counts,
        "priority_change_counts": priority_counts,
        "sku_observation_counts": sku_counts,
        "outcome_ids": outcome_ids,
        "completion_evidence_source": "USER_REPORT",
        "quality_scope": "DESCRIPTIVE_OBSERVATIONS_ONLY",
        "externally_verified": False,
        "persistent": False,
        "causal_inference_supported": False,
        "decision_rule_update_allowed": False,
        "automatic_execution_allowed": False,
        "execution_allowed": False,
        "execution_ready": False,
        "executed": False,
    }
    result.update(values)
    return result


def test_v941_non_mapping_quality_fails_closed():
    result = build_product_decision_user_action_learning_confidence(
        ["not", "a", "mapping"]
    )

    assert result["error"] is True
    assert result["code"] == "LEARNING_CONFIDENCE_QUALITY_INPUT_INVALID"


def test_v942_missing_explicit_quality_error_marker_is_not_success():
    source = _quality()
    source.pop("error")

    result = build_product_decision_user_action_learning_confidence(source)

    assert result["code"] == "LEARNING_CONFIDENCE_QUALITY_STATUS_INVALID"


def test_v943_string_observation_count_is_not_coerced():
    source = _quality()
    source["observation_count"] = "10"

    result = build_product_decision_user_action_learning_confidence(source)

    assert result["code"] == "LEARNING_CONFIDENCE_COUNTS_INVALID"


def test_v944_string_quality_score_is_not_coerced():
    source = _quality()
    source["evidence_quality_score"] = "3"

    result = build_product_decision_user_action_learning_confidence(source)

    assert result["code"] == "LEARNING_CONFIDENCE_QUALITY_FIELDS_INVALID"


def test_v945_quality_score_mismatch_blocks():
    source = _quality()
    source["evidence_quality_score"] = 2

    result = build_product_decision_user_action_learning_confidence(source)

    assert (
        result["code"]
        == "LEARNING_CONFIDENCE_QUALITY_SAMPLE_MISMATCH"
    )


def test_v946_aggregate_sum_mismatch_blocks():
    source = _quality()
    source["outcome_counts"] = {"NO_DECISION_CHANGE": 9}

    result = build_product_decision_user_action_learning_confidence(source)

    assert result["code"] == "LEARNING_CONFIDENCE_AGGREGATES_MISMATCH"


def test_v947_duplicate_outcome_ids_cannot_support_confidence():
    source = _quality()
    source["outcome_ids"][1] = source["outcome_ids"][0]

    result = build_product_decision_user_action_learning_confidence(source)

    assert result["code"] == "LEARNING_CONFIDENCE_AGGREGATES_INVALID"


def test_v948_quality_name_must_match_sample_shape():
    source = _quality(observation_count=2, sku_count=1)
    source["evidence_quality"] = "DESCRIPTIVE_BASELINE"
    source["evidence_quality_score"] = 3

    result = build_product_decision_user_action_learning_confidence(source)

    assert (
        result["code"]
        == "LEARNING_CONFIDENCE_QUALITY_SAMPLE_MISMATCH"
    )


def test_v949_high_confidence_keeps_existing_threshold():
    result = build_product_decision_user_action_learning_confidence(
        _quality(observation_count=30, sku_count=3)
    )

    assert result["error"] is False
    assert result["descriptive_confidence"] == "HIGH"
    assert result["minimum_sample_required"] == 30


def test_v950_valid_confidence_is_deterministic_safe_and_non_mutating():
    source = _quality(observation_count=10, sku_count=2)
    before = deepcopy(source)

    first = build_product_decision_user_action_learning_confidence(source)
    second = build_product_decision_user_action_learning_confidence(source)

    assert first == second
    assert first["error"] is False
    assert first["evidence_quality"] == "DESCRIPTIVE_BASELINE"
    assert first["evidence_quality_score"] == 3
    assert first["observation_count"] == 10
    assert first["sku_count"] == 2
    assert sum(first["outcome_counts"].values()) == 10
    assert sum(first["priority_change_counts"].values()) == 10
    assert sum(first["sku_observation_counts"].values()) == 10
    assert len(first["outcome_ids"]) == 10
    assert first["completion_evidence_source"] == "USER_REPORT"
    assert first["descriptive_confidence"] == "MEDIUM"
    assert first["minimum_sample_required"] == 10
    assert first["confidence_scope"] == "DESCRIPTIVE_PATTERN_CONFIDENCE_ONLY"
    assert first["externally_verified"] is False
    assert first["persistent"] is False
    assert first["causal_inference_supported"] is False
    assert first["decision_rule_update_allowed"] is False
    assert first["automatic_execution_allowed"] is False
    assert first["execution_allowed"] is False
    assert first["execution_ready"] is False
    assert first["executed"] is False
    assert source == before
