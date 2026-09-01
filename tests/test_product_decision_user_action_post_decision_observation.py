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


def test_observes_later_decision_without_causal_claim():
    result = build_product_decision_user_action_post_decision_observation(
        _status(),
        _decision(),
    )
    assert (
        result["status"]
        == "PRODUCT_DECISION_USER_ACTION_POST_DECISION_OBSERVED"
    )
    assert result["observation_only"] is True
    assert result["causal_claim_allowed"] is False
    assert result["decision_persistence_verified"] is True
    assert result["externally_verified"] is False
    assert result["executed"] is False


def test_partial_report_blocks():
    result = build_product_decision_user_action_post_decision_observation(
        _status(aggregate_status="USER_REPORTED_PARTIAL"),
        _decision(),
    )
    assert (
        result["code"]
        == "POST_DECISION_OBSERVATION_COMPLETE_REPORT_REQUIRED"
    )


def test_sku_mismatch_blocks():
    result = build_product_decision_user_action_post_decision_observation(
        _status(),
        _decision(sku="other"),
    )
    assert result["code"] == "POST_DECISION_OBSERVATION_SKU_MISMATCH"


def test_external_verification_flag_blocks():
    result = build_product_decision_user_action_post_decision_observation(
        _status(externally_verified=True),
        _decision(),
    )
    assert (
        result["code"]
        == "POST_DECISION_OBSERVATION_SAFETY_BOUNDARY_VIOLATION"
    )


def test_invalid_later_decision_blocks():
    result = build_product_decision_user_action_post_decision_observation(
        _status(),
        {"error": False, "sku": "hook-2"},
    )
    assert (
        result["code"]
        == "POST_DECISION_OBSERVATION_LATER_DECISION_INVALID"
    )
