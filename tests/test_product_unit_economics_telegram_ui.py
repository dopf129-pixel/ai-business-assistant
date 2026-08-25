from services.assistant_button_handler_service import (
    AssistantButtonHandlerService
)
from services.assistant_keyboard_service import (
    AssistantKeyboardService
)


class FakeAssistant:

    def ask(self, text, user_id=None):
        return {
            "error": False,
            "message": text
        }


class FakeProductService:

    def __init__(self, products=None):
        self.products = products or []

    def load_products(self):
        return list(self.products)


class FakeUnitEconomicsQuery:

    def __init__(self, products=None):
        self.product_service = FakeProductService(
            products=products
        )
        self.queries = []

    def query(self, sku):
        self.queries.append(sku)

        if sku == "missing":
            return {
                "error": True,
                "code": "SKU_NOT_FOUND",
                "sku": sku,
                "message": "SKU не найден"
            }

        return {
            "error": False,
            "available": True,
            "sku": sku,
            "unit_price": 1490.0,
            "cost": 520.0,
            "marketplace_fees": 370.0,
            "tax": 89.0,
            "net_profit_per_unit": 510.0,
            "margin_percent": 34.0,
            "missing_fields": [
                "advertising",
                "storage",
                "returns"
            ]
        }

    def format_response(self, result):
        if result.get("error"):
            return result["message"]

        return (
            f"Unit Economics — {result['sku']}\n\n"
            "Цена продажи:\n1490.00 ₽\n\n"
            "Себестоимость:\n520.00 ₽\n\n"
            "Расходы маркетплейса:\n370.00 ₽\n\n"
            "Налог:\n89.00 ₽\n\n"
            "Реклама:\n—\n\n"
            "Хранение:\n—\n\n"
            "Возвраты:\n—\n\n"
            "----------------\n\n"
            "Расчётная прибыль с 1 шт:\n510.00 ₽\n\n"
            "Маржа:\n34.00%"
        )


def _build_handler(products=None):
    query = FakeUnitEconomicsQuery(
        products=products
    )
    keyboard = AssistantKeyboardService()
    handler = AssistantButtonHandlerService(
        assistant=FakeAssistant(),
        keyboard_service=keyboard,
        unit_economics_query=query
    )
    return handler, query


def test_main_menu_contains_unit_economics_and_existing_buttons():
    keyboard = AssistantKeyboardService().build_main_keyboard()
    callbacks = [
        item["callback"]
        for item in keyboard["buttons"]
    ]

    assert callbacks == [
        "analyze",
        "plan",
        "history",
        "memory",
        "unit_economics",
        "product_decisions",
        "returns_finance_impact"
    ]


def test_open_unit_economics_menu_lists_available_skus():
    handler, _ = _build_handler(
        products=[
            {"product_id": 1, "sku": "hook-2"},
            (2, "offer-3", "hook-3")
        ]
    )

    result = handler.handle("unit_economics")

    assert result["error"] is False
    assert result["message"] == "Выберите товар:"
    assert result["keyboard"]["buttons"] == [
        {
            "text": "hook-2",
            "callback": "unit_economics:hook-2"
        },
        {
            "text": "hook-3",
            "callback": "unit_economics:hook-3"
        }
    ]


def test_select_sku_calls_existing_query_and_displays_result():
    handler, query = _build_handler(
        products=[{"product_id": 1, "sku": "hook-2"}]
    )

    result = handler.handle(
        "unit_economics:hook-2"
    )

    assert query.queries == ["hook-2"]
    assert result["error"] is False
    assert result["unit_economics"]["sku"] == "hook-2"
    assert "Unit Economics — hook-2" in result["message"]
    assert "Расчётная прибыль с 1 шт:" in result["message"]
    assert "Чистая прибыль" not in result["message"]


def test_unknown_expenses_are_displayed_as_dashes():
    handler, _ = _build_handler()

    result = handler.handle(
        "unit_economics:hook-2"
    )

    assert "Реклама:\n—" in result["message"]
    assert "Хранение:\n—" in result["message"]
    assert "Возвраты:\n—" in result["message"]


def test_missing_sku_uses_existing_query_error_message():
    handler, query = _build_handler()

    result = handler.handle(
        "unit_economics:missing"
    )

    assert query.queries == ["missing"]
    assert result["error"] is True
    assert result["message"] == "SKU не найден"


def test_empty_product_list_has_safe_menu_response():
    handler, _ = _build_handler(products=[])

    result = handler.handle("unit_economics")

    assert result == {
        "error": False,
        "message": "Товары не найдены"
    }


def test_existing_memory_handler_is_preserved():
    class FakeMemory:
        def get_memory(self, user_id):
            return {
                "error": False,
                "memory": {"user_id": user_id}
            }

    handler = AssistantButtonHandlerService(
        assistant=FakeAssistant(),
        memory_service=FakeMemory()
    )

    result = handler.handle("memory", user_id=10)

    assert result == {
        "error": False,
        "memory": {"user_id": 10}
    }
