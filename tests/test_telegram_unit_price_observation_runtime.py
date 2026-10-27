from copy import deepcopy
from datetime import datetime, timezone

import pytest

from services.assistant_keyboard_service import AssistantKeyboardService
from services.assistant_button_handler_service import AssistantButtonHandlerService
from services.planning_workspace_repository import PlanningWorkspaceRepository
from services.saved_planning_plan_service import SavedPlanningPlanService
from services.tax_service import TaxService
from services.tenant_context import reset_current_tenant_user_id, set_current_tenant_user_id
from services.telegram_unit_price_observation_runtime_service import TelegramUnitPriceObservationRuntimeService
from services.telegram_saved_planning_plan_runtime_service import TelegramSavedPlanningPlanRuntimeService
from services.unit_price_observation_result_service import UnitPriceObservationResultService
from services.unit_price_scenario_service import UnitPriceScenarioService
from services.unit_price_target_planning_service import UnitPriceTargetPlanningService
from services.ozon_account_repository import make_store_tenant_scope


NOW = datetime(2026, 10, 27, 10, 0, tzinfo=timezone.utc)


def _plan_payload(store_id="store-a", sku="sku-1", scheme="FBO"):
    return {
        "plan_kind": "single", "schema_version": 1, "calculation_version": 1,
        "target_margin_percent": "25.00",
        "items": [{
            "identity": {
                "product_id": "product-1", "offer_id": "offer-1", "sku": sku,
                "product_name": "Synthetic product", "store_id": store_id, "scheme": scheme,
            },
            "inputs": {
                "price": "500.00", "cost": "100.00", "commission_rate": "15",
                "advertising_rate": "8", "discount_points_rate": "20",
                "logistics_per_unit": "40", "last_mile_per_unit": "10",
                "acquiring_per_unit": "5", "tax_mode": "USN_INCOME",
                "tax_rate": "6", "minimum_tax_rate": "1",
            },
            "provenance": {"price": "manual_seller_scenario", "cost": "manual"},
            "sources": {"periods": {}, "as_of": None, "loaded_at": None,
                        "completeness": {"catalog_identity": {"complete": True}}},
            "projection": {"available": True, "missing_inputs": [],
                           "invalid_inputs": [], "revenue": "500.00", "profit": "100.00"},
        }],
    }


class _Collector:
    def __init__(self):
        self.calls = []

    def collect_window(self, observation_id, *, date_from, date_to):
        self.calls.append((observation_id, date_from, date_to))
        return {
            "error": False, "status": "INSUFFICIENT_DATA",
            "identity": {
                "store_id": "store-a", "product_id": "product-1",
                "offer_id": "offer-1", "sku": "sku-1", "sale_schema": "FBO",
            },
            "seller_price_cents": 12_300,
            "window": {"from": date_from, "to": date_to,
                       "timezone": "Europe/Moscow", "date_basis": "SOURCE_CALENDAR_DATE"},
            "sources": [
                {"name": "FINANCE", "status": "COMPLETE", "complete": True,
                 "row_count": 7, "source_date_basis": "OZON_ACCRUAL_DATE",
                 "source_window_start": date_from, "source_window_end": date_to,
                 "timezone": "Europe/Moscow"},
                {"name": "PERFORMANCE", "status": "COMPLETE", "complete": True,
                 "row_count": 4, "source_date_basis": "PERFORMANCE_REPORT_DATE",
                 "source_window_start": date_from, "source_window_end": date_to,
                 "timezone": "Europe/Moscow"},
            ],
            "metrics": {
                "gross_seller_revenue": "1000.00", "discount_points": "100.00",
                "finance_net": "500.00", "acquiring": "-10.00",
                "commission": "-100.00", "logistics": "-200.00",
                "other_fees": "-190.00", "cpc_spend": "100.00",
                "source_row_count": 7, "sample_days": 7,
                "successful_sale_units": None, "ordered_units": None,
            },
            "warnings": [], "read_only": True, "executed": False,
        }


@pytest.fixture
def flow(tmp_path):
    token = set_current_tenant_user_id(make_store_tenant_scope("owner-1", "store-a"))
    repo = PlanningWorkspaceRepository(
        db_path=tmp_path / "planning.sqlite", clock=lambda: NOW,
    )
    saved = repo.save_document(
        title="Plan", payload=_plan_payload(), idempotency_key="q20-plan-key-001",
    )
    assert saved["error"] is False
    planning = SavedPlanningPlanService(repo)
    collector = _Collector()
    scenario = UnitPriceScenarioService(TaxService())
    runtime = TelegramUnitPriceObservationRuntimeService(
        repository=repo, planning_service=planning, collection_service=collector,
        result_service=UnitPriceObservationResultService(
            scenario, UnitPriceTargetPlanningService(scenario),
        ), keyboard_service=AssistantKeyboardService(), clock=lambda: NOW,
        monotonic_clock=lambda: 100.0,
    )
    scope = {"owner_id": "owner-1", "store_id": "store-a",
             "tenant_scope": make_store_tenant_scope("owner-1", "store-a")}
    document = planning.get_document(saved["document_id"], revision=1)["document"]
    try:
        yield repo, runtime, collector, scope, document, saved
    finally:
        reset_current_tenant_user_id(token)


def _create_observation(runtime, scope, document):
    callback = runtime.plan_start_callback(scope, document)
    assert callback and len(callback.encode("utf-8")) <= 64
    assert runtime.handle_callback(callback, user_id="owner-1")["status"] == "SELLER_PRICE_INPUT_REQUIRED"
    assert runtime.handle_text("123,00", user_id="owner-1")["status"] == "EFFECTIVE_TIME_INPUT_REQUIRED"
    preview = runtime.handle_text("2026-09-30T12:00:00+03:00", user_id="owner-1")
    assert preview["status"] == "OBSERVATION_START_PREVIEW"
    confirm = preview["keyboard"]["buttons"][0]["callback"]
    card = runtime.handle_callback(confirm, user_id="owner-1")
    assert card["status"] == "OBSERVATION_CARD_READY"
    return card


def test_saved_plan_start_records_owner_price_and_keeps_callback_id_short(flow):
    repo, runtime, _, scope, document, _ = flow
    card = _create_observation(runtime, scope, document)
    assert "123.00 ₽" in card["message"]
    assert "не API-история" in card["message"]
    assert "не меняет цену Ozon" in card["message"]
    listed = repo.list_unit_price_observations(owner_id="owner-1", store_id="store-a")
    observation = listed["items"][0]
    assert observation["seller_price_cents"] == 12_300
    assert observation["effective_from"] == "2026-09-30T12:00:00+03:00"
    assert observation["price_evidence_source"] == "USER"
    assert observation["source_plan"] == {"document_id": document["document_id"], "revision": 1}


def test_collection_persists_incomplete_result_and_can_reopen_after_runtime_restart(flow):
    repo, runtime, collector, scope, document, _ = flow
    card = _create_observation(runtime, scope, document)
    observation_id = repo.list_unit_price_observations(owner_id="owner-1", store_id="store-a")["items"][0]["observation_id"]
    collect_callback = next(
        item["callback"] for item in card["keyboard"]["buttons"]
        if item["text"] == "Собрать данные за период"
    )
    assert runtime.handle_callback(collect_callback, user_id="owner-1")["status"] == "OBSERVATION_WINDOW_INPUT_REQUIRED"
    result = runtime.handle_text("2026-10-01 - 2026-10-07", user_id="owner-1")
    assert result["status"] == "OBSERVATION_CARD_READY"
    assert collector.calls == [(observation_id, "2026-10-01", "2026-10-07")]
    saved = repo.get_unit_price_observation(observation_id, owner_id="owner-1", store_id="store-a")
    assert saved["observation"]["result_revision"] == 1
    assert saved["result"]["payload"]["status"] in {"INSUFFICIENT_DATA", "INCOMPARABLE"}
    assert saved["result"]["payload"]["metrics"].get("observed_profit_per_unit") is None
    stale = runtime.handle_callback(collect_callback, user_id="owner-1")
    assert stale["status"] == "OBSERVATION_ACTION_STALE"
    assert len(collector.calls) == 1

    reopened = TelegramUnitPriceObservationRuntimeService(
        repository=repo, planning_service=runtime.planning_service,
        collection_service=collector, result_service=runtime.result_service,
        keyboard_service=runtime.keyboard_service, clock=lambda: NOW,
        monotonic_clock=lambda: 101.0,
    )
    assert reopened.handle_callback(f"upo:o:{observation_id}", user_id="owner-1")["status"] == "OBSERVATION_CARD_READY"
    history = reopened.handle_callback(f"upo:history:{observation_id}", user_id="owner-1")
    assert history["status"] == "OBSERVATION_HISTORY_READY"
    assert "#1" in history["message"]
    detail = reopened.handle_callback(f"upo:result:{observation_id}:1", user_id="owner-1")
    assert detail["status"] == "OBSERVATION_RESULT_READY"
    assert "Прибыль с единицы не рассчитана" in detail["message"]
    assert "Проверка сопоставимости" in detail["message"]
    assert detail["quality_assessment"]["status"] == "NOT_READY"
    assert detail["quality_assessment"]["verified"] is False
    assert "raw_response" not in detail["message"]


def test_note_and_finish_are_scoped_versioned_actions(flow):
    repo, runtime, _, scope, document, _ = flow
    card = _create_observation(runtime, scope, document)
    observation_id = repo.list_unit_price_observations(owner_id="owner-1", store_id="store-a")["items"][0]["observation_id"]
    note_callback = next(item["callback"] for item in card["keyboard"]["buttons"] if item["text"] == "Изменить заметку")
    runtime.handle_callback(note_callback, user_id="owner-1")
    noted = runtime.handle_text("test note", user_id="owner-1")
    assert "Заметка: test note" in noted["message"]
    finish_callback = next(item["callback"] for item in noted["keyboard"]["buttons"] if item["text"] == "Завершить наблюдение")
    finished = runtime.handle_callback(finish_callback, user_id="owner-1")
    assert "завершено" in finished["message"]
    assert repo.get_unit_price_observation(observation_id, owner_id="owner-1", store_id="store-a")["observation"]["status"] == "FINISHED"
    assert all(button["text"] != "Собрать данные за период" for button in finished["keyboard"]["buttons"])


def test_plan_start_is_fbo_row_and_tenant_bound(flow):
    _, runtime, _, scope, document, _ = flow
    multi = deepcopy(document)
    multi["payload"]["items"].append(deepcopy(multi["payload"]["items"][0]))
    assert runtime.plan_start_callback(scope, multi, item_index=1) is not None
    assert runtime.plan_start_callback(scope, multi, item_index=2) is None
    fbs = deepcopy(document)
    fbs["payload"]["items"][0]["identity"]["scheme"] = "FBS"
    assert runtime.plan_start_callback(scope, fbs) is None
    callback = runtime.plan_start_callback(scope, document)
    other = set_current_tenant_user_id(make_store_tenant_scope("owner-1", "store-b"))
    try:
        result = runtime.handle_callback(callback, user_id="owner-1")
        assert result["status"] == "OBSERVATION_ACTION_STALE"
    finally:
        reset_current_tenant_user_id(other)


def test_price_timestamp_and_window_validation_are_explicit(flow):
    repo, runtime, collector, scope, document, _ = flow
    callback = runtime.plan_start_callback(scope, document)
    runtime.handle_callback(callback, user_id="owner-1")
    assert runtime.handle_text("0", user_id="owner-1")["status"] == "PRICE_INPUT_REQUIRED"
    assert runtime.handle_text("123,456", user_id="owner-1")["status"] == "PRICE_INPUT_REQUIRED"
    assert runtime.handle_text("123,00", user_id="owner-1")["status"] == "EFFECTIVE_TIME_INPUT_REQUIRED"
    assert runtime.handle_text("2026-09-30T12:00:00", user_id="owner-1")["status"] == "EFFECTIVE_TIME_INPUT_REQUIRED"
    preview = runtime.handle_text("2026-09-30T12:00:00+03:00", user_id="owner-1")
    assert preview["status"] == "OBSERVATION_START_PREVIEW"
    # No API access occurs before explicit start confirmation and an exact period.
    assert collector.calls == []
    card = runtime.handle_callback(preview["keyboard"]["buttons"][0]["callback"], user_id="owner-1")
    collect = next(item["callback"] for item in card["keyboard"]["buttons"] if item["text"] == "Собрать данные за период")
    runtime.handle_callback(collect, user_id="owner-1")
    before_install = runtime.handle_text("2026-09-20 - 2026-09-26", user_id="owner-1")
    assert before_install["status"] == "OBSERVATION_WINDOW_INPUT_REQUIRED"
    assert "источник пока не запрашивался" in before_install["message"]
    assert collector.calls == []
    incomplete = runtime.handle_text("2026-10-25 - 2026-10-27", user_id="owner-1")
    assert incomplete["status"] == "OBSERVATION_WINDOW_INPUT_REQUIRED"
    assert collector.calls == []
    valid = runtime.handle_text("2026-10-18 - 2026-10-24", user_id="owner-1")
    assert valid["status"] == "OBSERVATION_CARD_READY"
    observation_id = repo.list_unit_price_observations(owner_id="owner-1", store_id="store-a")["items"][0]["observation_id"]
    assert collector.calls == [(observation_id, "2026-10-18", "2026-10-24")]


def test_saved_plan_detail_and_assistant_handler_expose_public_start_route(flow):
    _, runtime, _, scope, document, _ = flow
    planning = runtime.planning_service
    plan_runtime = TelegramSavedPlanningPlanRuntimeService(
        planning_service=planning, single_runtime=None, batch_runtime=None,
        keyboard_service=runtime.keyboard_service,
    )
    plan_runtime.unit_price_observation_runtime_service = runtime
    detail = plan_runtime._detail_screen(scope, {"error": False, "document": document})
    callback = next(
        item["callback"] for item in detail["keyboard"]["buttons"]
        if item["callback"].startswith("upo:p:")
    )
    handler = AssistantButtonHandlerService(
        assistant=None, keyboard_service=runtime.keyboard_service,
        unit_price_observation_runtime_service=runtime,
    )
    listed = handler.handle("upo:m", user_id="owner-1")
    assert listed["status"] == "OBSERVATION_LIST_READY"
    prompt = handler.handle(callback, user_id="owner-1")
    assert prompt["status"] == "SELLER_PRICE_INPUT_REQUIRED"
    assert handler.handle_text("123,00", user_id="owner-1")["status"] == "EFFECTIVE_TIME_INPUT_REQUIRED"


def test_saved_multi_sku_plan_starts_observation_for_selected_row(flow):
    repo, runtime, _, scope, _, _ = flow
    payload = _plan_payload()
    payload["plan_kind"] = "batch"
    payload["items"][0]["row_id"] = "row-sku-1"
    second = deepcopy(payload["items"][0])
    second["row_id"] = "row-sku-2"
    second["identity"].update({"product_id": "product-2", "offer_id": "offer-2", "sku": "sku-2"})
    payload["items"].append(second)
    saved = repo.save_document(
        title="Two SKU plan", payload=payload, idempotency_key="q20-multisku-plan-001",
    )
    assert saved.get("error") is False, saved
    document = runtime.planning_service.get_document(saved["document_id"], revision=1)["document"]
    callback = runtime.plan_start_callback(scope, document, item_index=1)
    assert callback and len(callback.encode("utf-8")) <= 64
    prompt = runtime.handle_callback(callback, user_id="owner-1")
    assert prompt["status"] == "SELLER_PRICE_INPUT_REQUIRED"
    assert "sku-2" in prompt["message"]
    runtime.handle_text("123,00", user_id="owner-1")
    preview = runtime.handle_text("2026-09-30T12:00:00+03:00", user_id="owner-1")
    card = runtime.handle_callback(preview["keyboard"]["buttons"][0]["callback"], user_id="owner-1")
    assert "sku-2" in card["message"]
    observations = repo.list_unit_price_observations(owner_id="owner-1", store_id="store-a")["items"]
    assert len(observations) == 1
    assert observations[0]["identity"]["sku"] == "sku-2"
    assert observations[0]["source_plan"] == {"document_id": saved["document_id"], "revision": 1}
