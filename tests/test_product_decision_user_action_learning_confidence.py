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


def test_none_below_three():
    result = build_product_decision_user_action_learning_confidence(
        _quality(observation_count=2, sku_count=1)
    )
    assert result["descriptive_confidence"] == "NONE"


def test_low_requires_three_observations():
    result = build_product_decision_user_action_learning_confidence(
        _quality(observation_count=3, sku_count=1)
    )
    assert result["descriptive_confidence"] == "LOW"


def test_medium_at_ten_across_two_skus():
    result = build_product_decision_user_action_learning_confidence(
        _quality()
    )
    assert result["descriptive_confidence"] == "MEDIUM"


def test_high_requires_thirty_and_three_skus():
    result = build_product_decision_user_action_learning_confidence(
        _quality(observation_count=30, sku_count=3)
    )
    assert result["descriptive_confidence"] == "HIGH"
    assert result["causal_inference_supported"] is False
    assert result["decision_rule_update_allowed"] is False


def test_many_observations_one_sku_stays_low():
    result = build_product_decision_user_action_learning_confidence(
        _quality(observation_count=100, sku_count=1)
    )
    assert result["descriptive_confidence"] == "LOW"


def test_safety_violation_blocks():
    result = build_product_decision_user_action_learning_confidence(
        _quality(automatic_execution_allowed=True)
    )
    assert (
        result["code"]
        == "LEARNING_CONFIDENCE_SAFETY_BOUNDARY_VIOLATION"
    )
