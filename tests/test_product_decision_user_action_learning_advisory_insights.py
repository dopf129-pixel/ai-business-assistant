from product_decision_user_action_learning_advisory_insights import build_product_decision_user_action_learning_advisory_insights


def _summary(**values):
    result = {
        "status": "PRODUCT_DECISION_USER_ACTION_LEARNING_SUMMARY_READY",
        "observation_count": 3,
        "outcome_counts": {"DECISION_CHANGED": 2, "NO_DECISION_CHANGE": 1},
        "priority_change_counts": {"PRIORITY_DECREASED": 2},
        "causal_claim_allowed": False,
        "decision_rule_update_allowed": False,
        "automatic_execution_allowed": False,
        "executed": False,
    }
    result.update(values)
    return result


def _confidence(**values):
    result = {
        "status": "PRODUCT_DECISION_USER_ACTION_LEARNING_CONFIDENCE_READY",
        "descriptive_confidence": "LOW",
        "causal_inference_supported": False,
        "decision_rule_update_allowed": False,
        "automatic_execution_allowed": False,
        "executed": False,
    }
    result.update(values)
    return result


def test_builds_advisory_insights_only():
    result = build_product_decision_user_action_learning_advisory_insights(_summary(), _confidence())
    assert result["status"] == "PRODUCT_DECISION_USER_ACTION_LEARNING_ADVISORY_READY"
    assert result["advisory_only"] is True
    assert len(result["insights"]) >= 2
    assert result["causal_claim_allowed"] is False
    assert result["decision_rule_update_allowed"] is False


def test_empty_observations_report_insufficient_evidence():
    result = build_product_decision_user_action_learning_advisory_insights(_summary(observation_count=0, outcome_counts={}, priority_change_counts={}), _confidence(descriptive_confidence="NONE"))
    assert "Недостаточно" in result["insights"][0]


def test_summary_safety_violation_blocks():
    result = build_product_decision_user_action_learning_advisory_insights(_summary(decision_rule_update_allowed=True), _confidence())
    assert result["code"] == "LEARNING_ADVISORY_SAFETY_BOUNDARY_VIOLATION"


def test_confidence_safety_violation_blocks():
    result = build_product_decision_user_action_learning_advisory_insights(_summary(), _confidence(causal_inference_supported=True))
    assert result["code"] == "LEARNING_ADVISORY_SAFETY_BOUNDARY_VIOLATION"


def test_invalid_confidence_status_blocks():
    result = build_product_decision_user_action_learning_advisory_insights(_summary(), _confidence(status="BLOCKED"))
    assert result["code"] == "LEARNING_ADVISORY_CONFIDENCE_STATUS_INVALID"
