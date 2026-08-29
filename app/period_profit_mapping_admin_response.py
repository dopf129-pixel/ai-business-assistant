def build_period_profit_mapping_admin_response(result, history=None):
    source = dict(result or {})
    if source.get("error"):
        return source

    lines = []
    status = source.get("status")
    if status == "PERIOD_PROFIT_MAPPING_ADMIN_PREVIEW_READY":
        lines.extend([
            f"Mapping scope: {source.get('scope')}",
            f"Действие: {source.get('action')}",
            f"Текущая active revision: {source.get('current_active_revision_id') or 'нет'}",
            f"Целевая revision: {source.get('target_revision_id')}",
            f"Mapping ID: {source.get('target_mapping_id')}",
            "Изменение ещё не применено. Нужен отдельный явный APPLY.",
        ])
    elif status in {
        "PERIOD_PROFIT_MAPPING_REVISION_ACTIVATED",
        "PERIOD_PROFIT_MAPPING_ROLLBACK_APPLIED",
    }:
        lines.extend([
            f"Mapping scope: {source.get('scope')}",
            f"Активная revision: {source.get('revision_id')}",
            f"Mapping ID: {source.get('mapping_id')}",
            "Изменена только активная evidence-mapping revision.",
            "Ozon и формула прибыли не изменялись.",
        ])
    elif status == "PERIOD_PROFIT_MAPPING_HISTORY_READY":
        lines.extend([
            f"Mapping scope: {source.get('scope')}",
            f"Active revision: {source.get('active_revision_id') or 'нет'}",
            f"Всего revisions: {len(source.get('revisions') or [])}",
            f"Событий audit: {len(source.get('events') or [])}",
        ])
    else:
        return {
            "error": True,
            "code": "PERIOD_PROFIT_MAPPING_ADMIN_RESPONSE_STATUS_UNSUPPORTED",
            "status": "PERIOD_PROFIT_MAPPING_ADMIN_RESPONSE_UNAVAILABLE",
        }

    if isinstance(history, dict) and history.get("status") == "PERIOD_PROFIT_MAPPING_HISTORY_READY":
        lines.append(f"Audit active revision: {history.get('active_revision_id') or 'нет'}")

    return {
        "error": False,
        "status": "PERIOD_PROFIT_MAPPING_ADMIN_RESPONSE_READY",
        "text": "\n".join(lines),
        "read_only_business_data": True,
        "ozon_mutation": False,
        "profit_adjustment_allowed": False,
        "executed": False,
    }
