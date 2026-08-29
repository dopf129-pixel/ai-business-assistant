from product_decision_user_action_learning_advisory_quality_signal import build_product_decision_user_action_learning_advisory_quality_signal


def _summary(**values):
    result = {
        "status": "PRODUCT_DECISION_USER_ACTION_LEARNING_ADVISORY_EVALUATION_SUMMARY_READY",
        "review_count": 10,
        "human_reported_usefulness_rate": 0.8,
        "evaluation_scope": "HUMAN_REPORTED_ADVISORY_USEFULNESS_ONLY",
        "causal_claim_allowed": False,
        "decision_rule_update_allowed": False,
        "automatic_execution_allowed": False,
        "executed": False,
    }
    result.update(values)
    return result


def test_high_reported_usefulness():
    result = build_product_decision_user_action_learning_advisory_quality_signal(_summary())
    assert result["quality_signal"] == "HIGH_REPORTED_USEFULNESS"
    assert result["automatic_advisory_change_allowed"] is False


def test_mixed_recommends_human_improvement_review():
    result = build_product_decision_user_action_learning_advisory_quality_signal(_summary(human_reported_usefulness_rate=0.6))
    assert result["quality_signal"] == "MIXED_REPORTED_USEFULNESS"
    assert result["advisory_improvement_review_recommended"] is True


def test_low_recommends_human_improvement_review():
    result = build_product_decision_user_action_learning_advisory_quality_signal(_summary(human_reported_usefulness_rate=0.2))
    assert result["quality_signal"] == "LOW_REPORTED_USEFULNESS"
    assert result["advisory_improvement_review_recommended"] is True


def test_fewer_than_five_reviews_is_insufficient():
    result = build_product_decision_user_action_learning_advisory_quality_signal(_summary(review_count=4, human_reported_usefulness_rate=1.0))
    assert result["quality_signal"] == "INSUFFICIENT_REVIEWS"


def test_safety_violation_blocks():
    result = build_product_decision_user_action_learning_advisory_quality_signal(_summary(decision_rule_update_allowed=True))
    assert result["code"] == "LEARNING_ADVISORY_QUALITY_SAFETY_BOUNDARY_VIOLATION"
