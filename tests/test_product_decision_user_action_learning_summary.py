from product_decision_user_action_learning_summary import (
    build_product_decision_user_action_learning_summary,
)


def _outcome(
    sku="hook-2",
    outcome_type="DECISION_CHANGED",
    priority_change="PRIORITY_DECREASED",
    **values,
):
    application_id = "app-1-" + sku
    verification_id = (
        "product-decision-persistence-verification:" + application_id
    )
    guidance_id = (
        "product-decision-user-action-guidance:" + verification_id
    )
    checklist_id = (
        "product-decision-user-action-checklist:" + guidance_id
    )
    observation_id = (
        "product-decision-user-action-post-decision-observation:"
        + checklist_id
    )

    if outcome_type == "NO_DECISION_CHANGE":
        prior_type = "HOLD_STOCK"
        later_type = "HOLD_STOCK"
        prior_priority = "LOW"
        later_priority = "LOW"
    else:
        prior_type = "REPLENISH_HIGH_PRIORITY"
        later_type = "HOLD_STOCK"
        prior_priority = "HIGH"
        later_priority = "LOW"

    result = {
        "error": False,
        "status": "PRODUCT_DECISION_USER_ACTION_POST_DECISION_OUTCOME_READY",
        "outcome_id": (
            "product-decision-user-action-post-decision-outcome:"
            + observation_id
        ),
        "observation_id": observation_id,
        "user_action_checklist_status_id": (
            "product-decision-user-action-checklist-status:" + checklist_id
        ),
        "user_action_checklist_id": checklist_id,
        "user_action_guidance_id": guidance_id,
        "decision_persistence_verification_id": verification_id,
        "decision_persistence_application_id": application_id,
        "sku": sku,
        "verified_recorded_at": "2026-09-01T12:00:00+00:00",
        "decision_persistence_verified": True,
        "aggregate_status": "USER_REPORTED_COMPLETE",
        "item_count": 2,
        "reported_count": 2,
        "completed_count": 2,
        "reported_item_ids": ["manual-step-1", "manual-step-2"],
        "completed_item_ids": ["manual-step-1", "manual-step-2"],
        "completion_evidence_source": "USER_REPORT",
        "prior_decision_type": prior_type,
        "later_decision_type": later_type,
        "prior_priority": prior_priority,
        "later_priority": later_priority,
        "prior_confidence": "HIGH",
        "later_confidence": "HIGH",
        "prior_reasons": ["POSITIVE_UNIT_PROFIT"],
        "later_reasons": ["POSITIVE_UNIT_PROFIT"],
        "decision_changed": prior_type != later_type,
        "priority_change": priority_change,
        "outcome_type": outcome_type,
        "interpretation": "OBSERVED_AFTER_USER_REPORT",
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


def test_summarizes_descriptive_outcomes_only():
    result = build_product_decision_user_action_learning_summary([
        _outcome(),
        _outcome(
            sku="hook-3",
            outcome_type="NO_DECISION_CHANGE",
            priority_change="PRIORITY_UNCHANGED",
        ),
        _outcome(sku="hook-4"),
    ])
    assert result["observation_count"] == 3
    assert result["outcome_counts"]["DECISION_CHANGED"] == 2
    assert result["sku_count"] == 3
    assert result["learning_scope"] == "DESCRIPTIVE_OBSERVATIONS_ONLY"
    assert result["causal_claim_allowed"] is False
    assert result["decision_rule_update_allowed"] is False
    assert result["automatic_execution_allowed"] is False


def test_invalid_or_unsafe_rows_block_instead_of_disappearing():
    result = build_product_decision_user_action_learning_summary([
        _outcome(),
        _outcome(status="BLOCKED", sku="hook-3"),
    ])
    assert result["error"] is True
    assert result["code"] == "LEARNING_SUMMARY_OUTCOME_RESULT_INVALID"


def test_empty_summary_is_valid_and_non_causal():
    result = build_product_decision_user_action_learning_summary([])
    assert result["error"] is False
    assert result["observation_count"] == 0
    assert result["outcome_counts"] == {}
    assert result["causal_claim_allowed"] is False
