import re


class AssistantPeriodProfitRuntimeService:
    """Narrow read-only route for explicit period-profit requests."""

    PERIOD_CODES = {"TODAY", "7D", "28D", "56D", "90D"}

    def __init__(self, query_service):
        self.query_service = query_service

    def handle_text(self, text, today=None):
        value = " ".join(str(text or "").strip().lower().split())
        if not self._is_profit_request(value):
            return None

        dates = re.findall(r"\b\d{4}-\d{2}-\d{2}\b", value)
        if len(dates) == 2:
            return self.query_service.query(
                date_from=dates[0],
                date_to=dates[1],
                compare_previous=True,
                today=today,
            )

        period = self._resolve_period(value)
        if period is None:
            return {
                "error": True,
                "code": "PERIOD_PROFIT_PERIOD_REQUIRED",
                "status": "PERIOD_PROFIT_QUERY_UNAVAILABLE",
                "message": "Укажите период: сегодня, 7, 28, 56, 90 дней или две даты YYYY-MM-DD.",
                "read_only": True,
                "executed": False,
            }

        return self.query_service.query(
            period_code=period,
            compare_previous=True,
            today=today,
        )

    def handle_callback(self, callback_data, today=None):
        value = str(callback_data or "").strip().upper()
        prefix = "PERIOD_PROFIT:"
        if not value.startswith(prefix):
            return None
        period = value[len(prefix):]
        if period not in self.PERIOD_CODES:
            return {
                "error": True,
                "code": "PERIOD_PROFIT_CALLBACK_INVALID",
                "status": "PERIOD_PROFIT_QUERY_UNAVAILABLE",
                "read_only": True,
                "executed": False,
            }
        return self.query_service.query(
            period_code=period,
            compare_previous=True,
            today=today,
        )

    @staticmethod
    def _is_profit_request(value):
        return any(token in value for token in ("прибыль", "заработал", "profit"))

    @staticmethod
    def _resolve_period(value):
        if "сегодня" in value or "today" in value:
            return "TODAY"
        matches = (
            (r"(?<!\d)(90\s*(?:дней|дня)?|90d)(?!\d)", "90D"),
            (r"(?<!\d)(56\s*(?:дней|дня)?|56d)(?!\d)", "56D"),
            (r"(?<!\d)(28\s*(?:дней|дня)?|28d)(?!\d)", "28D"),
            (r"(?<!\d)(7\s*(?:дней|дня)?|7d)(?!\d)", "7D"),
        )
        for pattern, code in matches:
            if re.search(pattern, value):
                return code
        return None
