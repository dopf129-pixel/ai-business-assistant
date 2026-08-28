from services.assistant_keyboard_service import AssistantKeyboardService
from services.assistant_button_handler_service import AssistantButtonHandlerService


class StubAssistant:
    def ask(self, message, user_id=None):
        return {"error": False, "message": message}


class StubProductService:
    def __init__(self, products=None):
        self.products = products

    def load_products(self):
        return self.products or [
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
    def __init__(self, result=None, products=None):
        self.product_service = StubProductService(products=products)
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
            "sales_velocity": 4.0,
            "sales_trend": "GROWING",
            "current_stock": 8,
            "days_of_stock": 2.0,
            "stock_priority": "CRITICAL",
            "decision_profit_per_unit": 35.10,
            "decision_margin_percent": 36.56,
        }
        self.calls = []
        self.decision_history_service = None

    def query(self, sku):
        self.calls.append(sku)
        result = dict(self.result)
        result.setdefault("sku", sku)
        return result

    def query_all(self):
        decisions = []
        for product in self.product_service.load_products():
            sku = product.get("offer_id") or product.get("sku")
            decision = dict(self.result)
            decision["sku"] = sku
            decisions.append(decision)
        counts = {}
        for decision in decisions:
            decision_type = decision["decision_type"]
            counts[decision_type] = counts.get(decision_type, 0) + 1
        return {
            "error": False,
            "code": None,
            "total": len(decisions),
            "counts": counts,
            "decisions": decisions,
        }


def _handler(result=None, products=None, history_service=None):
    keyboard = AssistantKeyboardService()
    query = StubDecisionQuery(result=result, products=products)
    query.decision_history_service = history_service
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


def test_product_decisions_menu_shows_ranked_decision_overview():
    handler, _, _ = _handler()

    result = handler.handle("product_decisions")

    assert result["error"] is False
    assert "🎯 Решения по товарам" in result["message"]
    assert "Всего товаров: 2" in result["message"]
    assert "Срочно пополнить: 2" in result["message"]
    assert "Товары отсортированы по срочности." in result["message"]
    callbacks = [
        item["callback"]
        for item in result["keyboard"]["buttons"]
    ]
    assert callbacks == [
        "product_decision:hook-2",
        "product_decision:hook-3",
    ]
    labels = [
        item["text"]
        for item in result["keyboard"]["buttons"]
    ]
    assert labels == [
        "🟠 hook-2 — Пополнить срочно",
        "🟠 hook-3 — Пополнить срочно",
    ]


def test_product_decisions_menu_paginates_large_assortment():
    products = [
        {
            "product_id": str(index),
            "offer_id": f"item-{index}",
            "sku": str(1000 + index),
        }
        for index in range(1, 11)
    ]
    handler, _, _ = _handler(products=products)

    first = handler.handle("product_decisions")
    first_callbacks = [
        item["callback"]
        for item in first["keyboard"]["buttons"]
    ]

    assert "Страница: 1 из 2" in first["message"]
    assert first_callbacks[:8] == [
        f"product_decision:item-{index}"
        for index in range(1, 9)
    ]
    assert first_callbacks[-1] == "product_decisions_page:2"

    second = handler.handle("product_decisions_page:2")
    second_callbacks = [
        item["callback"]
        for item in second["keyboard"]["buttons"]
    ]

    assert "Страница: 2 из 2" in second["message"]
    assert second_callbacks == [
        "product_decision:item-9",
        "product_decision:item-10",
        "product_decisions_page:1",
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
    assert "Артикул:\nhook-2" in result["message"]
    assert "Тип:" not in result["message"]
    assert "Приоритет:\nВысокий" in result["message"]
    assert "Скорость продаж: 4 шт./день" in result["message"]
    assert "Остаток: 8 шт." in result["message"]
    assert "Запас: 2 дн." in result["message"]
    assert "Прибыль с 1 шт.: 35.10 ₽" in result["message"]
    assert "Маржа: 36.56%" in result["message"]
    assert "Уверенность:\nВысокая" in result["message"]
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

    assert "Прибыль с 1 шт.: 33.98 ₽" in message
    assert (
        "Основа расчёта:\n"
        "С исторической оценкой возвратов"
    ) in message
    assert "Возвраты и невыкупы: 1.12 ₽" in message
    assert "Финансовое покрытие: 91.11%" in message
    assert "Уверенность:\nСредняя" in message


def test_product_decision_card_shows_previous_decision_after_change():
    handler, _, _ = _handler(
        {
            "error": False,
            "code": None,
            "product_id": "101",
            "sku": "hook-2",
            "decision_type": "INVESTIGATE_LOW_PROFIT",
            "priority": "HIGH",
            "reasons": ["NEGATIVE_UNIT_PROFIT"],
            "confidence": "HIGH",
            "missing_data": [],
            "decision_changed": True,
            "previous_decision_type": "REPLENISH_HIGH_PRIORITY",
        }
    )

    message = handler.handle("product_decision:hook-2")["message"]

    assert "Изменение решения:" in message
    assert (
        "Высокий приоритет пополнения → "
        "Проверить низкую прибыльность"
    ) in message
    assert "REPLENISH_HIGH_PRIORITY" not in message


class StubDecisionHistory:
    def __init__(self, result=None):
        self.result = result or {
            "error": False,
            "code": None,
            "sku": "hook-2",
            "feedback": "USEFUL",
            "saved": True,
        }
        self.calls = []

    def record_feedback(self, sku, feedback):
        self.calls.append((sku, feedback))
        result = dict(self.result)
        result["sku"] = sku
        result["feedback"] = str(feedback).upper()
        return result


def test_product_decision_card_offers_manual_feedback_buttons():
    result = {
        "error": False,
        "code": None,
        "product_id": "101",
        "sku": "hook-2",
        "decision_type": "HOLD_STOCK",
        "priority": "LOW",
        "reasons": ["POSITIVE_UNIT_PROFIT"],
        "confidence": "HIGH",
        "missing_data": [],
        "decision_history_available": True,
    }
    handler, _, _ = _handler(
        result=result,
        history_service=StubDecisionHistory(),
    )

    response = handler.handle("product_decision:hook-2")
    callbacks = [
        item["callback"]
        for item in response["keyboard"]["buttons"]
    ]

    assert callbacks == [
        "product_decision_feedback:useful:hook-2",
        "product_decision_feedback:not_relevant:hook-2",
    ]


def test_product_decision_feedback_callback_records_signal():
    history = StubDecisionHistory()
    handler, _, _ = _handler(history_service=history)

    response = handler.handle(
        "product_decision_feedback:useful:hook-2"
    )

    assert history.calls == [("hook-2", "useful")]
    assert response["error"] is False
    assert response["message"] == "Оценка сохранена: решение полезно."


def test_product_decision_feedback_requires_recorded_history():
    history = StubDecisionHistory({
        "error": True,
        "code": "DECISION_HISTORY_NOT_FOUND",
        "saved": False,
    })
    handler, _, _ = _handler(history_service=history)

    response = handler.handle(
        "product_decision_feedback:not_relevant:missing"
    )

    assert response["error"] is True
    assert response["message"] == (
        "Сначала откройте актуальное решение по товару"
    )
