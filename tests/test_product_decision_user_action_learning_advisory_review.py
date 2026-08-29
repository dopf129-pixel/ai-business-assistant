from product_decision_user_action_learning_advisory_review import build_product_decision_user_action_learning_advisory_review


def _advisory(**values):
    result = {
        "status": "PRODUCT_DECISION_USER_ACTION_LEARNING_ADVISORY_READY",
        "observation_count": 30,
        "descriptive_confidence": "HIGH",
        "insights": ["Наблюдалось снижение приоритета."],
        "advisory_only": True,
        "causal_claim_allowed": False,
        "decision_rule_update_allowed": False,
        "automatic_execution_allowed": False,
        "executed": False,
    }
    result.update(values)
    return result


def test_accept_records_human_usefulness_only():
    result = build_product_decision_user_action_learning_advisory_review(_advisory(), "accept_useful")
    assert result["status"].endswith("ACCEPTED")
    assert result["human_reported_useful"] is True
    assert result["review_source"] == "USER"
    assert result["persistent"] is False
    assert result["decision_rule_update_allowed"] is False


def test_reject_records_not_useful():
    result = build_product_decision_user_action_learning_advisory_review(_advisory(), "REJECT_NOT_USEFUL")
    assert result["status"].endswith("REJECTED")
    assert result["human_reported_useful"] is False


def test_invalid_decision_blocks():
    assert build_product_decision_user_action_learning_advisory_review(_advisory(), "ACCEPT")["error"] is True


def test_safety_violation_blocks():
    result = build_product_decision_user_action_learning_advisory_review(_advisory(decision_rule_update_allowed=True), "ACCEPT_USEFUL")
    assert result["code"] == "LEARNING_ADVISORY_REVIEW_SAFETY_BOUNDARY_VIOLATION"


def test_invalid_status_blocks():
    result = build_product_decision_user_action_learning_advisory_review(_advisory(status="BLOCKED"), "ACCEPT_USEFUL")
    assert result["code"] == "LEARNING_ADVISORY_REVIEW_STATUS_INVALID"
