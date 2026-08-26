from services.assistant_keyboard_service import AssistantKeyboardService
from services.assistant_button_handler_service import AssistantButtonHandlerService


class StubAssistant:
    def ask(self, message, user_id=None):
        return {"error": False, "message": message}


class StubProductService:
    def load_products(self):
        return [
            {
                "product_id": "101",
                "offer_id": "hook-2",
                "sku": "3921245627",
            },
            {
                "product_id": "102",
                "offer_id": "hook-3",
                "sku": "3921245628",
            },
        ]


class StubDecisionQuery:
    def __init__(self, result=None):
        self.product_service = StubProductService()
        self.result = result or {
            "error": False,
            "code": None,
            "product_id": "101",
            "sku": "hook-2",
            "decision_type": "REPLENISH_HIGH_PRIORITY",
            "priority": "HIGH",
            "reasons": [
                "DAYS_OF_STOCK_CRITICAL",
                "POSITIVE_UNIT_PROFIT",
            ],
            "confidence": "HIGH",
            "missing_data": ["advertising", "storage", "returns"],
        }
        self.calls = []

    def query(self, sku):
        self.calls.append(sku)
        result = dict(self.result)
        result.setdefault("sku", sku)
        return result


def _handler(result=None):
    keyboard = AssistantKeyboardService()
    query = StubDecisionQuery(result=result)
    handler = AssistantButtonHandlerService(
        assistant=StubAssistant(),
        keyboard_service=keyboard,
        product_business_decision_query=query,
    )
    return handler, keyboard, query


def test_main_keyboard_contains_product_decisions_and_preserves_existing_buttons():
    keyboard = AssistantKeyboardService()
    callbacks = [
        item["callback"]
        for item in keyboard.build_main_keyboard()["buttons"]
    ]

    assert "product_decisions" in callbacks
    for callback in (
        "analyze",
        "plan",
        "history",
        "memory",
        "unit_economics",
    ):
        assert callback in callbacks


def test_product_decisions_menu_shows_sku_buttons():
    handler, _, _ = _handler()

    result = handler.handle("product_decisions")

    assert result["error"] is False
    assert result["message"] == "Выберите товар:"
    callbacks = [
        item["callback"]
        for item in result["keyboard"]["buttons"]
    ]
    assert callbacks == [
        "product_decision:hook-2",
        "product_decision:hook-3",
    ]


def test_product_decision_callback_calls_query_and_formats_decision():
    handler, _, query = _handler()

    result = handler.handle("product_decision:hook-2")

    assert query.calls == ["hook-2"]
    assert result["error"] is False
    assert result["decision"]["decision_type"] == "REPLENISH_HIGH_PRIORITY"
    assert "🎯 Решение по товару" in result["message"]
    assert "hook-2" in result["message"]
    assert "Высокий приоритет пополнения" in result["message"]
    assert "DAYS_OF_STOCK_CRITICAL" not in result["message"]
    assert "Остаток критически низкий" in result["message"]
    assert "Реклама" in result["message"]
    assert "Хранение" in result["message"]
    assert "Возвраты" in result["message"]


def test_sku_not_found_returns_user_message():
    handler, _, _ = _handler(
        {
            "error": True,
            "code": "SKU_NOT_FOUND",
            "sku": "missing",
            "decision_type": "INSUFFICIENT_DATA",
            "priority": "NONE",
            "reasons": [],
            "confidence": "LOW",
            "missing_data": ["sku"],
        }
    )

    result = handler.handle("product_decision:missing")

    assert result["message"] == "Товар не найден"


def test_insufficient_data_returns_user_message():
    handler, _, _ = _handler(
        {
            "error": False,
            "code": "INSUFFICIENT_DATA",
            "product_id": "101",
            "sku": "hook-2",
            "decision_type": "INSUFFICIENT_DATA",
            "priority": "NONE",
            "reasons": [],
            "confidence": "LOW",
            "missing_data": ["profit_per_unit"],
        }
    )

    result = handler.handle("product_decision:hook-2")

    assert result["message"] == "Недостаточно данных для решения"


def test_product_decision_card_shows_returns_aware_economics():
    handler, _, _ = _handler(
        {
            "error": False,
            "code": None,
            "product_id": "101",
            "sku": "hook-2",
            "decision_type": "REPLENISH_HIGH_PRIORITY",
            "priority": "CRITICAL",
            "reasons": [
                "DAYS_OF_STOCK_CRITICAL",
                "POSITIVE_UNIT_PROFIT",
            ],
            "confidence": "MEDIUM",
            "missing_data": ["returns"],
            "economics_basis": "ESTIMATED_RETURNS",
            "decision_profit_per_unit": 33.98,
            "decision_margin_percent": 35.40,
            "returns_reserve_per_unit": 1.12,
            "returns_coverage_percent": 91.11,
        }
    )

    result = handler.handle("product_decision:hook-2")
    message = result["message"]

    assert "Прибыль в решении:\n33.98 ₽" in message
    assert (
        "Основа расчёта:\n"
        "С исторической оценкой возвратов"
    ) in message
    assert "Возвраты и невыкупы:\n1.12 ₽" in message
    assert "Финансовое покрытие:\n91.11%" in message
    assert "Уверенность:\nMEDIUM" in message
