from copy import deepcopy

from services.assistant_keyboard_service import AssistantKeyboardService
from services.assistant_button_handler_service import AssistantButtonHandlerService
from services.tax_service import TaxService
from services.tenant_context import reset_current_tenant_user_id, set_current_tenant_user_id
from services.telegram_unit_price_calculator_runtime_service import TelegramUnitPriceCalculatorRuntimeService
from services.telegram_unit_price_batch_plan_runtime_service import TelegramUnitPriceBatchPlanRuntimeService
from services.telegram_unit_price_sensitivity_runtime_service import TelegramUnitPriceSensitivityRuntimeService
from services.unit_price_scenario_service import UnitPriceScenarioService
from services.unit_price_sensitivity_service import UnitPriceSensitivityService


class _Products:
    def load_products(self):
        return [{"product_id": "p1", "offer_id": "hook-2", "sku": "sku-1", "name": "Крючок"}]


class _Source:
    def __init__(self, clock):
        self.product_service = _Products()
        self.calls = 0
        self.clock = clock

    def load_snapshot(self, sku, user_id, force_refresh=False):
        self.calls += 1
        return {
            "error": False,
            "snapshot_id": "snapshot-1",
            "identity": {
                "user_id": user_id,
                "store_id": "store-a",
                "tenant_scope": f"{user_id}::ozon::store-a",
                "product_id": "p1",
                "offer_id": "hook-2",
                "sku": sku,
            },
            "product": {"name": "Крючок", "scheme": "FBO"},
            "suggested_inputs": {
                "price": "500", "cost": "200", "commission_rate": "15",
                "advertising_rate": "10", "discount_points_rate": "20",
                "logistics_per_unit": "40", "last_mile_per_unit": "10",
                "acquiring_per_unit": "5", "tax_mode": "USN_INCOME",
                "tax_rate": "6", "minimum_tax_rate": "1",
            },
            "input_provenance": {"price": "source", "cost": "confirmed_store_cost"},
            "source_periods": {"seller_price_as_of": "2026-10-17T00:00:00Z"},
            "source_completeness": {"scheme": "FBO", "commission": {"complete": True}},
            "cache": {"age_seconds": 1, "ttl_seconds": 600},
        }


def _find(result, text):
    return next(button["callback"] for button in result["keyboard"]["buttons"] if button["text"] == text)


def _runtime(clock=lambda: 100):
    keyboard = AssistantKeyboardService()
    source = _Source(clock)
    scenario = UnitPriceScenarioService(TaxService())
    single = TelegramUnitPriceCalculatorRuntimeService(
        source=source,
        scenario_service=scenario,
        keyboard_service=keyboard,
        clock=clock,
    )
    sensitivity = TelegramUnitPriceSensitivityRuntimeService(
        sensitivity_service=UnitPriceSensitivityService(scenario),
        single_price_runtime_service=single,
        batch_plan_runtime_service=None,
        keyboard_service=keyboard,
        clock=clock,
    )
    return single, sensitivity, source


def _start_single(single, user="user-1"):
    callback = single.build_product_entry_button(user, "sku-1")["callback"]
    result = single.handle_callback(callback, user_id=user)
    return single.handle_callback(_find(result, "Реклама 0%"), user_id=user)


def test_single_sensitivity_runs_locally_pages_and_applies_only_explicit_fresh_cell():
    single, sensitivity, source = _runtime()
    tenant = set_current_tenant_user_id("user-1::ozon::store-a")
    try:
        scenario = _start_single(single)
        before = deepcopy(scenario["price_scenario"]["inputs"])
        active = single.active_scenario_identity("user-1")
        prompt = sensitivity.begin_from_single(
            active["scenario_id"], active["version"],
            user_id="user-1",
        )
        choose = _find(prompt, "Ось · Цена продавца")
        values = sensitivity.handle_callback(choose, user_id="user-1")
        report = sensitivity.handle_text("500;550;600", user_id="user-1")
        applied = sensitivity.handle_callback(
            _find(report, "Перенести сценарий 2"), user_id="user-1"
        )
    finally:
        reset_current_tenant_user_id(tenant)

    assert prompt["status"] == "UNIT_PRICE_SENSITIVITY_AXIS_REQUIRED"
    assert values["status"] == "UNIT_PRICE_SENSITIVITY_VALUES_REQUIRED"
    assert report["status"] == "UNIT_PRICE_SENSITIVITY_READY"
    assert report["sensitivity_result"]["cell_count"] == 3
    assert "среди проверенных" in report["message"]
    assert applied["status"] == "UNIT_PRICE_SCENARIO_READY"
    assert applied["price_scenario"]["inputs"]["price"]["value"] == 550
    assert before["price"]["value"] == 500
    assert source.calls == 1


def test_single_result_keyboard_routes_into_sensitivity_through_button_handler():
    single, sensitivity, _source = _runtime()
    handler = AssistantButtonHandlerService(
        assistant=None,
        keyboard_service=AssistantKeyboardService(),
        unit_price_calculator_runtime_service=single,
        unit_price_sensitivity_runtime_service=sensitivity,
    )
    tenant = set_current_tenant_user_id("user-1::ozon::store-a")
    try:
        scenario = _start_single(single)
        callback = _find(scenario, "Чувствительность")
        result = handler.handle(callback, user_id="user-1")
    finally:
        reset_current_tenant_user_id(tenant)

    assert callback.startswith("ups:s:")
    assert result["status"] == "UNIT_PRICE_SENSITIVITY_AXIS_REQUIRED"


def test_return_from_axis_prompt_clears_text_ownership():
    single, sensitivity, _source = _runtime()
    tenant = set_current_tenant_user_id("user-1::ozon::store-a")
    try:
        _start_single(single)
        active = single.active_scenario_identity("user-1")
        prompt = sensitivity.begin_from_single(active["scenario_id"], active["version"], user_id="user-1")
        returned = sensitivity.handle_callback(_find(prompt, "Назад к плану"), user_id="user-1")
        unhandled_text = sensitivity.handle_text("550;600;650", user_id="user-1")
    finally:
        reset_current_tenant_user_id(tenant)

    assert returned["status"] == "UNIT_PRICE_SCENARIO_READY"
    assert unhandled_text is None


def test_stale_source_remains_viewable_but_has_no_apply_action():
    now = [100]
    single, sensitivity, _source = _runtime(clock=lambda: now[0])
    tenant = set_current_tenant_user_id("user-1::ozon::store-a")
    try:
        scenario = _start_single(single)
        active = single.active_scenario_identity("user-1")
        prompt = sensitivity.begin_from_single(
            active["scenario_id"], active["version"],
            user_id="user-1",
        )
        values = sensitivity.handle_callback(_find(prompt, "Ось · Цена продавца"), user_id="user-1")
        report = sensitivity.handle_text("500;550;600", user_id="user-1")
        now[0] = 701
        refreshed = sensitivity.handle_callback(_find(report, "Следующая"), user_id="user-1") if any(
            item["text"] == "Следующая" for item in report["keyboard"]["buttons"]
        ) else sensitivity.handle_text("ignored", user_id="user-1")
    finally:
        reset_current_tenant_user_id(tenant)

    assert values["status"] == "UNIT_PRICE_SENSITIVITY_VALUES_REQUIRED"
    assert refreshed["status"] == "UNIT_PRICE_SENSITIVITY_READY"
    assert "устарел" in refreshed["message"]
    assert not any(item["text"].startswith("Перенести сценарий") for item in refreshed["keyboard"]["buttons"])


def test_two_axis_maximum_matrix_is_paginated_without_dropping_cells():
    single, sensitivity, _source = _runtime()
    tenant = set_current_tenant_user_id("user-1::ozon::store-a")
    values = "100;200;300;400;500;600;700"
    try:
        scenario = _start_single(single)
        active = single.active_scenario_identity("user-1")
        prompt = sensitivity.begin_from_single(
            active["scenario_id"], active["version"], user_id="user-1"
        )
        pair = sensitivity.handle_callback(
            _find(prompt, "Матрица · Цена продавца × Себестоимость"),
            user_id="user-1",
        )
        second_axis = sensitivity.handle_text(values, user_id="user-1")
        page_one = sensitivity.handle_text(values, user_id="user-1")
        page_two = sensitivity.handle_callback(
            _find(page_one, "Следующая"), user_id="user-1"
        )
    finally:
        reset_current_tenant_user_id(tenant)

    assert pair["status"] == "UNIT_PRICE_SENSITIVITY_VALUES_REQUIRED"
    assert second_axis["status"] == "UNIT_PRICE_SENSITIVITY_VALUES_REQUIRED"
    assert page_one["status"] == "UNIT_PRICE_SENSITIVITY_READY"
    assert page_one["sensitivity_result"]["cell_count"] == 49
    assert page_one["sensitivity_result"]["available_cell_count"] == 49
    assert len(page_one["sensitivity_result"]["cells"]) == 49
    assert "Страница 1 из 7" in page_one["message"]
    assert "Страница 2 из 7" in page_two["message"]
    assert len(page_one["message"].encode("utf-16-le")) // 2 <= sensitivity.TEXT_LIMIT_UTF16
    assert all(len(button["callback"].encode("utf-8")) <= 64 for button in page_one["keyboard"]["buttons"])


def test_foreign_store_cannot_open_or_apply_a_sensitivity_action():
    single, sensitivity, _source = _runtime()
    tenant = set_current_tenant_user_id("user-1::ozon::store-a")
    try:
        scenario = _start_single(single)
        active = single.active_scenario_identity("user-1")
        prompt = sensitivity.begin_from_single(
            active["scenario_id"], active["version"],
            user_id="user-1",
        )
        callback = _find(prompt, "Ось · Цена продавца")
    finally:
        reset_current_tenant_user_id(tenant)
    foreign = set_current_tenant_user_id("user-1::ozon::store-b")
    try:
        result = sensitivity.handle_callback(callback, user_id="user-1")
    finally:
        reset_current_tenant_user_id(foreign)
    assert result["status"] == "UNIT_PRICE_SENSITIVITY_ACTION_STALE"


def test_batch_sensitivity_revalidates_then_opens_cell_without_network_access():
    class _Overview:
        def get_price_plan_selection(self):
            return {"error": False, "items": [{"identity": {"sku": "sku-0"}}, {"identity": {"sku": "sku-1"}}]}

    class _Planner:
        @staticmethod
        def parse_target_margin(value):
            return {"error": False, "normalized": str(value)}

    class _BatchPlan:
        target_planning_service = _Planner()

        def build(self, items, user_id, target_margin_percent):
            rows = []
            for index in range(2):
                sku = f"sku-{index}"
                identity = {
                    "user_id": user_id,
                    "store_id": "store-a",
                    "tenant_scope": "user-1::ozon::store-a",
                    "product_id": f"product-{index}",
                    "offer_id": f"offer-{index}",
                    "sku": sku,
                }
                inputs = {
                    "price": "500", "cost": "100", "commission_rate": "15",
                    "advertising_rate": "0", "discount_points_rate": "20",
                    "logistics_per_unit": "40", "last_mile_per_unit": "10",
                    "acquiring_per_unit": "5", "tax_mode": "USN_INCOME",
                    "tax_rate": "6", "minimum_tax_rate": "1",
                }
                snapshot = {
                    "identity": identity,
                    "product": {"name": "Товар", "scheme": "FBO"},
                    "suggested_inputs": inputs,
                    "input_provenance": {"cost": "confirmed_store_cost"},
                    "source_periods": {"seller_price_as_of": "2026-10-17"},
                    "source_completeness": {"scheme": "FBO", "commission": {"complete": True}},
                }
                rows.append({
                    "row_id": f"row-{index}", "scheme": "FBO", "identity": {
                        "product_id": identity["product_id"],
                        "offer_id": identity["offer_id"],
                        "catalog_sku": sku,
                    },
                    "status": "READY", "snapshot": snapshot,
                    "inputs": inputs, "provenance": {"cost": "confirmed_store_cost"},
                    "source_age_seconds_at_load": 1, "source_ttl_seconds": 600,
                    "source_loaded_at": 100, "source_as_of": snapshot["source_periods"],
                    "scenario": {"calculated": {"profit": 100, "margin_percent": 20}},
                    "planning": {},
                })
            return {
                "error": False, "batch_id": "batch-x", "version": 1,
                "owner_id": user_id, "tenant_scope": "user-1::ozon::store-a",
                "target_margin_percent": target_margin_percent,
                "rows_selected": 2, "rows": rows,
            }

    keyboard = AssistantKeyboardService()
    single, _unused_sensitivity, source = _runtime()
    batch_runtime = TelegramUnitPriceBatchPlanRuntimeService(
        batch_plan_service=_BatchPlan(),
        product_overview_service=_Overview(),
        keyboard_service=keyboard,
        single_price_runtime_service=single,
        clock=lambda: 100,
        tenant_scope_provider=lambda: "user-1::ozon::store-a",
    )
    sensitivity = TelegramUnitPriceSensitivityRuntimeService(
        sensitivity_service=UnitPriceSensitivityService(single.scenario_service),
        single_price_runtime_service=single,
        batch_plan_runtime_service=batch_runtime,
        keyboard_service=keyboard,
        clock=lambda: 100,
    )
    batch_runtime.sensitivity_runtime_service = sensitivity
    tenant = set_current_tenant_user_id("user-1::ozon::store-a")
    try:
        batch_runtime.begin_from_overview_selection("user-1")
        batch = batch_runtime.handle_text("20", user_id="user-1")
        batch_action = next(
            item["callback"] for item in batch["keyboard"]["buttons"]
            if item["text"].startswith("Чувствительность")
        )
        prompt = batch_runtime.handle_callback(batch_action, user_id="user-1")
        values = sensitivity.handle_callback(_find(prompt, "Ось · Цена продавца"), user_id="user-1")
        report = sensitivity.handle_text("500;550;600", user_id="user-1")
        applied = sensitivity.handle_callback(_find(report, "Перенести сценарий 2"), user_id="user-1")
    finally:
        reset_current_tenant_user_id(tenant)

    assert prompt["status"] == "UNIT_PRICE_SENSITIVITY_AXIS_REQUIRED"
    assert values["status"] == "UNIT_PRICE_SENSITIVITY_VALUES_REQUIRED"
    assert report["status"] == "UNIT_PRICE_SENSITIVITY_READY"
    assert applied["status"] == "UNIT_PRICE_SCENARIO_READY"
    assert applied["price_scenario"]["inputs"]["price"]["value"] == 550
    assert applied["price_scenario"]["identity"]["sku"] == "sku-0"
    assert source.calls == 0
