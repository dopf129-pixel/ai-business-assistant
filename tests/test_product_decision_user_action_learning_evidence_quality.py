from product_decision_user_action_learning_evidence_quality import (
    build_product_decision_user_action_learning_evidence_quality,
)


def _summary(observation_count=0, sku_count=0, **values):
    if observation_count == 0:
        outcome_counts = {}
        priority_counts = {}
        sku_counts = {}
        outcome_ids = []
    else:
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


def test_no_evidence():
    result = build_product_decision_user_action_learning_evidence_quality(
        _summary()
    )
    assert result["evidence_quality"] == "NO_EVIDENCE"
    assert result["causal_inference_supported"] is False


def test_very_limited_evidence():
    result = build_product_decision_user_action_learning_evidence_quality(
        _summary(observation_count=2, sku_count=1)
    )
    assert result["evidence_quality"] == "VERY_LIMITED"


def test_limited_evidence():
    result = build_product_decision_user_action_learning_evidence_quality(
        _summary(observation_count=5, sku_count=2)
    )
    assert result["evidence_quality"] == "LIMITED"


def test_descriptive_baseline_requires_ten_observations_and_two_skus():
    result = build_product_decision_user_action_learning_evidence_quality(
        _summary(observation_count=10, sku_count=2)
    )
    assert result["evidence_quality"] == "DESCRIPTIVE_BASELINE"
    assert result["decision_rule_update_allowed"] is False


def test_one_sku_remains_limited_even_with_many_observations():
    result = build_product_decision_user_action_learning_evidence_quality(
        _summary(observation_count=20, sku_count=1)
    )
    assert result["evidence_quality"] == "LIMITED"


def test_safety_violation_blocks():
    result = build_product_decision_user_action_learning_evidence_quality(
        _summary(decision_rule_update_allowed=True)
    )
    assert (
        result["code"]
        == "LEARNING_EVIDENCE_QUALITY_SAFETY_BOUNDARY_VIOLATION"
    )
