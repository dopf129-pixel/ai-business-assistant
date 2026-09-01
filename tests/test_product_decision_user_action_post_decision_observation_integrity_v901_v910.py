from copy import deepcopy

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


def test_v901_non_mapping_checklist_status_fails_closed():
    result = build_product_decision_user_action_post_decision_observation(
        ["not", "a", "mapping"],
        _decision(),
    )

    assert result["error"] is True
    assert (
        result["code"]
        == "POST_DECISION_OBSERVATION_CHECKLIST_INPUT_INVALID"
    )


def test_v902_missing_status_identity_context_blocks():
    source = _status()
    source.pop("user_action_checklist_status_id")

    result = build_product_decision_user_action_post_decision_observation(
        source,
        _decision(),
    )

    assert result["code"] == "POST_DECISION_OBSERVATION_CONTEXT_REQUIRED"


def test_v903_forged_checklist_status_id_blocks():
    result = build_product_decision_user_action_post_decision_observation(
        _status(user_action_checklist_status_id="forged"),
        _decision(),
    )

    assert (
        result["code"]
        == "POST_DECISION_OBSERVATION_STATUS_ID_MISMATCH"
    )


def test_v904_verification_must_remain_bound_to_application():
    result = build_product_decision_user_action_post_decision_observation(
        _status(decision_persistence_application_id="other-app"),
        _decision(),
    )

    assert (
        result["code"]
        == "POST_DECISION_OBSERVATION_VERIFICATION_ID_MISMATCH"
    )


def test_v905_persisted_decision_verification_is_required():
    result = build_product_decision_user_action_post_decision_observation(
        _status(decision_persistence_verified=False),
        _decision(),
    )

    assert result["code"] == "POST_DECISION_OBSERVATION_VERIFICATION_REQUIRED"


def test_v906_complete_aggregate_requires_matching_counts():
    result = build_product_decision_user_action_post_decision_observation(
        _status(completed_count=1),
        _decision(),
    )

    assert (
        result["code"]
        == "POST_DECISION_OBSERVATION_COMPLETE_REPORT_INVALID"
    )


def test_v907_numeric_reported_item_id_is_not_coerced():
    result = build_product_decision_user_action_post_decision_observation(
        _status(
            reported_item_ids=["manual-step-1", 2],
            completed_item_ids=["manual-step-1", 2],
        ),
        _decision(),
    )

    assert (
        result["code"]
        == "POST_DECISION_OBSERVATION_COMPLETE_REPORT_INVALID"
    )


def test_v908_persistent_status_overclaim_blocks_observation():
    result = build_product_decision_user_action_post_decision_observation(
        _status(persistent=True),
        _decision(),
    )

    assert (
        result["code"]
        == "POST_DECISION_OBSERVATION_SAFETY_BOUNDARY_VIOLATION"
    )


def test_v909_missing_later_decision_error_marker_is_not_success():
    result = build_product_decision_user_action_post_decision_observation(
        _status(),
        {
            "sku": "hook-2",
            "decision_type": "HOLD_STOCK",
            "priority": "LOW",
            "confidence": "HIGH",
            "reasons": ["POSITIVE_UNIT_PROFIT"],
        },
    )

    assert (
        result["code"]
        == "POST_DECISION_OBSERVATION_LATER_DECISION_RESULT_INVALID"
    )


def test_v910_valid_observation_preserves_verified_lineage_without_mutation():
    source = _status()
    decision = _decision()
    source_before = deepcopy(source)
    decision_before = deepcopy(decision)

    result = build_product_decision_user_action_post_decision_observation(
        source,
        decision,
    )

    assert result["error"] is False
    assert (
        result["status"]
        == "PRODUCT_DECISION_USER_ACTION_POST_DECISION_OBSERVED"
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
    assert decision == decision_before
