def build_period_profit_mapping_observability_response(snapshot, audit_summary=None, readiness=None):
    source = dict(snapshot or {})
    if source.get("status") != "PERIOD_PROFIT_MAPPING_OBSERVABILITY_SNAPSHOT_READY":
        return {
            "error": True,
            "code": "PERIOD_PROFIT_MAPPING_OBSERVABILITY_SNAPSHOT_REQUIRED",
            "status": "PERIOD_PROFIT_MAPPING_OBSERVABILITY_RESPONSE_UNAVAILABLE",
        }

    lines = [
        "Состояние period-profit mapping registry:",
        f"• Health: {source.get('registry_health_status')}",
        f"• Schema: {source.get('schema_version')}",
        f"• Load allowed: {'да' if source.get('load_allowed') else 'нет'}",
        f"• Writable: {'да' if source.get('writable') else 'нет'}",
    ]

    stale = list(source.get("stale_scopes") or [])
    if stale:
        lines.append("• Stale active mappings: " + ", ".join(stale))
    else:
        lines.append("• Stale active mappings: нет")

    loadable = list(source.get("loadable_scopes") or [])
    lines.append("• Loadable mappings: " + (", ".join(loadable) if loadable else "нет"))

    audit = dict(audit_summary or {})
    if audit.get("status") == "PERIOD_PROFIT_MAPPING_AUDIT_SUMMARY_READY":
        lines.append(f"• Audit events: {int(audit.get('total_event_count') or 0)}")

    ready = dict(readiness or {})
    if ready.get("status") == "PERIOD_PROFIT_MAPPING_PRODUCTION_READINESS_READY":
        lines.append("• Production readiness: " + ("READY" if ready.get("ready") else "BLOCKED"))
        if ready.get("warnings"):
            lines.append("• Warnings: " + ", ".join(ready.get("warnings") or []))
        if ready.get("blocking_issues"):
            lines.append("• Blocking: " + ", ".join(ready.get("blocking_issues") or []))

    lines.append("Диагностика read-only: Ozon и формула прибыли не изменяются.")
    return {
        "error": False,
        "status": "PERIOD_PROFIT_MAPPING_OBSERVABILITY_RESPONSE_READY",
        "text": "\n".join(lines),
        "read_only": True,
        "ozon_mutation": False,
        "profit_adjustment_allowed": False,
        "executed": False,
    }
