class PeriodProfitMappingObservabilityService:
    """Read-only diagnostics and readiness over the mapping registry."""

    def __init__(self, registry_service):
        self.registry_service = registry_service

    def snapshot(self):
        health = self.registry_service.health()
        scopes = {}
        stale_scopes = []
        loadable_scopes = []
        for scope, row in sorted((health.get("scopes") or {}).items()):
            item = dict(row or {})
            stale = item.get("active_revision_stale") is True
            loadable = item.get("active_mapping_loadable") is True
            if stale:
                stale_scopes.append(scope)
            if loadable:
                loadable_scopes.append(scope)
            scopes[scope] = {
                "active_revision_id": item.get("active_revision_id"),
                "latest_revision_id": item.get("latest_revision_id"),
                "revision_count": int(item.get("revision_count") or 0),
                "active_revision_stale": stale,
                "active_mapping_loadable": loadable,
            }

        return {
            "error": False,
            "status": "PERIOD_PROFIT_MAPPING_OBSERVABILITY_SNAPSHOT_READY",
            "registry_health_status": health.get("health_status"),
            "schema_version": health.get("schema_version"),
            "load_allowed": health.get("load_allowed") is True,
            "writable": health.get("writable") is True,
            "issues": list(health.get("issues") or []),
            "scopes": scopes,
            "stale_scopes": stale_scopes,
            "loadable_scopes": loadable_scopes,
            "stale_mapping_warning_required": bool(stale_scopes),
            "fail_closed": health.get("fail_closed") is True,
            "read_only": True,
            "ozon_mutation": False,
            "profit_adjustment_allowed": False,
            "executed": False,
        }

    def audit_summary(self):
        snapshot = self.snapshot()
        scope_summaries = {}
        total_events = 0
        for scope in sorted((snapshot.get("scopes") or {}).keys()):
            history = self.registry_service.history(scope)
            events = [dict(row) for row in history.get("events") or [] if isinstance(row, dict)]
            total_events += len(events)
            last_event = events[-1] if events else None
            scope_summaries[scope] = {
                "event_count": len(events),
                "last_event": dict(last_event) if last_event else None,
                "active_revision_id": history.get("active_revision_id"),
            }
        return {
            "error": False,
            "status": "PERIOD_PROFIT_MAPPING_AUDIT_SUMMARY_READY",
            "total_event_count": total_events,
            "scopes": scope_summaries,
            "read_only": True,
            "executed": False,
        }

    def production_readiness(self):
        snapshot = self.snapshot()
        blocking = []
        warnings = []
        if snapshot.get("registry_health_status") == "CORRUPT":
            blocking.append("REGISTRY_CORRUPT")
        if snapshot.get("load_allowed") is not True:
            blocking.append("REGISTRY_LOAD_BLOCKED")
        if snapshot.get("fail_closed") is not True:
            blocking.append("FAIL_CLOSED_REQUIRED")
        for scope in snapshot.get("stale_scopes") or []:
            warnings.append(f"STALE_ACTIVE_MAPPING:{scope}")

        return {
            "error": False,
            "status": "PERIOD_PROFIT_MAPPING_PRODUCTION_READINESS_READY",
            "ready": not blocking,
            "blocking_issues": blocking,
            "warnings": warnings,
            "registry_health_status": snapshot.get("registry_health_status"),
            "stale_scopes": list(snapshot.get("stale_scopes") or []),
            "loadable_scopes": list(snapshot.get("loadable_scopes") or []),
            "ozon_mutation": False,
            "profit_adjustment_allowed": False,
            "executed": False,
        }
