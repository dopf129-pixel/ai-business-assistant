from copy import deepcopy

from product_decision_user_action_checklist import build_product_decision_user_action_checklist


def _guidance(**values):
    verification_id = "product-decision-persistence-verification:app-1"
    result = {
        "status": "PRODUCT_DECISION_USER_ACTION_GUIDANCE_READY",
        "user_action_guidance_id": "product-decision-user-action-guidance:" + verification_id,
        "decision_persistence_verification_id": verification_id,
        "sku": "hook-2",
        "decision_type": "REPLENISH_HIGH_PRIORITY",
        "priority": "HIGH",
        "action_type": "REVIEW_REPLENISHMENT",
        "title": "Проверить пополнение запаса",
        "steps": ["Проверить остаток.", "Определить объём вручную.", "Выполнить действие самостоятельно."],
        "user_execution_required": True,
        "automatic_execution_prohibited": True,
        "ozon_mutation_called": False,
        "execution_allowed": False,
        "execution_ready": False,
        "executed": False,
    }
    result.update(values)
    return result


def test_builds_uncompleted_user_owned_checklist_without_mutating_input():
    source = _guidance()
    before = deepcopy(source)
    result = build_product_decision_user_action_checklist(source)
    assert result["status"] == "PRODUCT_DECISION_USER_ACTION_CHECKLIST_READY"
    assert result["item_count"] == 3
    assert result["completed_count"] == 0
    assert all(item["completion_source"] == "USER" for item in result["items"])
    assert all(item["completed"] is False for item in result["items"])
    assert result["completion_recording_allowed"] is False
    assert source == before


def test_forged_guidance_id_blocks():
    result = build_product_decision_user_action_checklist(_guidance(user_action_guidance_id="forged"))
    assert result["code"] == "USER_ACTION_CHECKLIST_GUIDANCE_ID_MISMATCH"


def test_invalid_guidance_status_blocks():
    result = build_product_decision_user_action_checklist(_guidance(status="BLOCKED"))
    assert result["code"] == "USER_ACTION_CHECKLIST_GUIDANCE_STATUS_INVALID"


def test_execution_boundary_violation_blocks():
    result = build_product_decision_user_action_checklist(_guidance(executed=True))
    assert result["code"] == "USER_ACTION_CHECKLIST_SAFETY_BOUNDARY_VIOLATION"
    assert result["executed"] is False


def test_missing_steps_blocks():
    result = build_product_decision_user_action_checklist(_guidance(steps=[]))
    assert result["code"] == "USER_ACTION_CHECKLIST_STEPS_REQUIRED"


def test_blank_step_blocks():
    result = build_product_decision_user_action_checklist(_guidance(steps=["ok", " "]))
    assert result["code"] == "USER_ACTION_CHECKLIST_STEPS_REQUIRED"
