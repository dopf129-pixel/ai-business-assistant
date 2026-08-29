from period_profit_mapping_admin_contract import build_mapping_admin_decision


ALLOWED_DECISIONS = {"APPLY", "REJECT"}


def build_replacement_canonical_activation_preview(admin_service, handoff):
    """v144: restore the canonical existing admin preview from the v143 handoff."""
    source = _dict(handoff)
    if (
        source.get("status") != "PERIOD_PROFIT_MAPPING_REPLACEMENT_ACTIVATION_HANDOFF_READY"
        or source.get("error") is not False
        or source.get("action") != "ACTIVATE"
        or source.get("explicit_decision_required") is not True
        or source.get("automatic_apply_allowed") is not False
        or source.get("activation_allowed") is not False
        or source.get("executed") is not False
    ):
        return _error("PERIOD_PROFIT_MAPPING_REPLACEMENT_ACTIVATION_HANDOFF_REQUIRED")

    preview = admin_service.preview(source.get("scope"), "ACTIVATE", source.get("target_revision_id"))
    if (
        preview.get("error") is not False
        or preview.get("status") != "PERIOD_PROFIT_MAPPING_ADMIN_PREVIEW_READY"
        or preview.get("target_revision_id") != source.get("target_revision_id")
        or preview.get("target_mapping_id") != source.get("target_mapping_id")
        or preview.get("current_active_revision_id") != source.get("current_active_revision_id")
    ):
        return _error("PERIOD_PROFIT_MAPPING_REPLACEMENT_ACTIVATION_PREVIEW_STALE")
    return preview


def build_replacement_activation_decision(canonical_preview, decision):
    """v145: use the existing admin APPLY/REJECT contract and retain preview lineage."""
    preview = _dict(canonical_preview)
    choice = str(decision or "").strip().upper()
    if choice not in ALLOWED_DECISIONS:
        return _error("PERIOD_PROFIT_MAPPING_REPLACEMENT_ACTIVATION_DECISION_INVALID")
    if (
        preview.get("status") != "PERIOD_PROFIT_MAPPING_ADMIN_PREVIEW_READY"
        or preview.get("error") is not False
        or preview.get("action") != "ACTIVATE"
        or preview.get("automatic_apply_allowed") is not False
        or preview.get("profit_adjustment_allowed") is not False
        or preview.get("ozon_mutation") is not False
        or preview.get("executed") is not False
    ):
        return _error("PERIOD_PROFIT_MAPPING_REPLACEMENT_CANONICAL_PREVIEW_REQUIRED")

    result = build_mapping_admin_decision(preview, choice)
    if result.get("error") is not False:
        return _error("PERIOD_PROFIT_MAPPING_REPLACEMENT_ACTIVATION_DECISION_FAILED")
    result = dict(result)
    result["expected_current_active_revision_id"] = preview.get("current_active_revision_id")
    return result


def apply_replacement_activation(admin_service, persisted_revision, decision, actor="USER"):
    """v146: execute only an explicit, still-current APPLY through the existing admin service."""
    persisted = _dict(persisted_revision)
    source = _dict(decision)
    if (
        persisted.get("status") != "PERIOD_PROFIT_MAPPING_REPLACEMENT_INACTIVE_REVISION_SAVED"
        or persisted.get("error") is not False
        or persisted.get("active") is not False
        or source.get("status") != "PERIOD_PROFIT_MAPPING_ADMIN_DECISION_READY"
        or source.get("error") is not False
        or source.get("decision") != "APPLY"
        or source.get("action") != "ACTIVATE"
        or source.get("registry_apply_allowed") is not True
        or source.get("automatic_apply_allowed") is not False
        or source.get("target_revision_id") != persisted.get("revision_id")
        or source.get("target_mapping_id") != persisted.get("mapping_id")
        or source.get("scope") != persisted.get("scope")
    ):
        return _error("PERIOD_PROFIT_MAPPING_REPLACEMENT_EXPLICIT_ACTIVATION_APPLY_REQUIRED")

    current = admin_service.preview(source.get("scope"), "ACTIVATE", source.get("target_revision_id"))
    if (
        current.get("error") is not False
        or current.get("status") != "PERIOD_PROFIT_MAPPING_ADMIN_PREVIEW_READY"
        or current.get("target_mapping_id") != source.get("target_mapping_id")
        or current.get("current_active_revision_id") != source.get("expected_current_active_revision_id")
    ):
        return _error("PERIOD_PROFIT_MAPPING_REPLACEMENT_ACTIVATION_DECISION_STALE")

    result = admin_service.apply(source, actor=actor)
    if result.get("error") is not False:
        return result
    if (
        result.get("revision_id") != persisted.get("revision_id")
        or result.get("mapping_id") != persisted.get("mapping_id")
        or result.get("admin_explicit_apply") is not True
        or result.get("profit_adjustment_allowed") is not False
        or result.get("ozon_mutation") is not False
    ):
        return _error("PERIOD_PROFIT_MAPPING_REPLACEMENT_ACTIVATION_RESULT_INVALID")
    return result


def verify_replacement_activation(registry_service, persisted_revision, activation_result):
    """v147: verify registry state after explicit activation; no further mutation."""
    persisted = _dict(persisted_revision)
    result = _dict(activation_result)
    if (
        persisted.get("status") != "PERIOD_PROFIT_MAPPING_REPLACEMENT_INACTIVE_REVISION_SAVED"
        or persisted.get("error") is not False
        or result.get("error") is not False
        or result.get("revision_id") != persisted.get("revision_id")
        or result.get("mapping_id") != persisted.get("mapping_id")
        or result.get("admin_explicit_apply") is not True
    ):
        return _error("PERIOD_PROFIT_MAPPING_REPLACEMENT_ACTIVATION_RESULT_REQUIRED")

    history = registry_service.history(persisted.get("scope"))
    if history.get("error") is not False:
        return _error("PERIOD_PROFIT_MAPPING_REPLACEMENT_ACTIVATION_HISTORY_REQUIRED")
    active_revision_id = history.get("active_revision_id")
    revision = next(
        (dict(row) for row in history.get("revisions") or [] if isinstance(row, dict) and row.get("revision_id") == active_revision_id),
        None,
    )
    if active_revision_id != persisted.get("revision_id") or revision is None or revision.get("mapping_id") != persisted.get("mapping_id"):
        return _error("PERIOD_PROFIT_MAPPING_REPLACEMENT_ACTIVATION_VERIFICATION_FAILED")

    events = [row for row in history.get("events") or [] if isinstance(row, dict)]
    matching_events = [row for row in events if row.get("event") == "ACTIVATE" and row.get("revision_id") == persisted.get("revision_id")]
    if not matching_events:
        return _error("PERIOD_PROFIT_MAPPING_REPLACEMENT_ACTIVATION_EVENT_MISSING")

    return {
        "error": False,
        "status": "PERIOD_PROFIT_MAPPING_REPLACEMENT_ACTIVATION_VERIFIED",
        "scope": persisted.get("scope"),
        "revision_id": persisted.get("revision_id"),
        "mapping_id": persisted.get("mapping_id"),
        "active_revision_id": active_revision_id,
        "activation_event_count": len(matching_events),
        "registry_verified": True,
        "profit_adjustment_allowed": False,
        "ozon_mutation": False,
        "read_only": True,
        "executed": False,
    }


def build_replacement_activation_audit(verification, decision):
    """v148: produce a read-only audit receipt for the explicitly activated revision."""
    verified = _dict(verification)
    source = _dict(decision)
    if (
        verified.get("status") != "PERIOD_PROFIT_MAPPING_REPLACEMENT_ACTIVATION_VERIFIED"
        or verified.get("error") is not False
        or verified.get("registry_verified") is not True
        or source.get("status") != "PERIOD_PROFIT_MAPPING_ADMIN_DECISION_READY"
        or source.get("error") is not False
        or source.get("decision") != "APPLY"
        or source.get("target_revision_id") != verified.get("revision_id")
        or source.get("target_mapping_id") != verified.get("mapping_id")
    ):
        return _error("PERIOD_PROFIT_MAPPING_REPLACEMENT_ACTIVATION_VERIFICATION_REQUIRED")

    return {
        "error": False,
        "status": "PERIOD_PROFIT_MAPPING_REPLACEMENT_ACTIVATION_AUDIT_READY",
        "scope": verified.get("scope"),
        "revision_id": verified.get("revision_id"),
        "mapping_id": verified.get("mapping_id"),
        "decision": "APPLY",
        "explicit_human_apply": True,
        "registry_verified": True,
        "activation_event_count": verified.get("activation_event_count"),
        "automatic_activation": False,
        "profit_adjustment_allowed": False,
        "ozon_mutation": False,
        "read_only": True,
        "executed": False,
    }


def _dict(value):
    return dict(value) if isinstance(value, dict) else {}


def _error(code):
    return {
        "error": True,
        "code": code,
        "status": "PERIOD_PROFIT_MAPPING_REPLACEMENT_ACTIVATION_UNAVAILABLE",
        "registry_apply_allowed": False,
        "automatic_activation": False,
        "profit_adjustment_allowed": False,
        "ozon_mutation": False,
        "executed": False,
    }
