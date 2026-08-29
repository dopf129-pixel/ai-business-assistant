from period_profit_expense_operation_authorized_mapping import (
    build_period_profit_expense_operation_authorized_mapping,
)
from period_profit_mapping_integrity import verify_period_profit_mapping_integrity
from period_profit_mapping_rereview import build_mapping_replacement_diff
from return_financial_operation_authorized_mapping import (
    build_return_financial_operation_authorized_mapping,
)


ALLOWED_SCOPES = {"RETURN", "ADVERTISING", "STORAGE"}
ALLOWED_SAVE_DECISIONS = {"SAVE", "REJECT"}


def build_authorized_replacement_mapping(authorization):
    """v139: build the immutable production-compatible mapping artifact after v138 authorization."""
    source = _dict(authorization)
    if (
        source.get("status") != "PERIOD_PROFIT_MAPPING_REPLACEMENT_AUTHORIZED"
        or source.get("error") is not False
        or source.get("decision") != "AUTHORIZE"
        or source.get("mapping_build_allowed") is not True
        or source.get("mapping_authorized") is not True
        or source.get("registry_save_allowed") is not False
        or source.get("activation_allowed") is not False
        or source.get("automatic_activation_allowed") is not False
        or source.get("profit_adjustment_allowed") is not False
        or source.get("executed") is not False
    ):
        return _error("PERIOD_PROFIT_MAPPING_REPLACEMENT_BUILD_AUTHORIZATION_REQUIRED")

    scope = _scope(source.get("scope"))
    if scope not in ALLOWED_SCOPES:
        return _error("PERIOD_PROFIT_MAPPING_REPLACEMENT_SCOPE_INVALID")
    operations = _normalized_operations(source.get("replacement_operations"))
    if not operations:
        return _error("PERIOD_PROFIT_MAPPING_REPLACEMENT_OPERATIONS_REQUIRED")

    if scope == "RETURN":
        artifact = build_return_financial_operation_authorized_mapping({
            "error": False,
            "status": "RETURN_FINANCIAL_OPERATION_SELECTION_AUTHORIZED",
            "mapping_authorized": True,
            "financial_evidence_mapping_allowed": True,
            "selected_operations": operations,
        })
    else:
        artifact = build_period_profit_expense_operation_authorized_mapping({
            "error": False,
            "status": "PERIOD_PROFIT_EXPENSE_OPERATION_AUTHORIZED",
            "scope": scope,
            "mapping_authorized": True,
            "financial_evidence_mapping_allowed": True,
            "selected_operations": operations,
        })

    if artifact.get("error") is not False:
        return _error("PERIOD_PROFIT_MAPPING_REPLACEMENT_ARTIFACT_BUILD_FAILED")
    integrity = verify_period_profit_mapping_integrity(scope, artifact)
    if integrity.get("integrity_valid") is not True:
        return _error("PERIOD_PROFIT_MAPPING_REPLACEMENT_ARTIFACT_INTEGRITY_FAILED")
    return artifact


def build_replacement_persistence_preview(registry_service, authorization, artifact, diff):
    """v140: preview the exact inactive revision that SAVE would append. No registry mutation."""
    auth = _dict(authorization)
    mapping = _dict(artifact)
    change = _dict(diff)
    if not _authorized_chain_valid(auth, mapping, change):
        return _error("PERIOD_PROFIT_MAPPING_REPLACEMENT_PREVIEW_INPUT_INVALID")

    scope = _scope(auth.get("scope"))
    history = registry_service.history(scope)
    if history.get("error") is not False or history.get("status") != "PERIOD_PROFIT_MAPPING_HISTORY_READY":
        return _error("PERIOD_PROFIT_MAPPING_REPLACEMENT_REGISTRY_HISTORY_REQUIRED")
    if history.get("registry_health_status") != "HEALTHY":
        return _error("PERIOD_PROFIT_MAPPING_REPLACEMENT_REGISTRY_HEALTH_BLOCKED")

    revisions = list(history.get("revisions") or [])
    active_revision_id = history.get("active_revision_id")
    active_revision = next(
        (row for row in revisions if isinstance(row, dict) and row.get("revision_id") == active_revision_id),
        None,
    )
    if active_revision is None or active_revision.get("mapping_id") != auth.get("active_mapping_id"):
        return _error("PERIOD_PROFIT_MAPPING_REPLACEMENT_ACTIVE_LINEAGE_MISMATCH")
    active_mapping = active_revision.get("mapping")
    if not isinstance(active_mapping, dict):
        return _error("PERIOD_PROFIT_MAPPING_REPLACEMENT_ACTIVE_MAPPING_REQUIRED")

    recomputed = build_mapping_replacement_diff(
        active_mapping,
        {
            "error": False,
            "status": "PERIOD_PROFIT_MAPPING_REPLACEMENT_DRAFT_READY",
            "scope": scope,
            "active_mapping_id": auth.get("active_mapping_id"),
            "operations": list(mapping.get("operations") or []),
        },
    )
    if recomputed.get("error") is not False or not _diff_matches(change, recomputed):
        return _error("PERIOD_PROFIT_MAPPING_REPLACEMENT_DIFF_MISMATCH")

    expected_number = len(revisions) + 1
    expected_revision_id = f"{scope.lower()}-mapping-r{expected_number}"
    return {
        "error": False,
        "status": "PERIOD_PROFIT_MAPPING_REPLACEMENT_PERSISTENCE_PREVIEW_READY",
        "scope": scope,
        "current_active_revision_id": active_revision_id,
        "current_active_mapping_id": active_revision.get("mapping_id"),
        "current_revision_count": len(revisions),
        "new_mapping_id": mapping.get("mapping_id"),
        "expected_revision_number": expected_number,
        "expected_revision_id": expected_revision_id,
        "added_operations": list(recomputed.get("added_operations") or []),
        "removed_operations": list(recomputed.get("removed_operations") or []),
        "changed_operations": list(recomputed.get("changed_operations") or []),
        "change_count": int(recomputed.get("change_count") or 0),
        "explicit_save_decision_required": True,
        "registry_save_allowed": False,
        "activation_allowed": False,
        "automatic_activation_allowed": False,
        "profit_adjustment_allowed": False,
        "ozon_mutation": False,
        "read_only": True,
        "executed": False,
    }


def build_replacement_save_decision(preview, decision):
    """v141: explicit SAVE/REJECT gate. SAVE permits persistence only, never activation."""
    source = _dict(preview)
    if source.get("status") != "PERIOD_PROFIT_MAPPING_REPLACEMENT_PERSISTENCE_PREVIEW_READY" or source.get("error") is not False:
        return _error("PERIOD_PROFIT_MAPPING_REPLACEMENT_PERSISTENCE_PREVIEW_REQUIRED")
    choice = str(decision or "").strip().upper()
    if choice not in ALLOWED_SAVE_DECISIONS:
        return _error("PERIOD_PROFIT_MAPPING_REPLACEMENT_SAVE_DECISION_INVALID")
    save_allowed = choice == "SAVE"
    return {
        "error": False,
        "status": "PERIOD_PROFIT_MAPPING_REPLACEMENT_SAVE_DECISION_READY",
        "decision": choice,
        "scope": source.get("scope"),
        "current_active_revision_id": source.get("current_active_revision_id"),
        "current_revision_count": source.get("current_revision_count"),
        "target_mapping_id": source.get("new_mapping_id"),
        "expected_revision_id": source.get("expected_revision_id"),
        "registry_save_allowed": save_allowed,
        "activation_allowed": False,
        "automatic_activation_allowed": False,
        "profit_adjustment_allowed": False,
        "ozon_mutation": False,
        "executed": False,
    }


def persist_replacement_as_inactive(registry_service, artifact, save_decision, actor="USER"):
    """v142: append an immutable inactive revision only after an explicit, still-current SAVE."""
    mapping = _dict(artifact)
    decision = _dict(save_decision)
    if (
        decision.get("status") != "PERIOD_PROFIT_MAPPING_REPLACEMENT_SAVE_DECISION_READY"
        or decision.get("error") is not False
        or decision.get("decision") != "SAVE"
        or decision.get("registry_save_allowed") is not True
        or decision.get("activation_allowed") is not False
        or decision.get("automatic_activation_allowed") is not False
        or decision.get("profit_adjustment_allowed") is not False
        or decision.get("ozon_mutation") is not False
        or decision.get("executed") is not False
    ):
        return _error("PERIOD_PROFIT_MAPPING_REPLACEMENT_EXPLICIT_SAVE_REQUIRED")

    scope = _scope(decision.get("scope"))
    if scope not in ALLOWED_SCOPES or mapping.get("mapping_id") != decision.get("target_mapping_id"):
        return _error("PERIOD_PROFIT_MAPPING_REPLACEMENT_SAVE_TARGET_MISMATCH")
    if verify_period_profit_mapping_integrity(scope, mapping).get("integrity_valid") is not True:
        return _error("PERIOD_PROFIT_MAPPING_REPLACEMENT_ARTIFACT_INTEGRITY_FAILED")

    before = registry_service.history(scope)
    if (
        before.get("error") is not False
        or before.get("active_revision_id") != decision.get("current_active_revision_id")
        or len(before.get("revisions") or []) != decision.get("current_revision_count")
    ):
        return _error("PERIOD_PROFIT_MAPPING_REPLACEMENT_SAVE_PREVIEW_STALE")

    saved = registry_service.save(scope, mapping, actor=actor, activate=False)
    if saved.get("error") is not False:
        return saved
    if saved.get("active") is not False or saved.get("revision_id") != decision.get("expected_revision_id"):
        return _error("PERIOD_PROFIT_MAPPING_REPLACEMENT_INACTIVE_SAVE_INVARIANT_FAILED")

    after = registry_service.history(scope)
    if after.get("active_revision_id") != decision.get("current_active_revision_id"):
        return _error("PERIOD_PROFIT_MAPPING_REPLACEMENT_ACTIVE_REVISION_CHANGED")
    return {
        "error": False,
        "status": "PERIOD_PROFIT_MAPPING_REPLACEMENT_INACTIVE_REVISION_SAVED",
        "scope": scope,
        "revision_id": saved.get("revision_id"),
        "mapping_id": saved.get("mapping_id"),
        "active": False,
        "active_revision_id": after.get("active_revision_id"),
        "activation_handoff_required": True,
        "activation_allowed": False,
        "automatic_activation_allowed": False,
        "profit_adjustment_allowed": False,
        "ozon_mutation": False,
        "executed": False,
    }


def build_replacement_activation_handoff(admin_service, persisted_revision):
    """v143: hand the inactive revision to the existing preview -> APPLY/REJECT admin flow."""
    source = _dict(persisted_revision)
    if (
        source.get("status") != "PERIOD_PROFIT_MAPPING_REPLACEMENT_INACTIVE_REVISION_SAVED"
        or source.get("error") is not False
        or source.get("active") is not False
        or source.get("activation_handoff_required") is not True
    ):
        return _error("PERIOD_PROFIT_MAPPING_REPLACEMENT_INACTIVE_REVISION_REQUIRED")
    preview = admin_service.preview(source.get("scope"), "ACTIVATE", source.get("revision_id"))
    if preview.get("error") is not False or preview.get("status") != "PERIOD_PROFIT_MAPPING_ADMIN_PREVIEW_READY":
        return _error("PERIOD_PROFIT_MAPPING_REPLACEMENT_ACTIVATION_PREVIEW_FAILED")
    if preview.get("target_revision_id") != source.get("revision_id") or preview.get("target_mapping_id") != source.get("mapping_id"):
        return _error("PERIOD_PROFIT_MAPPING_REPLACEMENT_ACTIVATION_TARGET_MISMATCH")
    result = dict(preview)
    result["status"] = "PERIOD_PROFIT_MAPPING_REPLACEMENT_ACTIVATION_HANDOFF_READY"
    result["explicit_decision_required"] = True
    result["activation_allowed"] = False
    result["automatic_activation_allowed"] = False
    result["executed"] = False
    return result


def _authorized_chain_valid(auth, mapping, diff):
    scope = _scope(auth.get("scope"))
    authorized_operations = _normalized_operations(auth.get("replacement_operations"))
    mapping_operations = _normalized_operations(mapping.get("operations"))
    diff_operations = _normalized_operations(diff.get("replacement_operations"))
    return (
        auth.get("status") == "PERIOD_PROFIT_MAPPING_REPLACEMENT_AUTHORIZED"
        and auth.get("error") is False
        and auth.get("decision") == "AUTHORIZE"
        and auth.get("mapping_build_allowed") is True
        and auth.get("registry_save_allowed") is False
        and auth.get("activation_allowed") is False
        and auth.get("automatic_activation_allowed") is False
        and auth.get("profit_adjustment_allowed") is False
        and auth.get("executed") is False
        and scope in ALLOWED_SCOPES
        and authorized_operations is not None
        and authorized_operations == mapping_operations
        and authorized_operations == diff_operations
        and mapping.get("error") is False
        and verify_period_profit_mapping_integrity(scope, mapping).get("integrity_valid") is True
        and diff.get("status") == "PERIOD_PROFIT_MAPPING_REPLACEMENT_DIFF_READY"
        and diff.get("error") is False
        and _scope(diff.get("scope")) == scope
        and diff.get("active_mapping_id") == auth.get("active_mapping_id")
    )


def _diff_matches(provided, recomputed):
    return (
        _normalized_operations(provided.get("added_operations")) == _normalized_operations(recomputed.get("added_operations"))
        and _normalized_operations(provided.get("removed_operations")) == _normalized_operations(recomputed.get("removed_operations"))
        and _normalized_changed(provided.get("changed_operations")) == _normalized_changed(recomputed.get("changed_operations"))
        and int(provided.get("change_count") or 0) == int(recomputed.get("change_count") or 0)
    )


def _normalized_changed(value):
    if not isinstance(value, (list, tuple)):
        return None
    result = []
    for row in value:
        if not isinstance(row, dict) or row.get("type_id") is None:
            return None
        before = _normalized_operations([row.get("before")])
        after = _normalized_operations([row.get("after")])
        if before is None or after is None:
            return None
        try:
            type_id = int(row.get("type_id"))
        except (TypeError, ValueError):
            return None
        result.append({"type_id": type_id, "before": before[0], "after": after[0]})
    result.sort(key=lambda row: row["type_id"])
    return result


def _normalized_operations(value):
    if not isinstance(value, (list, tuple)):
        return None
    operations = []
    seen_type_ids = set()
    for row in value:
        if not isinstance(row, dict) or row.get("type_id") is None or not row.get("name"):
            return None
        try:
            type_id = int(row.get("type_id"))
        except (TypeError, ValueError):
            return None
        if type_id in seen_type_ids:
            return None
        seen_type_ids.add(type_id)
        operations.append({
            "type_id": type_id,
            "name": row.get("name"),
            "description": row.get("description"),
            "source": row.get("source"),
        })
    operations.sort(key=lambda row: (row["type_id"], str(row.get("name"))))
    return operations


def _dict(value):
    return dict(value) if isinstance(value, dict) else {}


def _scope(value):
    return str(value or "").strip().upper()


def _error(code):
    return {
        "error": True,
        "code": code,
        "status": "PERIOD_PROFIT_MAPPING_REPLACEMENT_PERSISTENCE_UNAVAILABLE",
        "registry_save_allowed": False,
        "activation_allowed": False,
        "automatic_activation_allowed": False,
        "profit_adjustment_allowed": False,
        "ozon_mutation": False,
        "executed": False,
    }
