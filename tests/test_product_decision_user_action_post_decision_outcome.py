from product_decision_user_action_post_decision_outcome import (
    build_product_decision_user_action_post_decision_outcome,
)


def _observation(**values):
    application_id = "app-1"
    verification_id = (
        "product-decision-persistence-verification:" + application_id
    )
    guidance_id = (
        "product-decision-user-action-guidance:" + verification_id
    )
    checklist_id = (
        "product-decision-user-action-checklist:" + guidance_id
    )
    result = {
        "error": False,
        "status": "PRODUCT_DECISION_USER_ACTION_POST_DECISION_OBSERVED",
        "observation_id": (
            "product-decision-user-action-post-decision-observation:"
            + checklist_id
        ),
        "user_action_checklist_status_id": (
            "product-decision-user-action-checklist-status:" + checklist_id
        ),
        "user_action_checklist_id": checklist_id,
        "user_action_guidance_id": guidance_id,
        "decision_persistence_verification_id": verification_id,
        "decision_persistence_application_id": application_id,
        "sku": "hook-2",
        "verified_recorded_at": "2026-09-01T12:00:00+00:00",
        "decision_persistence_verified": True,
        "aggregate_status": "USER_REPORTED_COMPLETE",
        "item_count": 2,
        "reported_count": 2,
        "completed_count": 2,
        "reported_item_ids": ["manual-step-1", "manual-step-2"],
        "completed_item_ids": ["manual-step-1", "manual-step-2"],
        "completion_evidence_source": "USER_REPORT",
        "later_decision_type": "HOLD_STOCK",
        "later_priority": "LOW",
        "later_confidence": "HIGH",
        "later_reasons": ["POSITIVE_UNIT_PROFIT"],
        "observation_only": True,
        "causal_claim_allowed": False,
        "externally_verified": False,
        "persistent": False,
        "checklist_mutated": False,
        "ozon_mutation_called": False,
        "execution_allowed": False,
        "execution_ready": False,
        "executed": False,
    }
    result.update(values)
    return result


def _prior(**values):
    result = {
        "sku": "hook-2",
        "decision_type": "REPLENISH_HIGH_PRIORITY",
        "priority": "HIGH",
        "confidence": "HIGH",
        "reasons": ["DAYS_OF_STOCK_CRITICAL", "POSITIVE_UNIT_PROFIT"],
    }
    result.update(values)
    return result


def test_changed_decision_is_classified_non_causally():
    result = build_product_decision_user_action_post_decision_outcome(
        _observation(),
        _prior(),
    )
    assert result["outcome_type"] == "DECISION_CHANGED"
    assert result["priority_change"] == "PRIORITY_DECREASED"
    assert result["interpretation"] == "OBSERVED_AFTER_USER_REPORT"
    assert result["causal_claim_allowed"] is False


def test_same_decision_lower_priority():
    result = build_product_decision_user_action_post_decision_outcome(
        _observation(later_decision_type="REPLENISH_HIGH_PRIORITY"),
        _prior(),
    )
    assert result["outcome_type"] == "SAME_DECISION_LOWER_PRIORITY"


def test_same_decision_higher_priority():
    result = build_product_decision_user_action_post_decision_outcome(
        _observation(
            later_decision_type="REPLENISH_HIGH_PRIORITY",
            later_priority="CRITICAL",
        ),
        _prior(priority="HIGH"),
    )
    assert result["outcome_type"] == "SAME_DECISION_HIGHER_PRIORITY"


def test_no_change():
    result = build_product_decision_user_action_post_decision_outcome(
        _observation(
            later_decision_type="HOLD_STOCK",
            later_priority="LOW",
        ),
        _prior(
            decision_type="HOLD_STOCK",
            priority="LOW",
            reasons=["POSITIVE_UNIT_PROFIT"],
        ),
    )
    assert result["outcome_type"] == "NO_DECISION_CHANGE"


def test_forged_observation_id_blocks():
    result = build_product_decision_user_action_post_decision_outcome(
        _observation(observation_id="forged"),
        _prior(),
    )
    assert result["code"] == "POST_DECISION_OUTCOME_OBSERVATION_ID_MISMATCH"


def test_causal_flag_violation_blocks():
    result = build_product_decision_user_action_post_decision_outcome(
        _observation(causal_claim_allowed=True),
        _prior(),
    )
    assert result["code"] == "POST_DECISION_OUTCOME_CAUSAL_SAFETY_VIOLATION"
