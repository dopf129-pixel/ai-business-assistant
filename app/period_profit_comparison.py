from copy import deepcopy


def build_period_profit_comparison(current, previous):
    current = deepcopy(dict(current or {}))
    previous = deepcopy(dict(previous or {}))
    for source in (current, previous):
        if source.get("status") != "PERIOD_PROFIT_SUMMARY_READY" or source.get("error") is not False:
            return {"error": True, "code": "PERIOD_PROFIT_COMPARISON_SUMMARY_REQUIRED", "status": "PERIOD_PROFIT_COMPARISON_UNAVAILABLE"}
    if current.get("profit_scope") != previous.get("profit_scope"):
        return {"error": True, "code": "PERIOD_PROFIT_COMPARISON_SCOPE_MISMATCH", "status": "PERIOD_PROFIT_COMPARISON_UNAVAILABLE"}
    for flag in ("returns_included", "advertising_included", "storage_included"):
        if bool(current.get(flag)) != bool(previous.get(flag)):
            return {"error": True, "code": "PERIOD_PROFIT_COMPARISON_SCOPE_MISMATCH", "status": "PERIOD_PROFIT_COMPARISON_UNAVAILABLE"}

    current_profit = float(current.get("profit") or 0)
    previous_profit = float(previous.get("profit") or 0)
    change = current_profit - previous_profit
    percent = None if previous_profit == 0 else round(change / abs(previous_profit) * 100, 2)
    direction = "UP" if change > 0 else "DOWN" if change < 0 else "UNCHANGED"
    return {
        "error": False,
        "status": "PERIOD_PROFIT_COMPARISON_READY",
        "current_period": {"date_from": current.get("date_from"), "date_to": current.get("date_to"), "profit": current_profit},
        "previous_period": {"date_from": previous.get("date_from"), "date_to": previous.get("date_to"), "profit": previous_profit},
        "profit_change": round(change, 2),
        "profit_change_percent": percent,
        "profit_direction": direction,
        "profit_scope": current.get("profit_scope"),
        "returns_included": bool(current.get("returns_included")),
        "advertising_included": bool(current.get("advertising_included")),
        "storage_included": bool(current.get("storage_included")),
    }
