from copy import deepcopy

from product_decision_user_action_completion_evidence import (
    build_product_decision_user_action_completion_evidence,
)


def _checklist(**values):
    application_id = "app-1"
    verification_id = (
        "product-decision-persistence-verification:" + application_id
    )
    guidance_id = (
        "product-decision-user-action-guidance:" + verification_id
    )
    result = {
        "error": False,
        "status": "PRODUCT_DECISION_USER_ACTION_CHECKLIST_READY",
        "user_action_checklist_id":
            "product-decision-user-action-checklist:" + guidance_id,
        "user_action_guidance_id": guidance_id,
        "decision_persistence_verification_id": verification_id,
        "decision_persistence_application_id": application_id,
        "sku": "hook-2",
        "verified_recorded_at": "2026-09-01T12:00:00+00:00",
        "decision_persistence_verified": True,
        "externally_verified": False,
        "persistent": True,
        "items": [
            {
                "item_id": "manual-step-1",
                "position": 1,
                "instruction": "Проверить остаток.",
                "completion_source": "USER",
                "completed": False,
            },
            {
                "item_id": "manual-step-2",
                "position": 2,
                "instruction": "Определить действие вручную.",
                "completion_source": "USER",
                "completed": False,
            },
        ],
        "item_count": 2,
        "completed_count": 0,
        "completion_recording_allowed": False,
        "user_execution_required": True,
        "automatic_execution_prohibited": True,
        "ozon_mutation_called": False,
        "execution_allowed": False,
        "execution_ready": False,
        "executed": False,
    }
    result.update(values)
    return result


def test_v861_non_mapping_checklist_fails_closed():
    result = build_product_decision_user_action_completion_evidence(
        ["not", "a", "mapping"],
        "manual-step-1",
        "CONFIRM_COMPLETED",
    )

    assert result["error"] is True
    assert (
        result["code"]
        == "USER_ACTION_COMPLETION_CHECKLIST_INPUT_INVALID"
    )
    assert result["executed"] is False


def test_v862_missing_explicit_checklist_success_marker_is_not_trusted():
    source = _checklist()
    source.pop("error")

    result = build_product_decision_user_action_completion_evidence(
        source,
        "manual-step-1",
        "CONFIRM_COMPLETED",
    )

    assert (
        result["code"]
        == "USER_ACTION_COMPLETION_CHECKLIST_STATUS_INVALID"
    )


def test_v863_numeric_item_id_is_not_coerced_into_user_report():
    result = build_product_decision_user_action_completion_evidence(
        _checklist(),
        1,
        "CONFIRM_COMPLETED",
    )

    assert result["code"] == "USER_ACTION_COMPLETION_CONTEXT_REQUIRED"


def test_v864_guidance_id_must_bind_to_persistence_verification():
    source = _checklist(
        user_action_guidance_id="product-decision-user-action-guidance:other"
    )
    source["user_action_checklist_id"] = (
        "product-decision-user-action-checklist:"
        + source["user_action_guidance_id"]
    )

    result = build_product_decision_user_action_completion_evidence(
        source,
        "manual-step-1",
        "CONFIRM_COMPLETED",
    )

    assert (
        result["code"]
        == "USER_ACTION_COMPLETION_GUIDANCE_ID_MISMATCH"
    )


def test_v865_verification_id_must_bind_to_application():
    source = _checklist(
        decision_persistence_application_id="other-app"
    )

    result = build_product_decision_user_action_completion_evidence(
        source,
        "manual-step-1",
        "CONFIRM_COMPLETED",
    )

    assert (
        result["code"]
        == "USER_ACTION_COMPLETION_VERIFICATION_ID_MISMATCH"
    )


def test_v866_external_verification_overclaim_blocks_user_report():
    result = build_product_decision_user_action_completion_evidence(
        _checklist(externally_verified=True),
        "manual-step-1",
        "CONFIRM_COMPLETED",
    )

    assert (
        result["code"]
        == "USER_ACTION_COMPLETION_SAFETY_BOUNDARY_VIOLATION"
    )
    assert result["externally_verified"] is False


def test_v867_item_count_must_match_exact_checklist_shape():
    result = build_product_decision_user_action_completion_evidence(
        _checklist(item_count=3),
        "manual-step-1",
        "CONFIRM_COMPLETED",
    )

    assert result["code"] == "USER_ACTION_COMPLETION_ITEMS_INVALID"


def test_v868_numeric_instruction_cannot_become_user_evidence():
    source = _checklist()
    source["items"][0]["instruction"] = 123

    result = build_product_decision_user_action_completion_evidence(
        source,
        "manual-step-1",
        "CONFIRM_COMPLETED",
    )

    assert result["code"] == "USER_ACTION_COMPLETION_ITEMS_INVALID"


def test_v869_non_string_completion_decision_is_not_coerced():
    result = build_product_decision_user_action_completion_evidence(
        _checklist(),
        "manual-step-1",
        1,
    )

    assert result["code"] == "USER_ACTION_COMPLETION_DECISION_INVALID"


def test_v870_valid_completion_evidence_preserves_verified_lineage():
    source = _checklist()
    before = deepcopy(source)

    result = build_product_decision_user_action_completion_evidence(
        source,
        "manual-step-1",
        "confirm_completed",
    )

    assert result["error"] is False
    assert (
        result["status"]
        == "PRODUCT_DECISION_USER_ACTION_COMPLETION_CONFIRMED"
    )
    assert result["decision_persistence_application_id"] == "app-1"
    assert result["decision_persistence_verified"] is True
    assert (
        result["verified_recorded_at"]
        == "2026-09-01T12:00:00+00:00"
    )
    assert result["completion_evidence_source"] == "USER_REPORT"
    assert result["user_reported_completed"] is True
    assert result["externally_verified"] is False
    assert result["persistent"] is False
    assert result["checklist_mutated"] is False
    assert result["ozon_mutation_called"] is False
    assert result["execution_allowed"] is False
    assert result["execution_ready"] is False
    assert result["executed"] is False
    assert source == before
