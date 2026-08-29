from copy import deepcopy

from product_decision_user_action_completion_evidence import build_product_decision_user_action_completion_evidence


def _checklist(**values):
    guidance_id = "product-decision-user-action-guidance:verify-1"
    result = {
        "status": "PRODUCT_DECISION_USER_ACTION_CHECKLIST_READY",
        "user_action_checklist_id": "product-decision-user-action-checklist:" + guidance_id,
        "user_action_guidance_id": guidance_id,
        "sku": "hook-2",
        "items": [{"item_id": "manual-step-1", "instruction": "Проверить остаток.", "completion_source": "USER", "completed": False}],
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


def test_user_can_report_completed_without_mutating_checklist():
    source = _checklist()
    before = deepcopy(source)
    result = build_product_decision_user_action_completion_evidence(source, "manual-step-1", "confirm_completed")
    assert result["status"] == "PRODUCT_DECISION_USER_ACTION_COMPLETION_CONFIRMED"
    assert result["user_reported_completed"] is True
    assert result["completion_evidence_source"] == "USER_REPORT"
    assert result["externally_verified"] is False
    assert result["persistent"] is False
    assert result["executed"] is False
    assert source == before


def test_user_can_report_not_completed():
    result = build_product_decision_user_action_completion_evidence(_checklist(), "manual-step-1", "NOT_COMPLETED")
    assert result["status"] == "PRODUCT_DECISION_USER_ACTION_COMPLETION_DECLINED"
    assert result["user_reported_completed"] is False


def test_invalid_decision_blocks():
    result = build_product_decision_user_action_completion_evidence(_checklist(), "manual-step-1", "YES")
    assert result["code"] == "USER_ACTION_COMPLETION_DECISION_INVALID"


def test_forged_checklist_id_blocks():
    result = build_product_decision_user_action_completion_evidence(_checklist(user_action_checklist_id="forged"), "manual-step-1", "CONFIRM_COMPLETED")
    assert result["code"] == "USER_ACTION_COMPLETION_CHECKLIST_ID_MISMATCH"


def test_missing_item_blocks():
    result = build_product_decision_user_action_completion_evidence(_checklist(), "manual-step-2", "CONFIRM_COMPLETED")
    assert result["code"] == "USER_ACTION_COMPLETION_ITEM_NOT_FOUND"


def test_precompleted_item_blocks():
    source = _checklist()
    source["items"][0]["completed"] = True
    result = build_product_decision_user_action_completion_evidence(source, "manual-step-1", "CONFIRM_COMPLETED")
    assert result["code"] == "USER_ACTION_COMPLETION_ITEM_STATE_INVALID"


def test_execution_boundary_violation_blocks():
    result = build_product_decision_user_action_completion_evidence(_checklist(execution_ready=True), "manual-step-1", "CONFIRM_COMPLETED")
    assert result["code"] == "USER_ACTION_COMPLETION_SAFETY_BOUNDARY_VIOLATION"
    assert result["execution_ready"] is False
