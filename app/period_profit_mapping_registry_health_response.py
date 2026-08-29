def build_period_profit_mapping_registry_health_response(health):
    source = dict(health or {})
    if source.get("status") != "PERIOD_PROFIT_MAPPING_REGISTRY_HEALTH_READY":
        return {
            "error": True,
            "code": "PERIOD_PROFIT_MAPPING_REGISTRY_HEALTH_REQUIRED",
            "status": "PERIOD_PROFIT_MAPPING_REGISTRY_HEALTH_RESPONSE_UNAVAILABLE",
        }

    lines = [
        f"Registry health: {source.get('health_status')}",
        f"Schema version: {source.get('schema_version')}",
        f"Load allowed: {'да' if source.get('load_allowed') else 'нет'}",
        f"Writes allowed: {'да' if source.get('writable') else 'нет'}",
        "Fail-closed: да",
    ]
    issues = list(source.get("issues") or [])
    if issues:
        lines.append("Проблемы: " + ", ".join(str(issue) for issue in issues))

    for scope, state in sorted((source.get("scopes") or {}).items()):
        lines.append(
            f"{scope}: active={state.get('active_revision_id') or 'нет'}, "
            f"latest={state.get('latest_revision_id') or 'нет'}, "
            f"loadable={'да' if state.get('active_mapping_loadable') else 'нет'}, "
            f"stale={'да' if state.get('active_revision_stale') else 'нет'}"
        )

    if source.get("load_allowed") is not True:
        lines.append("Повреждённые или несовместимые mappings не загружаются в period-profit runtime.")

    return {
        "error": False,
        "status": "PERIOD_PROFIT_MAPPING_REGISTRY_HEALTH_RESPONSE_READY",
        "text": "\n".join(lines),
        "read_only": True,
        "fail_closed": True,
        "ozon_mutation": False,
        "profit_adjustment_allowed": False,
        "executed": False,
    }
