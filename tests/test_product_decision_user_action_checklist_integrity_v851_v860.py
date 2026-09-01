from copy import deepcopy

from product_decision_user_action_checklist import (
    build_product_decision_user_action_checklist,
)


def _guidance(**values):
    application_id = "app-1"
    verification_id = (
        "product-decision-persistence-verification:" + application_id
    )
    result = {
        "error": False,
        "status": "PRODUCT_DECISION_USER_ACTION_GUIDANCE_READY",
        "user_action_guidance_id":
            "product-decision-user-action-guidance:" + verification_id,
        "decision_persistence_verification_id": verification_id,
        "decision_persistence_application_id": application_id,
        "sku": "hook-2",
        "decision_type": "REPLENISH_HIGH_PRIORITY",
        "priority": "HIGH",
        "confidence": "HIGH",
        "action_type": "REVIEW_REPLENISHMENT",
        "title": "Проверить пополнение запаса",
        "steps": [
            "Проверить остаток.",
            "Определить объём вручную.",
        ],
        "reasons": ["LOW_STOCK"],
        "verified_recorded_at": "2026-09-01T12:00:00+00:00",
        "decision_persistence_verified": True,
        "externally_verified": False,
        "persistent": True,
        "user_execution_required": True,
        "automatic_execution_prohibited": True,
        "ozon_mutation_called": False,
        "execution_allowed": False,
        "execution_ready": False,
        "executed": False,
    }
    result.update(values)
    return result


def test_v851_non_mapping_guidance_fails_closed():
    result = build_product_decision_user_action_checklist(
        ["not", "a", "mapping"]
    )

    assert result["error"] is True
    assert (
        result["code"]
        == "USER_ACTION_CHECKLIST_GUIDANCE_INPUT_INVALID"
    )
    assert result["executed"] is False


def test_v852_missing_explicit_guidance_success_marker_is_not_trusted():
    source = _guidance()
    source.pop("error")

    result = build_product_decision_user_action_checklist(source)

    assert (
        result["code"]
        == "USER_ACTION_CHECKLIST_GUIDANCE_STATUS_INVALID"
    )


def test_v853_numeric_identity_is_not_coerced_into_checklist_lineage():
    result = build_product_decision_user_action_checklist(
        _guidance(sku=123)
    )

    assert result["code"] == "USER_ACTION_CHECKLIST_CONTEXT_REQUIRED"


def test_v854_verification_must_bind_to_application_id():
    source = _guidance(
        decision_persistence_application_id="other-app"
    )

    result = build_product_decision_user_action_checklist(source)

    assert (
        result["code"]
        == "USER_ACTION_CHECKLIST_VERIFICATION_ID_MISMATCH"
    )


def test_v855_verified_recorded_at_is_required_for_lineage():
    result = build_product_decision_user_action_checklist(
        _guidance(verified_recorded_at=None)
    )

    assert result["code"] == "USER_ACTION_CHECKLIST_CONTEXT_REQUIRED"


def test_v856_numeric_step_cannot_be_coerced_into_manual_instruction():
    result = build_product_decision_user_action_checklist(
        _guidance(steps=["Проверить остаток.", 123])
    )

    assert result["code"] == "USER_ACTION_CHECKLIST_STEPS_REQUIRED"


def test_v857_action_type_must_match_verified_decision_type():
    result = build_product_decision_user_action_checklist(
        _guidance(action_type="MONITOR_ONLY")
    )

    assert (
        result["code"]
        == "USER_ACTION_CHECKLIST_GUIDANCE_SEMANTICS_INVALID"
    )


def test_v858_reasons_string_cannot_become_character_evidence():
    result = build_product_decision_user_action_checklist(
        _guidance(reasons="LOW_STOCK")
    )

    assert (
        result["code"]
        == "USER_ACTION_CHECKLIST_GUIDANCE_SEMANTICS_INVALID"
    )


def test_v859_external_verification_overclaim_blocks_checklist():
    result = build_product_decision_user_action_checklist(
        _guidance(externally_verified=True)
    )

    assert (
        result["code"]
        == "USER_ACTION_CHECKLIST_SAFETY_BOUNDARY_VIOLATION"
    )
    assert result["externally_verified"] is False


def test_v860_valid_checklist_preserves_verified_read_only_lineage():
    source = _guidance()
    before = deepcopy(source)

    result = build_product_decision_user_action_checklist(source)

    assert result["error"] is False
    assert (
        result["status"]
        == "PRODUCT_DECISION_USER_ACTION_CHECKLIST_READY"
    )
    assert result["decision_persistence_application_id"] == "app-1"
    assert result["decision_persistence_verified"] is True
    assert (
        result["verified_recorded_at"]
        == "2026-09-01T12:00:00+00:00"
    )
    assert result["confidence"] == "HIGH"
    assert result["reasons"] == ["LOW_STOCK"]
    assert result["externally_verified"] is False
    assert result["persistent"] is True
    assert result["completion_recording_allowed"] is False
    assert result["user_execution_required"] is True
    assert result["automatic_execution_prohibited"] is True
    assert result["ozon_mutation_called"] is False
    assert result["execution_allowed"] is False
    assert result["execution_ready"] is False
    assert result["executed"] is False
    assert source == before

    result["reasons"].append("MUTATED_COPY")
    result["items"][0]["instruction"] = "changed"
    assert source["reasons"] == ["LOW_STOCK"]
    assert source["steps"][0] == "Проверить остаток."
