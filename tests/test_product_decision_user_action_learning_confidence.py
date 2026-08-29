from product_decision_user_action_learning_confidence import build_product_decision_user_action_learning_confidence


def _quality(**values):
    result = {
        "status": "PRODUCT_DECISION_USER_ACTION_LEARNING_EVIDENCE_QUALITY_READY",
        "evidence_quality": "DESCRIPTIVE_BASELINE",
        "observation_count": 10,
        "sku_count": 2,
        "causal_inference_supported": False,
        "decision_rule_update_allowed": False,
        "automatic_execution_allowed": False,
        "executed": False,
    }
    result.update(values)
    return result


def test_none_below_three():
    assert build_product_decision_user_action_learning_confidence(_quality(observation_count=2, sku_count=1))["descriptive_confidence"] == "NONE"


def test_low_requires_three_observations():
    assert build_product_decision_user_action_learning_confidence(_quality(observation_count=3, sku_count=1))["descriptive_confidence"] == "LOW"


def test_medium_at_ten_across_two_skus():
    assert build_product_decision_user_action_learning_confidence(_quality())["descriptive_confidence"] == "MEDIUM"


def test_high_requires_thirty_and_three_skus():
    result = build_product_decision_user_action_learning_confidence(_quality(observation_count=30, sku_count=3))
    assert result["descriptive_confidence"] == "HIGH"
    assert result["causal_inference_supported"] is False
    assert result["decision_rule_update_allowed"] is False


def test_many_observations_one_sku_stays_low():
    assert build_product_decision_user_action_learning_confidence(_quality(observation_count=100, sku_count=1))["descriptive_confidence"] == "LOW"


def test_safety_violation_blocks():
    result = build_product_decision_user_action_learning_confidence(_quality(automatic_execution_allowed=True))
    assert result["code"] == "LEARNING_CONFIDENCE_SAFETY_BOUNDARY_VIOLATION"
