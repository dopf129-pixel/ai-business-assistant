from copy import deepcopy


def build_product_decision_user_action_checklist(guidance):
    source = deepcopy(dict(guidance or {}))
    guidance_id = str(source.get("user_action_guidance_id") or "").strip()
    verification_id = str(source.get("decision_persistence_verification_id") or "").strip()
    sku = str(source.get("sku") or "").strip()

    if not guidance_id or not verification_id or not sku:
        return _blocked("USER_ACTION_CHECKLIST_CONTEXT_REQUIRED", source)
    if guidance_id != "product-decision-user-action-guidance:" + verification_id:
        return _blocked("USER_ACTION_CHECKLIST_GUIDANCE_ID_MISMATCH", source)
    if source.get("status") != "PRODUCT_DECISION_USER_ACTION_GUIDANCE_READY":
        return _blocked("USER_ACTION_CHECKLIST_GUIDANCE_STATUS_INVALID", source)
    if (
        source.get("user_execution_required") is not True
        or source.get("automatic_execution_prohibited") is not True
        or source.get("ozon_mutation_called") is not False
        or source.get("execution_allowed") is not False
        or source.get("execution_ready") is not False
        or source.get("executed") is not False
    ):
        return _blocked("USER_ACTION_CHECKLIST_SAFETY_BOUNDARY_VIOLATION", source)

    steps = source.get("steps")
    if not isinstance(steps, list) or not steps or any(not str(step).strip() for step in steps):
        return _blocked("USER_ACTION_CHECKLIST_STEPS_REQUIRED", source)

    items = [
        {
            "item_id": "manual-step-%d" % (index + 1),
            "position": index + 1,
            "instruction": str(step).strip(),
            "completion_source": "USER",
            "completed": False,
        }
        for index, step in enumerate(steps)
    ]

    return {
        "error": False,
        "status": "PRODUCT_DECISION_USER_ACTION_CHECKLIST_READY",
        "user_action_checklist_id": "product-decision-user-action-checklist:" + guidance_id,
        "user_action_guidance_id": guidance_id,
        "decision_persistence_verification_id": verification_id,
        "sku": sku,
        "decision_type": source.get("decision_type"),
        "priority": source.get("priority"),
        "action_type": source.get("action_type"),
        "title": source.get("title"),
        "items": items,
        "item_count": len(items),
        "completed_count": 0,
        "completion_recording_allowed": False,
        "user_execution_required": True,
        "automatic_execution_prohibited": True,
        "ozon_mutation_called": False,
        "execution_allowed": False,
        "execution_ready": False,
        "executed": False,
    }


def _blocked(code, source):
    return {
        "error": True,
        "code": code,
        "status": "PRODUCT_DECISION_USER_ACTION_CHECKLIST_BLOCKED",
        "user_action_checklist_id": None,
        "user_action_guidance_id": source.get("user_action_guidance_id"),
        "decision_persistence_verification_id": source.get("decision_persistence_verification_id"),
        "sku": source.get("sku"),
        "items": [],
        "item_count": 0,
        "completed_count": 0,
        "completion_recording_allowed": False,
        "user_execution_required": True,
        "automatic_execution_prohibited": True,
        "ozon_mutation_called": False,
        "execution_allowed": False,
        "execution_ready": False,
        "executed": False,
    }
