SCOPES = {"RETURN", "ADVERTISING", "STORAGE"}
ACTIONS = {"ACTIVATE", "ROLLBACK"}
DECISIONS = {"APPLY", "REJECT"}


def build_mapping_admin_preview(history, scope, action, revision_id):
    normalized_scope = str(scope or "").strip().upper()
    normalized_action = str(action or "").strip().upper()
    source = dict(history or {})
    if normalized_scope not in SCOPES or normalized_action not in ACTIONS:
        return _error("PERIOD_PROFIT_MAPPING_ADMIN_REQUEST_INVALID")
    if source.get("status") != "PERIOD_PROFIT_MAPPING_HISTORY_READY" or source.get("scope") != normalized_scope:
        return _error("PERIOD_PROFIT_MAPPING_HISTORY_REQUIRED")

    revision = next(
        (dict(item) for item in source.get("revisions") or [] if item.get("revision_id") == revision_id),
        None,
    )
    if revision is None:
        return _error("PERIOD_PROFIT_MAPPING_REVISION_NOT_FOUND")

    return {
        "error": False,
        "status": "PERIOD_PROFIT_MAPPING_ADMIN_PREVIEW_READY",
        "scope": normalized_scope,
        "action": normalized_action,
        "target_revision_id": revision_id,
        "current_active_revision_id": source.get("active_revision_id"),
        "target_mapping_id": revision.get("mapping_id"),
        "target_revision": revision,
        "explicit_decision_required": True,
        "automatic_apply_allowed": False,
        "ozon_mutation": False,
        "profit_adjustment_allowed": False,
        "executed": False,
    }


def build_mapping_admin_decision(preview, decision):
    source = dict(preview or {})
    if source.get("status") != "PERIOD_PROFIT_MAPPING_ADMIN_PREVIEW_READY" or source.get("error") is not False:
        return _error("PERIOD_PROFIT_MAPPING_ADMIN_PREVIEW_REQUIRED")
    choice = str(decision or "").strip().upper()
    if choice not in DECISIONS:
        return _error("PERIOD_PROFIT_MAPPING_ADMIN_DECISION_INVALID")
    apply_allowed = choice == "APPLY"
    return {
        "error": False,
        "status": "PERIOD_PROFIT_MAPPING_ADMIN_DECISION_READY",
        "decision": choice,
        "scope": source.get("scope"),
        "action": source.get("action"),
        "target_revision_id": source.get("target_revision_id"),
        "target_mapping_id": source.get("target_mapping_id"),
        "registry_apply_allowed": apply_allowed,
        "automatic_apply_allowed": False,
        "ozon_mutation": False,
        "profit_adjustment_allowed": False,
        "executed": False,
    }


def _error(code):
    return {
        "error": True,
        "code": code,
        "status": "PERIOD_PROFIT_MAPPING_ADMIN_UNAVAILABLE",
        "automatic_apply_allowed": False,
        "ozon_mutation": False,
        "profit_adjustment_allowed": False,
        "executed": False,
    }
