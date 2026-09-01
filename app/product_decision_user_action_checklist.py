from copy import deepcopy


ALLOWED_DECISION_ACTIONS = {
    "REPLENISH_HIGH_PRIORITY": "REVIEW_REPLENISHMENT",
    "REPLENISH_NORMAL": "REVIEW_REPLENISHMENT",
    "INVESTIGATE_LOW_PROFIT": "REVIEW_UNIT_ECONOMICS",
    "WATCH_LOW_MARGIN": "REVIEW_MARGIN",
    "HOLD_STOCK": "MONITOR_ONLY",
}

ALLOWED_PRIORITIES = {"CRITICAL", "HIGH", "NORMAL", "LOW", "NONE"}
ALLOWED_CONFIDENCE = {"HIGH", "MEDIUM", "LOW"}


def build_product_decision_user_action_checklist(guidance):
    if not isinstance(guidance, dict):
        return _blocked(
            "USER_ACTION_CHECKLIST_GUIDANCE_INPUT_INVALID",
            {},
        )

    source = deepcopy(guidance)

    guidance_id = _required_string(source.get("user_action_guidance_id"))
    verification_id = _required_string(
        source.get("decision_persistence_verification_id")
    )
    application_id = _required_string(
        source.get("decision_persistence_application_id")
    )
    sku = _required_string(source.get("sku"))
    verified_recorded_at = _required_string(
        source.get("verified_recorded_at")
    )

    if not all(
        (
            guidance_id,
            verification_id,
            application_id,
            sku,
            verified_recorded_at,
        )
    ):
        return _blocked("USER_ACTION_CHECKLIST_CONTEXT_REQUIRED", source)

    if (
        guidance_id
        != "product-decision-user-action-guidance:" + verification_id
    ):
        return _blocked(
            "USER_ACTION_CHECKLIST_GUIDANCE_ID_MISMATCH",
            source,
        )

    if (
        verification_id
        != "product-decision-persistence-verification:" + application_id
    ):
        return _blocked(
            "USER_ACTION_CHECKLIST_VERIFICATION_ID_MISMATCH",
            source,
        )

    if (
        source.get("error") is not False
        or source.get("status")
        != "PRODUCT_DECISION_USER_ACTION_GUIDANCE_READY"
    ):
        return _blocked(
            "USER_ACTION_CHECKLIST_GUIDANCE_STATUS_INVALID",
            source,
        )

    if source.get("decision_persistence_verified") is not True:
        return _blocked(
            "USER_ACTION_CHECKLIST_VERIFICATION_REQUIRED",
            source,
        )

    if (
        source.get("externally_verified") is not False
        or source.get("persistent") is not True
        or source.get("user_execution_required") is not True
        or source.get("automatic_execution_prohibited") is not True
        or source.get("ozon_mutation_called") is not False
        or source.get("execution_allowed") is not False
        or source.get("execution_ready") is not False
        or source.get("executed") is not False
    ):
        return _blocked(
            "USER_ACTION_CHECKLIST_SAFETY_BOUNDARY_VIOLATION",
            source,
        )

    decision_type = _required_string(source.get("decision_type"))
    priority = _required_string(source.get("priority"))
    confidence = _required_string(source.get("confidence"))
    action_type = _required_string(source.get("action_type"))
    title = _required_string(source.get("title"))
    reasons = source.get("reasons")

    expected_action_type = ALLOWED_DECISION_ACTIONS.get(decision_type)
    if (
        expected_action_type is None
        or action_type != expected_action_type
        or priority not in ALLOWED_PRIORITIES
        or confidence not in ALLOWED_CONFIDENCE
        or title is None
        or not isinstance(reasons, list)
        or not reasons
        or any(_required_string(reason) is None for reason in reasons)
    ):
        return _blocked(
            "USER_ACTION_CHECKLIST_GUIDANCE_SEMANTICS_INVALID",
            source,
        )

    steps = source.get("steps")
    if (
        not isinstance(steps, list)
        or not steps
        or any(_required_string(step) is None for step in steps)
    ):
        return _blocked(
            "USER_ACTION_CHECKLIST_STEPS_REQUIRED",
            source,
        )

    normalized_steps = [_required_string(step) for step in steps]
    items = [
        {
            "item_id": "manual-step-%d" % (index + 1),
            "position": index + 1,
            "instruction": step,
            "completion_source": "USER",
            "completed": False,
        }
        for index, step in enumerate(normalized_steps)
    ]

    return {
        "error": False,
        "status": "PRODUCT_DECISION_USER_ACTION_CHECKLIST_READY",
        "user_action_checklist_id":
            "product-decision-user-action-checklist:" + guidance_id,
        "user_action_guidance_id": guidance_id,
        "decision_persistence_verification_id": verification_id,
        "decision_persistence_application_id": application_id,
        "sku": sku,
        "decision_type": decision_type,
        "priority": priority,
        "confidence": confidence,
        "action_type": action_type,
        "title": title,
        "reasons": deepcopy(reasons),
        "verified_recorded_at": verified_recorded_at,
        "decision_persistence_verified": True,
        "externally_verified": False,
        "persistent": True,
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


def _required_string(value):
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _blocked(code, source):
    safe_source = source if isinstance(source, dict) else {}
    return {
        "error": True,
        "code": code,
        "status": "PRODUCT_DECISION_USER_ACTION_CHECKLIST_BLOCKED",
        "user_action_checklist_id": None,
        "user_action_guidance_id": safe_source.get(
            "user_action_guidance_id"
        ),
        "decision_persistence_verification_id": safe_source.get(
            "decision_persistence_verification_id"
        ),
        "decision_persistence_application_id": safe_source.get(
            "decision_persistence_application_id"
        ),
        "sku": safe_source.get("sku"),
        "decision_type": None,
        "priority": None,
        "confidence": None,
        "action_type": None,
        "title": None,
        "reasons": [],
        "verified_recorded_at": None,
        "decision_persistence_verified": False,
        "externally_verified": False,
        "persistent": False,
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
