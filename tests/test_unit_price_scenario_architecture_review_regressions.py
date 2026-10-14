from copy import deepcopy
from threading import Event, Thread

import pytest

from services.assistant_button_handler_service import AssistantButtonHandlerService
from services.assistant_keyboard_service import AssistantKeyboardService
from services.tax_service import TaxService
from services.tenant_context import reset_current_tenant_user_id, set_current_tenant_user_id
from services.telegram_unit_price_calculator_runtime_service import (
    TelegramUnitPriceCalculatorRuntimeService,
)
from services.unit_price_scenario_service import UnitPriceScenarioService
from telegram_app_layer.return_inventory_telegram_adapter import ReturnInventoryTelegramAdapter
from telegram_app_layer.seller_cost_telegram_adapter import SellerCostTelegramAdapter
from telegram_app_layer.telegram_command_service import TelegramCommandService

THREAD_WAIT_SECONDS = 10


class ProductCatalog:
    def __init__(self, products=None):
        self.products = list(products or [])

    def load_products(self):
        return deepcopy(self.products)


def _product(reference, sku):
    return {
        "product_id": "product-" + str(sku),
        "offer_id": str(reference),
        "sku": str(sku),
        "name": "Товар " + str(sku),
    }


class ScenarioSource:
    def __init__(self, products=None, block_skus=()):
        self.product_service = ProductCatalog(products or [_product("offer-1", "sku-1")])
        self.calls = []
        self.block_skus = set(block_skus)
        self.started = {sku: Event() for sku in self.block_skus}
        self.release = {sku: Event() for sku in self.block_skus}

    def load_snapshot(self, sku, user_id, force_refresh=False):
        sku = str(sku)
        self.calls.append((sku, user_id, force_refresh))
        if sku in self.block_skus:
            self.started[sku].set()
            assert self.release[sku].wait(THREAD_WAIT_SECONDS), "test did not release blocked source read"
        from services.tenant_context import get_current_tenant_user_id
        scope = str(get_current_tenant_user_id() or "")
        return {
            "error": False,
            "snapshot_id": "snapshot-" + sku,
            "identity": {
                "user_id": user_id,
                "store_id": scope.rsplit("::", 1)[-1],
                "tenant_scope": scope,
                "product_id": "product-" + sku,
                "offer_id": "offer-" + sku,
                "sku": sku,
            },
            "product": {"name": "Товар " + sku, "scheme": "FBO"},
            "suggested_inputs": {
                "price": 500,
                "cost": 120,
                "commission_rate": 15,
                "logistics_per_unit": 40,
                "last_mile_per_unit": 10,
                "acquiring_per_unit": 5,
                "advertising_rate": None,
                "discount_points_rate": 20,
                "tax_mode": "USN_INCOME",
                "tax_rate": 6,
                "minimum_tax_rate": 1,
            },
            "input_provenance": {"price": "source", "commission_rate": "source"},
            "source_periods": {
                "seller_price_as_of": "2026-10-14T09:00:00+03:00",
                "discount_points": {"from": "2026-09-16", "to": "2026-10-13"},
            },
            "source_completeness": {"discount_points": {"complete": True}},
        }


class BlockingRefreshSource(ScenarioSource):
    def __init__(self, products, fail_refresh=False):
        super().__init__(products)
        self.refresh_started = Event()
        self.release_refresh = Event()
        self.fail_refresh = fail_refresh

    def load_snapshot(self, sku, user_id, force_refresh=False):
        if force_refresh:
            self.refresh_started.set()
            assert self.release_refresh.wait(THREAD_WAIT_SECONDS), "test did not release blocked refresh"
            if self.fail_refresh:
                raise RuntimeError("injected refresh failure")
        return super().load_snapshot(sku, user_id, force_refresh)


class RefreshPriceSource(ScenarioSource):
    def __init__(self, fail_refresh=False):
        super().__init__()
        self.fail_refresh = fail_refresh

    def load_snapshot(self, sku, user_id, force_refresh=False):
        if force_refresh and self.fail_refresh:
            self.calls.append((str(sku), user_id, force_refresh))
            return {"error": True, "code": "SOURCE_UNAVAILABLE"}
        result = super().load_snapshot(sku, user_id, force_refresh)
        if force_refresh:
            result["suggested_inputs"]["price"] = 550
            result["source_periods"]["seller_price_as_of"] = "2026-10-14T12:00:00+03:00"
        return result


def _runtime(source=None, **kwargs):
    source = source or ScenarioSource()
    runtime = TelegramUnitPriceCalculatorRuntimeService(
        source=source,
        scenario_service=UnitPriceScenarioService(TaxService()),
        keyboard_service=AssistantKeyboardService(),
        **kwargs,
    )
    return runtime, source


def _tenant(user="user-1", store="store-1"):
    return set_current_tenant_user_id(f"{user}::ozon::{store}")


def _select(runtime, reference="offer-1", user="user-1", store="store-1"):
    token = _tenant(user, store)
    try:
        runtime.begin_catalog_selection(user)
        callback_builder = getattr(runtime, "build_catalog_product_callback", None)
        if callable(callback_builder):
            callback = callback_builder(user, reference)
            return runtime.handle_callback(callback, user_id=user)
        return runtime.handle_catalog_selection(reference, user_id=user)
    finally:
        reset_current_tenant_user_id(token)


def _handler(runtime, catalog):
    query = type("Query", (), {"product_service": catalog})()
    return AssistantButtonHandlerService(
        assistant=object(),
        keyboard_service=AssistantKeyboardService(),
        unit_economics_query=query,
        unit_price_calculator_runtime_service=runtime,
    )


def test_catalog_picker_callback_is_bound_to_the_picker_store_and_generation():
    catalog = ProductCatalog([_product("same-offer", "sku-A")])
    source = ScenarioSource(catalog.products)
    source.product_service = catalog
    runtime, _ = _runtime(source)
    handler = _handler(runtime, catalog)

    a_token = _tenant(store="store-A")
    try:
        picker_a = handler.handle("upc:m", user_id="user-1")
        callback_a = picker_a["keyboard"]["buttons"][0]["callback"]
    finally:
        reset_current_tenant_user_id(a_token)

    catalog.products = [_product("same-offer", "sku-B")]
    b_token = _tenant(store="store-B")
    try:
        picker_b = handler.handle("upc:m", user_id="user-1")
        callback_b = picker_b["keyboard"]["buttons"][0]["callback"]
        stale = handler.handle(callback_a, user_id="user-1")
        assert stale["status"] == "UNIT_PRICE_SCENARIO_STALE"
        assert source.calls == []
        selected = handler.handle(callback_b, user_id="user-1")
    finally:
        reset_current_tenant_user_id(b_token)

    assert selected["price_scenario"]["identity"]["tenant_scope"] == "user-1::ozon::store-B"
    assert selected["price_scenario"]["identity"]["sku"] == "sku-B"
    assert source.calls == [("sku-B", "user-1", False)]
    assert len(callback_a.encode("utf-8")) <= 64
    assert len(callback_b.encode("utf-8")) <= 64


def test_reopening_same_store_picker_invalidates_old_button_without_consuming_new_one():
    catalog = ProductCatalog([_product("offer-1", "sku-1")])
    source = ScenarioSource(catalog.products)
    runtime, _ = _runtime(source)
    source.product_service = catalog
    handler = _handler(runtime, catalog)
    token = _tenant()
    try:
        old_picker = handler.handle("upc:m", user_id="user-1")
        old_callback = old_picker["keyboard"]["buttons"][0]["callback"]
        new_picker = handler.handle("upc:m", user_id="user-1")
        new_callback = new_picker["keyboard"]["buttons"][0]["callback"]
        stale = handler.handle(old_callback, user_id="user-1")
        assert stale["status"] == "UNIT_PRICE_SCENARIO_STALE"
        assert source.calls == []
        selected = handler.handle(new_callback, user_id="user-1")
    finally:
        reset_current_tenant_user_id(token)

    assert selected["price_scenario"]["identity"]["sku"] == "sku-1"
    assert source.calls == [("sku-1", "user-1", False)]


def test_late_initial_load_cannot_resurrect_scenario_after_navigation():
    source = ScenarioSource([_product("offer-A", "sku-A")], block_skus={"sku-A"})
    runtime, _ = _runtime(source)
    result = {}

    def load_in_worker():
        token = _tenant()
        try:
            result["load"] = runtime._start_product_selection(
                "offer-A", "user-1", "user-1::ozon::store-1"
            )
        finally:
            reset_current_tenant_user_id(token)

    thread = Thread(target=load_in_worker)
    thread.start()
    assert source.started["sku-A"].wait(THREAD_WAIT_SECONDS)
    token = _tenant()
    try:
        runtime.clear_pending("user-1")
    finally:
        reset_current_tenant_user_id(token)
    source.release["sku-A"].set()
    thread.join(THREAD_WAIT_SECONDS)
    assert not thread.is_alive()

    assert result["load"]["status"] == "UNIT_PRICE_SCENARIO_STALE"


def test_late_older_load_cannot_replace_newer_selected_product():
    source = ScenarioSource(
        [_product("offer-A", "sku-A"), _product("offer-B", "sku-B")],
        block_skus={"sku-A"},
    )
    runtime, _ = _runtime(source)
    results = {}

    def load_a():
        token = _tenant()
        try:
            results["a"] = runtime._start_product_selection(
                "offer-A", "user-1", "user-1::ozon::store-1"
            )
        finally:
            reset_current_tenant_user_id(token)

    thread = Thread(target=load_a)
    thread.start()
    assert source.started["sku-A"].wait(THREAD_WAIT_SECONDS)
    token = _tenant()
    try:
        results["b"] = runtime._start_product_selection(
            "offer-B", "user-1", "user-1::ozon::store-1"
        )
    finally:
        reset_current_tenant_user_id(token)
    source.release["sku-A"].set()
    thread.join(THREAD_WAIT_SECONDS)
    assert not thread.is_alive()

    token = _tenant()
    try:
        current = runtime.handle_callback(
            f"upc:v:{results['b']['price_scenario']['scenario_id']}:1",
            user_id="user-1",
        )
    finally:
        reset_current_tenant_user_id(token)
    assert results["a"]["status"] == "UNIT_PRICE_SCENARIO_STALE"
    assert current["status"] == "UNIT_PRICE_SCENARIO_INPUT_REQUIRED"
    assert current["price_scenario"]["identity"]["sku"] == "sku-B"


@pytest.mark.parametrize("fail_refresh", [False, True])
def test_late_refresh_success_or_failure_cannot_restore_old_product(fail_refresh):
    products = [_product("offer-A", "sku-A"), _product("offer-B", "sku-B")]
    source = BlockingRefreshSource(products, fail_refresh=fail_refresh)
    runtime, _ = _runtime(source)
    old = _select(runtime, "offer-A")
    old_sid = old["price_scenario"]["scenario_id"]
    refresh_result = {}

    def refresh_old():
        token = _tenant()
        try:
            refresh_result["value"] = runtime.handle_callback(
                f"upc:r:{old_sid}:1", user_id="user-1"
            )
        finally:
            reset_current_tenant_user_id(token)

    thread = Thread(target=refresh_old)
    thread.start()
    assert source.refresh_started.wait(THREAD_WAIT_SECONDS)
    token = _tenant()
    try:
        newer = runtime._start_product_selection(
            "offer-B", "user-1", "user-1::ozon::store-1"
        )
    finally:
        reset_current_tenant_user_id(token)
    source.release_refresh.set()
    thread.join(THREAD_WAIT_SECONDS)
    assert not thread.is_alive()

    assert refresh_result["value"]["status"] == "UNIT_PRICE_SCENARIO_STALE"
    token = _tenant()
    try:
        active_id = runtime._active[("user-1", "user-1::ozon::store-1")]
        active = runtime._scenarios[active_id]
    finally:
        reset_current_tenant_user_id(token)
    assert active["scenario_id"] == newer["price_scenario"]["scenario_id"]
    assert active["sku"] == "sku-B"


def test_eviction_of_inactive_scenario_preserves_active_scenario_text_input():
    products = [
        _product("offer-A", "sku-A"),
        _product("offer-B", "sku-B"),
        _product("offer-C", "sku-C"),
    ]
    runtime, _ = _runtime(ScenarioSource(products), max_scenarios=2)
    first = _select(runtime, "offer-A")
    second = _select(runtime, "offer-B")
    token = _tenant()
    try:
        sid = second["price_scenario"]["scenario_id"]
        prompt = runtime.handle_callback(f"upc:e:{sid}:1:price", user_id="user-1")
        _select(runtime, "offer-C", user="user-2", store="store-2")
        entered = runtime.handle_text("600", user_id="user-1")
    finally:
        reset_current_tenant_user_id(token)

    assert first["price_scenario"]["scenario_id"] != second["price_scenario"]["scenario_id"]
    assert prompt["status"] == "UNIT_PRICE_SCENARIO_INPUT_PENDING"
    assert entered["status"] == "UNIT_PRICE_SCENARIO_INPUT_REQUIRED"
    assert entered["price_scenario"]["identity"]["sku"] == "sku-B"
    assert entered["price_scenario"]["inputs"]["price"]["value"] == 600


def test_text_on_result_screen_returns_current_calculator_keyboard_without_mutation():
    runtime, source = _runtime()
    scenario = _select(runtime)
    sid = scenario["price_scenario"]["scenario_id"]
    token = _tenant()
    try:
        ready = runtime.handle_callback(f"upc:z:{sid}:1", user_id="user-1")
        before = deepcopy(ready["price_scenario"])
        reads_before = list(source.calls)
        repeated = runtime.handle_text("текст не для ввода", user_id="user-1")
    finally:
        reset_current_tenant_user_id(token)

    assert repeated["status"] == "UNIT_PRICE_SCENARIO_READY"
    assert repeated["price_scenario"]["scenario_id"] == before["scenario_id"]
    assert repeated["price_scenario"]["scenario_version"] == before["scenario_version"]
    assert repeated["price_scenario"]["inputs"] == before["inputs"]
    assert repeated["keyboard"]["buttons"]
    assert source.calls == reads_before


def test_extreme_finite_price_is_rejected_without_losing_retry_keyboard():
    runtime, _ = _runtime()
    scenario = _select(runtime)
    sid = scenario["price_scenario"]["scenario_id"]
    token = _tenant()
    try:
        runtime.handle_callback(f"upc:e:{sid}:1:price", user_id="user-1")
        invalid = runtime.handle_text("1e100", user_id="user-1")
        retry = runtime.handle_text("600", user_id="user-1")
    finally:
        reset_current_tenant_user_id(token)

    assert invalid["status"] == "UNIT_PRICE_SCENARIO_INPUT_PENDING"
    assert invalid["keyboard"]["buttons"]
    assert "некорректно" in invalid["message"].lower()
    assert retry["price_scenario"]["inputs"]["price"]["value"] == 600


def test_source_snapshot_expires_independently_from_session_activity():
    class Clock:
        now = 0

        def __call__(self):
            return self.now

    clock = Clock()
    runtime, source = _runtime(clock=clock, session_ttl_seconds=600)
    scenario = _select(runtime)
    sid = scenario["price_scenario"]["scenario_id"]
    token = _tenant()
    try:
        ready = runtime.handle_callback(f"upc:z:{sid}:1", user_id="user-1")
        clock.now = 590
        active = runtime.handle_callback(
            f"upc:b:{ready['price_scenario']['scenario_id']}:2",
            user_id="user-1",
        )
        clock.now = 1180
        stale_source = runtime.handle_callback(
            f"upc:v:{active['price_scenario']['scenario_id']}:3",
            user_id="user-1",
        )
        assumptions = runtime.handle_callback(
            f"upc:a:{active['price_scenario']['scenario_id']}:3",
            user_id="user-1",
        )
    finally:
        reset_current_tenant_user_id(token)

    assert stale_source["status"] == "UNIT_PRICE_SCENARIO_READY"
    assert stale_source["price_scenario"]["comparison"]["available"] is False
    assert "устарел" in stale_source["message"].lower()
    assert "источники устарели" in assumptions["message"].lower()
    assert "2026-10-14T09:00:00+03:00" in assumptions["message"]
    assert "текущая карточка" not in assumptions["message"].lower()
    assert source.calls == [("sku-1", "user-1", False)]


@pytest.mark.parametrize("fail_refresh", [False, True])
def test_refresh_resets_only_successful_source_freshness_and_preserves_manual_inputs(fail_refresh):
    class Clock:
        now = 0

        def __call__(self):
            return self.now

    clock = Clock()
    source = RefreshPriceSource(fail_refresh=fail_refresh)
    runtime, _ = _runtime(source, clock=clock, session_ttl_seconds=600)
    scenario = _select(runtime)
    sid = scenario["price_scenario"]["scenario_id"]
    token = _tenant()
    try:
        prompt = runtime.handle_callback(f"upc:e:{sid}:1:price", user_id="user-1")
        changed_price = runtime.handle_text("600", user_id="user-1")
        sid = changed_price["price_scenario"]["scenario_id"]
        with_zero_ad = runtime.handle_callback(
            f"upc:z:{sid}:3", user_id="user-1"
        )
        clock.now = 590
        touched = runtime.handle_callback(
            f"upc:v:{sid}:4", user_id="user-1"
        )
        clock.now = 1180
        version = 4
        refreshed = runtime.handle_callback(
            f"upc:r:{sid}:{version}", user_id="user-1"
        )
    finally:
        reset_current_tenant_user_id(token)

    assert prompt["status"] == "UNIT_PRICE_SCENARIO_INPUT_PENDING"
    assert with_zero_ad["status"] == "UNIT_PRICE_SCENARIO_READY"
    assert touched["price_scenario"]["source_freshness"]["status"] == "FRESH"
    if fail_refresh:
        assert refreshed["price_scenario"]["source_freshness"]["status"] == "STALE"
        assert refreshed["price_scenario"]["comparison"]["available"] is False
        assert "не удалось обновить" in refreshed["message"].lower()
        assert refreshed["price_scenario"]["inputs"]["price"]["value"] == 600
    else:
        assert refreshed["price_scenario"]["source_freshness"]["status"] == "FRESH"
        assert refreshed["price_scenario"]["comparison"]["available"] is True
        assert refreshed["price_scenario"]["comparison"]["price"] == 550
        assert refreshed["price_scenario"]["inputs"]["price"]["value"] == 600
        assert refreshed["price_scenario"]["inputs"]["advertising_rate"]["value"] == 0


class _SellerCostStub:
    def __init__(self):
        self.texts = []

    def open_menu(self):
        return {"error": False, "message": "seller cost menu", "keyboard": {"buttons": []}}

    def handle_text(self, user_id, text):
        self.texts.append((user_id, text))
        return {"error": False, "handled": False}

    def clear_pending(self, _user_id):
        return None

    def is_confirmation_callback(self, _callback):
        return False


def test_seller_cost_adapter_navigation_clears_calculator_text_stage():
    runtime, _ = _runtime()
    scenario = _select(runtime)
    sid = scenario["price_scenario"]["scenario_id"]
    button_handler = _handler(runtime, runtime.source.product_service)
    adapter = SellerCostTelegramAdapter(
        assistant=object(),
        keyboard_service=AssistantKeyboardService(),
        button_handler=button_handler,
        seller_cost_service=_SellerCostStub(),
    )
    token = _tenant()
    try:
        prompt = adapter.handle_button(f"upc:e:{sid}:1:price", user_id="user-1")
        assert prompt["status"] == "UNIT_PRICE_SCENARIO_INPUT_PENDING"
        menu = adapter.handle_button("seller_cost", user_id="user-1")
        text_result = adapter.handle_text("600", user_id="user-1")
        old_callback = runtime.handle_callback(f"upc:c:{sid}:2", user_id="user-1")
    finally:
        reset_current_tenant_user_id(token)

    assert menu["message"] == "seller cost menu"
    assert runtime._active.get(("user-1", "user-1::ozon::store-1")) is None
    assert runtime._pending.get(("user-1", "user-1::ozon::store-1")) is None
    assert old_callback["status"] == "UNIT_PRICE_SCENARIO_STALE"
    assert not (isinstance(text_result, dict) and "price_scenario" in text_result)


class _ReturnInventoryStub:
    def open_menu(self, _user_id):
        return {"error": False, "message": "return inventory menu"}

    def handle_text(self, _user_id, _text):
        return {"error": False, "handled": False}

    def clear_pending(self, _user_id):
        return None


def test_return_inventory_adapter_navigation_clears_calculator_text_stage():
    runtime, _ = _runtime()
    scenario = _select(runtime)
    sid = scenario["price_scenario"]["scenario_id"]
    adapter = ReturnInventoryTelegramAdapter(
        assistant=object(),
        keyboard_service=AssistantKeyboardService(),
        button_handler=_handler(runtime, runtime.source.product_service),
        seller_cost_service=_SellerCostStub(),
        return_inventory_service=_ReturnInventoryStub(),
    )
    token = _tenant()
    try:
        prompt = adapter.handle_button(f"upc:e:{sid}:1:price", user_id="user-1")
        assert prompt["status"] == "UNIT_PRICE_SCENARIO_INPUT_PENDING"
        menu = adapter.handle_button("return_inventory", user_id="user-1")
        text_result = adapter.handle_text("600", user_id="user-1")
        old_callback = runtime.handle_callback(f"upc:c:{sid}:2", user_id="user-1")
    finally:
        reset_current_tenant_user_id(token)

    assert menu["message"] == "return inventory menu"
    assert runtime._active.get(("user-1", "user-1::ozon::store-1")) is None
    assert runtime._pending.get(("user-1", "user-1::ozon::store-1")) is None
    assert old_callback["status"] == "UNIT_PRICE_SCENARIO_STALE"
    assert not (isinstance(text_result, dict) and "price_scenario" in text_result)


def test_store_switch_and_disconnect_commands_clear_calculator_before_store_mutation():
    events = []

    class Adapter:
        def clear_unit_price_calculator_state(self, user_id):
            events.append(("clear", user_id))

    class OzonAccountStub:
        def stores(self, user_id):
            events.append(("stores", user_id))
            return {"error": False}

        def select(self, user_id, client_id):
            events.append(("select", user_id, client_id))
            return {"error": False}

        def disconnect(self, user_id):
            events.append(("disconnect", user_id))
            return {"error": False}

    commands = TelegramCommandService(
        Adapter(),
        ozon_account_service=OzonAccountStub(),
    )
    commands.handle("user-1", "/ozon_disconnect")
    commands.handle_callback("user-1", "ozon_store:client-2")

    assert events == [
        ("clear", "user-1"),
        ("disconnect", "user-1"),
        ("clear", "user-1"),
        ("select", "user-1", "client-2"),
    ]
