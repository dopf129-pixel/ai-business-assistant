from copy import deepcopy


VALID_COMPLETION_DECISIONS = {"CONFIRM_COMPLETED", "NOT_COMPLETED"}


def build_product_decision_user_action_completion_evidence(checklist, item_id, decision):
    source = deepcopy(dict(checklist or {}))
    checklist_id = str(source.get("user_action_checklist_id") or "").strip()
    guidance_id = str(source.get("user_action_guidance_id") or "").strip()
    sku = str(source.get("sku") or "").strip()
    normalized_item_id = str(item_id or "").strip()
    normalized_decision = str(decision or "").strip().upper()

    if not checklist_id or not guidance_id or not sku or not normalized_item_id:
        return _blocked("USER_ACTION_COMPLETION_CONTEXT_REQUIRED", source, normalized_item_id)
    if checklist_id != "product-decision-user-action-checklist:" + guidance_id:
        return _blocked("USER_ACTION_COMPLETION_CHECKLIST_ID_MISMATCH", source, normalized_item_id)
    if source.get("status") != "PRODUCT_DECISION_USER_ACTION_CHECKLIST_READY":
        return _blocked("USER_ACTION_COMPLETION_CHECKLIST_STATUS_INVALID", source, normalized_item_id)
    if normalized_decision not in VALID_COMPLETION_DECISIONS:
        return _blocked("USER_ACTION_COMPLETION_DECISION_INVALID", source, normalized_item_id)
    if (
        source.get("completion_recording_allowed") is not False
        or source.get("user_execution_required") is not True
        or source.get("automatic_execution_prohibited") is not True
        or source.get("ozon_mutation_called") is not False
        or source.get("execution_allowed") is not False
        or source.get("execution_ready") is not False
        or source.get("executed") is not False
    ):
        return _blocked("USER_ACTION_COMPLETION_SAFETY_BOUNDARY_VIOLATION", source, normalized_item_id)

    items = source.get("items")
    if not isinstance(items, list):
        return _blocked("USER_ACTION_COMPLETION_ITEMS_REQUIRED", source, normalized_item_id)
    matches = [item for item in items if isinstance(item, dict) and item.get("item_id") == normalized_item_id]
    if len(matches) != 1:
        return _blocked("USER_ACTION_COMPLETION_ITEM_NOT_FOUND", source, normalized_item_id)
    item = matches[0]
    if item.get("completion_source") != "USER" or item.get("completed") is not False:
        return _blocked("USER_ACTION_COMPLETION_ITEM_STATE_INVALID", source, normalized_item_id)

    completed = normalized_decision == "CONFIRM_COMPLETED"
    return {
        "error": False,
        "status": "PRODUCT_DECISION_USER_ACTION_COMPLETION_CONFIRMED" if completed else "PRODUCT_DECISION_USER_ACTION_COMPLETION_DECLINED",
        "user_action_completion_evidence_id": "product-decision-user-action-completion-evidence:%s:%s" % (checklist_id, normalized_item_id),
        "user_action_checklist_id": checklist_id,
        "user_action_guidance_id": guidance_id,
        "sku": sku,
        "item_id": normalized_item_id,
        "instruction": item.get("instruction"),
        "completion_decision": normalized_decision,
        "user_reported_completed": completed,
        "completion_evidence_source": "USER_REPORT",
        "externally_verified": False,
        "persistent": False,
        "checklist_mutated": False,
        "ozon_mutation_called": False,
        "execution_allowed": False,
        "execution_ready": False,
        "executed": False,
    }


def _blocked(code, source, item_id):
    return {
        "error": True,
        "code": code,
        "status": "PRODUCT_DECISION_USER_ACTION_COMPLETION_BLOCKED",
        "user_action_completion_evidence_id": None,
        "user_action_checklist_id": source.get("user_action_checklist_id"),
        "user_action_guidance_id": source.get("user_action_guidance_id"),
        "sku": source.get("sku"),
        "item_id": item_id or None,
        "completion_decision": None,
        "user_reported_completed": False,
        "completion_evidence_source": None,
        "externally_verified": False,
        "persistent": False,
        "checklist_mutated": False,
        "ozon_mutation_called": False,
        "execution_allowed": False,
        "execution_ready": False,
        "executed": False,
    }
