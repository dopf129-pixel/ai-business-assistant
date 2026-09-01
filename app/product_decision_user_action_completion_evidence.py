from copy import deepcopy


VALID_COMPLETION_DECISIONS = {"CONFIRM_COMPLETED", "NOT_COMPLETED"}


def build_product_decision_user_action_completion_evidence(
    checklist,
    item_id,
    decision,
):
    if not isinstance(checklist, dict):
        return _blocked(
            "USER_ACTION_COMPLETION_CHECKLIST_INPUT_INVALID",
            {},
            None,
        )

    source = deepcopy(checklist)

    checklist_id = _required_string(
        source.get("user_action_checklist_id")
    )
    guidance_id = _required_string(
        source.get("user_action_guidance_id")
    )
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
    normalized_item_id = _required_string(item_id)
    normalized_decision = _required_string(decision)

    if normalized_decision is not None:
        normalized_decision = normalized_decision.upper()

    if not all(
        (
            checklist_id,
            guidance_id,
            verification_id,
            application_id,
            sku,
            verified_recorded_at,
            normalized_item_id,
        )
    ):
        return _blocked(
            "USER_ACTION_COMPLETION_CONTEXT_REQUIRED",
            source,
            normalized_item_id,
        )

    if (
        checklist_id
        != "product-decision-user-action-checklist:" + guidance_id
    ):
        return _blocked(
            "USER_ACTION_COMPLETION_CHECKLIST_ID_MISMATCH",
            source,
            normalized_item_id,
        )

    if (
        guidance_id
        != "product-decision-user-action-guidance:" + verification_id
    ):
        return _blocked(
            "USER_ACTION_COMPLETION_GUIDANCE_ID_MISMATCH",
            source,
            normalized_item_id,
        )

    if (
        verification_id
        != "product-decision-persistence-verification:" + application_id
    ):
        return _blocked(
            "USER_ACTION_COMPLETION_VERIFICATION_ID_MISMATCH",
            source,
            normalized_item_id,
        )

    if (
        source.get("error") is not False
        or source.get("status")
        != "PRODUCT_DECISION_USER_ACTION_CHECKLIST_READY"
    ):
        return _blocked(
            "USER_ACTION_COMPLETION_CHECKLIST_STATUS_INVALID",
            source,
            normalized_item_id,
        )

    if source.get("decision_persistence_verified") is not True:
        return _blocked(
            "USER_ACTION_COMPLETION_VERIFICATION_REQUIRED",
            source,
            normalized_item_id,
        )

    if normalized_decision not in VALID_COMPLETION_DECISIONS:
        return _blocked(
            "USER_ACTION_COMPLETION_DECISION_INVALID",
            source,
            normalized_item_id,
        )

    if (
        source.get("externally_verified") is not False
        or source.get("persistent") is not True
        or source.get("completion_recording_allowed") is not False
        or source.get("user_execution_required") is not True
        or source.get("automatic_execution_prohibited") is not True
        or source.get("ozon_mutation_called") is not False
        or source.get("execution_allowed") is not False
        or source.get("execution_ready") is not False
        or source.get("executed") is not False
    ):
        return _blocked(
            "USER_ACTION_COMPLETION_SAFETY_BOUNDARY_VIOLATION",
            source,
            normalized_item_id,
        )

    items = source.get("items")
    if not isinstance(items, list) or not items:
        return _blocked(
            "USER_ACTION_COMPLETION_ITEMS_REQUIRED",
            source,
            normalized_item_id,
        )

    item_count = source.get("item_count")
    completed_count = source.get("completed_count")
    if (
        type(item_count) is not int
        or item_count != len(items)
        or type(completed_count) is not int
        or completed_count != 0
    ):
        return _blocked(
            "USER_ACTION_COMPLETION_ITEMS_INVALID",
            source,
            normalized_item_id,
        )

    normalized_items = []
    item_ids = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            return _blocked(
                "USER_ACTION_COMPLETION_ITEMS_INVALID",
                source,
                normalized_item_id,
            )

        current_item_id = _required_string(item.get("item_id"))
        instruction = _required_string(item.get("instruction"))
        position = item.get("position")

        if (
            current_item_id is None
            or instruction is None
            or type(position) is not int
            or position != index + 1
        ):
            return _blocked(
                "USER_ACTION_COMPLETION_ITEMS_INVALID",
                source,
                normalized_item_id,
            )

        if (
            item.get("completion_source") != "USER"
            or item.get("completed") is not False
        ):
            code = (
                "USER_ACTION_COMPLETION_ITEM_STATE_INVALID"
                if current_item_id == normalized_item_id
                else "USER_ACTION_COMPLETION_ITEMS_INVALID"
            )
            return _blocked(
                code,
                source,
                normalized_item_id,
            )

        item_ids.append(current_item_id)
        normalized_items.append(
            {
                "item_id": current_item_id,
                "position": position,
                "instruction": instruction,
            }
        )

    if len(set(item_ids)) != len(item_ids):
        return _blocked(
            "USER_ACTION_COMPLETION_ITEMS_INVALID",
            source,
            normalized_item_id,
        )

    matches = [
        item
        for item in normalized_items
        if item["item_id"] == normalized_item_id
    ]
    if len(matches) != 1:
        return _blocked(
            "USER_ACTION_COMPLETION_ITEM_NOT_FOUND",
            source,
            normalized_item_id,
        )

    item = matches[0]
    completed = normalized_decision == "CONFIRM_COMPLETED"

    return {
        "error": False,
        "status": (
            "PRODUCT_DECISION_USER_ACTION_COMPLETION_CONFIRMED"
            if completed
            else "PRODUCT_DECISION_USER_ACTION_COMPLETION_DECLINED"
        ),
        "user_action_completion_evidence_id": (
            "product-decision-user-action-completion-evidence:%s:%s"
            % (checklist_id, normalized_item_id)
        ),
        "user_action_checklist_id": checklist_id,
        "user_action_guidance_id": guidance_id,
        "decision_persistence_verification_id": verification_id,
        "decision_persistence_application_id": application_id,
        "sku": sku,
        "verified_recorded_at": verified_recorded_at,
        "decision_persistence_verified": True,
        "item_id": normalized_item_id,
        "instruction": item["instruction"],
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


def _required_string(value):
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _blocked(code, source, item_id):
    safe_source = source if isinstance(source, dict) else {}
    return {
        "error": True,
        "code": code,
        "status": "PRODUCT_DECISION_USER_ACTION_COMPLETION_BLOCKED",
        "user_action_completion_evidence_id": None,
        "user_action_checklist_id": safe_source.get(
            "user_action_checklist_id"
        ),
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
        "verified_recorded_at": None,
        "decision_persistence_verified": False,
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
