from services.assistant_button_handler_service import AssistantButtonHandlerService
from services.assistant_keyboard_service import AssistantKeyboardService
from services.product_overview_service import ProductOverviewService
from services.scoped_transient_snapshot_store import ScopedTransientSnapshotStore
from services.analytics_export_service import AnalyticsExportService
from services.tenant_context import (
    reset_current_tenant_user_id,
    set_current_tenant_user_id,
)


def _decision_row(selector="offer-1", sku="sku-1"):
    return {
        "selector": selector,
        "identity": {
            "product_id": "101",
            "offer_id": selector,
            "catalog_sku": sku,
        },
        "status": "READY",
        "code": None,
        "decision": {
            "error": False,
            "decision_type": "INVESTIGATE_LOW_PROFIT",
            "priority": "HIGH",
            "confidence": "HIGH",
            "reasons": ["NEGATIVE_UNIT_PROFIT"],
            "missing_data": [],
            "sales_velocity": 3.0,
            "sales_trend": "GROWING",
            "current_stock": 7,
            "days_of_stock": 2.3,
            "decision_profit_per_unit": -4.5,
            "decision_margin_percent": -2.0,
            "sales_observed_at": "2026-10-17T10:00:00Z",
            "sales_period_from": "2026-10-01",
            "sales_period_to": "2026-10-16",
        },
    }


class _Query:
    def __init__(self):
        self.calls = 0
        self.rows = [_decision_row()]

    def query_catalog_group(self, offset=0, limit=20):
        self.calls += 1
        rows = self.rows[offset : offset + limit]
        return {
            "error": False,
            "rows": rows,
            "selection_scope": {
                "mode": "FIRST_SORTED_CATALOG_GROUP",
                "sort_by": "offer_id_then_catalog_sku",
                "selected_count": len(rows),
                "catalog_identity_count": len(self.rows),
                "offset": offset,
                "has_previous_group": False,
                "has_next_group": False,
                "limit": limit,
            },
        }

    def query_selected_products(self, selectors):
        self.calls += 1
        return {"error": False, "rows": [_decision_row()]}


class _PriceRuntime:
    def __init__(self, active=None):
        self.active = active
        self.callbacks = []
        self.products = []

    def active_scenario_identity(self, user_id):
        return self.active

    def build_product_entry_button(self, user_id, product_reference):
        self.products.append((user_id, product_reference))
        return {"text": "plan", "callback": "upc:p:selection1"}

    def handle_callback(self, callback, user_id=None):
        self.callbacks.append((callback, user_id))
        return {"error": False, "message": "price scenario", "read_only": True, "executed": False}


def _handler(runtime=None, analytics_export_service=None):
    query = _Query()
    overview = ProductOverviewService(
        query,
        ScopedTransientSnapshotStore(),
    )
    keyboard = AssistantKeyboardService()
    handler = AssistantButtonHandlerService(
        assistant=None,
        keyboard_service=keyboard,
        unit_price_calculator_runtime_service=runtime,
        product_overview_service=overview,
        analytics_export_service=analytics_export_service,
    )
    return handler, overview, query, keyboard


def _tenant():
    return set_current_tenant_user_id("owner-1::ozon::store-1")


def test_main_menu_opens_snapshot_and_row_callbacks_fit_telegram_limit():
    handler, _overview, query, keyboard = _handler()
    menu_callbacks = {
        item["callback"] for item in keyboard.build_main_keyboard()["buttons"]
    }
    tenant = _tenant()
    try:
        response = handler.handle("product_overview", user_id="owner-1")
        row_button = next(
            item for item in response["keyboard"]["buttons"]
            if item["callback"].startswith("pov:d:")
        )
        detail = handler.handle(row_button["callback"], user_id="owner-1")
    finally:
        reset_current_tenant_user_id(tenant)

    detail_callbacks = [item["callback"] for item in detail["keyboard"]["buttons"]]
    assert {
        "product_overview",
        "period_profit",
        "external_expenses",
        "experimental_calculations",
        "seller_cost",
        "unit_economics",
        "product_decisions",
        "returns_finance_impact",
    } <= menu_callbacks
    assert response["error"] is False
    assert "не рейтинг" in response["message"]
    assert len(row_button["callback"].encode("utf-8")) == 64
    assert any(callback.startswith("pov:e:") for callback in detail_callbacks)
    assert all(len(callback.encode("utf-8")) <= 64 for callback in detail_callbacks)
    assert query.calls == 1


def test_filter_navigation_reuses_snapshot_and_messages_fit_telegram_limit():
    handler, _overview, query, _keyboard = _handler()
    query.rows = [
        _decision_row(f"offer-{index}", f"sku-{index}")
        for index in range(7)
    ]
    tenant = _tenant()
    try:
        initial = handler.handle("product_overview", user_id="owner-1")
        filter_callback = next(
            item["callback"] for item in initial["keyboard"]["buttons"]
            if item["callback"].startswith("pov:f:")
        )
        filtered = handler.handle(filter_callback, user_id="owner-1")
        page_callback = next(
            item["callback"] for item in filtered["keyboard"]["buttons"]
            if item["callback"].startswith("pov:p:")
        )
        second_page = handler.handle(page_callback, user_id="owner-1")
    finally:
        reset_current_tenant_user_id(tenant)

    assert filtered["error"] is False
    assert query.calls == 1
    assert "2 из 2" in second_page["message"]
    assert [row for row in second_page["message"].splitlines() if "offer-" in row][0].startswith("1.")
    assert len(filtered["message"].encode("utf-16-le")) // 2 <= 4096
    assert all(
        len(item["callback"].encode("utf-8")) <= 64
        for item in filtered["keyboard"]["buttons"]
    )


def test_refresh_invalidates_prior_card_callback_without_opening_another_product():
    handler, _overview, query, _keyboard = _handler()
    tenant = _tenant()
    try:
        first = handler.handle("product_overview", user_id="owner-1")
        stale_row = next(
            item["callback"] for item in first["keyboard"]["buttons"]
            if item["callback"].startswith("pov:d:")
        )
        refresh = next(
            item["callback"] for item in first["keyboard"]["buttons"]
            if item["callback"].startswith("pov:r:")
        )
        handler.handle(refresh, user_id="owner-1")
        response = handler.handle(stale_row, user_id="owner-1")
    finally:
        reset_current_tenant_user_id(tenant)

    assert query.calls == 2
    assert response["code"] == "PRODUCT_OVERVIEW_VIEW_STALE"
    assert "Товар из обзора" not in response["message"]


def test_replacing_an_active_price_plan_requires_current_explicit_confirmation():
    runtime = _PriceRuntime(active={
        "scenario_id": "scenario-old",
        "version": 3,
        "tenant_scope": "owner-1::ozon::store-1",
    })
    handler, _overview, _query, _keyboard = _handler(runtime)
    tenant = _tenant()
    try:
        overview = handler.handle("product_overview", user_id="owner-1")
        detail_callback = next(
            item["callback"] for item in overview["keyboard"]["buttons"]
            if item["callback"].startswith("pov:d:")
        )
        detail = handler.handle(detail_callback, user_id="owner-1")
        plan_callback = next(
            item["callback"] for item in detail["keyboard"]["buttons"]
            if item["callback"].startswith("pov:u:")
        )
        prompt = handler.handle(plan_callback, user_id="owner-1")
        confirmation = prompt["keyboard"]["buttons"][0]["callback"]
        runtime.active = {
            "scenario_id": "scenario-newer",
            "version": 1,
            "tenant_scope": "owner-1::ozon::store-1",
        }
        stale = handler.handle(confirmation, user_id="owner-1")
    finally:
        reset_current_tenant_user_id(tenant)

    assert "Подтвердите переход" in prompt["message"]
    assert runtime.products == [("owner-1", "sku-1")]
    assert runtime.callbacks == []
    assert "изменился" in stale["message"]


def test_confirmed_price_plan_transition_opens_the_selected_product():
    active = {
        "scenario_id": "scenario-old",
        "version": 3,
        "tenant_scope": "owner-1::ozon::store-1",
    }
    runtime = _PriceRuntime(active=active)
    handler, _overview, _query, _keyboard = _handler(runtime)
    tenant = _tenant()
    try:
        overview = handler.handle("product_overview", user_id="owner-1")
        detail_callback = next(
            item["callback"] for item in overview["keyboard"]["buttons"]
            if item["callback"].startswith("pov:d:")
        )
        detail = handler.handle(detail_callback, user_id="owner-1")
        plan_callback = next(
            item["callback"] for item in detail["keyboard"]["buttons"]
            if item["callback"].startswith("pov:u:")
        )
        prompt = handler.handle(plan_callback, user_id="owner-1")
        confirmation = prompt["keyboard"]["buttons"][0]["callback"]
        result = handler.handle(confirmation, user_id="owner-1")
    finally:
        reset_current_tenant_user_id(tenant)

    assert result["message"] == "price scenario"
    assert runtime.callbacks == [("upc:p:selection1", "owner-1")]


def test_export_button_uses_exact_snapshot_and_does_not_query_catalog_again():
    handler, _overview, query, _keyboard = _handler(
        analytics_export_service=AnalyticsExportService()
    )
    tenant = _tenant()
    try:
        query.rows = [
            _decision_row(selector=f"offer-{index}", sku=f"sku-{index}")
            for index in range(7)
        ]
        overview = handler.handle("product_overview", user_id="owner-1")
        calls_after_snapshot = query.calls
        export_callback = next(
            item["callback"] for item in overview["keyboard"]["buttons"]
            if item["callback"].startswith("pov:export:") and item["callback"].endswith(":json")
        )
        document = handler.handle(export_callback, user_id="owner-1")
    finally:
        reset_current_tenant_user_id(tenant)

    assert document["error"] is False
    assert document["document_kind"] == "analytics_export"
    assert document["row_count"] == 7
    assert query.calls == calls_after_snapshot == 1
    assert document["read_only"] is True and document["executed"] is False
