from product_decision_user_action_learning_evidence_quality import build_product_decision_user_action_learning_evidence_quality


def _summary(**values):
    result = {
        "status": "PRODUCT_DECISION_USER_ACTION_LEARNING_SUMMARY_READY",
        "observation_count": 0,
        "sku_count": 0,
        "outcome_counts": {},
        "learning_scope": "DESCRIPTIVE_OBSERVATIONS_ONLY",
        "causal_claim_allowed": False,
        "decision_rule_update_allowed": False,
        "automatic_execution_allowed": False,
        "executed": False,
    }
    result.update(values)
    return result


def test_no_evidence():
    result = build_product_decision_user_action_learning_evidence_quality(_summary())
    assert result["evidence_quality"] == "NO_EVIDENCE"
    assert result["causal_inference_supported"] is False


def test_very_limited_evidence():
    result = build_product_decision_user_action_learning_evidence_quality(_summary(observation_count=2, sku_count=1))
    assert result["evidence_quality"] == "VERY_LIMITED"


def test_limited_evidence():
    result = build_product_decision_user_action_learning_evidence_quality(_summary(observation_count=5, sku_count=2))
    assert result["evidence_quality"] == "LIMITED"


def test_descriptive_baseline_requires_ten_observations_and_two_skus():
    result = build_product_decision_user_action_learning_evidence_quality(_summary(observation_count=10, sku_count=2))
    assert result["evidence_quality"] == "DESCRIPTIVE_BASELINE"
    assert result["decision_rule_update_allowed"] is False


def test_one_sku_remains_limited_even_with_many_observations():
    result = build_product_decision_user_action_learning_evidence_quality(_summary(observation_count=20, sku_count=1))
    assert result["evidence_quality"] == "LIMITED"


def test_safety_violation_blocks():
    result = build_product_decision_user_action_learning_evidence_quality(_summary(decision_rule_update_allowed=True))
    assert result["code"] == "LEARNING_EVIDENCE_QUALITY_SAFETY_BOUNDARY_VIOLATION"
