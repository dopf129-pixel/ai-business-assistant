from copy import deepcopy

from services.assistant_keyboard_service import AssistantKeyboardService
from services.tax_service import TaxService
from services.tenant_context import reset_current_tenant_user_id, set_current_tenant_user_id
from services.telegram_unit_price_calculator_runtime_service import (
    TelegramUnitPriceCalculatorRuntimeService,
)
from services.unit_price_scenario_service import UnitPriceScenarioService


class _ProductService:
    def __init__(self):
        self.products = [{
            "product_id": "p1",
            "offer_id": "hook-2",
            "sku": "3921245627",
            "name": "Самоклеящийся крючок",
        }]

    def load_products(self):
        return deepcopy(self.products)


class _Source:
    def __init__(self):
        self.product_service = _ProductService()
        self.calls = []

    def load_snapshot(self, sku, user_id, force_refresh=False):
        self.calls.append((sku, user_id, force_refresh))
        return {
            "error": False,
            "snapshot_id": "snapshot-1",
            "identity": {
                "user_id": user_id,
                "store_id": "store-1",
                "tenant_scope": f"{user_id}::ozon::store-1",
                "product_id": "p1",
                "offer_id": "hook-2",
                "sku": sku,
            },
            "product": {"name": "Самоклеящийся крючок", "scheme": "FBO"},
            "suggested_inputs": {
                "price": 500,
                "cost": 120,
                "commission_rate": 15,
                "logistics_per_unit": 40,
                "last_mile_per_unit": 10,
                "acquiring_per_unit": 5,
                "advertising_rate": None,
                "discount_points_rate": "20",
                "tax_mode": "USN_INCOME",
                "tax_rate": 6,
                "minimum_tax_rate": 1,
            },
            "input_provenance": {
                "price": "ozon_current_seller_price",
                "cost": "confirmed_store_cost",
                "commission_rate": "ozon_current_fbo_rate",
                "discount_points_rate": "weighted_exact_sku_finance_average_28_completed_days",
            },
            "source_periods": {
                "discount_points": {
                    "from": "2026-09-16",
                    "to": "2026-10-13",
                    "calendar_days": 28,
                },
                "seller_price_as_of": "2026-10-14T09:00:00+03:00",
            },
            "source_completeness": {
                "discount_points": {
                    "complete": True,
                    "positive_sale_observations": 12,
                }
            },
        }


def _runtime(clock=None):
    source = _Source()
    runtime = TelegramUnitPriceCalculatorRuntimeService(
        source=source,
        scenario_service=UnitPriceScenarioService(TaxService()),
        keyboard_service=AssistantKeyboardService(),
        clock=clock,
    )
    return runtime, source


def _activate(store="store-1"):
    return set_current_tenant_user_id(f"user-1::ozon::{store}")


def _find_button(result, text):
    return next(
        item for item in result["keyboard"]["buttons"]
        if item["text"] == text
    )


def test_catalog_selection_uses_exact_sku_and_initially_requires_manual_advertising():
    runtime, source = _runtime()
    token = _activate()
    try:
        menu = runtime.open_menu("user-1")
        select = menu["keyboard"]["buttons"][0]["callback"]
        result = runtime.handle_callback(select, user_id="user-1")
    finally:
        reset_current_tenant_user_id(token)

    assert select.startswith("upc:s:")
    assert len(select.encode("utf-8")) <= 64
    assert source.calls == [("3921245627", "user-1", False)]
    assert result["status"] == "UNIT_PRICE_SCENARIO_INPUT_REQUIRED"
    assert result["price_scenario"]["missing_inputs"] == ["advertising_rate"]
    assert "Реклама" in result["message"]
    assert all(len(button["callback"].encode("utf-8")) <= 64 for button in result["keyboard"]["buttons"])


def test_price_edit_accepts_comma_decimal_and_stale_buttons_fail_closed():
    runtime, _ = _runtime()
    token = _activate()
    try:
        menu = runtime.open_menu("user-1")
        scenario = runtime.handle_callback(menu["keyboard"]["buttons"][0]["callback"], user_id="user-1")
        sid = scenario["price_scenario"]["scenario_id"]
        old_edit = f"upc:e:{sid}:1:price"
        prompt = runtime.handle_callback(old_edit, user_id="user-1")
        old_zero_ad = f"upc:z:{sid}:1"
        invalid = runtime.handle_text("-1", user_id="user-1")
        valid = runtime.handle_text("600,50", user_id="user-1")
        stale = runtime.handle_callback(old_zero_ad, user_id="user-1")
    finally:
        reset_current_tenant_user_id(token)

    assert prompt["status"] == "UNIT_PRICE_SCENARIO_INPUT_PENDING"
    assert invalid["status"] == "UNIT_PRICE_SCENARIO_INPUT_PENDING"
    assert valid["price_scenario"]["inputs"]["price"]["value"] == 600.5
    assert valid["price_scenario"]["available"] is False
    assert stale["status"] == "UNIT_PRICE_SCENARIO_STALE"


def test_manual_zero_advertising_completes_scenario_and_reports_comparison():
    runtime, _ = _runtime()
    token = _activate()
    try:
        menu = runtime.open_menu("user-1")
        scenario = runtime.handle_callback(menu["keyboard"]["buttons"][0]["callback"], user_id="user-1")
        sid = scenario["price_scenario"]["scenario_id"]
        result = runtime.handle_callback(f"upc:z:{sid}:1", user_id="user-1")
    finally:
        reset_current_tenant_user_id(token)

    assert result["status"] == "UNIT_PRICE_SCENARIO_READY"
    assert result["price_scenario"]["calculated"]["profit"] == 226.0
    assert result["price_scenario"]["comparison"]["available"] is True
    assert "При текущей цене 500,00 ₽" in result["message"]
    assert "Оценка одной успешной продажи FBO" in result["message"]
    assert "FBS не поддержан" in result["message"]
    assert "не включены" in result["message"]


def test_manual_inputs_survive_source_refresh_and_auto_points_can_be_restored():
    runtime, source = _runtime()
    token = _activate()
    try:
        menu = runtime.open_menu("user-1")
        result = runtime.handle_callback(menu["keyboard"]["buttons"][0]["callback"], user_id="user-1")
        sid = result["price_scenario"]["scenario_id"]
        result = runtime.handle_callback(f"upc:e:{sid}:1:advertising_rate", user_id="user-1")
        result = runtime.handle_text("8", user_id="user-1")
        sid = result["price_scenario"]["scenario_id"]
        result = runtime.handle_callback(f"upc:e:{sid}:3:discount_points_rate", user_id="user-1")
        result = runtime.handle_text("10", user_id="user-1")
        sid = result["price_scenario"]["scenario_id"]
        refreshed = runtime.handle_callback(f"upc:r:{sid}:5", user_id="user-1")
        sid = refreshed["price_scenario"]["scenario_id"]
        restored = runtime.handle_callback(f"upc:b:{sid}:6", user_id="user-1")
    finally:
        reset_current_tenant_user_id(token)

    assert source.calls[-1] == ("3921245627", "user-1", True)
    assert refreshed["price_scenario"]["inputs"]["advertising_rate"]["value"] == 8.0
    assert refreshed["price_scenario"]["inputs"]["discount_points_rate"]["value"] == 10.0
    assert restored["price_scenario"]["inputs"]["discount_points_rate"]["value"] == 20.0
    assert "ручные допущения сохранены" in refreshed["message"]


def test_old_product_entry_button_cannot_cross_store_scope():
    runtime, source = _runtime()
    token = _activate("store-1")
    try:
        button = runtime.build_product_entry_button("user-1", "hook-2")
    finally:
        reset_current_tenant_user_id(token)
    other_token = _activate("store-2")
    try:
        stale = runtime.handle_callback(button["callback"], user_id="user-1")
    finally:
        reset_current_tenant_user_id(other_token)

    assert stale["status"] == "UNIT_PRICE_SCENARIO_STALE"
    assert source.calls == []


def test_leaving_calculator_clears_pending_text_stage():
    runtime, _ = _runtime()
    token = _activate()
    try:
        menu = runtime.open_menu("user-1")
        scenario = runtime.handle_callback(menu["keyboard"]["buttons"][0]["callback"], user_id="user-1")
        sid = scenario["price_scenario"]["scenario_id"]
        runtime.handle_callback(f"upc:e:{sid}:1:price", user_id="user-1")
        runtime.clear_pending("user-1")
        text_result = runtime.handle_text("600", user_id="user-1")
    finally:
        reset_current_tenant_user_id(token)

    assert text_result is None


def test_current_unit_economics_detail_has_entry_to_same_calculator_runtime():
    from services.assistant_button_handler_service import AssistantButtonHandlerService

    class _Query:
        product_service = _Source().product_service

        def query(self, sku):
            return {
                "error": False,
                "available": True,
                "source": "current",
                "sku": sku,
                "missing_fields": [],
            }

        def format_response(self, _result):
            return "unit economics detail"

    runtime, _ = _runtime()
    handler = AssistantButtonHandlerService(
        assistant=object(),
        keyboard_service=AssistantKeyboardService(),
        unit_economics_query=_Query(),
        unit_price_calculator_runtime_service=runtime,
    )
    token = _activate()
    try:
        result = handler.handle("unit_economics:hook-2", user_id="user-1")
        scenario = handler.handle(
            result["keyboard"]["buttons"][0]["callback"],
            user_id="user-1",
        )
    finally:
        reset_current_tenant_user_id(token)

    assert result["keyboard"]["buttons"][0]["text"] == "🧮 Подставить свою цену"
    assert result["keyboard"]["buttons"][0]["callback"].startswith("upc:p:")
    assert scenario["price_scenario"]["identity"]["sku"] == "3921245627"


def test_opening_calculator_clears_pending_period_and_expense_text_stages():
    from services.assistant_button_handler_service import AssistantButtonHandlerService

    class _PendingFlow:
        def __init__(self):
            self.cleared = []

        def clear_pending_custom_period_input(self, user_id):
            self.cleared.append(("period", user_id))

        def clear_pending(self, user_id):
            self.cleared.append(("expense", user_id))

    runtime, _ = _runtime()
    pending = _PendingFlow()
    handler = AssistantButtonHandlerService(
        assistant=object(),
        keyboard_service=AssistantKeyboardService(),
        unit_price_calculator_runtime_service=runtime,
        period_profit_runtime_service=pending,
        external_expense_runtime_service=pending,
    )
    token = _activate()
    try:
        result = handler.handle("unit_price_calculator", user_id="user-1")
    finally:
        reset_current_tenant_user_id(token)

    assert result["status"] == "UNIT_PRICE_SCENARIO_PRODUCT_SELECTION_REQUIRED"
    assert pending.cleared == [("period", "user-1"), ("expense", "user-1")]


def test_existing_unit_economics_menu_discoverably_opens_calculator():
    from services.assistant_button_handler_service import AssistantButtonHandlerService

    query = type("Query", (), {})()
    query.product_service = _Source().product_service
    runtime, _ = _runtime()
    handler = AssistantButtonHandlerService(
        assistant=object(),
        keyboard_service=AssistantKeyboardService(),
        unit_economics_query=query,
        unit_price_calculator_runtime_service=runtime,
    )
    token = _activate()
    try:
        menu = handler.handle("unit_economics", user_id="user-1")
    finally:
        reset_current_tenant_user_id(token)

    assert menu["keyboard"]["buttons"][0] == {
        "text": "🧮 Калькулятор цены",
        "callback": "upc:m",
    }


def test_factory_leaves_optional_calculator_disabled_when_sources_are_unavailable():
    from unit_price_scenario_factory import create_unit_price_scenario_runtime

    assert create_unit_price_scenario_runtime(
        core_components={},
        unit_economics_query=object(),
        keyboard_service=AssistantKeyboardService(),
    ) is None
