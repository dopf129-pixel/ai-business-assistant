from services.assistant_period_profit_runtime_service import AssistantPeriodProfitRuntimeService


class Query:
    def __init__(self): self.calls = []
    def query(self, **kwargs):
        self.calls.append(kwargs)
        return {"error": False, "status": "PERIOD_PROFIT_QUERY_READY", "text": "ok", "read_only": True, "executed": False}


def test_non_profit_text_falls_through():
    query = Query()
    assert AssistantPeriodProfitRuntimeService(query).handle_text("что с остатками?") is None
    assert query.calls == []


def test_profit_7_days_routes_with_comparison():
    query = Query()
    result = AssistantPeriodProfitRuntimeService(query).handle_text("сколько я заработал за 7 дней", today="2026-08-29")
    assert result["status"] == "PERIOD_PROFIT_QUERY_READY"
    assert query.calls == [{"period_code": "7D", "compare_previous": True, "today": "2026-08-29"}]


def test_profit_today_routes_account_level_period_profit():
    query = Query()
    result = AssistantPeriodProfitRuntimeService(query).handle_text(
        "прибыль за сегодня",
        today="2026-09-05",
    )
    assert result["status"] == "PERIOD_PROFIT_QUERY_READY"
    assert result["read_only"] is True
    assert result["executed"] is False
    assert query.calls == [{"period_code": "TODAY", "compare_previous": True, "today": "2026-09-05"}]


def test_margin_today_routes_account_level_period_profit():
    query = Query()
    result = AssistantPeriodProfitRuntimeService(query).handle_text(
        "какая маржа сегодня?",
        today="2026-09-05",
    )
    assert result["status"] == "PERIOD_PROFIT_QUERY_READY"
    assert query.calls == [{"period_code": "TODAY", "compare_previous": True, "today": "2026-09-05"}]


def test_margin_period_routes_account_level_period_profit():
    query = Query()
    AssistantPeriodProfitRuntimeService(query).handle_text(
        "маржинальность за 28 дней",
        today="2026-09-05",
    )
    assert query.calls == [{"period_code": "28D", "compare_previous": True, "today": "2026-09-05"}]


def test_explicit_unit_economics_margin_falls_through():
    query = Query()
    result = AssistantPeriodProfitRuntimeService(query).handle_text(
        "юнит-экономика: какая маржа сегодня?",
        today="2026-09-05",
    )
    assert result is None
    assert query.calls == []


def test_custom_dates_route():
    query = Query()
    AssistantPeriodProfitRuntimeService(query).handle_text("прибыль 2026-08-01 2026-08-20")
    assert query.calls[0]["date_from"] == "2026-08-01"
    assert query.calls[0]["date_to"] == "2026-08-20"


def test_missing_period_returns_safe_prompt():
    result = AssistantPeriodProfitRuntimeService(Query()).handle_text("покажи прибыль")
    assert result["code"] == "PERIOD_PROFIT_PERIOD_REQUIRED"
    assert result["executed"] is False


def test_callback_routes_known_period_only():
    query = Query()
    service = AssistantPeriodProfitRuntimeService(query)
    service.handle_callback("period_profit:28D")
    assert query.calls[0]["period_code"] == "28D"
    assert service.handle_callback("other:28D") is None
    assert service.handle_callback("period_profit:ALL")["code"] == "PERIOD_PROFIT_CALLBACK_INVALID"
