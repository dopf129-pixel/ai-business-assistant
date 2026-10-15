from copy import deepcopy
from decimal import Decimal
from math import isfinite
import re


_SCOPE_FLAGS = (
    "returns_included",
    "advertising_included",
    "storage_included",
)
_SAFE_ERROR_CODE = re.compile(r"^[A-Z0-9_]{1,96}$")


def build_period_profit_comparison(current, previous):
    current = _copy_summary(current)
    previous = _copy_summary(previous)
    if current is None or previous is None:
        return _error("PERIOD_PROFIT_COMPARISON_SUMMARY_REQUIRED")

    for source in (current, previous):
        if (
            source.get("status") != "PERIOD_PROFIT_SUMMARY_READY"
            or source.get("error") is not False
        ):
            return _error("PERIOD_PROFIT_COMPARISON_SUMMARY_REQUIRED")
        if not isinstance(source.get("profit_scope"), str) or not source.get(
            "profit_scope"
        ).strip():
            return _error("PERIOD_PROFIT_COMPARISON_SUMMARY_INVALID")
        if any(type(source.get(flag)) is not bool for flag in _SCOPE_FLAGS):
            return _error("PERIOD_PROFIT_COMPARISON_SUMMARY_INVALID")

    if current.get("profit_scope") != previous.get("profit_scope"):
        return _error("PERIOD_PROFIT_COMPARISON_SCOPE_MISMATCH")
    if any(current[flag] != previous[flag] for flag in _SCOPE_FLAGS):
        return _error("PERIOD_PROFIT_COMPARISON_SCOPE_MISMATCH")

    current_profit = _finite_amount(current.get("profit"))
    previous_profit = _finite_amount(previous.get("profit"))
    if current_profit is None or previous_profit is None:
        return _error("PERIOD_PROFIT_COMPARISON_PROFIT_INVALID")

    change = current_profit - previous_profit
    if not isfinite(change):
        return _error("PERIOD_PROFIT_COMPARISON_PROFIT_INVALID")

    percent = None
    if previous_profit != 0:
        percent_value = change / abs(previous_profit) * 100
        if not isfinite(percent_value):
            return _error("PERIOD_PROFIT_COMPARISON_PROFIT_INVALID")
        percent = round(percent_value, 2)

    direction = "UP" if change > 0 else "DOWN" if change < 0 else "UNCHANGED"
    return {
        "error": False,
        "status": "PERIOD_PROFIT_COMPARISON_READY",
        "current_period": {
            "date_from": current.get("date_from"),
            "date_to": current.get("date_to"),
            "profit": current_profit,
        },
        "previous_period": {
            "date_from": previous.get("date_from"),
            "date_to": previous.get("date_to"),
            "profit": previous_profit,
        },
        "profit_change": round(change, 2),
        "profit_change_percent": percent,
        "profit_direction": direction,
        "profit_scope": current.get("profit_scope"),
        "returns_included": current["returns_included"],
        "advertising_included": current["advertising_included"],
        "storage_included": current["storage_included"],
    }


def mark_period_profit_comparison_unavailable(current_result, error_code):
    """Keep a proven current result while safely recording optional comparison failure."""
    result = dict(current_result)
    result["comparison"] = None
    result["previous_summary"] = None
    result["comparison_status"] = "PERIOD_PROFIT_COMPARISON_UNAVAILABLE"
    code = error_code if isinstance(error_code, str) else ""
    result["comparison_error_code"] = (
        code if _SAFE_ERROR_CODE.fullmatch(code) else "PERIOD_PROFIT_COMPARISON_UNAVAILABLE"
    )
    result["comparison_read_only"] = True
    text = result.get("text")
    if isinstance(text, str) and text.strip():
        result["text"] = (
            text.rstrip()
            + "\n\n⚠️ Сравнение с прошлым периодом недоступно; "
            "текущий расчёт сохранён."
        )
    return result


def _copy_summary(source):
    if not isinstance(source, dict):
        return None
    try:
        return deepcopy(source)
    except Exception:
        return None


def _finite_amount(value):
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        return None
    try:
        number = float(value)
    except (OverflowError, TypeError, ValueError):
        return None
    return number if isfinite(number) else None


def _error(code):
    return {
        "error": True,
        "code": code,
        "status": "PERIOD_PROFIT_COMPARISON_UNAVAILABLE",
    }
