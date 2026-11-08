from collections import OrderedDict
from threading import Event, Thread

from services.assistant_button_handler_service import (
    AssistantButtonHandlerService
)
import services.assistant_button_handler_service as assistant_button_handler_module
from services.assistant_keyboard_service import (
    AssistantKeyboardService
)
from telegram_app_layer.seller_cost_telegram_adapter import SellerCostTelegramAdapter
from services.tenant_context import (
    reset_current_tenant_user_id,
    set_current_tenant_user_id,
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


def test_unit_economics_detail_snapshot_is_rejected_after_cost_revision_changes():
    class RevisionCostAdapter:
        revision = "cost-r1"
        allocation_revision = "allocation-r1"

        def get_current_cost_date(self):
            return "2026-11-08"

        def resolve_current_cost(self, product, *, store_id, as_of_date):
            return {
                "error": False,
                "cost_revision": self.revision,
                "cost_basis": {
                    "quantity_allocation_basis": {
                        "revision": self.allocation_revision,
                    },
                },
            }

    handler, query = _build_handler()
    adapter = RevisionCostAdapter()
    query.cost_adapter = adapter
    tenant = set_current_tenant_user_id("user-42::ozon::store-a")
    identity = {
        "store_id": "store-a", "product_id": "product-1",
        "offer_id": "offer-1", "sku": "sku-1",
    }
    try:
        callback = handler._store_unit_economics_detail_snapshot(
            "42", "Current revision detail", sku="sku-1",
            cost_identity=identity, cost_revision="cost-r1",
            allocation_revision="allocation-r1",
        )
        current = handler.handle(callback, user_id=42)
        adapter.revision = "cost-r2"
        adapter.allocation_revision = "allocation-r2"
        stale = handler.handle(callback, user_id=42)
    finally:
        reset_current_tenant_user_id(tenant)

    assert current["message"] == "Current revision detail"
    assert stale["code"] == "UNIT_ECONOMICS_BREAKDOWN_STALE"
    assert "откройте sku заново" in stale["message"].lower()


def test_fifo_apply_cache_invalidation_removes_only_old_exact_revision():
    class RevisionCostAdapter:
        def get_current_cost_date(self):
            return "2026-11-08"

        def resolve_current_cost(self, product, *, store_id, as_of_date):
            return {
                "error": False,
                "cost_revision": "cost-r2",
                "cost_basis": {
                    "quantity_allocation_basis": {"revision": "allocation-r2"},
                },
            }

    handler, query = _build_handler()
    query.cost_adapter = RevisionCostAdapter()
    tenant = set_current_tenant_user_id("user-42::ozon::store-a")
    identity = {
        "store_id": "store-a", "product_id": "product-1",
        "offer_id": "offer-1", "sku": "sku-1",
    }
    try:
        old_callback = handler._store_unit_economics_detail_snapshot(
            "42", "old", sku="sku-1", cost_identity=identity,
            cost_revision="cost-r1", allocation_revision="allocation-r1",
        )
        current_callback = handler._store_unit_economics_detail_snapshot(
            "42", "current", sku="sku-1", cost_identity=identity,
            cost_revision="cost-r2", allocation_revision="allocation-r2",
        )
        other_identity = {**identity, "sku": "sku-2"}
        other_callback = handler._store_unit_economics_detail_snapshot(
            "42", "other sku", sku="sku-2", cost_identity=other_identity,
            cost_revision="cost-r1", allocation_revision="allocation-r1",
        )
        invalidated = handler.invalidate_fifo_transition_snapshots(identity)
        tokens = {
            item.split(":", 1)[1]
            for item in (current_callback, other_callback)
        }
        stored_tokens = {key[1] for key in handler._unit_economics_detail_snapshots}
    finally:
        reset_current_tenant_user_id(tenant)

    assert invalidated == 1
    assert old_callback.split(":", 1)[1] not in stored_tokens
    assert tokens <= stored_tokens


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

        def refresh(self, sku):
            self.refresh_calls = getattr(self, "refresh_calls", 0) + 1
            return self.query(sku)

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
    cost_callback = next(item for item in callbacks if item.startswith("seller_cost_return:"))
    assert cost_callback != "seller_cost_return:sku-1"
    assert len(cost_callback.encode("utf-8")) <= 64
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
    assert query.refresh_calls == 1

    tenant["value"] = "owner::ozon::store-b"
    stale = handler.handle(refresh, user_id=42)
    assert stale["code"] == "UNIT_ECONOMICS_REFRESH_CONTEXT_STALE"
    stale_detail = handler.handle(
        next(item for item in callbacks if item.startswith("unit_economics_details:")),
        user_id=42,
    )
    assert stale_detail["code"] == "UNIT_ECONOMICS_BREAKDOWN_EXPIRED"
    assert query.queries == ["sku-1", "sku-1"]


def test_old_seller_cost_entry_button_is_bound_to_user_and_store(monkeypatch):
    tenant = {"value": "owner::ozon::store-a"}
    monkeypatch.setattr(
        assistant_button_handler_module,
        "get_current_tenant_user_id",
        lambda: tenant["value"],
    )
    handler = AssistantButtonHandlerService(assistant=FakeAssistant())

    class CostFlow:
        def __init__(self):
            self.selected = []

        def select_sku(self, user_id, sku, return_to_unit_economics=False):
            self.selected.append((user_id, sku, return_to_unit_economics))
            return {"error": False, "seller_cost_input_pending": True}

    cost_flow = CostFlow()
    adapter = SellerCostTelegramAdapter(
        assistant=FakeAssistant(),
        keyboard_service=AssistantKeyboardService(),
        button_handler=handler,
        seller_cost_service=cost_flow,
    )
    callback = handler.create_seller_cost_return_callback(42, "sku-1")
    assert callback and "sku-1" not in callback

    tenant["value"] = "owner::ozon::store-b"
    stale = adapter.handle_button(callback, user_id=42)
    assert stale["error"] is True
    assert stale["code"] == "SELLER_COST_ENTRY_STALE"
    assert cost_flow.selected == []

    tenant["value"] = "owner::ozon::store-a"
    replay = adapter.handle_button(callback, user_id=42)
    assert replay["error"] is True
    assert replay["code"] == "SELLER_COST_ENTRY_STALE"
    assert cost_flow.selected == []

    fresh = handler.create_seller_cost_return_callback(42, "sku-1")
    accepted = adapter.handle_button(fresh, user_id=42)
    assert accepted["seller_cost_input_pending"] is True
    assert cost_flow.selected == [(42, "sku-1", True)]


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


def test_unit_economics_snapshot_cache_expiration_and_insertion_are_thread_safe(monkeypatch):
    handler = AssistantButtonHandlerService(
        assistant=FakeAssistant(), keyboard_service=AssistantKeyboardService(),
    )
    tenant = {"value": "owner::ozon::store-a"}
    monkeypatch.setattr(
        assistant_button_handler_module,
        "get_current_tenant_user_id",
        lambda: tenant["value"],
    )
    iteration_paused = Event()
    release_iteration = Event()
    second_started = Event()
    second_finished = Event()
    errors = []

    class PausingOrderedDict(OrderedDict):
        pause_next_iteration = True

        def items(self):
            entries = super().items()
            if not self.pause_next_iteration:
                return entries
            self.pause_next_iteration = False

            def paused_entries():
                for index, entry in enumerate(entries):
                    yield entry
                    if index == 0:
                        iteration_paused.set()
                        if not release_iteration.wait(5):
                            raise AssertionError("test did not release snapshot iteration")

            return paused_entries()

    handler._unit_economics_detail_snapshots = PausingOrderedDict({
        ("old-user-a", "old-a"): {"expires_at": 9999999999},
        ("old-user-b", "old-b"): {"expires_at": 9999999999},
    })

    def store_first():
        try:
            handler._store_unit_economics_detail_snapshot(
                "first-user", "first snapshot", sku="sku-1",
            )
        except Exception as exc:  # surfaced in the assertion thread below
            errors.append(exc)

    def store_second():
        second_started.set()
        try:
            handler._store_unit_economics_detail_snapshot(
                "second-user", "second snapshot", sku="sku-2",
            )
        except Exception as exc:  # surfaced in the assertion thread below
            errors.append(exc)
        finally:
            second_finished.set()

    first = Thread(target=store_first)
    first.start()
    assert iteration_paused.wait(2)
    second = Thread(target=store_second)
    second.start()
    assert second_started.wait(2)
    second_was_blocked_by_snapshot_lock = not second_finished.wait(0.05)
    release_iteration.set()
    first.join(2)
    second.join(2)

    assert not first.is_alive() and not second.is_alive()
    assert second_was_blocked_by_snapshot_lock is True
    assert errors == []
    assert len(handler._unit_economics_detail_snapshots) == 4
