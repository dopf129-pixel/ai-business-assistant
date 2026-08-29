ALLOWED_SCOPES = {"RETURN", "ADVERTISING", "STORAGE"}
ALLOWED_CONFIRMATIONS = {"KEEP", "USE_CURRENT", "REMOVE", "REPLACE"}
ALLOWED_AUTHORIZATION_DECISIONS = {"AUTHORIZE", "REJECT"}


def build_mapping_rereview_candidate(scope_quality, active_mapping, catalog):
    quality = _dict(scope_quality)
    source_catalog = _dict(catalog)
    scope = str(quality.get("scope") or "").strip().upper()
    if scope not in ALLOWED_SCOPES:
        return _error("PERIOD_PROFIT_MAPPING_REREVIEW_SCOPE_INVALID")
    if quality.get("mapping_available") is not True or not isinstance(active_mapping, dict):
        return _error("PERIOD_PROFIT_MAPPING_REREVIEW_ACTIVE_MAPPING_REQUIRED")
    mapping = dict(active_mapping)
    if not mapping.get("mapping_id"):
        return _error("PERIOD_PROFIT_MAPPING_REREVIEW_ACTIVE_MAPPING_REQUIRED")
    mapping_scope = str(mapping.get("scope") or "").strip().upper()
    if mapping_scope and mapping_scope != scope:
        return _error("PERIOD_PROFIT_MAPPING_REREVIEW_SCOPE_MISMATCH")
    if source_catalog.get("status") != "RETURN_FINANCIAL_OPERATION_CATALOG_READY" or source_catalog.get("error") is not False:
        return _error("PERIOD_PROFIT_MAPPING_REREVIEW_CATALOG_REQUIRED")

    try:
        missing = {int(value) for value in quality.get("missing_type_ids") or []}
        renamed = {
            int(row.get("type_id"))
            for row in quality.get("renamed_operations") or []
            if isinstance(row, dict) and row.get("type_id") is not None
        }
    except (TypeError, ValueError):
        return _error("PERIOD_PROFIT_MAPPING_REREVIEW_DRIFT_TARGETS_INVALID")
    affected_ids = sorted(missing | renamed)
    if not affected_ids:
        return _error("PERIOD_PROFIT_MAPPING_REREVIEW_DRIFT_TARGETS_REQUIRED")

    mapping_operations = [row for row in mapping.get("operations") or [] if _valid_operation(row)]
    catalog_operations = [row for row in source_catalog.get("operations") or [] if _valid_operation(row)]
    mapped_by_id = {int(row["type_id"]): dict(row) for row in mapping_operations}
    catalog_by_id = {int(row["type_id"]): dict(row) for row in catalog_operations}
    targets = []
    for type_id in affected_ids:
        mapped = mapped_by_id.get(type_id)
        if mapped is None:
            return _error("PERIOD_PROFIT_MAPPING_REREVIEW_MAPPING_TARGET_MISSING")
        targets.append({
            "type_id": type_id,
            "drift_kind": "MISSING" if type_id in missing else "RENAMED",
            "mapped_operation": _operation(mapped),
            "current_operation": _operation(catalog_by_id[type_id]) if type_id in catalog_by_id else None,
            "human_confirmation_required": True,
        })

    return {
        "error": False,
        "status": "PERIOD_PROFIT_MAPPING_REREVIEW_CANDIDATE_READY",
        "scope": scope,
        "active_mapping_id": mapping.get("mapping_id"),
        "active_operations": [_operation(row) for row in mapping_operations],
        "targets": targets,
        "affected_type_ids": affected_ids,
        "catalog_operations": [_operation(row) for row in catalog_operations],
        "human_confirmation_required": True,
        "automatic_remap_allowed": False,
        "automatic_activation_allowed": False,
        "profit_adjustment_allowed": False,
        "read_only": True,
        "executed": False,
    }


def build_mapping_rereview_confirmation(candidate, decisions):
    source = _dict(candidate)
    if source.get("status") != "PERIOD_PROFIT_MAPPING_REREVIEW_CANDIDATE_READY" or source.get("error") is not False:
        return _error("PERIOD_PROFIT_MAPPING_REREVIEW_CANDIDATE_REQUIRED")
    if decisions is not None and not isinstance(decisions, (list, tuple)):
        return _error("PERIOD_PROFIT_MAPPING_REREVIEW_CONFIRMATION_INVALID")
    decision_by_id = {}
    for raw in decisions or []:
        if not isinstance(raw, dict) or raw.get("type_id") is None:
            return _error("PERIOD_PROFIT_MAPPING_REREVIEW_CONFIRMATION_INVALID")
        try:
            type_id = int(raw.get("type_id"))
        except (TypeError, ValueError):
            return _error("PERIOD_PROFIT_MAPPING_REREVIEW_CONFIRMATION_INVALID")
        choice = str(raw.get("decision") or "").strip().upper()
        if choice not in ALLOWED_CONFIRMATIONS or type_id in decision_by_id:
            return _error("PERIOD_PROFIT_MAPPING_REREVIEW_CONFIRMATION_INVALID")
        decision_by_id[type_id] = dict(raw, decision=choice)

    try:
        required = {int(value) for value in source.get("affected_type_ids") or []}
    except (TypeError, ValueError):
        return _error("PERIOD_PROFIT_MAPPING_REREVIEW_CANDIDATE_INVALID")
    if set(decision_by_id) != required:
        return _error("PERIOD_PROFIT_MAPPING_REREVIEW_ALL_TARGETS_REQUIRE_CONFIRMATION")

    catalog_by_id = {
        int(row["type_id"]): dict(row)
        for row in source.get("catalog_operations") or []
        if _valid_operation(row)
    }
    targets = {
        int(row["type_id"]): dict(row)
        for row in source.get("targets") or []
        if isinstance(row, dict) and row.get("type_id") is not None
    }
    active_operations = [
        _operation(row) for row in source.get("active_operations") or [] if _valid_operation(row)
    ]
    active_type_ids = {row["type_id"] for row in active_operations}
    if not required.issubset(targets):
        return _error("PERIOD_PROFIT_MAPPING_REREVIEW_CANDIDATE_INVALID")

    confirmed = []
    for type_id in sorted(required):
        decision = decision_by_id[type_id]
        choice = decision["decision"]
        target = targets[type_id]
        replacement = None
        if choice == "KEEP":
            replacement = target.get("mapped_operation")
            if not _valid_operation(replacement):
                return _error("PERIOD_PROFIT_MAPPING_REREVIEW_MAPPED_OPERATION_INVALID")
        elif choice == "USE_CURRENT":
            replacement = target.get("current_operation")
            if not _valid_operation(replacement):
                return _error("PERIOD_PROFIT_MAPPING_REREVIEW_CURRENT_OPERATION_UNAVAILABLE")
        elif choice == "REPLACE":
            try:
                replacement_id = int(decision.get("replacement_type_id"))
            except (TypeError, ValueError):
                return _error("PERIOD_PROFIT_MAPPING_REREVIEW_REPLACEMENT_TYPE_ID_REQUIRED")
            if replacement_id in active_type_ids and replacement_id != type_id:
                return _error("PERIOD_PROFIT_MAPPING_REREVIEW_REPLACEMENT_COLLIDES_WITH_ACTIVE_OPERATION")
            replacement = catalog_by_id.get(replacement_id)
            if replacement is None:
                return _error("PERIOD_PROFIT_MAPPING_REREVIEW_REPLACEMENT_NOT_IN_CATALOG")
        confirmed.append({
            "type_id": type_id,
            "decision": choice,
            "replacement_operation": _operation(replacement) if replacement else None,
            "human_confirmed": True,
        })

    return {
        "error": False,
        "status": "PERIOD_PROFIT_MAPPING_REREVIEW_CONFIRMATION_READY",
        "scope": source.get("scope"),
        "active_mapping_id": source.get("active_mapping_id"),
        "active_operations": active_operations,
        "confirmations": confirmed,
        "human_confirmed": True,
        "authorization_required": True,
        "automatic_remap_allowed": False,
        "automatic_activation_allowed": False,
        "profit_adjustment_allowed": False,
        "read_only": True,
        "executed": False,
    }


def build_mapping_replacement_draft(confirmation):
    source = _dict(confirmation)
    if source.get("status") != "PERIOD_PROFIT_MAPPING_REREVIEW_CONFIRMATION_READY" or source.get("error") is not False:
        return _error("PERIOD_PROFIT_MAPPING_REREVIEW_CONFIRMATION_REQUIRED")
    active_operations = [row for row in source.get("active_operations") or [] if _valid_operation(row)]
    operations = {int(row["type_id"]): _operation(row) for row in active_operations}
    for row in source.get("confirmations") or []:
        if not isinstance(row, dict) or row.get("type_id") is None:
            return _error("PERIOD_PROFIT_MAPPING_REREVIEW_CONFIRMATION_INVALID")
        try:
            old_id = int(row.get("type_id"))
        except (TypeError, ValueError):
            return _error("PERIOD_PROFIT_MAPPING_REREVIEW_CONFIRMATION_INVALID")
        operations.pop(old_id, None)
        replacement = row.get("replacement_operation")
        if replacement is not None:
            if not _valid_operation(replacement):
                return _error("PERIOD_PROFIT_MAPPING_REREVIEW_REPLACEMENT_INVALID")
            normalized = _operation(replacement)
            operations[int(normalized["type_id"])] = normalized
    replacement_operations = sorted(operations.values(), key=lambda row: (row["type_id"], str(row.get("name"))))
    if not replacement_operations:
        return _error("PERIOD_PROFIT_MAPPING_REPLACEMENT_DRAFT_EMPTY")
    return {
        "error": False,
        "status": "PERIOD_PROFIT_MAPPING_REPLACEMENT_DRAFT_READY",
        "scope": source.get("scope"),
        "active_mapping_id": source.get("active_mapping_id"),
        "operations": replacement_operations,
        "type_ids": [row["type_id"] for row in replacement_operations],
        "operation_names": [row.get("name") for row in replacement_operations],
        "authorization_required": True,
        "mapping_authorized": False,
        "automatic_activation_allowed": False,
        "profit_adjustment_allowed": False,
        "read_only": True,
        "executed": False,
    }


def build_mapping_replacement_diff(active_mapping, draft):
    if not isinstance(active_mapping, dict):
        return _error("PERIOD_PROFIT_MAPPING_REREVIEW_ACTIVE_MAPPING_REQUIRED")
    active = dict(active_mapping)
    source = _dict(draft)
    if source.get("status") != "PERIOD_PROFIT_MAPPING_REPLACEMENT_DRAFT_READY" or source.get("error") is not False:
        return _error("PERIOD_PROFIT_MAPPING_REPLACEMENT_DRAFT_REQUIRED")
    before = {int(row["type_id"]): _operation(row) for row in active.get("operations") or [] if _valid_operation(row)}
    after = {int(row["type_id"]): _operation(row) for row in source.get("operations") or [] if _valid_operation(row)}
    added = [after[key] for key in sorted(after.keys() - before.keys())]
    removed = [before[key] for key in sorted(before.keys() - after.keys())]
    changed = [
        {"type_id": key, "before": before[key], "after": after[key]}
        for key in sorted(before.keys() & after.keys())
        if before[key] != after[key]
    ]
    return {
        "error": False,
        "status": "PERIOD_PROFIT_MAPPING_REPLACEMENT_DIFF_READY",
        "scope": source.get("scope"),
        "active_mapping_id": active.get("mapping_id"),
        "added_operations": added,
        "removed_operations": removed,
        "changed_operations": changed,
        "change_count": len(added) + len(removed) + len(changed),
        "replacement_operations": list(source.get("operations") or []),
        "authorization_required": True,
        "automatic_activation_allowed": False,
        "profit_adjustment_allowed": False,
        "read_only": True,
        "executed": False,
    }


def build_mapping_replacement_authorization(diff, decision):
    source = _dict(diff)
    if source.get("status") != "PERIOD_PROFIT_MAPPING_REPLACEMENT_DIFF_READY" or source.get("error") is not False:
        return _error("PERIOD_PROFIT_MAPPING_REPLACEMENT_DIFF_REQUIRED")
    choice = str(decision or "").strip().upper()
    if choice not in ALLOWED_AUTHORIZATION_DECISIONS:
        return _error("PERIOD_PROFIT_MAPPING_REPLACEMENT_AUTHORIZATION_DECISION_INVALID")
    authorized = choice == "AUTHORIZE"
    return {
        "error": False,
        "status": "PERIOD_PROFIT_MAPPING_REPLACEMENT_AUTHORIZED" if authorized else "PERIOD_PROFIT_MAPPING_REPLACEMENT_REJECTED",
        "scope": source.get("scope"),
        "decision": choice,
        "active_mapping_id": source.get("active_mapping_id"),
        "replacement_operations": list(source.get("replacement_operations") or []),
        "change_count": int(source.get("change_count") or 0),
        "mapping_build_allowed": authorized,
        "mapping_authorized": authorized,
        "registry_save_allowed": False,
        "activation_allowed": False,
        "automatic_activation_allowed": False,
        "profit_adjustment_allowed": False,
        "read_only": True,
        "executed": False,
    }


def _dict(value):
    return dict(value) if isinstance(value, dict) else {}


def _valid_operation(row):
    if not isinstance(row, dict) or row.get("type_id") is None or not row.get("name"):
        return False
    try:
        int(row.get("type_id"))
    except (TypeError, ValueError):
        return False
    return True


def _operation(row):
    source = dict(row)
    return {
        "type_id": int(source.get("type_id")),
        "name": source.get("name"),
        "description": source.get("description"),
        "source": source.get("source"),
    }


def _error(code):
    return {
        "error": True,
        "code": code,
        "status": "PERIOD_PROFIT_MAPPING_REREVIEW_UNAVAILABLE",
        "automatic_remap_allowed": False,
        "automatic_activation_allowed": False,
        "profit_adjustment_allowed": False,
        "executed": False,
    }
