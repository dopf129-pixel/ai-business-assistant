DECISIONS = {"APPLY", "REJECT"}


def build_registry_recovery_preview(health, action="QUARANTINE"):
    source = dict(health or {})
    normalized_action = str(action or "").strip().upper()
    if source.get("status") != "PERIOD_PROFIT_MAPPING_REGISTRY_HEALTH_READY":
        return _error("PERIOD_PROFIT_MAPPING_REGISTRY_HEALTH_REQUIRED")
    if normalized_action != "QUARANTINE":
        return _error("PERIOD_PROFIT_MAPPING_RECOVERY_ACTION_INVALID")
    if source.get("health_status") != "CORRUPT":
        return _error("PERIOD_PROFIT_MAPPING_RECOVERY_NOT_REQUIRED")
    return {
        "error": False,
        "status": "PERIOD_PROFIT_MAPPING_RECOVERY_PREVIEW_READY",
        "action": "QUARANTINE",
        "health_status": source.get("health_status"),
        "issues": list(source.get("issues") or []),
        "explicit_decision_required": True,
        "automatic_repair_allowed": False,
        "registry_write_allowed": False,
        "ozon_mutation": False,
        "profit_adjustment_allowed": False,
        "executed": False,
    }


def build_registry_recovery_decision(preview, decision):
    source = dict(preview or {})
    if source.get("status") != "PERIOD_PROFIT_MAPPING_RECOVERY_PREVIEW_READY" or source.get("error") is not False:
        return _error("PERIOD_PROFIT_MAPPING_RECOVERY_PREVIEW_REQUIRED")
    choice = str(decision or "").strip().upper()
    if choice not in DECISIONS:
        return _error("PERIOD_PROFIT_MAPPING_RECOVERY_DECISION_INVALID")
    return {
        "error": False,
        "status": "PERIOD_PROFIT_MAPPING_RECOVERY_DECISION_READY",
        "decision": choice,
        "action": source.get("action"),
        "recovery_apply_allowed": choice == "APPLY",
        "automatic_repair_allowed": False,
        "ozon_mutation": False,
        "profit_adjustment_allowed": False,
        "executed": False,
    }


def build_registry_migration_preview(health, target_schema_version):
    source = dict(health or {})
    if source.get("status") != "PERIOD_PROFIT_MAPPING_REGISTRY_HEALTH_READY":
        return _error("PERIOD_PROFIT_MAPPING_REGISTRY_HEALTH_REQUIRED")
    try:
        target = int(target_schema_version)
    except (TypeError, ValueError):
        return _error("PERIOD_PROFIT_MAPPING_MIGRATION_TARGET_INVALID")
    current = source.get("schema_version")
    return {
        "error": False,
        "status": "PERIOD_PROFIT_MAPPING_MIGRATION_PREVIEW_READY",
        "source_schema_version": current,
        "target_schema_version": target,
        "migration_required": current != target,
        "migration_implementation_available": False,
        "migration_apply_allowed": False,
        "automatic_migration_allowed": False,
        "source_registry_mutation": False,
        "executed": False,
    }


def _error(code):
    return {
        "error": True,
        "code": code,
        "status": "PERIOD_PROFIT_MAPPING_RECOVERY_UNAVAILABLE",
        "automatic_repair_allowed": False,
        "ozon_mutation": False,
        "profit_adjustment_allowed": False,
        "executed": False,
    }
