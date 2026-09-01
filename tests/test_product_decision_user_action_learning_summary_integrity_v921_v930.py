from copy import deepcopy

from product_decision_user_action_learning_summary import (
    build_product_decision_user_action_learning_summary,
)


def _outcome(
    sku="hook-2",
    prior_type="REPLENISH_HIGH_PRIORITY",
    later_type="HOLD_STOCK",
    prior_priority="HIGH",
    later_priority="LOW",
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
    decision_changed = prior_type != later_type
    delta = {
        "NONE": 0,
        "LOW": 1,
        "NORMAL": 2,
        "HIGH": 3,
        "CRITICAL": 4,
    }[later_priority] - {
        "NONE": 0,
        "LOW": 1,
        "NORMAL": 2,
        "HIGH": 3,
        "CRITICAL": 4,
    }[prior_priority]
    priority_change = (
        "PRIORITY_DECREASED"
        if delta < 0
        else "PRIORITY_INCREASED"
        if delta > 0
        else "PRIORITY_UNCHANGED"
    )
    outcome_type = (
        "DECISION_CHANGED"
        if decision_changed
        else "SAME_DECISION_LOWER_PRIORITY"
        if delta < 0
        else "SAME_DECISION_HIGHER_PRIORITY"
        if delta > 0
        else "NO_DECISION_CHANGE"
    )
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
        "decision_changed": decision_changed,
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


def test_v921_non_list_outcomes_cannot_be_clean_empty_summary():
    result = build_product_decision_user_action_learning_summary(
        {"outcome": _outcome()}
    )

    assert result["error"] is True
    assert result["code"] == "LEARNING_SUMMARY_OUTCOMES_INPUT_INVALID"


def test_v922_non_mapping_row_fails_closed():
    result = build_product_decision_user_action_learning_summary(
        [_outcome(), "not-an-outcome"]
    )

    assert result["code"] == "LEARNING_SUMMARY_OUTCOME_INVALID"


def test_v923_missing_explicit_outcome_error_marker_is_not_success():
    outcome = _outcome()
    outcome.pop("error")

    result = build_product_decision_user_action_learning_summary([outcome])

    assert result["code"] == "LEARNING_SUMMARY_OUTCOME_RESULT_INVALID"


def test_v924_verification_lineage_mismatch_blocks_summary():
    result = build_product_decision_user_action_learning_summary([
        _outcome(decision_persistence_application_id="other-app")
    ])

    assert result["code"] == "LEARNING_SUMMARY_VERIFICATION_ID_MISMATCH"


def test_v925_unsafe_outcome_is_not_silently_excluded():
    result = build_product_decision_user_action_learning_summary([
        _outcome(execution_ready=True)
    ])

    assert result["code"] == "LEARNING_SUMMARY_OUTCOME_SAFETY_INVALID"


def test_v926_noncanonical_medium_priority_is_not_counted():
    outcome = _outcome()
    outcome["later_priority"] = "MEDIUM"

    result = build_product_decision_user_action_learning_summary([
        outcome
    ])

    assert (
        result["code"]
        == "LEARNING_SUMMARY_OUTCOME_CLASSIFICATION_INVALID"
    )


def test_v927_contradictory_outcome_classification_blocks():
    result = build_product_decision_user_action_learning_summary([
        _outcome(outcome_type="NO_DECISION_CHANGE")
    ])

    assert (
        result["code"]
        == "LEARNING_SUMMARY_OUTCOME_CLASSIFICATION_MISMATCH"
    )


def test_v928_duplicate_outcome_id_cannot_inflate_learning_counts():
    outcome = _outcome()
    result = build_product_decision_user_action_learning_summary([
        outcome,
        deepcopy(outcome),
    ])

    assert result["code"] == "LEARNING_SUMMARY_OUTCOME_ID_DUPLICATE"
    assert result["observation_count"] == 0


def test_v929_canonical_none_priority_outcome_is_counted():
    result = build_product_decision_user_action_learning_summary([
        _outcome(
            prior_type="INSUFFICIENT_DATA",
            later_type="INSUFFICIENT_DATA",
            prior_priority="NONE",
            later_priority="NONE",
            prior_confidence="LOW",
            later_confidence="LOW",
            prior_reasons=["ECONOMICS_INCOMPLETE"],
            later_reasons=["ECONOMICS_INCOMPLETE"],
        )
    ])

    assert result["error"] is False
    assert result["observation_count"] == 1
    assert result["outcome_counts"] == {"NO_DECISION_CHANGE": 1}
    assert result["priority_change_counts"] == {
        "PRIORITY_UNCHANGED": 1
    }


def test_v930_valid_summary_is_deterministic_safe_and_non_mutating():
    outcomes = [_outcome(), _outcome(sku="hook-3")]
    before = deepcopy(outcomes)

    first = build_product_decision_user_action_learning_summary(outcomes)
    second = build_product_decision_user_action_learning_summary(outcomes)

    assert first == second
    assert first["error"] is False
    assert first["observation_count"] == 2
    assert first["sku_count"] == 2
    assert len(first["outcome_ids"]) == 2
    assert first["completion_evidence_source"] == "USER_REPORT"
    assert first["learning_scope"] == "DESCRIPTIVE_OBSERVATIONS_ONLY"
    assert first["causal_claim_allowed"] is False
    assert first["externally_verified"] is False
    assert first["persistent"] is False
    assert first["decision_rule_update_allowed"] is False
    assert first["automatic_execution_allowed"] is False
    assert first["execution_allowed"] is False
    assert first["execution_ready"] is False
    assert first["executed"] is False
    assert outcomes == before
