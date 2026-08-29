PERIOD_BUTTONS = (
    ("Сегодня", "TODAY"),
    ("7 дней", "7D"),
    ("28 дней", "28D"),
    ("56 дней", "56D"),
    ("90 дней", "90D"),
)


def build_period_profit_telegram_menu():
    return {
        "text": "За какой период показать прибыль?",
        "buttons": [
            {"text": label, "callback_data": f"period_profit:{code}"}
            for label, code in PERIOD_BUTTONS
        ],
        "custom_period_supported": True,
        "read_only": True,
        "executed": False,
    }


def parse_period_profit_callback(callback_data):
    value = str(callback_data or "").strip()
    prefix = "period_profit:"
    if not value.startswith(prefix):
        return {"error": True, "code": "PERIOD_PROFIT_CALLBACK_INVALID"}
    period_code = value[len(prefix):].upper()
    allowed = {code for _, code in PERIOD_BUTTONS}
    if period_code not in allowed:
        return {"error": True, "code": "PERIOD_PROFIT_CALLBACK_PERIOD_INVALID"}
    return {
        "error": False,
        "status": "PERIOD_PROFIT_CALLBACK_READY",
        "period_code": period_code,
        "compare_previous": True,
        "read_only": True,
        "executed": False,
    }
