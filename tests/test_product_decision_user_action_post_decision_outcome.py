from product_decision_user_action_post_decision_outcome import build_product_decision_user_action_post_decision_outcome


def _observation(**values):
    result = {
        "status": "PRODUCT_DECISION_USER_ACTION_POST_DECISION_OBSERVED",
        "observation_id": "product-decision-user-action-post-decision-observation:check-1",
        "user_action_checklist_id": "check-1",
        "sku": "hook-2",
        "later_decision_type": "HOLD_STOCK",
        "later_priority": "LOW",
        "observation_only": True,
        "causal_claim_allowed": False,
    }
    result.update(values)
    return result


def _prior(**values):
    result = {"sku": "hook-2", "decision_type": "REPLENISH_HIGH_PRIORITY", "priority": "HIGH"}
    result.update(values)
    return result


def test_changed_decision_is_classified_non_causally():
    result = build_product_decision_user_action_post_decision_outcome(_observation(), _prior())
    assert result["outcome_type"] == "DECISION_CHANGED"
    assert result["priority_change"] == "PRIORITY_DECREASED"
    assert result["interpretation"] == "OBSERVED_AFTER_USER_REPORT"
    assert result["causal_claim_allowed"] is False


def test_same_decision_lower_priority():
    result = build_product_decision_user_action_post_decision_outcome(_observation(later_decision_type="REPLENISH_HIGH_PRIORITY"), _prior())
    assert result["outcome_type"] == "SAME_DECISION_LOWER_PRIORITY"


def test_same_decision_higher_priority():
    result = build_product_decision_user_action_post_decision_outcome(_observation(later_decision_type="REPLENISH_HIGH_PRIORITY", later_priority="CRITICAL"), _prior(priority="HIGH"))
    assert result["outcome_type"] == "SAME_DECISION_HIGHER_PRIORITY"


def test_no_change():
    result = build_product_decision_user_action_post_decision_outcome(_observation(later_decision_type="HOLD_STOCK", later_priority="LOW"), _prior(decision_type="HOLD_STOCK", priority="LOW"))
    assert result["outcome_type"] == "NO_DECISION_CHANGE"


def test_forged_observation_id_blocks():
    result = build_product_decision_user_action_post_decision_outcome(_observation(observation_id="forged"), _prior())
    assert result["code"] == "POST_DECISION_OUTCOME_OBSERVATION_ID_MISMATCH"


def test_causal_flag_violation_blocks():
    result = build_product_decision_user_action_post_decision_outcome(_observation(causal_claim_allowed=True), _prior())
    assert result["code"] == "POST_DECISION_OUTCOME_CAUSAL_SAFETY_VIOLATION"
