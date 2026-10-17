from threading import Event, Thread

from services.assistant_button_handler_service import AssistantButtonHandlerService
from services.assistant_keyboard_service import AssistantKeyboardService
from services.telegram_unit_price_batch_plan_runtime_service import (
    TelegramUnitPriceBatchPlanRuntimeService,
)
from services.tax_service import TaxService
from services.tenant_context import (
    reset_current_tenant_user_id,
    set_current_tenant_user_id,
)
from services.telegram_unit_price_calculator_runtime_service import (
    TelegramUnitPriceCalculatorRuntimeService,
)
from services.unit_price_scenario_service import UnitPriceScenarioService


class _Overview:
    def __init__(self, items):
        self.items = items

    def get_price_plan_selection(self):
        return {"error": False, "items": self.items, "selected_count": len(self.items)}


class _Keyboard:
    def build_unit_price_batch_keyboard(self, buttons):
        return {"error": False, "type": "inline_keyboard", "buttons": buttons}

    def build_main_keyboard(self):
        return {"error": False, "type": "inline_keyboard", "buttons": []}


def _row(index, status="READY"):
    return {
        "row_id": f"row-{index}",
        "scheme": "FBO",
        "identity": {
            "offer_id": f"offer-{index}",
            "catalog_sku": f"sku-{index}",
        },
        "status": status,
        "inputs": {"price": "500", "cost": "100", "advertising_rate": "0"},
        "provenance": {"advertising_rate": "source"},
        "source_age_seconds_at_load": 1,
        "source_ttl_seconds": 600,
        "source_loaded_at": 100,
        "source_as_of": {"seller_price_as_of": "2026-10-17"},
        "snapshot": {
            "identity": {"catalog_sku": f"sku-{index}"},
            "product": {"scheme": "FBO"},
        },
        "scenario": {"calculated": {"profit": 100, "margin_percent": 20}},
        "planning": {
            "break_even": {"status": "FOUND", "price": "300"},
            "target": {"status": "FOUND", "price": "600", "profit": "120", "margin_percent": "20"},
        },
    }


class _BatchService:
    class _Planner:
        @staticmethod
        def parse_target_margin(value):
            try:
                number = float(str(value).replace(",", ".").replace("%", "").strip())
            except ValueError:
                return {"error": True}
            if not 0 <= number <= 100:
                return {"error": True}
            return {"error": False, "normalized": str(number)}

    target_planning_service = _Planner()

    def __init__(self, count=2, build_started=None, continue_build=None):
        self.calls = []
        self.count = count
        self.build_started = build_started
        self.continue_build = continue_build

    def build(self, items, user_id, target_margin_percent):
        self.calls.append(("build", user_id, target_margin_percent))
        if self.build_started:
            self.build_started.set()
        if self.continue_build:
            self.continue_build.wait(2)
        return {
            "error": False,
            "batch_id": "batch-1",
            "version": 1,
            "owner_id": user_id,
            "tenant_scope": "user-1::ozon::store-a",
            "target_margin_percent": str(target_margin_percent),
            "rows_selected": len(items),
            "rows": [_row(index) for index in range(len(items))],
        }

    def edit_row_assumption(self, batch, row_id, field, value):
        self.calls.append(("edit", row_id, field, value))
        updated = {**batch, "version": batch["version"] + 1}
        updated["rows"] = [dict(row) for row in batch["rows"]]
        updated["rows"][0]["inputs"] = {**updated["rows"][0]["inputs"], field: value}
        return updated

    def set_target_margin(self, batch, value):
        self.calls.append(("target", value))
        return {**batch, "version": batch["version"] + 1, "target_margin_percent": value}

    def preview_advertising_rate(self, batch, row_ids, value):
        self.calls.append(("ad_preview", list(row_ids), value))
        return {"rows": [{"row_id": row_ids[0], "identity": batch["rows"][0]["identity"], "previous_value": "0", "new_value": value}]}

    def apply_advertising_rate(self, batch, row_ids, rate, **kwargs):
        self.calls.append(("ad_apply", list(row_ids), rate, kwargs))
        return {**batch, "version": batch["version"] + 1}

    def refresh(self, batch):
        self.calls.append(("refresh", batch["version"]))
        return {**batch, "version": batch["version"] + 1}


class _SingleOpener:
    def __init__(self):
        self.calls = []

    def open_batch_candidate(self, batch, row_id, user_id=None, expected_batch_version=None):
        self.calls.append((batch["batch_id"], row_id, user_id, expected_batch_version))
        return {"error": False, "status": "HANDOFF_OPENED", "read_only": True, "executed": False}


def _runtime(service=None, overview=None, clock=lambda: 100):
    return TelegramUnitPriceBatchPlanRuntimeService(
        batch_plan_service=service or _BatchService(),
        product_overview_service=overview or _Overview([{"identity": {"offer_id": "offer-0"}}, {"identity": {"offer_id": "offer-1"}}]),
        keyboard_service=_Keyboard(),
        clock=clock,
        tenant_scope_provider=lambda: "user-1::ozon::store-a",
    )


def _button(result, label):
    matches = [item for item in result["keyboard"]["buttons"] if item["text"] == label]
    if not matches:
        raise AssertionError(
            f"Button {label!r} not found; available: "
            f"{[item['text'] for item in result['keyboard']['buttons']]!r}; "
            f"row status: {(result.get('batch_plan') or {}).get('rows', [{}])[0].get('status')}"
        )
    return matches[0]["callback"]


def test_batch_prompt_and_render_are_bounded_and_read_only():
    runtime = _runtime()
    token = set_current_tenant_user_id("user-1::ozon::store-a")
    try:
        prompt = runtime.begin_from_overview_selection("user-1")
        result = runtime.handle_text("20", user_id="user-1")
    finally:
        reset_current_tenant_user_id(token)

    assert prompt["status"] == "UNIT_PRICE_BATCH_TARGET_INPUT_REQUIRED"
    assert result["status"] == "UNIT_PRICE_BATCH_PLAN_READY"
    assert result["read_only"] is True and result["executed"] is False
    assert len(result["message"].encode("utf-16-le")) // 2 <= runtime.TEXT_LIMIT_UTF16
    assert all(len(button["callback"].encode("utf-8")) <= 64 for button in result["keyboard"]["buttons"])


def test_local_edit_zero_sort_and_pages_make_no_source_requests_and_invalidate_old_actions():
    service = _BatchService()
    runtime = _runtime(service)
    token = set_current_tenant_user_id("user-1::ozon::store-a")
    try:
        runtime.begin_from_overview_selection("user-1")
        result = runtime.handle_text("20", user_id="user-1")
        old_sort = _button(result, "Сортировать по прибыли/шт.")
        edit_menu = runtime.handle_callback(_button(result, "Изменить · offer-0"), "user-1")
        field_menu = runtime.handle_callback(_button(edit_menu, "Реклама %"), "user-1")
        edited = runtime.handle_text("0", user_id="user-1")
        stale = runtime.handle_callback(old_sort, "user-1")
        sorted_result = runtime.handle_callback(_button(edited, "Сортировать по прибыли/шт."), "user-1")
    finally:
        reset_current_tenant_user_id(token)

    assert field_menu["status"] == "UNIT_PRICE_BATCH_INPUT_REQUIRED"
    assert service.calls[-1] == ("edit", "row-0", "advertising_rate", "0")
    assert stale["status"] == "UNIT_PRICE_BATCH_ACTION_STALE"
    assert sorted_result["status"] == "UNIT_PRICE_BATCH_PLAN_READY"
    assert [call[0] for call in service.calls] == ["build", "edit"]


def test_advertising_requires_explicit_preview_confirmation():
    service = _BatchService()
    runtime = _runtime(service)
    token = set_current_tenant_user_id("user-1::ozon::store-a")
    try:
        runtime.begin_from_overview_selection("user-1")
        result = runtime.handle_text("20", user_id="user-1")
        prompt = runtime.handle_callback(_button(result, "Реклама для выбранных строк"), "user-1")
        preview = runtime.handle_text("12.5", user_id="user-1")
        assert prompt["status"] == "UNIT_PRICE_BATCH_INPUT_REQUIRED"
        assert preview["status"] == "UNIT_PRICE_BATCH_ADVERTISING_CONFIRMATION_REQUIRED"
        assert [call[0] for call in service.calls] == ["build", "ad_preview"]
        confirmed = runtime.handle_callback(_button(preview, "Подтвердить"), "user-1")
    finally:
        reset_current_tenant_user_id(token)

    assert confirmed["status"] == "UNIT_PRICE_BATCH_PLAN_READY"
    assert [call[0] for call in service.calls] == ["build", "ad_preview", "ad_apply"]


def test_cancelled_advertising_preview_revokes_confirmation_token():
    service = _BatchService()
    runtime = _runtime(service)
    token = set_current_tenant_user_id("user-1::ozon::store-a")
    try:
        runtime.begin_from_overview_selection("user-1")
        result = runtime.handle_text("20", user_id="user-1")
        runtime.handle_callback(_button(result, "Реклама для выбранных строк"), "user-1")
        preview = runtime.handle_text("12.5", user_id="user-1")
        confirm_callback = _button(preview, "Подтвердить")
        cancelled = runtime.handle_callback(_button(preview, "Отмена"), "user-1")
        replay = runtime.handle_callback(confirm_callback, "user-1")
    finally:
        reset_current_tenant_user_id(token)

    assert cancelled["status"] == "UNIT_PRICE_BATCH_ADVERTISING_CANCELLED"
    assert replay["status"] == "UNIT_PRICE_BATCH_ACTION_STALE"
    assert [call[0] for call in service.calls] == ["build", "ad_preview"]


def test_callback_is_bound_to_owner_store_and_expires():
    now = [100]
    runtime = _runtime(clock=lambda: now[0])
    token = set_current_tenant_user_id("user-1::ozon::store-a")
    try:
        runtime.begin_from_overview_selection("user-1")
        result = runtime.handle_text("20", user_id="user-1")
        callback = _button(result, "Изменить цель")
        foreign = runtime.handle_callback(callback, "user-2")
        now[0] += runtime.PENDING_TTL_SECONDS + 1
        expired = runtime.handle_callback(callback, "user-1")
    finally:
        reset_current_tenant_user_id(token)

    assert foreign["status"] == "UNIT_PRICE_BATCH_CONTEXT_UNAVAILABLE"
    assert expired["status"] == "UNIT_PRICE_BATCH_ACTION_STALE"


def test_late_build_result_is_discarded_after_store_switch():
    started, proceed = Event(), Event()
    service = _BatchService(build_started=started, continue_build=proceed)
    runtime = TelegramUnitPriceBatchPlanRuntimeService(
        service, _Overview([{"identity": {"offer_id": "0"}}, {"identity": {"offer_id": "1"}}]),
        _Keyboard(), tenant_scope_provider=lambda: current_scope[0],
    )
    current_scope = ["user-1::ozon::store-a"]
    token = set_current_tenant_user_id("user-1::ozon::store-a")
    try:
        runtime.begin_from_overview_selection("user-1")
        output = []
        worker = Thread(target=lambda: output.append(runtime.handle_text("20", user_id="user-1")))
        worker.start()
        assert started.wait(1)
        current_scope[0] = "user-1::ozon::store-b"
        proceed.set()
        worker.join(2)
    finally:
        reset_current_tenant_user_id(token)

    assert output[0]["status"] == "UNIT_PRICE_BATCH_RESULT_STALE"


def test_assistant_handler_routes_batch_callback_and_overview_entry():
    overview = _Overview([{"identity": {"offer_id": "one"}}, {"identity": {"offer_id": "two"}}])
    runtime = _runtime(overview=overview)
    handler = AssistantButtonHandlerService(
        assistant=None,
        keyboard_service=_Keyboard(),
        product_overview_service=overview,
        unit_price_batch_plan_runtime_service=runtime,
    )
    token = set_current_tenant_user_id("user-1::ozon::store-a")
    try:
        prompt = handler.handle("pov:bp", user_id="user-1")
        result = handler.handle_text("20", user_id="user-1")
        changed = handler.handle(_button(result, "Изменить цель"), user_id="user-1")
    finally:
        reset_current_tenant_user_id(token)

    assert prompt["status"] == "UNIT_PRICE_BATCH_TARGET_INPUT_REQUIRED"
    assert result["status"] == "UNIT_PRICE_BATCH_PLAN_READY"
    assert changed["status"] == "UNIT_PRICE_BATCH_INPUT_REQUIRED"


def test_batch_screen_keeps_own_text_routing_until_user_leaves_the_flow():
    overview = _Overview([{"identity": {"offer_id": "one"}}, {"identity": {"offer_id": "two"}}])
    runtime = _runtime(overview=overview)

    class _SingleRuntime:
        def handle_text(self, text, user_id=None):
            return {"status": "SINGLE_RUNTIME_RECEIVED_TEXT"}

        def clear_pending(self, user_id):
            return None

    handler = AssistantButtonHandlerService(
        assistant=None,
        keyboard_service=_Keyboard(),
        product_overview_service=overview,
        unit_price_batch_plan_runtime_service=runtime,
        unit_price_calculator_runtime_service=_SingleRuntime(),
    )
    token = set_current_tenant_user_id("user-1::ozon::store-a")
    try:
        handler.handle("pov:bp", user_id="user-1")
        result = handler.handle_text("20", user_id="user-1")
        stray_text = handler.handle_text("не команда", user_id="user-1")
        handler.handle("main_menu", user_id="user-1")
        after_exit = handler.handle_text("other", user_id="user-1")
    finally:
        reset_current_tenant_user_id(token)

    assert result["status"] == "UNIT_PRICE_BATCH_PLAN_READY"
    assert stray_text["status"] == "UNIT_PRICE_BATCH_PLAN_READY"
    assert after_exit["status"] == "SINGLE_RUNTIME_RECEIVED_TEXT"


def test_ready_row_handoff_button_uses_public_single_runtime_contract():
    opener = _SingleOpener()
    service = _BatchService()
    runtime = TelegramUnitPriceBatchPlanRuntimeService(
        batch_plan_service=service,
        product_overview_service=_Overview([{"identity": {"offer_id": "0"}}, {"identity": {"offer_id": "1"}}]),
        keyboard_service=_Keyboard(),
        single_price_runtime_service=opener,
        clock=lambda: 100,
        tenant_scope_provider=lambda: "user-1::ozon::store-a",
    )
    token = set_current_tenant_user_id("user-1::ozon::store-a")
    try:
        runtime.begin_from_overview_selection("user-1")
        result = runtime.handle_text("20", user_id="user-1")
        opened = runtime.handle_callback(_button(result, "Открыть план · offer-0"), "user-1")
    finally:
        reset_current_tenant_user_id(token)

    assert opened["status"] == "HANDOFF_OPENED"
    assert opener.calls == [("batch-1", "row-0", "user-1", 1)]


def test_public_single_runtime_handoff_rechecks_candidate_and_uses_no_source_io():
    class _Source:
        def __init__(self):
            self.calls = []

        def load_snapshot(self, *args, **kwargs):
            self.calls.append((args, kwargs))
            raise AssertionError("handoff must not reload sources")

    scenario = UnitPriceScenarioService(TaxService())
    source = _Source()
    single = TelegramUnitPriceCalculatorRuntimeService(
        source=source,
        scenario_service=scenario,
        keyboard_service=AssistantKeyboardService(),
        target_planning_service=None,
        clock=lambda: 100,
    )
    identity = {
        "product_id": "product-1",
        "offer_id": "offer-1",
        "catalog_sku": "sku-1",
    }
    snapshot = {
        "identity": {
            "user_id": "user-1",
            "store_id": "store-a",
            "tenant_scope": "user-1::ozon::store-a",
            "product_id": "product-1",
            "offer_id": "offer-1",
            "sku": "sku-1",
        },
        "product": {"scheme": "FBO", "name": "Item"},
        "suggested_inputs": {
            "price": "500", "cost": "120", "commission_rate": "15",
            "advertising_rate": "10", "discount_points_rate": "20",
            "logistics_per_unit": "40", "last_mile_per_unit": "10",
            "acquiring_per_unit": "5", "tax_mode": "USN_INCOME",
            "tax_rate": "6", "minimum_tax_rate": "1",
        },
        "input_provenance": {"cost": "confirmed_store_cost"},
        "source_periods": {"seller_price_as_of": "2026-10-17T00:00:00Z"},
        "source_completeness": {"discount_points": {"complete": True}},
        "cache": {"age_seconds": 1, "ttl_seconds": 600},
    }
    candidate_inputs = {**snapshot["suggested_inputs"], "price": "600"}
    sources = {"periods": snapshot["source_periods"], "completeness": snapshot["source_completeness"]}
    forwarded = scenario.calculate(candidate_inputs, identity={}, provenance={}, sources=sources)
    profit = forwarded["calculated"]["profit"]
    batch = {
        "kind": "UNIT_PRICE_BATCH_PLAN", "batch_id": "batch-1", "version": 3,
        "owner_id": "user-1", "tenant_scope": "user-1::ozon::store-a",
        "target_margin_percent": "0", "read_only": True, "executed": False,
        "rows": [{
            "row_id": "stable-row-1", "identity": identity, "scheme": "FBO",
            "status": "READY", "snapshot": snapshot,
            "inputs": snapshot["suggested_inputs"], "provenance": snapshot["input_provenance"],
            "source_age_seconds_at_load": 1, "source_loaded_at": 100,
            "source_ttl_seconds": 600,
            "planning": {"target": {
                "status": "FOUND", "price": "600",
                "forward_result": {"available": True, "calculated": {"profit": profit}},
            }},
        }],
    }
    token = set_current_tenant_user_id("user-1::ozon::store-a")
    try:
        result = single.open_batch_candidate(
            batch, "stable-row-1", user_id="user-1", expected_batch_version=3
        )
        session_identity = single.active_scenario_identity("user-1")
        replay = single.open_batch_candidate(
            {**batch, "rows": [{**batch["rows"][0], "scheme": "FBS"}]},
            "stable-row-1", user_id="user-1", expected_batch_version=3,
        )
    finally:
        reset_current_tenant_user_id(token)

    assert result["status"] == "UNIT_PRICE_SCENARIO_READY"
    assert result["price_scenario"]["inputs"]["price"]["value"] == 600
    assert session_identity["tenant_scope"] == "user-1::ozon::store-a"
    assert replay["status"] == "UNIT_PRICE_SCENARIO_STALE"
    assert source.calls == []
