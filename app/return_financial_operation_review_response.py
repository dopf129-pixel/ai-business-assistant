def build_return_financial_operation_review_response(report):
    source = dict(report or {})
    if source.get("status") != "RETURN_FINANCIAL_OPERATION_REVIEW_REPORT_READY" or source.get("error") is not False:
        return {
            "error": True,
            "code": "RETURN_FINANCIAL_OPERATION_REVIEW_REPORT_REQUIRED",
            "status": "RETURN_FINANCIAL_OPERATION_REVIEW_RESPONSE_UNAVAILABLE",
        }

    operations = [row for row in source.get("operations", []) if isinstance(row, dict)]
    lines = [
        "Финансовые типы операций Ozon для ручной проверки возвратов:",
        "",
    ]
    if not operations:
        lines.append("Каталог операций пуст.")
    else:
        for row in operations:
            type_id = row.get("type_id")
            name = row.get("name") or "без названия"
            description = row.get("description")
            line = f"• ID {type_id}: {name}"
            if description:
                line += f" — {description}"
            lines.append(line)

    lines.extend([
        "",
        "Ни одна операция не помечена как возвратная автоматически.",
        "Для активации mapping нужен ручной выбор и отдельная авторизация конкретных type_id.",
        "Прибыль этим отчётом не изменяется.",
    ])
    return {
        "error": False,
        "status": "RETURN_FINANCIAL_OPERATION_REVIEW_RESPONSE_READY",
        "text": "\n".join(lines),
        "operation_count": len(operations),
        "mapping_activation_allowed": False,
        "returns_profit_adjustment_allowed": False,
        "read_only": True,
        "executed": False,
    }
