from services.assistant_button_handler_service import (
    AssistantButtonHandlerService
)
import services.assistant_button_handler_service as assistant_button_handler_module
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
        self.breakdown_calls = []

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
            "source": "historical",
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

    def format_expense_breakdown(self, result):
        self.breakdown_calls.append(result["sku"])
        return "🧾 Проверенная локальная расшифровка — " + result["sku"]


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
        "ozon_stores",
        "analyze",
        "plan",
        "history",
        "memory",
        "period_profit",
        "external_expenses",
        "experimental_calculations",
        "seller_cost",
        "unit_economics",
        "unit_price_calculator",
        "product_decisions",
        "seller_attention",
        "product_overview",
        "returns_finance_impact",
        "help",
        "about_bot"
    ]


def test_open_unit_economics_menu_lists_available_skus():
    handler, _ = _build_handler(
        products=[
            {
                "product_id": 1,
                "offer_id": "hook-2",
                "sku": "3921245627"
            },
            (2, "offer-3", "3921245628")
        ]
    )

    result = handler.handle("unit_economics")

    assert result["error"] is False
    assert "Базовая юнит-экономика" in result["message"]
    assert "Плановая экономика» для сценария" not in result["message"]
    assert result["keyboard"]["buttons"] == [
        {
            "text": "hook-2",
            "callback": "unit_economics:hook-2"
        },
        {
            "text": "offer-3",
            "callback": "unit_economics:offer-3"
        }
    ]


def test_select_sku_calls_existing_query_and_displays_result():
    handler, query = _build_handler(
        products=[{
            "product_id": 1,
            "offer_id": "hook-2",
            "sku": "3921245627"
        }]
    )

    result = handler.handle(
        "unit_economics:hook-2",
        user_id=42,
    )

    assert query.queries == ["hook-2"]
    assert result["error"] is False
    assert result["unit_economics"]["sku"] == "hook-2"
    assert "Unit Economics — hook-2" in result["message"]
    assert "Расчётная прибыль с 1 шт:" in result["message"]
    assert "Чистая прибыль" not in result["message"]
    detail_button = result["keyboard"]["buttons"][0]
    assert detail_button["text"] == "Из чего складывается"
    detail_result = handler.handle(
        detail_button["callback"],
        user_id=42,
    )
    assert query.queries == ["hook-2"]
    assert query.breakdown_calls == ["hook-2"]
    assert detail_result["message"] == "🧾 Проверенная локальная расшифровка — hook-2"


def test_unit_economics_breakdown_snapshot_is_user_scoped_and_expires():
    handler, query = _build_handler()
    result = handler.handle("unit_economics:hook-2", user_id=42)
    callback = result["keyboard"]["buttons"][0]["callback"]

    other_user = handler.handle(callback, user_id=99)
    assert other_user["code"] == "UNIT_ECONOMICS_BREAKDOWN_EXPIRED"
    assert query.queries == ["hook-2"]

    key = ("42", callback.split(":", 1)[1])
    handler._unit_economics_detail_snapshots[key]["expires_at"] = 0
    expired = handler.handle(callback, user_id=42)
    assert expired["code"] == "UNIT_ECONOMICS_BREAKDOWN_EXPIRED"
    assert query.queries == ["hook-2"]


def test_unit_economics_detail_callbacks_keep_their_own_sku_snapshot():
    handler, query = _build_handler()
    first = handler.handle("unit_economics:sku-one", user_id=42)
    second = handler.handle("unit_economics:sku-two", user_id=42)

    first_detail = handler.handle(
        first["keyboard"]["buttons"][0]["callback"],
        user_id=42,
    )
    second_detail = handler.handle(
        second["keyboard"]["buttons"][0]["callback"],
        user_id=42,
    )

    assert first_detail["message"].endswith("sku-one")
    assert second_detail["message"].endswith("sku-two")
    assert query.queries == ["sku-one", "sku-two"]


def test_incomplete_economics_exposes_explicit_sku_actions_and_scoped_refresh(monkeypatch):
    class IncompleteQuery(FakeUnitEconomicsQuery):
        cost_service = object()

        def query(self, sku):
            result = super().query(sku)
            if not result.get("error"):
                result["pre_ad_margin"] = {
                    "status": "AVAILABLE",
                    "basis": "CURRENT_MODEL",
                    "expense_scope": {
                        "unknown_non_ad_expense_keys": ["COGS", "OZON_COMMISSION"],
                        "known_non_ad_expenses_rub": {"LOGISTICS": "20.00"},
                    },
                    "advertising_status": "UNKNOWN",
                }
            return result

        def format_expense_breakdown(self, result):
            return "Расшифровка " + result["sku"]

    class Calculator:
        def build_product_entry_button(self, user_id, sku):
            return {"text": "Планировать цену", "callback": "upc:p:scenario-" + str(sku)}

    tenant = {"value": "owner::ozon::store-a"}
    monkeypatch.setattr(
        assistant_button_handler_module,
        "get_current_tenant_user_id",
        lambda: tenant["value"],
    )
    query = IncompleteQuery()
    handler = AssistantButtonHandlerService(
        assistant=FakeAssistant(),
        keyboard_service=AssistantKeyboardService(),
        unit_economics_query=query,
        unit_price_calculator_runtime_service=Calculator(),
    )

    result = handler.handle("unit_economics:sku-1", user_id=42)
    callbacks = [button["callback"] for button in result["keyboard"]["buttons"]]
    assert "seller_cost_return:sku-1" in callbacks
    assert "upc:p:scenario-sku-1" in callbacks
    refresh = next(item for item in callbacks if item.startswith("unit_economics_refresh:"))
    assert query.queries == ["sku-1"]

    detail = handler.handle(
        next(item for item in callbacks if item.startswith("unit_economics_details:")),
        user_id=42,
    )
    assert "OZON_COMMISSION" not in detail["message"]
    assert any(item.startswith("seller_cost_return:") for item in [
        button["callback"] for button in detail["keyboard"]["buttons"]
    ])
    assert query.queries == ["sku-1"]

    refreshed = handler.handle(refresh, user_id=42)
    assert refreshed["error"] is False
    assert query.queries == ["sku-1", "sku-1"]

    tenant["value"] = "owner::ozon::store-b"
    stale = handler.handle(refresh, user_id=42)
    assert stale["code"] == "UNIT_ECONOMICS_REFRESH_CONTEXT_STALE"
    stale_detail = handler.handle(
        next(item for item in callbacks if item.startswith("unit_economics_details:")),
        user_id=42,
    )
    assert stale_detail["code"] == "UNIT_ECONOMICS_BREAKDOWN_EXPIRED"
    assert query.queries == ["sku-1", "sku-1"]


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
