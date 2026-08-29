from copy import deepcopy


VALID_DECISIONS = {"CONFIRM_COMPLETED", "NOT_COMPLETED"}


def build_product_decision_user_action_completion_revision(previous_persisted, decision):
    source = deepcopy(dict(previous_persisted or {}))
    normalized_decision = str(decision or "").strip().upper()
    evidence_id = str(source.get("user_action_completion_evidence_id") or "").strip()
    checklist_id = str(source.get("user_action_checklist_id") or "").strip()
    sku = str(source.get("sku") or "").strip()

    if not evidence_id or not checklist_id or not sku:
        return _blocked("USER_ACTION_COMPLETION_REVISION_CONTEXT_REQUIRED", source)
    if source.get("status") != "PRODUCT_DECISION_USER_ACTION_COMPLETION_PERSISTED":
        return _blocked("USER_ACTION_COMPLETION_REVISION_SOURCE_STATUS_INVALID", source)
    if source.get("completion_persisted") is not True or source.get("persistent") is not True:
        return _blocked("USER_ACTION_COMPLETION_REVISION_PERSISTED_SOURCE_REQUIRED", source)
    if source.get("completion_evidence_source") != "USER_REPORT" or source.get("externally_verified") is not False:
        return _blocked("USER_ACTION_COMPLETION_REVISION_SOURCE_INVALID", source)
    if normalized_decision not in VALID_DECISIONS:
        return _blocked("USER_ACTION_COMPLETION_REVISION_DECISION_INVALID", source)
    if (
        source.get("checklist_mutated") is not False
        or source.get("ozon_mutation_called") is not False
        or source.get("execution_allowed") is not False
        or source.get("execution_ready") is not False
        or source.get("executed") is not False
    ):
        return _blocked("USER_ACTION_COMPLETION_REVISION_SAFETY_BOUNDARY_VIOLATION", source)

    try:
        previous_revision = int(source.get("completion_revision") or 1)
    except (TypeError, ValueError):
        return _blocked("USER_ACTION_COMPLETION_REVISION_NUMBER_INVALID", source)
    if previous_revision < 1:
        return _blocked("USER_ACTION_COMPLETION_REVISION_NUMBER_INVALID", source)

    next_revision = previous_revision + 1
    completed = normalized_decision == "CONFIRM_COMPLETED"
    root_id = str(source.get("completion_evidence_root_id") or evidence_id).strip()
    status = (
        "PRODUCT_DECISION_USER_ACTION_COMPLETION_CONFIRMED"
        if completed
        else "PRODUCT_DECISION_USER_ACTION_COMPLETION_DECLINED"
    )

    return {
        "error": False,
        "status": status,
        "completion_revision_ready": True,
        "completion_evidence_root_id": root_id,
        "user_action_completion_evidence_id": "%s:revision:%d" % (root_id, next_revision),
        "previous_user_action_completion_evidence_id": evidence_id,
        "user_action_checklist_id": checklist_id,
        "user_action_guidance_id": source.get("user_action_guidance_id"),
        "sku": sku,
        "item_id": source.get("item_id"),
        "completion_revision": next_revision,
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


def _blocked(code, source):
    return {
        "error": True,
        "code": code,
        "status": "PRODUCT_DECISION_USER_ACTION_COMPLETION_REVISION_BLOCKED",
        "completion_revision_ready": False,
        "completion_evidence_root_id": source.get("completion_evidence_root_id"),
        "user_action_completion_evidence_id": None,
        "user_action_checklist_id": source.get("user_action_checklist_id"),
        "sku": source.get("sku"),
        "completion_revision": None,
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
