from copy import deepcopy


def build_product_decision_user_action_checklist_status(checklist, persisted_reports):
    source = deepcopy(dict(checklist or {}))
    reports = [deepcopy(item) for item in list(persisted_reports or []) if isinstance(item, dict)]
    checklist_id = str(source.get("user_action_checklist_id") or "").strip()
    guidance_id = str(source.get("user_action_guidance_id") or "").strip()
    sku = str(source.get("sku") or "").strip()

    if not checklist_id or not guidance_id or not sku:
        return _blocked("USER_ACTION_CHECKLIST_STATUS_CONTEXT_REQUIRED", source)
    if checklist_id != "product-decision-user-action-checklist:" + guidance_id:
        return _blocked("USER_ACTION_CHECKLIST_STATUS_ID_MISMATCH", source)
    if source.get("status") != "PRODUCT_DECISION_USER_ACTION_CHECKLIST_READY":
        return _blocked("USER_ACTION_CHECKLIST_STATUS_SOURCE_INVALID", source)
    if (
        source.get("user_execution_required") is not True
        or source.get("automatic_execution_prohibited") is not True
        or source.get("ozon_mutation_called") is not False
        or source.get("execution_allowed") is not False
        or source.get("execution_ready") is not False
        or source.get("executed") is not False
    ):
        return _blocked("USER_ACTION_CHECKLIST_STATUS_SAFETY_BOUNDARY_VIOLATION", source)

    items = source.get("items")
    if not isinstance(items, list) or not items:
        return _blocked("USER_ACTION_CHECKLIST_STATUS_ITEMS_REQUIRED", source)
    item_ids = [str(item.get("item_id") or "").strip() for item in items if isinstance(item, dict)]
    if len(item_ids) != len(items) or any(not item_id for item_id in item_ids) or len(set(item_ids)) != len(item_ids):
        return _blocked("USER_ACTION_CHECKLIST_STATUS_ITEMS_INVALID", source)

    latest = {}
    for report in reports:
        if report.get("status") != "PRODUCT_DECISION_USER_ACTION_COMPLETION_PERSISTED":
            continue
        if report.get("user_action_checklist_id") != checklist_id or str(report.get("sku") or "").strip() != sku:
            continue
        if report.get("completion_evidence_source") != "USER_REPORT" or report.get("externally_verified") is not False:
            continue
        if report.get("persistent") is not True or report.get("completion_persisted") is not True:
            continue
        if report.get("executed") is not False or report.get("execution_allowed") is not False or report.get("execution_ready") is not False:
            continue
        item_id = str(report.get("item_id") or "").strip()
        if item_id not in item_ids:
            continue
        try:
            revision = int(report.get("completion_revision") or 1)
        except (TypeError, ValueError):
            continue
        current = latest.get(item_id)
        if current is None or revision > current[0]:
            latest[item_id] = (revision, report)

    completed_item_ids = []
    reported_item_ids = []
    for item_id in item_ids:
        entry = latest.get(item_id)
        if entry is None:
            continue
        reported_item_ids.append(item_id)
        if entry[1].get("user_reported_completed") is True:
            completed_item_ids.append(item_id)

    item_count = len(item_ids)
    completed_count = len(completed_item_ids)
    reported_count = len(reported_item_ids)
    if completed_count == item_count:
        aggregate_status = "USER_REPORTED_COMPLETE"
    elif reported_count == 0:
        aggregate_status = "NO_USER_REPORTS"
    else:
        aggregate_status = "USER_REPORTED_PARTIAL"

    return {
        "error": False,
        "status": "PRODUCT_DECISION_USER_ACTION_CHECKLIST_STATUS_READY",
        "user_action_checklist_status_id": "product-decision-user-action-checklist-status:" + checklist_id,
        "user_action_checklist_id": checklist_id,
        "user_action_guidance_id": guidance_id,
        "sku": sku,
        "aggregate_status": aggregate_status,
        "item_count": item_count,
        "reported_count": reported_count,
        "completed_count": completed_count,
        "reported_item_ids": reported_item_ids,
        "completed_item_ids": completed_item_ids,
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
        "status": "PRODUCT_DECISION_USER_ACTION_CHECKLIST_STATUS_BLOCKED",
        "user_action_checklist_status_id": None,
        "user_action_checklist_id": source.get("user_action_checklist_id"),
        "sku": source.get("sku"),
        "aggregate_status": None,
        "item_count": 0,
        "reported_count": 0,
        "completed_count": 0,
        "reported_item_ids": [],
        "completed_item_ids": [],
        "completion_evidence_source": "USER_REPORT",
        "externally_verified": False,
        "persistent": False,
        "checklist_mutated": False,
        "ozon_mutation_called": False,
        "execution_allowed": False,
        "execution_ready": False,
        "executed": False,
    }
