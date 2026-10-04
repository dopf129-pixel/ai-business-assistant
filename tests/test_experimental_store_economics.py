from services.assistant_button_handler_service import AssistantButtonHandlerService
from services.assistant_keyboard_service import AssistantKeyboardService
from services.experimental_store_economics_runtime_service import (
    ExperimentalStoreEconomicsRuntimeService,
)
from services.period_profit_cost_exclusion_context import cost_excluded
from telegram_app_layer.assistant_telegram_adapter import AssistantTelegramAdapter
from telegram_app_layer.telegram_bot_service import TelegramBotService
from telegram_app_layer.telegram_command_service import TelegramCommandService
from telegram_app_layer.telegram_response_formatter import TelegramResponseFormatter


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
            "revenue": 100000.0,
            "revenue_tax_base": 92000.0,
            "discount_points": 8000.0,
            "profit": 13000.0,
            "acquiring": -1500.0,
            "commission": -22000.0,
            "logistics": -18000.0,
            "products": [{"sku": "9001"}],
            "fee_breakdown": {
                "Доставка до покупателя — последняя миля": -8000.0,
                "Услуги кросс-докинга": -1200.0,
                "Платное хранение товара": -350.0,
            },
        }


class _Query:
    def __init__(self):
        self.summary_service = _Summary()
        self.product_provider = lambda: [{"sku": "1001"}, {"sku": "2002"}]


class _Advertising:
    def __init__(self, result=None):
        self.result = result or {
            "error": False,
            "configured": True,
            "complete": True,
            "expense": 345.67,
            "campaign_count": 2,
        }
        self.calls = []

    def load(self, date_from, date_to, accepted_skus):
        self.calls.append((date_from, date_to, set(accepted_skus)))
        return self.result


class _Analytics:
    def __init__(self, result=None):
        self.result = result or {
            "error": False,
            "result": {
                "data": [
                    {"metrics": [12, 2]},
                    {"metrics": [5, 1]},
                ]
            },
        }
        self.calls = []

    def get_analytics_data(self, date_from, date_to, **kwargs):
        self.calls.append((date_from, date_to, kwargs))
        return self.result


class _Profile:
    def create_user(self, user_id):
        return {"error": False, "user": {"user_id": user_id}}


class _Assistant:
    def __init__(self):
        self.calls = []

    def ask(self, text, user_id=None):
        self.calls.append((text, user_id))
        return {"error": False, "message": "unused assistant"}


def _service(advertising=None, analytics=None):
    query = _Query()
    runtime = ExperimentalStoreEconomicsRuntimeService(
        query,
        advertising_service=advertising or _Advertising(),
        analytics_client=analytics or _Analytics(),
    )
    return query, runtime


def _bot(runtime):
    keyboard = AssistantKeyboardService()
    assistant = _Assistant()
    handler = AssistantButtonHandlerService(
        assistant,
        keyboard_service=keyboard,
        experimental_store_economics_runtime_service=runtime,
    )
    adapter = AssistantTelegramAdapter(
        assistant,
        keyboard,
        handler,
        _Profile(),
    )
    bot = TelegramBotService(
        adapter,
        TelegramCommandService(adapter),
    )
    return bot, assistant


def test_store_economics_uses_existing_pre_cogs_profit_and_adds_only_confirmed_values():
    query = _Query()
    ads = _Advertising()
    analytics = _Analytics()
    runtime = ExperimentalStoreEconomicsRuntimeService(
        query,
        advertising_service=ads,
        analytics_client=analytics,
    )

    result = runtime.handle_callback(
        "experimental_store_economics:7D",
        today="2026-10-05",
    )

    assert result["error"] is False
    assert result["cost_excluded"] is True
    assert result["profit_complete"] is False
    assert result["metrics"]["profit"] == 13000.0
    assert result["metrics"]["advertising"]["cpc"] == 345.67
    assert result["metrics"]["analytics"]["ordered_units"] == 17
    assert result["metrics"]["analytics"]["cancellations"] == 3
    assert result["metrics"]["fee_subcategories"] == {
        "last_mile": -8000.0,
        "cross_docking": -1200.0,
        "paid_storage": -350.0,
    }
    assert "1. Выручка общая (100%): 100 000.00 ₽" in result["text"]
    assert "2. Выручка ФНС (выручка − баллы): 92 000.00 ₽" in result["text"]
    assert "3. Баллы за скидки: 8 000.00 ₽" in result["text"]
    assert "4. Прибыль без себестоимости: 13 000.00 ₽" in result["text"]
    assert "5. Расходы на рекламу:" in result["text"]
    assert "CPC по сопоставленным SKU (не общий бюджет): 345.67 ₽" in result["text"]
    assert "CPO: не включён" in result["text"]
    assert "CPM и другие типы: не включены" in result["text"]
    assert "6. Эквайринг: -1 500.00 ₽" in result["text"]
    assert "7. Вознаграждение Ozon: -22 000.00 ₽" in result["text"]
    assert "8. Логистика всего: -18 000.00 ₽" in result["text"]
    assert "9. Последняя миля: -8 000.00 ₽" in result["text"]
    assert "10. Кросс-докинг: -1 200.00 ₽" in result["text"]
    assert "11. Платное хранение: -350.00 ₽" in result["text"]
    assert "12. Заказанные единицы: 17" in result["text"]
    assert "13. Отменённые единицы: 3" in result["text"]
    assert query.summary_service.calls[0][3] is True
    assert cost_excluded() is False
    assert ads.calls[0][2] == {"1001", "2002", "9001"}
    assert analytics.calls[0][2]["metrics"] == ["ordered_units", "cancellations"]


def test_unconfirmed_expenses_and_unavailable_analytics_are_never_shown_as_zero():
    query = _Query()
    query.summary_service.calculate = lambda date_from, date_to, products: {
        "error": False,
        "status": "PERIOD_PROFIT_SUMMARY_READY",
        "date_from": date_from,
        "date_to": date_to,
        "revenue": 100.0,
        "revenue_tax_base": 90.0,
        "discount_points": 10.0,
        "profit": 12.0,
        "acquiring": 0.0,
        "commission": 0.0,
        "logistics": 0.0,
        "products": [],
        "fee_breakdown": {},
    }
    ads = _Advertising({"error": False, "configured": False, "complete": False})
    analytics = _Analytics({"error": True, "code": "OZON_ANALYTICS_DEPENDENCY_UNAVAILABLE"})
    runtime = ExperimentalStoreEconomicsRuntimeService(
        query,
        advertising_service=ads,
        analytics_client=analytics,
    )

    result = runtime.calculate("2026-10-01", "2026-10-02")

    assert result["error"] is False
    assert result["metrics"]["advertising"]["cpc"] is None
    assert result["metrics"]["analytics"]["ordered_units"] is None
    assert result["metrics"]["analytics"]["cancellations"] is None
    assert "CPC по сопоставленным SKU (не общий бюджет): Performance не подключён" in result["text"]
    assert "Заказанные единицы: аналитика Ozon недоступна" in result["text"]
    assert "Отменённые единицы: аналитика Ozon недоступна" in result["text"]
    assert "Последняя миля: не выделено отдельной строкой" in result["text"]
    assert "Кросс-докинг: не выделено отдельной строкой" in result["text"]
    assert "Платное хранение: не выделено отдельной строкой" in result["text"]


def test_generic_storage_label_is_not_reported_as_paid_storage():
    result = ExperimentalStoreEconomicsRuntimeService._fee_subcategories(
        {"fee_breakdown": {"Хранение товара": -350.0, "Storage": -125.0}}
    )

    assert result["paid_storage"] is None


def test_custom_period_is_user_scoped_and_traverses_telegram_to_result():
    query, runtime = _service()
    bot, assistant = _bot(runtime)

    experiments = bot.on_callback("seller-a", "experimental_calculations")
    period_menu = bot.on_callback(
        "seller-a",
        experiments["keyboard"]["buttons"][0]["callback"],
    )
    prompt = bot.on_callback(
        "seller-a",
        "experimental_store_economics:custom",
    )
    other_user_text = bot.on_message("seller-b", "01.10.2026 - 02.10.2026")
    result = bot.on_message("seller-a", "01.10.2026 - 02.10.2026")

    assert period_menu["error"] is False
    assert prompt["status"] == "EXPERIMENTAL_STORE_ECONOMICS_CUSTOM_PERIOD_INPUT_REQUIRED"
    assert other_user_text["message"] == "unused assistant"
    assert result["error"] is False
    assert result["status"] == "EXPERIMENTAL_STORE_ECONOMICS_READY"
    assert result["date_from"] == "2026-10-01"
    assert result["date_to"] == "2026-10-02"
    assert "Экономика магазина за период 2026-10-01 — 2026-10-02" in result["text"]
    assert TelegramResponseFormatter().format(result) == result["text"]
    assert result["read_only"] is True
    assert result["executed"] is False
    assert result["keyboard"]["buttons"][0]["callback"] == "experimental_store_economics"
    assert assistant.calls == [("01.10.2026 - 02.10.2026", "seller-b")]
    assert query.summary_service.calls[0][:2] == ("2026-10-01", "2026-10-02")


def test_invalid_analytics_rows_fail_closed_without_exposing_partial_totals():
    query = _Query()
    analytics = _Analytics({
        "error": False,
        "result": {"data": [{"metrics": [10, "not-a-number"]}]},
    })
    runtime = ExperimentalStoreEconomicsRuntimeService(
        query,
        advertising_service=_Advertising(),
        analytics_client=analytics,
    )

    result = runtime.calculate("2026-10-01", "2026-10-02")

    assert result["metrics"]["analytics"] == {
        "status": "INVALID",
        "ordered_units": None,
        "cancellations": None,
    }
    assert "Заказанные единицы: данные некорректны" in result["text"]
    assert "Отменённые единицы: данные некорректны" in result["text"]
