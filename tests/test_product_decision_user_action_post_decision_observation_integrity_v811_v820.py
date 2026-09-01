from product_decision_user_action_post_decision_observation import (
    build_product_decision_user_action_post_decision_observation,
)


def _status(**values):
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
        "status": "PRODUCT_DECISION_USER_ACTION_CHECKLIST_STATUS_READY",
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

def _decision(**values):
    result = {
        "error": False,
        "sku": "hook-2",
        "decision_type": "HOLD_STOCK",
        "priority": "LOW",
        "confidence": "HIGH",
        "reasons": ["POSITIVE_UNIT_PROFIT"],
    }
    result.update(values)
    return result


def test_v811_non_mapping_checklist_fails_closed():
    result = build_product_decision_user_action_post_decision_observation(
        ["not", "a", "mapping"],
        _decision(),
    )
    assert result["error"] is True
    assert result["code"] == "POST_DECISION_OBSERVATION_CHECKLIST_INPUT_INVALID"
    assert result["executed"] is False


def test_v812_non_mapping_later_decision_fails_closed():
    result = build_product_decision_user_action_post_decision_observation(
        _status(),
        "not-a-decision",
    )
    assert result["code"] == "POST_DECISION_OBSERVATION_LATER_DECISION_REQUIRED"


def test_v813_missing_explicit_decision_error_flag_is_not_success():
    decision = _decision()
    decision.pop("error")
    result = build_product_decision_user_action_post_decision_observation(
        _status(),
        decision,
    )
    assert result["code"] == "POST_DECISION_OBSERVATION_LATER_DECISION_RESULT_INVALID"


def test_v814_explicit_later_decision_failure_is_preserved():
    result = build_product_decision_user_action_post_decision_observation(
        _status(),
        _decision(error=True),
    )
    assert result["code"] == "POST_DECISION_OBSERVATION_LATER_DECISION_FAILED"


def test_v815_user_report_evidence_is_required():
    result = build_product_decision_user_action_post_decision_observation(
        _status(completion_evidence_source=None),
        _decision(),
    )
    assert result["code"] == "POST_DECISION_OBSERVATION_USER_REPORT_EVIDENCE_REQUIRED"


def test_v816_execution_readiness_claim_on_checklist_status_blocks():
    result = build_product_decision_user_action_post_decision_observation(
        _status(execution_ready=True),
        _decision(),
    )
    assert result["code"] == "POST_DECISION_OBSERVATION_SAFETY_BOUNDARY_VIOLATION"


def test_v817_numeric_identity_is_not_coerced_into_canonical_identity():
    result = build_product_decision_user_action_post_decision_observation(
        _status(user_action_checklist_id=123),
        _decision(),
    )
    assert result["code"] == "POST_DECISION_OBSERVATION_CONTEXT_REQUIRED"


def test_v818_reasons_string_is_not_split_into_fake_reason_evidence():
    result = build_product_decision_user_action_post_decision_observation(
        _status(),
        _decision(reasons="POSITIVE_UNIT_PROFIT"),
    )
    assert result["code"] == "POST_DECISION_OBSERVATION_LATER_DECISION_INVALID"


def test_v819_unknown_priority_is_not_observed_as_business_fact():
    result = build_product_decision_user_action_post_decision_observation(
        _status(),
        _decision(priority="URGENT"),
    )
    assert result["code"] == "POST_DECISION_OBSERVATION_LATER_DECISION_INVALID"


def test_v820_valid_observation_keeps_read_only_safety_boundary():
    result = build_product_decision_user_action_post_decision_observation(
        _status(),
        _decision(),
    )
    assert result["error"] is False
    assert result["later_reasons"] == ["POSITIVE_UNIT_PROFIT"]
    assert result["causal_claim_allowed"] is False
    assert result["externally_verified"] is False
    assert result["execution_allowed"] is False
    assert result["execution_ready"] is False
    assert result["executed"] is False
