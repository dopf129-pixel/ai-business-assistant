from product_decision_user_action_learning_advisory_evaluation_summary import build_product_decision_user_action_learning_advisory_evaluation_summary


def _review(useful=True, **values):
    result = {
        "status": "PRODUCT_DECISION_USER_ACTION_LEARNING_ADVISORY_REVIEW_ACCEPTED" if useful else "PRODUCT_DECISION_USER_ACTION_LEARNING_ADVISORY_REVIEW_REJECTED",
        "human_reported_useful": useful,
        "review_source": "USER",
        "persistent": False,
        "advisory_only": True,
        "causal_claim_allowed": False,
        "decision_rule_update_allowed": False,
        "automatic_execution_allowed": False,
        "executed": False,
    }
    result.update(values)
    return result


def test_summarizes_human_usefulness():
    result = build_product_decision_user_action_learning_advisory_evaluation_summary([_review(True), _review(True), _review(False)])
    assert result["review_count"] == 3
    assert result["accepted_count"] == 2
    assert result["rejected_count"] == 1
    assert result["human_reported_usefulness_rate"] == 2 / 3
    assert result["decision_rule_update_allowed"] is False


def test_empty_summary_has_no_rate():
    result = build_product_decision_user_action_learning_advisory_evaluation_summary([])
    assert result["review_count"] == 0
    assert result["human_reported_usefulness_rate"] is None


def test_invalid_or_unsafe_rows_are_ignored():
    result = build_product_decision_user_action_learning_advisory_evaluation_summary([
        _review(True),
        _review(True, executed=True),
        _review(False, review_source="SYSTEM"),
        {"status": "OTHER"},
    ])
    assert result["review_count"] == 1
    assert result["accepted_count"] == 1
