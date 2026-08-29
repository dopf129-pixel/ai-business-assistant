from copy import deepcopy


def build_period_profit_response(summary, comparison=None):
    source = deepcopy(dict(summary or {}))
    if source.get("status") != "PERIOD_PROFIT_SUMMARY_READY" or source.get("error") is not False:
        return {"error": True, "code": "PERIOD_PROFIT_RESPONSE_SUMMARY_REQUIRED", "status": "PERIOD_PROFIT_RESPONSE_UNAVAILABLE"}

    lines = [
        f"💰 Прибыль за период {source.get('date_from')} — {source.get('date_to')}",
        "",
        f"Выручка: {_money(source.get('revenue'))}",
        f"Начисления Ozon после комиссий/услуг: {_money(source.get('net_accrual'))}",
        f"Себестоимость: {_money(source.get('product_cost'))}",
        f"Налог: {_money(source.get('tax'))}",
        f"Прибыль: {_money(source.get('profit'))}",
        f"Маржа: {_percent(source.get('margin_percent'))}",
    ]

    if isinstance(comparison, dict) and comparison.get("status") == "PERIOD_PROFIT_COMPARISON_READY":
        direction = {"UP": "выросла", "DOWN": "снизилась", "UNCHANGED": "не изменилась"}.get(comparison.get("profit_direction"), "изменилась")
        delta = _money(abs(float(comparison.get("profit_change") or 0)))
        percent = comparison.get("profit_change_percent")
        suffix = f" ({abs(percent):.2f}%)" if percent is not None else ""
        lines.extend(["", f"К предыдущему сопоставимому периоду прибыль {direction} на {delta}{suffix}."])

    missing = []
    if source.get("returns_included") is not True:
        missing.append("возвраты")
    if source.get("advertising_included") is not True:
        missing.append("реклама")
    if source.get("storage_included") is not True:
        missing.append("хранение")
    if missing:
        lines.extend(["", "⚠️ В текущую версию прибыли пока не включены: " + ", ".join(missing) + "."])
        lines.append("Это операционная оценка в указанном составе, а не бухгалтерская чистая прибыль.")

    return {"error": False, "status": "PERIOD_PROFIT_RESPONSE_READY", "text": "\n".join(lines), "profit_scope": source.get("profit_scope")}


def _money(value):
    return f"{float(value or 0):,.2f} ₽".replace(",", " ")


def _percent(value):
    return f"{float(value or 0):.2f}%"
