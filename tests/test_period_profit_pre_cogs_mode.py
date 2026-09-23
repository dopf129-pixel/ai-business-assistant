from services.assistant_button_handler_service import AssistantButtonHandlerService
from services.assistant_keyboard_service import AssistantKeyboardService
from services.assistant_period_profit_runtime_service import (
    AssistantPeriodProfitRuntimeService,
)
from services.period_profit_cost_exclusion_context import cost_excluded


class _Summary:
    def __init__(self):
        self.calls = []

    def calculate(self, date_from, date_to, products):
        self.calls.append((date_from, date_to, products, cost_excluded()))
        assert cost_excluded() is True
        return {
            "error": False,
            "status": "PERIOD_PROFIT_SUMMARY_READY",
            "date_from": date_from,
            "date_to": date_to,
            "products": [],
            "revenue": 1000.0,
            "net_accrual": 700.0,
            "product_cost": 0.0,
            "tax": 60.0,
            "profit": 640.0,
            "margin_percent": 64.0,
        }


class _Query:
    def __init__(self):
        self.summary_service = _Summary()
        self.product_provider = lambda: [{"sku": "101", "product_id": "1"}]


def _handler(runtime):
    return AssistantButtonHandlerService(
        object(),
        keyboard_service=AssistantKeyboardService(),
        period_profit_runtime_service=runtime,
    )


def test_period_profit_menu_exposes_separate_pre_cogs_mode():
    runtime = AssistantPeriodProfitRuntimeService(_Query())

    menu = _handler(runtime).handle("period_profit", "seller-1")

    assert {
        "text": "🧮 Без учёта себестоимости",
        "callback": "period_profit_pre_cogs",
    } in menu["keyboard"]["buttons"]


def test_pre_cogs_mode_calculates_even_without_cost_and_is_explicitly_incomplete():
    query = _Query()
    runtime = AssistantPeriodProfitRuntimeService(query)

    result = runtime.handle_callback(
        "period_profit_pre_cogs:7D", today="2026-09-23"
    )

    assert result["error"] is False
    assert result["cost_excluded"] is True
    assert result["profit_complete"] is False
    assert "Результат до себестоимости: 640.00 ₽" in result["text"]
    assert "Это не итоговая прибыль магазина" in result["text"]
    assert query.summary_service.calls == [(
        "2026-09-17",
        "2026-09-23",
        [{"sku": "101", "product_id": "1"}],
        True,
    )]
    assert cost_excluded() is False


def test_pre_cogs_custom_period_pending_state_is_per_user():
    query = _Query()
    runtime = AssistantPeriodProfitRuntimeService(query)
    handler = _handler(runtime)

    periods = handler.handle("period_profit_pre_cogs", "seller-1")
    prompt = handler.handle("period_profit_pre_cogs:custom", "seller-1")
    unrelated = runtime.handle_text(
        "01.01.2026-02.02.2026", user_id="seller-2"
    )
    result = runtime.handle_text(
        "01.01.2026-02.02.2026", user_id="seller-1"
    )

    assert periods["keyboard"]["buttons"][-1] == {
        "text": "📅 Указать период",
        "callback": "period_profit_pre_cogs:custom",
    }
    assert prompt["status"] == (
        "PERIOD_PROFIT_PRE_COGS_CUSTOM_PERIOD_INPUT_REQUIRED"
    )
    assert unrelated is None
    assert result["error"] is False
    assert query.summary_service.calls[0][:2] == (
        "2026-01-01", "2026-02-02"
    )
