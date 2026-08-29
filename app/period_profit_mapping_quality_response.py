def build_period_profit_mapping_quality_response(report):
    source = dict(report or {})
    if source.get("status") != "PERIOD_PROFIT_MAPPING_QUALITY_REPORT_READY":
        return {
            "error": True,
            "code": "PERIOD_PROFIT_MAPPING_QUALITY_REPORT_REQUIRED",
            "status": "PERIOD_PROFIT_MAPPING_QUALITY_RESPONSE_UNAVAILABLE",
        }

    score = source.get("overall_quality_score")
    lines = [
        "Качество period-profit mappings:",
        f"• Registry health: {source.get('registry_health_status')}",
        f"• Ozon operation catalog: {'доступен' if source.get('catalog_available') else 'недоступен'}",
        f"• Общий quality score: {score if score is not None else 'нет данных'}",
    ]

    for scope, row in sorted((source.get("scopes") or {}).items()):
        item = dict(row or {})
        if item.get("mapping_available") is not True:
            lines.append(f"• {scope}: mapping не настроен")
            continue
        details = [
            f"quality={item.get('quality_score')}",
            f"freshness={item.get('freshness_status')}",
        ]
        if item.get("missing_type_ids"):
            details.append("missing type_id=" + ",".join(str(v) for v in item.get("missing_type_ids") or []))
        if item.get("renamed_operations"):
            details.append(f"renamed={len(item.get('renamed_operations') or [])}")
        if item.get("review_required") is True:
            details.append("нужна ручная проверка")
        lines.append(f"• {scope}: " + "; ".join(details))

    if source.get("review_required") is True:
        lines.append("⚠️ Есть mappings, требующие ручной перепроверки по текущему Ozon catalog.")
    else:
        lines.append("Активные mappings не требуют дополнительной проверки по текущим правилам качества.")
    lines.append("Диагностика read-only: remap, activation, Ozon и формула прибыли не изменяются.")

    return {
        "error": False,
        "status": "PERIOD_PROFIT_MAPPING_QUALITY_RESPONSE_READY",
        "text": "\n".join(lines),
        "review_required": source.get("review_required") is True,
        "automatic_remap_allowed": False,
        "automatic_activation_allowed": False,
        "ozon_mutation": False,
        "profit_adjustment_allowed": False,
        "executed": False,
    }
