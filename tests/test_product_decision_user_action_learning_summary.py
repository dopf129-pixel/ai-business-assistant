from product_decision_user_action_learning_summary import build_product_decision_user_action_learning_summary


def _outcome(sku="hook-2", outcome_type="DECISION_CHANGED", priority_change="PRIORITY_DECREASED", **values):
    result = {
        "status": "PRODUCT_DECISION_USER_ACTION_POST_DECISION_OUTCOME_READY",
        "sku": sku,
        "outcome_type": outcome_type,
        "priority_change": priority_change,
        "interpretation": "OBSERVED_AFTER_USER_REPORT",
        "causal_claim_allowed": False,
        "executed": False,
    }
    result.update(values)
    return result


def test_summarizes_descriptive_outcomes_only():
    result = build_product_decision_user_action_learning_summary([
        _outcome(),
        _outcome(sku="hook-3", outcome_type="NO_DECISION_CHANGE", priority_change="PRIORITY_UNCHANGED"),
        _outcome(),
    ])
    assert result["observation_count"] == 3
    assert result["outcome_counts"]["DECISION_CHANGED"] == 2
    assert result["sku_count"] == 2
    assert result["learning_scope"] == "DESCRIPTIVE_OBSERVATIONS_ONLY"
    assert result["causal_claim_allowed"] is False
    assert result["decision_rule_update_allowed"] is False
    assert result["automatic_execution_allowed"] is False


def test_invalid_or_unsafe_rows_are_excluded():
    result = build_product_decision_user_action_learning_summary([
        _outcome(),
        _outcome(status="BLOCKED"),
        _outcome(causal_claim_allowed=True),
        _outcome(executed=True),
        _outcome(interpretation="CAUSED_BY_USER_ACTION"),
    ])
    assert result["observation_count"] == 1


def test_empty_summary_is_valid_and_non_causal():
    result = build_product_decision_user_action_learning_summary([])
    assert result["observation_count"] == 0
    assert result["outcome_counts"] == {}
    assert result["causal_claim_allowed"] is False
