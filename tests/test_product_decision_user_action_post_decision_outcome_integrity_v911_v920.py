from copy import deepcopy

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


def test_v911_non_mapping_observation_fails_closed():
    result = build_product_decision_user_action_post_decision_outcome(
        ["not", "a", "mapping"],
        _prior(),
    )

    assert result["error"] is True
    assert (
        result["code"]
        == "POST_DECISION_OUTCOME_OBSERVATION_INPUT_INVALID"
    )


def test_v912_non_mapping_prior_decision_fails_closed():
    result = build_product_decision_user_action_post_decision_outcome(
        _observation(),
        "not-a-decision",
    )

    assert result["code"] == "POST_DECISION_OUTCOME_PRIOR_DECISION_INVALID"


def test_v913_missing_explicit_observation_error_marker_is_not_success():
    source = _observation()
    source.pop("error")

    result = build_product_decision_user_action_post_decision_outcome(
        source,
        _prior(),
    )

    assert (
        result["code"]
        == "POST_DECISION_OUTCOME_OBSERVATION_STATUS_INVALID"
    )


def test_v914_numeric_observation_identity_is_not_coerced():
    result = build_product_decision_user_action_post_decision_outcome(
        _observation(observation_id=123),
        _prior(),
    )

    assert result["code"] == "POST_DECISION_OUTCOME_CONTEXT_REQUIRED"


def test_v915_verification_lineage_must_remain_bound_to_application():
    result = build_product_decision_user_action_post_decision_outcome(
        _observation(decision_persistence_application_id="other-app"),
        _prior(),
    )

    assert (
        result["code"]
        == "POST_DECISION_OUTCOME_VERIFICATION_ID_MISMATCH"
    )


def test_v916_persisted_decision_verification_is_required():
    result = build_product_decision_user_action_post_decision_outcome(
        _observation(decision_persistence_verified=False),
        _prior(),
    )

    assert result["code"] == "POST_DECISION_OUTCOME_VERIFICATION_REQUIRED"


def test_v917_complete_report_counts_cannot_be_forged():
    result = build_product_decision_user_action_post_decision_outcome(
        _observation(completed_count=1),
        _prior(),
    )

    assert (
        result["code"]
        == "POST_DECISION_OUTCOME_COMPLETION_EVIDENCE_INVALID"
    )


def test_v918_noncanonical_medium_business_priority_is_rejected():
    result = build_product_decision_user_action_post_decision_outcome(
        _observation(later_priority="MEDIUM"),
        _prior(),
    )

    assert result["code"] == "POST_DECISION_OUTCOME_DECISION_FIELDS_INVALID"


def test_v919_canonical_none_priority_is_supported_for_insufficient_data():
    result = build_product_decision_user_action_post_decision_outcome(
        _observation(
            later_decision_type="INSUFFICIENT_DATA",
            later_priority="NONE",
            later_confidence="LOW",
            later_reasons=["ECONOMICS_INCOMPLETE"],
        ),
        _prior(
            decision_type="INSUFFICIENT_DATA",
            priority="NONE",
            confidence="LOW",
            reasons=["ECONOMICS_INCOMPLETE"],
        ),
    )

    assert result["error"] is False
    assert result["outcome_type"] == "NO_DECISION_CHANGE"
    assert result["priority_change"] == "PRIORITY_UNCHANGED"
    assert result["prior_priority"] == "NONE"
    assert result["later_priority"] == "NONE"


def test_v920_valid_outcome_preserves_verified_lineage_without_mutation():
    source = _observation()
    prior = _prior()
    source_before = deepcopy(source)
    prior_before = deepcopy(prior)

    result = build_product_decision_user_action_post_decision_outcome(
        source,
        prior,
    )

    assert result["error"] is False
    assert (
        result["status"]
        == "PRODUCT_DECISION_USER_ACTION_POST_DECISION_OUTCOME_READY"
    )
    assert result["user_action_checklist_status_id"] == (
        source["user_action_checklist_status_id"]
    )
    assert result["decision_persistence_application_id"] == "app-1"
    assert result["decision_persistence_verified"] is True
    assert (
        result["verified_recorded_at"]
        == "2026-09-01T12:00:00+00:00"
    )
    assert result["item_count"] == 2
    assert result["reported_count"] == 2
    assert result["completed_count"] == 2
    assert result["completion_evidence_source"] == "USER_REPORT"
    assert result["prior_confidence"] == "HIGH"
    assert result["later_confidence"] == "HIGH"
    assert result["interpretation"] == "OBSERVED_AFTER_USER_REPORT"
    assert result["observation_only"] is True
    assert result["causal_claim_allowed"] is False
    assert result["externally_verified"] is False
    assert result["persistent"] is False
    assert result["checklist_mutated"] is False
    assert result["ozon_mutation_called"] is False
    assert result["execution_allowed"] is False
    assert result["execution_ready"] is False
    assert result["executed"] is False
    assert source == source_before
    assert prior == prior_before
