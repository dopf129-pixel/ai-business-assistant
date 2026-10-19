from copy import deepcopy
import pytest

from services.assistant_keyboard_service import AssistantKeyboardService
from services.assistant_button_handler_service import AssistantButtonHandlerService
from services.planning_workspace_repository import PlanningWorkspaceRepository
from services.saved_planning_plan_service import SavedPlanningPlanService
from services.tax_service import TaxService
from services.tenant_context import reset_current_tenant_user_id, set_current_tenant_user_id
from services.telegram_saved_planning_plan_runtime_service import TelegramSavedPlanningPlanRuntimeService
from services.telegram_unit_price_batch_plan_runtime_service import TelegramUnitPriceBatchPlanRuntimeService
from services.telegram_unit_price_calculator_runtime_service import TelegramUnitPriceCalculatorRuntimeService
from services.unit_price_scenario_service import UnitPriceScenarioService
from services.unit_price_advertising_cap_service import UnitPriceAdvertisingCapService
from services.sales_mix_planning_service import SalesMixPlanningService
from services.analytics_export_service import AnalyticsExportService
from services.period_profit_final_application_query_service import PeriodProfitFinalApplicationQueryService
from services.period_profit_query_service import PeriodProfitQueryService
from services.period_profit_sku_runtime_service import PeriodProfitSkuRuntimeService
from services.period_profit_summary_service import PeriodProfitSummaryService
from services.unit_price_target_planning_service import UnitPriceTargetPlanningService


class _Products:
    def __init__(self):
        self.product_id = "product-1"
        self.offer_id = "offer-1"

    def load_products(self):
        return [{"product_id": self.product_id, "offer_id": self.offer_id,
                 "sku": "sku-1", "name": "Тестовый товар"}]


class _Source:
    def __init__(self, store_id="store-a"):
        self.product_service = _Products()
        self.calls = []
        self.price = "500"
        self.store_id = store_id

    def load_snapshot(self, sku, user_id, force_refresh=False):
        self.calls.append((sku, user_id, force_refresh))
        return {
            "error": False,
            "identity": {"user_id": user_id, "store_id": self.store_id,
                         "tenant_scope": f"{user_id}::ozon::{self.store_id}" if self.store_id else user_id,
                         "product_id": self.product_service.product_id,
                         "offer_id": self.product_service.offer_id, "sku": sku},
            "product": {"name": "Тестовый товар", "scheme": "FBO"},
            "suggested_inputs": {
                "price": self.price, "cost": "100", "commission_rate": "15",
                "logistics_per_unit": "40", "last_mile_per_unit": "10", "acquiring_per_unit": "5",
                "advertising_rate": "8", "discount_points_rate": "20", "tax_mode": "USN_INCOME",
                "tax_rate": "6", "minimum_tax_rate": "1",
            },
            "input_provenance": {"price": "ozon_current_seller_price", "cost": "confirmed_store_cost",
                                 "advertising_rate": "manual_seller_assumption"},
            "source_periods": {"seller_price_as_of": "2026-10-19T12:00:00+00:00",
                               "cost_as_of": None,
                               "discount_points": {"from": "2026-09-21", "to": "2026-10-18", "calendar_days": 28}},
            "source_completeness": {
                "catalog_identity": {"complete": True},
                "discount_points": {"complete": True, "positive_sale_observations": 3},
            },
            "cache": {"age_seconds": 0, "ttl_seconds": 600},
        }


def _button(result, label):
    return next(button["callback"] for button in result["keyboard"]["buttons"] if button["text"] == label)


def _setup(tmp_path, *, store_id="store-a"):
    source = _Source(store_id=store_id)
    keyboard = AssistantKeyboardService()
    scenario = UnitPriceScenarioService(TaxService())
    single = TelegramUnitPriceCalculatorRuntimeService(
        source=source, scenario_service=scenario, keyboard_service=keyboard,
        target_planning_service=UnitPriceTargetPlanningService(scenario),
        advertising_cap_service=UnitPriceAdvertisingCapService(scenario),
    )
    service = SavedPlanningPlanService(
        PlanningWorkspaceRepository(db_path=tmp_path / "plans.sqlite"), scenario,
    )
    runtime = TelegramSavedPlanningPlanRuntimeService(
        service, single, None, keyboard,
        sales_mix_planning_service=SalesMixPlanningService(scenario, scenario.tax_service),
    )
    return runtime, single, source, service


def _activate():
    return set_current_tenant_user_id("user-1::ozon::store-a")


def _select_single(single):
    callback = single.build_product_entry_button("user-1", "sku-1")["callback"]
    return single.handle_callback(callback, user_id="user-1")


def test_single_save_list_open_and_continue_uses_historical_snapshot_without_source_calls(tmp_path):
    saved_runtime, single, source, service = _setup(tmp_path)
    tenant = _activate()
    try:
        current = _select_single(single)
        assert len(source.calls) == 1
        save_prompt = saved_runtime.handle_callback(_button(current, "💾 Сохранить план"), user_id="user-1")
        assert save_prompt["status"] == "PLANNING_TITLE_REQUIRED"
        saved = saved_runtime.handle_text("  План   осень  ", user_id="user-1")
        assert saved["status"] == "PLANNING_DOCUMENT_SAVED"
        assert saved["local_write"] is True

        # Simulate a process restart: construct a fresh repository, application
        # service, runtime and transient unit-price editor over the same SQLite DB.
        restarted_single = TelegramUnitPriceCalculatorRuntimeService(
            source=source, scenario_service=single.scenario_service,
            keyboard_service=single.keyboard_service,
            target_planning_service=single.target_planning_service,
            advertising_cap_service=single.advertising_cap_service,
        )
        restarted_service = SavedPlanningPlanService(
            PlanningWorkspaceRepository(db_path=service.repository.db_path),
            single.scenario_service,
        )
        restarted_runtime = TelegramSavedPlanningPlanRuntimeService(
            restarted_service, restarted_single, None, single.keyboard_service,
        )
        restarted_handler = AssistantButtonHandlerService(
            assistant=None, saved_planning_plan_runtime_service=restarted_runtime,
        )
        plan_list = restarted_handler.handle("upp:m", user_id="user-1")
        open_result = restarted_handler.handle(
            _button(plan_list, "План осень · v1"), user_id="user-1",
        )
        assert open_result["status"] == "PLANNING_DOCUMENT_DETAILS"
        assert "исторический снимок" in open_result["message"]
        readiness = restarted_handler.handle(
            _button(open_result, "Готовность плана"), user_id="user-1",
        )
        assert readiness["readiness"]["counts"]["calculations_ready"] == 1
        assert readiness["readiness"]["calculation_status"] == "READY"
        historical_cap = restarted_handler.handle(
            _button(open_result, "Рекламный предел (сохранённые допущения)"),
            user_id="user-1",
        )
        assert historical_cap["status"] == "PLANNING_HISTORICAL_ADVERTISING_CAP"
        assert "безубыточность" in historical_cap["message"].lower()
        assert not any("Подставить" in item["text"] for item in historical_cap["keyboard"]["buttons"])
        assert len(source.calls) == 1
        continued = restarted_handler.handle(
            _button(open_result, "Продолжить по сохранённым допущениям"), user_id="user-1",
        )
        assert continued["status"] == "UNIT_PRICE_SCENARIO_READY"
        assert "исторический сценарий" in continued["message"]
        assert len(source.calls) == 1
        saved_doc = restarted_service.list_documents()["items"][0]
        assert saved_doc["title"] == "План осень"
    finally:
        reset_current_tenant_user_id(tenant)


def test_old_save_callback_cannot_save_after_scenario_version_changes(tmp_path):
    saved_runtime, single, source, service = _setup(tmp_path)
    tenant = _activate()
    try:
        current = _select_single(single)
        prompt = saved_runtime.handle_callback(_button(current, "💾 Сохранить план"), user_id="user-1")
        assert prompt["status"] == "PLANNING_TITLE_REQUIRED"
        stale = single.handle_callback(_button(current, "Цена") if any(
            button["text"] == "Цена" for button in current["keyboard"]["buttons"]
        ) else "upc:e:" + current["price_scenario"]["scenario_id"] + ":1:price", user_id="user-1")
        assert stale["status"] == "UNIT_PRICE_SCENARIO_INPUT_PENDING"
        result = saved_runtime.handle_text("Не должен сохраниться", user_id="user-1")
        assert result["status"] == "PLANNING_ACTION_STALE"
        assert service.list_documents()["items"] == []
    finally:
        reset_current_tenant_user_id(tenant)


def test_sales_mix_public_flow_confirms_zero_expenses_and_saves_revision_without_source_reads(tmp_path):
    saved_runtime, single, source, service = _setup(tmp_path)
    tenant = _activate()
    try:
        current = _select_single(single)
        prompt = saved_runtime.handle_callback(_button(current, "💾 Сохранить план"), user_id="user-1")
        saved_runtime.handle_text("План объёма", user_id="user-1")
        listing = saved_runtime.handle_callback("upp:m", user_id="user-1")
        detail = saved_runtime.handle_callback(_button(listing, "План объёма · v1"), user_id="user-1")
        period = saved_runtime.handle_callback(_button(detail, "План объёма продаж"), user_id="user-1")
        quantity_prompt = saved_runtime.handle_text("01.08.2026 - 31.08.2026", user_id="user-1")
        quantity = saved_runtime.handle_callback(
            _button(quantity_prompt, "Оставить количество неизвестным"), user_id="user-1",
        )
        preview = saved_runtime.handle_text("0", user_id="user-1")
        saved = saved_runtime.handle_callback(
            _button(preview, "Подтвердить и сохранить ревизию"), user_id="user-1",
        )
        document = service.get_document(saved["document_id"])
    finally:
        reset_current_tenant_user_id(tenant)

    assert prompt["status"] == "PLANNING_TITLE_REQUIRED"
    assert period["status"] == "SALES_MIX_INPUT_REQUIRED"
    assert quantity_prompt["status"] == "SALES_MIX_INPUT_REQUIRED"
    assert quantity["status"] == "SALES_MIX_INPUT_REQUIRED"
    assert preview["status"] == "SALES_MIX_PREVIEW"
    assert preview["sales_mix_result"]["tax"] is None
    assert preview["sales_mix_result"]["excluded_rows"][0]["reason"] == "QUANTITY_UNKNOWN"
    assert saved["status"] == "PLANNING_DOCUMENT_DETAILS"
    assert saved["document_id"] == document["document"]["document_id"]
    assert document["document"]["current_revision"] == 2
    mix = document["document"]["payload"]["sales_mix"]
    assert mix["quantities"]["sku-1"] is None
    assert mix["expenses"] == [] and mix["confirmed"] is True
    assert "Показан подтверждённый subtotal" in saved["message"]
    assert len(source.calls) == 1


def test_sales_mix_result_shows_per_sku_components_and_price_times_quantity(tmp_path):
    saved_runtime, single, source, service = _setup(tmp_path)
    tenant = _activate()
    try:
        current = _select_single(single)
        prompt = saved_runtime.handle_callback(
            _button(current, "💾 Сохранить план"), user_id="user-1",
        )
        saved = saved_runtime.handle_text("План объёма", user_id="user-1")
        document = service.get_document(saved["document_id"])["document"]
        payload = deepcopy(document["payload"])
        payload["target_margin_percent"] = "25"
        revised = service.repository.save_document(
            title=document["title"], payload=payload, document_id=document["document_id"],
            expected_revision=1, expected_state_revision=document["state_revision"],
            idempotency_key="seed-target-cap-001",
            owner_id="user-1", store_id="store-a",
        )
        assert revised["revision"] == 2
        details = saved_runtime.handle_callback("upp:m", user_id="user-1")
        details = saved_runtime.handle_callback(_button(details, "План объёма · v2"), user_id="user-1")
        period = saved_runtime.handle_callback(_button(details, "План объёма продаж"), user_id="user-1")
        saved_runtime.handle_text("01.08.2026 - 31.08.2026", user_id="user-1")
        quantity = saved_runtime.handle_text("10", user_id="user-1")
        expense_prompt = saved_runtime.handle_text("1", user_id="user-1")
        preview = saved_runtime.handle_text("Подготовка; 300", user_id="user-1")

        assert prompt["status"] == "PLANNING_TITLE_REQUIRED"
        assert quantity["status"] == "SALES_MIX_INPUT_REQUIRED"
        assert expense_prompt["status"] == "SALES_MIX_INPUT_REQUIRED"
        assert period["status"] == "SALES_MIX_INPUT_REQUIRED"
        assert preview["status"] == "SALES_MIX_PREVIEW"
        assert "10 × 500.00 → выручка 5000.00 ₽" in preview["message"]
        assert "себест. 1000.00 ₽" in preview["message"]
        assert "комиссия 750.00 ₽" in preview["message"]
        assert "реклама 400.00 ₽" in preview["message"]
        assert "fees 550.00 ₽" in preview["message"]
        assert "вклад 2300.00 ₽" in preview["message"]
        assert "Расход за период · Подготовка: 300.00 ₽" in preview["message"]
        assert "Прибыль до налога после расходов: 2000.00 ₽" in preview["message"]
        assert "итоговая прибыль: 1760.00 ₽" in preview["message"]
        assert "Сумма индивидуальных рекламных пределов при цели 25%" in preview["message"]
        assert "не гарантирует маржу группы" in preview["message"]
        confirm_callback = _button(preview, "Подтвердить и сохранить ревизию")
        mix_service = saved_runtime.sales_mix_planning_service
        calculate = mix_service.calculate

        def replace_ticket_during_verification(*args, **kwargs):
            verified = calculate(*args, **kwargs)
            with saved_runtime._lock:
                pending = deepcopy(saved_runtime._pending[("user-1", "user-1::ozon::store-a")])
                pending["ticket"] = "newer-action-ticket"
                saved_runtime._pending[("user-1", "user-1::ozon::store-a")] = pending
            return verified

        mix_service.calculate = replace_ticket_during_verification
        stale = saved_runtime.handle_callback(confirm_callback, user_id="user-1")
        stored = service.get_document(saved["document_id"])["document"]
        assert stale["status"] == "PLANNING_ACTION_STALE"
        assert stored["current_revision"] == 2
        assert saved_runtime._pending[("user-1", "user-1::ozon::store-a")]["ticket"] == "newer-action-ticket"
        assert len(source.calls) == 1
    finally:
        reset_current_tenant_user_id(tenant)


def test_public_plan_fact_flow_uses_finalized_canonical_result_and_snapshot_exports(tmp_path):
    class Finance:
        def __init__(self):
            self.daily_calls = []

        def get_daily_finance(self, day, sku=None):
            self.daily_calls.append((day, sku))
            first = day == "2026-08-01"
            return {
                "error": False, "sales_count": 8 if first else 0,
                "gross_sales": 4160.0 if first else 0.0,
                "discount_points": 900.0 if first else 0.0,
                "net_accrual": 3000.0 if first else 0.0,
                "commission": -500.0 if first else 0.0,
                "logistics": -250.0 if first else 0.0,
                "acquiring": -40.0 if first else 0.0,
                "other_fees": -15.0 if first else 0.0,
                "fee_breakdown": {}, "accrual_type_breakdown": {},
            }

    class Costs:
        def get_cost(self, product_id):
            return 150.0 if str(product_id) == "product-1" else None

    class NoopReturnCogsApplication:
        def apply(self, summary, evidence):
            return {"error": False, "status": "NOT_APPLIED", "summary": summary, "evidence": evidence}

    saved_runtime, single, source, plan_service = _setup(tmp_path)
    finance = Finance()
    summary_service = PeriodProfitSummaryService(finance, Costs(), tax_rate=0.06)
    base_query = PeriodProfitQueryService(
        summary_service,
        lambda: [{"product_id": "product-1", "offer_id": "offer-1", "sku": "sku-1"}],
    )
    finalized_query = PeriodProfitFinalApplicationQueryService(
        base_query, NoopReturnCogsApplication(),
    )
    selected_sku_runtime = PeriodProfitSkuRuntimeService(finalized_query, cost_service=Costs())
    saved_runtime.period_profit_sku_runtime = selected_sku_runtime
    saved_runtime.analytics_export_service = AnalyticsExportService()
    tenant = _activate()
    try:
        current = _select_single(single)
        saved_runtime.handle_callback(_button(current, "💾 Сохранить план"), user_id="user-1")
        saved_runtime.handle_text("План и факт", user_id="user-1")
        listing = saved_runtime.handle_callback("upp:m", user_id="user-1")
        detail = saved_runtime.handle_callback(_button(listing, "План и факт · v1"), user_id="user-1")
        period = saved_runtime.handle_callback(_button(detail, "План объёма продаж"), user_id="user-1")
        quantity_prompt = saved_runtime.handle_text("01.08.2026 - 31.08.2026", user_id="user-1")
        expense_count_prompt = saved_runtime.handle_text("10", user_id="user-1")
        preview = saved_runtime.handle_text("0", user_id="user-1")
        confirmed = saved_runtime.handle_callback(
            _button(preview, "Подтвердить и сохранить ревизию"), user_id="user-1",
        )
        comparison = saved_runtime.handle_callback(
            _button(confirmed, "Сравнить план с фактом"), user_id="user-1",
        )
        assert comparison["status"] == "PLAN_FACT_COMPARISON_PARTIAL"
        assert "Выручка: план 5000.00 ₽, факт 4160.00 ₽, разница -840.00 ₽." in comparison["message"]
        assert "факт не подтверждён" in comparison["message"]
        assert comparison["plan_fact_comparison"]["actual"]["profit_status"] == "NOT_COMPARABLE"
        calls_after_refresh = len(finance.daily_calls)
        assert calls_after_refresh == 31

        # A callback created for one store must not expose the immutable
        # snapshot after the active tenant changes.
        foreign_callback = _button(comparison, "Обновить факт")
        tenant_b = set_current_tenant_user_id("user-1::ozon::store-b")
        foreign_store = saved_runtime.handle_callback(foreign_callback, user_id="user-1")
        assert foreign_store["status"] == "PLANNING_ACTION_STALE"
        reset_current_tenant_user_id(tenant_b)

        detail_callback = _button(comparison, "Подробнее")
        details = saved_runtime.handle_callback(detail_callback, user_id="user-1")
        csv_result = saved_runtime.handle_callback(_button(comparison, "CSV"), user_id="user-1")
        json_result = saved_runtime.handle_callback(_button(comparison, "JSON"), user_id="user-1")
        assert details["status"] == "PLAN_FACT_COMPARISON_PARTIAL"
        assert csv_result["status"] == "ANALYTICS_EXPORT_READY"
        assert json_result["status"] == "ANALYTICS_EXPORT_READY"
        assert len(finance.daily_calls) == calls_after_refresh
        assert "all_rows_in_exact_saved_plan_fact_snapshot" in json_result["file_content"].decode("utf-8")
        assert plan_service.get_document(confirmed["document_id"])["document"]["current_revision"] == 2
    finally:
        reset_current_tenant_user_id(tenant)


def test_plan_fact_refresh_does_not_publish_after_plan_revision_changes(tmp_path):
    class Finance:
        def get_daily_finance(self, day, sku=None):
            first = day == "2026-08-01"
            return {
                "error": False, "sales_count": 8 if first else 0,
                "gross_sales": 4160.0 if first else 0.0,
                "discount_points": 900.0 if first else 0.0,
                "net_accrual": 3000.0 if first else 0.0,
                "commission": -500.0 if first else 0.0,
                "logistics": -250.0 if first else 0.0,
                "acquiring": -40.0 if first else 0.0,
                "other_fees": -15.0 if first else 0.0,
                "fee_breakdown": {}, "accrual_type_breakdown": {},
            }

    class Costs:
        def get_cost(self, product_id):
            return 150.0 if str(product_id) == "product-1" else None

    class NoopReturnCogsApplication:
        def apply(self, summary, evidence):
            return {"error": False, "status": "NOT_APPLIED", "summary": summary, "evidence": evidence}

    saved_runtime, single, _source, plan_service = _setup(tmp_path)
    finance = Finance()
    summary_service = PeriodProfitSummaryService(finance, Costs(), tax_rate=0.06)
    base_query = PeriodProfitQueryService(
        summary_service,
        lambda: [{"product_id": "product-1", "offer_id": "offer-1", "sku": "sku-1"}],
    )
    finalized_query = PeriodProfitFinalApplicationQueryService(
        base_query, NoopReturnCogsApplication(),
    )
    canonical_runtime = PeriodProfitSkuRuntimeService(finalized_query, cost_service=Costs())

    class ConcurrentRevisionRuntime:
        def query_selected_identities(self, identities, *, date_from, date_to):
            current = plan_service.get_document(document_id)["document"]
            mix = deepcopy(current["payload"]["sales_mix"])
            row_id = next(iter(mix["quantities"]))
            mix["quantities"][row_id] += 1
            changed = plan_service.save_sales_mix_revision(
                document_id, mix, expected_revision=current["current_revision"],
                expected_state_revision=current["state_revision"],
                idempotency_key="concurrent-plan-update",
            )
            assert changed["error"] is False, changed
            return canonical_runtime.query_selected_identities(
                identities, date_from=date_from, date_to=date_to,
            )

    saved_runtime.period_profit_sku_runtime = ConcurrentRevisionRuntime()
    tenant = _activate()
    try:
        current = _select_single(single)
        saved_runtime.handle_callback(_button(current, "💾 Сохранить план"), user_id="user-1")
        saved = saved_runtime.handle_text("Race plan", user_id="user-1")
        document_id = saved["document_id"]
        listing = saved_runtime.handle_callback("upp:m", user_id="user-1")
        detail = saved_runtime.handle_callback(_button(listing, "Race plan · v1"), user_id="user-1")
        saved_runtime.handle_callback(_button(detail, "План объёма продаж"), user_id="user-1")
        saved_runtime.handle_text("01.08.2026 - 31.08.2026", user_id="user-1")
        saved_runtime.handle_text("10", user_id="user-1")
        preview = saved_runtime.handle_text("0", user_id="user-1")
        confirmed = saved_runtime.handle_callback(
            _button(preview, "Подтвердить и сохранить ревизию"), user_id="user-1",
        )

        stale = saved_runtime.handle_callback(
            _button(confirmed, "Сравнить план с фактом"), user_id="user-1",
        )
        stored = plan_service.get_document(document_id)["document"]
        assert stale["code"] == "PLANNING_DOCUMENT_REVISION_CONFLICT"
        assert stored["current_revision"] == 3
        assert saved_runtime.comparison_snapshot_store._snapshots == {}
        assert "PLAN_FACT_COMPARISON" not in str(stale)
    finally:
        reset_current_tenant_user_id(tenant)


def test_plan_fact_late_response_cannot_recreate_snapshot_after_user_state_reset(tmp_path):
    saved_runtime, single, _source, plan_service = _setup(tmp_path)

    class ResetDuringQuery:
        def query_selected_identities(self, identities, *, date_from, date_to):
            saved_runtime.clear_user_state("user-1")
            return {"error": False, "rows": [], "status": "COMPLETE"}

    class Comparison:
        @staticmethod
        def _period(_label):
            return ("2026-08-01", "2026-08-31")

        def compare(self, _document, _facts, *, tenant_scope, generated_at_utc):
            return {"error": False, "status": "COMPARABLE", "coverage": {}}

    saved_runtime.period_profit_sku_runtime = ResetDuringQuery()
    saved_runtime.plan_fact_comparison_service = Comparison()
    tenant = _activate()
    try:
        current = _select_single(single)
        saved_runtime.handle_callback(_button(current, "💾 Сохранить план"), user_id="user-1")
        saved = saved_runtime.handle_text("Reset race", user_id="user-1")
        document = plan_service.get_document(saved["document_id"])["document"]
        mix = {
            "period_label": "01.08.2026 - 31.08.2026",
            "quantities": {"sku-1": 10}, "expenses": [], "confirmed": True,
        }
        changed = plan_service.save_sales_mix_revision(
            saved["document_id"], mix,
            expected_revision=document["current_revision"],
            expected_state_revision=document["state_revision"],
            idempotency_key="reset-race-mix-save",
        )
        assert changed["error"] is False
        listing = saved_runtime.handle_callback("upp:m", user_id="user-1")
        detail = saved_runtime.handle_callback(
            _button(listing, "Reset race · v2"), user_id="user-1",
        )
        result = saved_runtime.handle_callback(
            _button(detail, "Сравнить план с фактом"), user_id="user-1",
        )
        assert result["error"] is True
        assert result["code"] == "TRANSIENT_SNAPSHOT_GENERATION_STALE"
        assert saved_runtime.comparison_snapshot_store._snapshots == {}
        assert saved_runtime.comparison_snapshot_store._generations == {}
    finally:
        reset_current_tenant_user_id(tenant)


def test_readiness_can_correct_one_unknown_quantity_and_keeps_old_revision_until_confirm(tmp_path):
    saved_runtime, single, source, plan_service = _setup(tmp_path)
    tenant = _activate()
    try:
        current = _select_single(single)
        saved_runtime.handle_callback(_button(current, "💾 Сохранить план"), user_id="user-1")
        saved = saved_runtime.handle_text("Readiness plan", user_id="user-1")
        document = plan_service.get_document(saved["document_id"])["document"]
        item = document["payload"]["items"][0]
        row_id = str(item.get("row_id") or item["identity"]["sku"])
        mix = {
            "period_label": "01.08.2026 - 31.08.2026",
            "quantities": {row_id: None}, "expenses": [], "confirmed": True,
        }
        saved_mix = plan_service.save_sales_mix_revision(
            saved["document_id"], mix, expected_revision=1,
            expected_state_revision=document["state_revision"],
            idempotency_key="readiness-mix-seed",
        )
        assert saved_mix["error"] is False
        listing = saved_runtime.handle_callback("upp:m", user_id="user-1")
        detail = saved_runtime.handle_callback(_button(listing, "Readiness plan · v2"), user_id="user-1")
        readiness = saved_runtime.handle_callback(_button(detail, "Готовность плана"), user_id="user-1")
        assert readiness["readiness"]["items"][0]["quantity_status"] == "UNKNOWN"
        assert readiness["readiness"]["fact_status"] == "NOT_CHECKED"
        quantity_prompt = saved_runtime.handle_callback(
            _button(readiness, "Задать количество · Тестовый товар"), user_id="user-1",
        )
        assert quantity_prompt["status"] == "SALES_MIX_QUANTITY_EDIT_REQUIRED"
        preview = saved_runtime.handle_text("0", user_id="user-1")
        assert preview["status"] == "SALES_MIX_PREVIEW"
        before_confirm = plan_service.get_document(saved["document_id"])["document"]
        assert before_confirm["current_revision"] == 2
        confirmed = saved_runtime.handle_callback(
            _button(preview, "Подтвердить и сохранить ревизию"), user_id="user-1",
        )
        after_confirm = plan_service.get_document(saved["document_id"])["document"]
        assert confirmed["status"] == "PLANNING_DOCUMENT_DETAILS"
        assert after_confirm["current_revision"] == 3
        assert after_confirm["payload"]["sales_mix"]["quantities"][row_id] == 0
        assert len(source.calls) == 1
    finally:
        reset_current_tenant_user_id(tenant)


def test_readiness_routes_to_one_missing_single_plan_field_without_saving_it(tmp_path):
    saved_runtime, single, _source, plan_service = _setup(tmp_path)
    handler = AssistantButtonHandlerService(
        assistant=None, saved_planning_plan_runtime_service=saved_runtime,
        unit_price_calculator_runtime_service=single,
    )
    tenant = _activate()
    try:
        current = _select_single(single)
        saved_runtime.handle_callback(_button(current, "💾 Сохранить план"), user_id="user-1")
        saved = saved_runtime.handle_text("Incomplete plan", user_id="user-1")
        document = plan_service.get_document(saved["document_id"])["document"]
        payload = deepcopy(document["payload"])
        payload["items"][0]["inputs"]["cost"] = None
        payload["items"][0]["projection"].update(
            available=False, status="INCOMPLETE_INPUTS", missing_inputs=["cost"],
        )
        saved_mix = {
            "period_label": "01.08.2026 - 31.08.2026",
            "quantities": {"sku-1": 100},
            "expenses": [{"name": "Packaging", "amount": "1200.00"}],
            "confirmed": True,
        }
        payload["sales_mix"] = deepcopy(saved_mix)
        updated = plan_service.repository.save_document(
            title=document["title"], payload=payload, owner_id="user-1", store_id="store-a",
            document_id=document["document_id"], expected_revision=1,
            expected_state_revision=document["state_revision"],
            idempotency_key="readiness-incomplete-seed",
        )
        assert updated["error"] is False
        listing = handler.handle("upp:m", user_id="user-1")
        detail = handler.handle(_button(listing, "Incomplete plan · v2"), user_id="user-1")
        readiness = handler.handle(_button(detail, "Готовность плана"), user_id="user-1")
        edit_prompt = handler.handle(
            _button(readiness, "Исправить · Тестовый товар"), user_id="user-1",
        )
        assert edit_prompt["status"] == "UNIT_PRICE_SCENARIO_INPUT_PENDING"
        assert "себестоимость" in edit_prompt["message"].lower()
        assert plan_service.get_document(saved["document_id"])["document"]["current_revision"] == 2
        edited = handler.handle_text("125", user_id="user-1")
        assert edited["error"] is False
        price_prompt = handler.handle(_button(edited, "Цена"), user_id="user-1")
        assert price_prompt["status"] == "UNIT_PRICE_SCENARIO_INPUT_PENDING"
        edited_again = handler.handle_text("700", user_id="user-1")
        update_callback = _button(edited_again, "💾 Сохранить изменения в этот план")
        assert plan_service.get_document(saved["document_id"])["document"]["current_revision"] == 2
        updated = handler.handle(update_callback, user_id="user-1")
        assert updated["status"] == "PLANNING_DOCUMENT_UPDATED"
        saved_document = plan_service.get_document(saved["document_id"])["document"]
        assert saved_document["current_revision"] == 3
        assert saved_document["payload"]["items"][0]["inputs"]["cost"] == "125"
        assert saved_document["payload"]["items"][0]["inputs"]["price"] == "700"
        assert saved_document["payload"]["sales_mix"] == saved_mix

        conflicted_payload = deepcopy(saved_document["payload"])
        conflicted_payload["items"][0]["inputs"]["cost"] = None
        conflicted_payload["items"][0]["projection"].update(
            available=False, status="INCOMPLETE_INPUTS", missing_inputs=["cost"],
        )
        plan_service.repository.save_document(
            title=saved_document["title"], payload=conflicted_payload,
            owner_id="user-1", store_id="store-a", document_id=saved["document_id"],
            expected_revision=3, expected_state_revision=saved_document["state_revision"],
            idempotency_key="readiness-reopen-field",
        )
        listing = handler.handle("upp:m", user_id="user-1")
        detail = handler.handle(_button(listing, "Incomplete plan · v4"), user_id="user-1")
        readiness = handler.handle(_button(detail, "Готовность плана"), user_id="user-1")
        handler.handle(_button(readiness, "Исправить · Тестовый товар"), user_id="user-1")
        stale_edit = handler.handle_text("130", user_id="user-1")
        stale_callback = _button(stale_edit, "💾 Сохранить изменения в этот план")
        competing = plan_service.get_document(saved["document_id"])["document"]
        plan_service.repository.save_document(
            title=competing["title"], payload=competing["payload"],
            owner_id="user-1", store_id="store-a", document_id=saved["document_id"],
            expected_revision=4, expected_state_revision=competing["state_revision"],
            idempotency_key="readiness-concurrent-revision",
        )
        rejected = handler.handle(stale_callback, user_id="user-1")
        assert rejected["error"] is True
        assert rejected["code"] == "PLANNING_DOCUMENT_STATE_CONFLICT"
        latest = plan_service.get_document(saved["document_id"])["document"]
        assert latest["current_revision"] == 5
        assert latest["payload"]["items"][0]["inputs"]["cost"] is None
    finally:
        reset_current_tenant_user_id(tenant)


def test_saved_document_crud_uses_explicit_copy_archive_restore_and_delete_confirmation(tmp_path):
    saved_runtime, single, _source, service = _setup(tmp_path)
    tenant = _activate()
    try:
        current = _select_single(single)
        saved_runtime.handle_callback(_button(current, "💾 Сохранить план"), user_id="user-1")
        saved_runtime.handle_text("Original", user_id="user-1")
        listing = saved_runtime.handle_callback("upp:m", user_id="user-1")
        detail = saved_runtime.handle_callback(_button(listing, "Original · v1"), user_id="user-1")
        saved_runtime.handle_callback(_button(detail, "Сохранить копию"), user_id="user-1")
        copied = saved_runtime.handle_text("Копия", user_id="user-1")
        assert copied["status"] == "PLANNING_DOCUMENT_COPIED"
        listing = saved_runtime.handle_callback("upp:m", user_id="user-1")
        detail = saved_runtime.handle_callback(_button(listing, "Original · v1"), user_id="user-1")
        archived = saved_runtime.handle_callback(_button(detail, "В архив"), user_id="user-1")
        assert "архив" in archived["message"]
        archived_list = saved_runtime.handle_callback("upp:l:a:0", user_id="user-1")
        restored_detail = saved_runtime.handle_callback(_button(archived_list, "Original · v1"), user_id="user-1")
        restored = saved_runtime.handle_callback(_button(restored_detail, "Восстановить"), user_id="user-1")
        assert "восстановлен" in restored["message"]
        listing = saved_runtime.handle_callback("upp:m", user_id="user-1")
        detail = saved_runtime.handle_callback(_button(listing, "Original · v1"), user_id="user-1")
        confirm = saved_runtime.handle_callback(_button(detail, "Удалить…"), user_id="user-1")
        assert confirm["status"] == "PLANNING_DELETE_CONFIRMATION_REQUIRED"
        rename_prompt = saved_runtime.handle_callback(_button(detail, "Переименовать"), user_id="user-1")
        renamed = saved_runtime.handle_text("Renamed", user_id="user-1")
        assert rename_prompt["status"] == "PLANNING_TITLE_REQUIRED"
        assert renamed["status"] == "PLANNING_DOCUMENT_UPDATED"
        stale_delete = saved_runtime.handle_callback(
            _button(confirm, "Удалить план и версии"), user_id="user-1",
        )
        assert stale_delete["error"] is True
        assert stale_delete["code"] == "PLANNING_DOCUMENT_STATE_CONFLICT"
        current_list = saved_runtime.handle_callback("upp:m", user_id="user-1")
        current_detail = saved_runtime.handle_callback(
            _button(current_list, "Renamed · v1"), user_id="user-1",
        )
        current_confirm = saved_runtime.handle_callback(
            _button(current_detail, "Удалить…"), user_id="user-1",
        )
        deleted = saved_runtime.handle_callback(
            _button(current_confirm, "Удалить план и версии"), user_id="user-1",
        )
        assert "удалены" in deleted["message"]
        assert len(service.list_documents()["items"]) == 1
    finally:
        reset_current_tenant_user_id(tenant)


def test_public_handler_preserves_refreshed_batch_until_saved_revision_is_written(tmp_path):
    class BatchBuilder:
        BATCH_CALCULATION_LIMIT = 100

        def __init__(self, scenario_service):
            self.scenario_service = scenario_service

        def refresh(self, batch, parent_trace=None):
            refreshed = deepcopy(batch)
            refreshed["version"] += 1
            for row in refreshed["rows"]:
                row.update(
                    status="READY", source_age_seconds_at_load=0,
                    source_loaded_at=100, source_ttl_seconds=600,
                )
            return refreshed

        def edit_row_assumption(self, batch, row_id, field, value):
            updated = deepcopy(batch)
            updated["version"] += 1
            row = next(item for item in updated["rows"] if item["row_id"] == row_id)
            row["inputs"][field] = value
            row.setdefault("provenance", {})[field] = "manual_seller_assumption"
            return updated

    saved_runtime, single, _source, plan_service = _setup(tmp_path)
    keyboard = AssistantKeyboardService()
    builder = BatchBuilder(single.scenario_service)
    batch_runtime = TelegramUnitPriceBatchPlanRuntimeService(
        builder, None, keyboard, clock=lambda: 100,
        tenant_scope_provider=lambda: "user-1::ozon::store-a",
    )
    saved_runtime.batch_runtime = batch_runtime
    handler = AssistantButtonHandlerService(
        assistant=None, keyboard_service=keyboard,
        saved_planning_plan_runtime_service=saved_runtime,
        unit_price_batch_plan_runtime_service=batch_runtime,
    )
    tenant = _activate()
    try:
        current_scenario = _select_single(single)
        scenario_callback = next(
            button["callback"] for button in current_scenario["keyboard"]["buttons"]
            if button["callback"].startswith("upc:e:")
        )
        _, _, scenario_id, scenario_version, _ = scenario_callback.split(":")
        payload_capture = single.get_saved_plan_capture(
            scenario_id, int(scenario_version),
            user_id="user-1",
        )
        payload = deepcopy(payload_capture["payload"])
        payload["plan_kind"] = "batch"
        payload["target_margin_percent"] = "25"
        payload["items"][0]["row_id"] = "row-1"
        payload["items"][0]["projection"].update(
            available=True, status="READY", missing_inputs=[], invalid_inputs=[],
        )
        second = deepcopy(payload["items"][0])
        second["row_id"] = "row-2"
        second["identity"].update(
            product_id="product-2", offer_id="offer-2", sku="sku-2",
            product_name="Тестовый товар 2",
        )
        second["sources"]["completeness"]["catalog_identity"] = {"complete": True}
        payload["items"].append(second)
        planned_mix = {
            "period_label": "01.08.2026 - 31.08.2026",
            "quantities": {"row-1": 10, "row-2": 5},
            "expenses": [{"name": "Packaging", "amount": "1200.00"}],
            "confirmed": True,
        }
        payload["sales_mix"] = deepcopy(planned_mix)
        created = plan_service.repository.save_document(
            title="Batch", payload=payload, owner_id="user-1", store_id="store-a",
            idempotency_key="batch-save-seed-01",
        )
        listing = handler.handle("upp:m", user_id="user-1")
        detail = handler.handle(_button(listing, "Batch · v1"), user_id="user-1")
        refreshed = handler.handle(_button(detail, "Обновить источники"), user_id="user-1")
        edit_button = next(
            button["callback"] for button in refreshed["keyboard"]["buttons"]
            if button["text"].startswith("Изменить ·")
        )
        edit_menu = handler.handle(edit_button, user_id="user-1")
        price_callback = next(
            button["callback"] for button in edit_menu["keyboard"]["buttons"]
            if button["text"].startswith("Цена продавца")
        )
        price_prompt = handler.handle(price_callback, user_id="user-1")
        edited = handler.handle_text("650", user_id="user-1")
        save_callback = _button(edited, "💾 Сохранить изменения в этот план")
        saved = handler.handle(save_callback, user_id="user-1")
        current = plan_service.get_document(created["document_id"])["document"]
    finally:
        reset_current_tenant_user_id(tenant)

    assert refreshed["status"] == "UNIT_PRICE_BATCH_PLAN_READY"
    assert saved["status"] == "PLANNING_DOCUMENT_UPDATED"
    assert current["current_revision"] == 2
    assert current["payload"]["plan_kind"] == "batch"
    assert current["payload"]["sales_mix"] == planned_mix
    assert price_prompt["status"] == "UNIT_PRICE_BATCH_INPUT_REQUIRED"
    assert current["payload"]["items"][0]["inputs"]["price"] == "650"


def test_public_plan_variant_comparison_and_owner_exports_use_historical_saved_scope(tmp_path):
    saved_runtime, single, source, service = _setup(tmp_path)
    saved_runtime.analytics_export_service = AnalyticsExportService()
    handler = AssistantButtonHandlerService(
        assistant=None, saved_planning_plan_runtime_service=saved_runtime,
        unit_price_calculator_runtime_service=single,
    )
    tenant = _activate()
    try:
        current = _select_single(single)
        saved_runtime.handle_callback(_button(current, "💾 Сохранить план"), user_id="user-1")
        saved = saved_runtime.handle_text("Option A", user_id="user-1")
        first = service.get_document(saved["document_id"])["document"]
        first_item = first["payload"]["items"][0]
        row_id = first_item.get("row_id") or first_item["identity"]["sku"]
        sales_mix = {
            "period_label": "01.08.2026 - 31.08.2026",
            "quantities": {row_id: 10}, "expenses": [], "confirmed": True,
        }
        mix_saved = service.save_sales_mix_revision(
            first["document_id"], sales_mix, expected_revision=1,
            expected_state_revision=first["state_revision"],
            idempotency_key="option-a-mix",
        )
        assert mix_saved["error"] is False
        first = service.get_document(first["document_id"])["document"]
        second_payload = deepcopy(first["payload"])
        second_payload["items"][0]["inputs"]["price"] = "550"
        second = service.repository.save_document(
            title="Option B", payload=second_payload, owner_id="user-1",
            store_id="store-a", idempotency_key="option-b-seed",
        )
        assert second["error"] is False
        second_document = service.get_document(second["document_id"])["document"]
        assert second_document["payload"].get("sales_mix") is not None
        assert saved_runtime.plan_comparison_service._project_mix(first["payload"]) is not None
        assert saved_runtime.plan_comparison_service._project_mix(second_document["payload"]) is not None

        listing = handler.handle("upp:m", user_id="user-1")
        first_plan_button = next(
            button["callback"] for button in listing["keyboard"]["buttons"]
            if button["text"].startswith("Option A")
        )
        first_detail = handler.handle(first_plan_button, user_id="user-1")
        picker = handler.handle(_button(first_detail, "Сравнить варианты"), user_id="user-1")
        second_button = next(
            button["callback"] for button in picker["keyboard"]["buttons"]
            if button["text"].startswith("Option B ·")
        )
        comparison = handler.handle(second_button, user_id="user-1")
        assert comparison["status"] == "PLANNING_COMPARISON_READY", comparison.get("plan_comparison", {}).get("reason")
        assert comparison["plan_comparison"]["status"] == "COMPARABLE"
        assert comparison["plan_comparison"]["external_reads"] == 0
        assert "п.п." in comparison["message"]
        comparison_export = handler.handle(_button(comparison, "CSV"), user_id="user-1")
        assert comparison_export["error"] is False
        assert comparison_export["export_kind"] == "plan_comparison"

        csv_plan = handler.handle(_button(first_detail, "Экспорт плана · CSV"), user_id="user-1")
        assert csv_plan["error"] is False and csv_plan["export_kind"] == "saved_plan"
        mix_export = handler.handle(_button(first_detail, "Экспорт объёма · CSV"), user_id="user-1")
        assert mix_export["error"] is False and mix_export["export_kind"] == "sales_mix"
        cap_screen = handler.handle(
            _button(first_detail, "Рекламный предел (сохранённые допущения)"), user_id="user-1",
        )
        cap_export = handler.handle(_button(cap_screen, "Экспорт предела · CSV"), user_id="user-1")
        assert cap_export["error"] is False and cap_export["export_kind"] == "advertising_cap"
        assert len(source.calls) == 1
    finally:
        reset_current_tenant_user_id(tenant)


class _Overview:
    def get_price_plan_selection(self):
        return {"error": False, "items": [
            {"identity": {"product_id": "product-1", "offer_id": "offer-1", "catalog_sku": "sku-1"}},
            {"identity": {"product_id": "product-2", "offer_id": "offer-2", "catalog_sku": "sku-2"}},
        ]}


class _TargetPlanner:
    def parse_target_margin(self, value):
        return {"error": False, "value": str(value), "normalized": str(value)}


class _BatchBuilder:
    BATCH_CALCULATION_LIMIT = 1280

    def __init__(self, scenario):
        self.scenario_service = scenario
        self.target_planning_service = _TargetPlanner()

    def build(self, items, user_id, target_margin_percent, **kwargs):
        rows = []
        for index, selection in enumerate(items, start=1):
            identity = selection["identity"]
            product_id = identity["product_id"]
            offer_id = identity["offer_id"]
            sku = identity["catalog_sku"]
            source_identity = {
                "user_id": user_id, "store_id": "store-a",
                "tenant_scope": f"{user_id}::ozon::store-a",
                "product_id": product_id, "offer_id": offer_id, "sku": sku,
            }
            inputs = {
                "price": "500", "cost": "100", "commission_rate": "15",
                "advertising_rate": "8", "discount_points_rate": "20",
                "logistics_per_unit": "40", "last_mile_per_unit": "10",
                "acquiring_per_unit": "5", "tax_mode": "USN_INCOME",
                "tax_rate": "6", "minimum_tax_rate": "1",
            }
            periods = {"seller_price_as_of": "2026-10-19T12:00:00+00:00"}
            completeness = {"scheme": "FBO", "catalog_identity": {"complete": True}}
            snapshot = {
                "identity": source_identity,
                "product": {"name": f"Товар {index}", "scheme": "FBO"},
                "suggested_inputs": inputs,
                "input_provenance": {"cost": "confirmed_store_cost"},
                "source_periods": periods,
                "source_completeness": completeness,
            }
            scenario = self.scenario_service.calculate(inputs, identity=source_identity,
                                                       sources={"periods": periods, "completeness": completeness})
            rows.append({
                "row_id": f"row-{index}", "scheme": "FBO", "identity": identity,
                "status": "READY", "inputs": inputs,
                "provenance": {"cost": "confirmed_store_cost"},
                "manual_assumptions": {}, "snapshot": snapshot,
                "scenario": scenario, "planning": {"target": {}},
                "missing_inputs": [], "source_as_of": periods,
                "source_age_seconds_at_load": 0, "source_loaded_at": 100,
                "source_ttl_seconds": 600,
            })
        return {
            "error": False, "kind": "UNIT_PRICE_BATCH_PLAN", "batch_id": "batch-1",
            "version": 1, "owner_id": user_id,
            "tenant_scope": f"{user_id}::ozon::store-a", "store_id": "store-a",
            "target_margin_percent": str(target_margin_percent), "rows": rows,
            "rows_selected": len(rows), "rows_attempted": len(rows), "rows_completed": len(rows),
            "evaluation_count": 0, "evaluation_limit": self.BATCH_CALCULATION_LIMIT,
            "read_only": True, "executed": False,
        }


def test_batch_plan_save_and_continue_preserves_rows_without_refresh(tmp_path):
    keyboard = AssistantKeyboardService()
    scenario = UnitPriceScenarioService(TaxService())
    batch = TelegramUnitPriceBatchPlanRuntimeService(
        batch_plan_service=_BatchBuilder(scenario), product_overview_service=_Overview(),
        keyboard_service=keyboard,
    )
    source = _Source()
    single = TelegramUnitPriceCalculatorRuntimeService(
        source=source, scenario_service=scenario, keyboard_service=keyboard,
        target_planning_service=UnitPriceTargetPlanningService(scenario),
    )
    plan_service = SavedPlanningPlanService(
        PlanningWorkspaceRepository(db_path=tmp_path / "plans.sqlite"), scenario,
    )
    saved = TelegramSavedPlanningPlanRuntimeService(plan_service, single, batch, keyboard)
    handler = AssistantButtonHandlerService(
        assistant=None, unit_price_batch_plan_runtime_service=batch,
        saved_planning_plan_runtime_service=saved,
    )
    tenant = _activate()
    try:
        batch.begin_from_overview_selection("user-1")
        current = batch.handle_text("25", user_id="user-1")
        prompt = handler.handle(_button(current, "💾 Сохранить план"), user_id="user-1")
        assert prompt["status"] == "PLANNING_TITLE_REQUIRED"
        result = handler.handle_text("План партии", user_id="user-1")
        assert result["status"] == "PLANNING_DOCUMENT_SAVED"
        listing = handler.handle("upp:m", user_id="user-1")
        detail = handler.handle(_button(listing, "План партии · v1"), user_id="user-1")
        reopened = handler.handle(_button(detail, "Продолжить по сохранённым допущениям"), user_id="user-1")
        assert reopened["status"] == "UNIT_PRICE_BATCH_PLAN_READY"
        assert len(reopened["batch_plan"]["rows"]) == 2
        assert reopened["batch_plan"]["restored_from_saved_plan"] is True
        assert all(row["status"] == "SOURCE_STALE" for row in reopened["batch_plan"]["rows"])
    finally:
        reset_current_tenant_user_id(tenant)


def test_archiving_does_not_bypass_total_plan_quota_and_error_explains_delete(tmp_path, monkeypatch):
    monkeypatch.setattr(PlanningWorkspaceRepository, "MAX_DOCUMENTS_PER_STORE", 1)
    saved_runtime, single, _source, service = _setup(tmp_path)
    handler = AssistantButtonHandlerService(
        assistant=None, saved_planning_plan_runtime_service=saved_runtime,
    )
    tenant = _activate()
    try:
        current = _select_single(single)
        handler.handle(_button(current, "💾 Сохранить план"), user_id="user-1")
        assert handler.handle_text("Первый", user_id="user-1")["status"] == "PLANNING_DOCUMENT_SAVED"
        listing = handler.handle("upp:m", user_id="user-1")
        detail = handler.handle(_button(listing, "Первый · v1"), user_id="user-1")
        handler.handle(_button(detail, "В архив"), user_id="user-1")

        next_scenario = single.handle_callback(
            f"upc:z:{current['price_scenario']['scenario_id']}:1", user_id="user-1",
        )
        handler.handle(_button(next_scenario, "💾 Сохранить план"), user_id="user-1")
        rejected = handler.handle_text("Второй", user_id="user-1")
        assert rejected["code"] == "PLANNING_DOCUMENT_QUOTA_REACHED"
        assert "архивирование лимит не освобождает" in rejected["message"]
        assert service.list_documents(include_archived=True)["items"][0]["title"] == "Первый"
    finally:
        reset_current_tenant_user_id(tenant)


def test_public_handler_saves_and_refreshes_existing_plan_with_cas_and_manual_override(tmp_path):
    saved_runtime, single, source, service = _setup(tmp_path)
    handler = AssistantButtonHandlerService(
        assistant=None, saved_planning_plan_runtime_service=saved_runtime,
        unit_price_calculator_runtime_service=single,
    )
    tenant = _activate()
    try:
        current = _select_single(single)
        scenario_id = current["price_scenario"]["scenario_id"]
        single.handle_callback(f"upc:e:{scenario_id}:1:price", user_id="user-1")
        edited = single.handle_text("600", user_id="user-1")
        assert edited["price_scenario"]["inputs"]["price"]["value"] == 600

        prompt = handler.handle(
            _button(edited, "💾 Сохранить план"), user_id="user-1",
        )
        assert prompt["status"] == "PLANNING_TITLE_REQUIRED"
        saved = handler.handle_text("Мой план", user_id="user-1")
        assert saved["status"] == "PLANNING_DOCUMENT_SAVED"
        listing = handler.handle("upp:m", user_id="user-1")
        detail = handler.handle(
            _button(listing, "Мой план · v1"), user_id="user-1",
        )

        # A refreshed catalog price is not allowed to overwrite the seller's
        # explicit price assumption in the new revision.
        source.price = "700"
        refreshed = handler.handle(
            _button(detail, "Обновить источники"), user_id="user-1",
        )
        assert refreshed["status"] == "UNIT_PRICE_SCENARIO_READY"
        assert refreshed["price_scenario"]["inputs"]["price"]["value"] == 600
        assert _button(refreshed, "📄 Сохранить копию")
        price_prompt = handler.handle(_button(refreshed, "Цена"), user_id="user-1")
        price_edit = handler.handle_text("650", user_id="user-1")
        cost_prompt = handler.handle(_button(price_edit, "Себестоимость"), user_id="user-1")
        edited = handler.handle_text("125", user_id="user-1")
        update_callback = _button(edited, "💾 Сохранить изменения в этот план")
        updated = handler.handle(update_callback, user_id="user-1")
        assert updated["status"] == "PLANNING_DOCUMENT_UPDATED"
        assert updated["revision"] == 2

        revisions = service.list_revisions(service.list_documents()["items"][0]["document_id"])
        assert [item["revision"] for item in revisions["items"]] == [2, 1]
        current_doc = service.get_document(service.list_documents()["items"][0]["document_id"])
        saved_item = current_doc["document"]["payload"]["items"][0]
        assert saved_item["inputs"]["price"] == "650"
        assert saved_item["inputs"]["cost"] == "125"
        assert saved_item["provenance"]["price"] == "manual_seller_assumption"
        assert price_prompt["status"] == "UNIT_PRICE_SCENARIO_INPUT_PENDING"
        assert cost_prompt["status"] == "UNIT_PRICE_SCENARIO_INPUT_PENDING"
        assert source.calls == [
            ("sku-1", "user-1", False), ("sku-1", "user-1", True),
        ]
    finally:
        reset_current_tenant_user_id(tenant)


def test_fallback_tenant_scope_preserves_sales_mix_on_refresh_and_explicit_update(tmp_path):
    saved_runtime, single, _source, service = _setup(tmp_path, store_id=None)
    handler = AssistantButtonHandlerService(
        assistant=None, saved_planning_plan_runtime_service=saved_runtime,
        unit_price_calculator_runtime_service=single,
    )
    tenant = set_current_tenant_user_id("user-1")
    try:
        selected = _select_single(single)
        save_prompt = handler.handle(_button(selected, "💾 Сохранить план"), user_id="user-1")
        saved = handler.handle_text("Fallback scope plan", user_id="user-1")
        document = service.get_document(saved["document_id"])["document"]
        item = document["payload"]["items"][0]
        row_id = str(item.get("row_id") or item["identity"]["sku"])
        mix = {
            "period_label": "01.08.2026 - 31.08.2026",
            "quantities": {row_id: 10}, "expenses": [], "confirmed": True,
        }
        mix_saved = service.save_sales_mix_revision(
            document["document_id"], mix, expected_revision=1,
            expected_state_revision=document["state_revision"],
            idempotency_key="fallback-scope-mix",
        )
        assert mix_saved["error"] is False, mix_saved
        listing = handler.handle("upp:m", user_id="user-1")
        detail = handler.handle(_button(listing, "Fallback scope plan · v2"), user_id="user-1")
        refreshed = handler.handle(_button(detail, "Обновить источники"), user_id="user-1")
        saved_update = handler.handle(
            _button(refreshed, "💾 Сохранить изменения в этот план"), user_id="user-1",
        )
        current = service.get_document(document["document_id"])["document"]
    finally:
        reset_current_tenant_user_id(tenant)

    assert save_prompt["status"] == "PLANNING_TITLE_REQUIRED"
    assert refreshed["status"] == "UNIT_PRICE_SCENARIO_READY"
    assert saved_update["status"] == "PLANNING_DOCUMENT_UPDATED"
    assert current["current_revision"] == 3
    assert current["payload"]["sales_mix"] == mix


def test_fallback_tenant_can_export_compare_and_edit_readiness_in_public_flow(tmp_path):
    saved_runtime, single, source, service = _setup(tmp_path, store_id=None)
    saved_runtime.analytics_export_service = AnalyticsExportService()
    handler = AssistantButtonHandlerService(
        assistant=None, saved_planning_plan_runtime_service=saved_runtime,
        unit_price_calculator_runtime_service=single,
    )
    tenant = set_current_tenant_user_id("user-1")
    try:
        current = _select_single(single)
        saved_runtime.handle_callback(_button(current, "💾 Сохранить план"), user_id="user-1")
        saved = saved_runtime.handle_text("Fallback plan", user_id="user-1")
        document = service.get_document(saved["document_id"])["document"]
        payload = deepcopy(document["payload"])
        payload["items"][0]["inputs"]["cost"] = None
        payload["items"][0]["provenance"].pop("cost", None)
        payload["items"][0]["projection"].update(
            available=False, status="INCOMPLETE_INPUTS", missing_inputs=["cost"],
        )
        payload["sales_mix"] = {
            "period_label": "01.08.2026 - 31.08.2026",
            "quantities": {"sku-1": None}, "expenses": [], "confirmed": True,
        }
        updated = service.repository.save_document(
            title="Fallback plan", payload=payload, owner_id="user-1", store_id="",
            document_id=document["document_id"], expected_revision=1,
            expected_state_revision=document["state_revision"],
            idempotency_key="fallback-readiness-seed",
        )
        assert updated["error"] is False

        other_payload = deepcopy(payload)
        other_payload["items"][0]["inputs"]["price"] = "550"
        second = service.repository.save_document(
            title="Fallback option", payload=other_payload, owner_id="user-1", store_id="",
            idempotency_key="fallback-comparison-seed",
        )
        assert second["error"] is False

        listing = handler.handle("upp:m", user_id="user-1")
        detail = handler.handle(
            _button(listing, "Fallback plan · v2"), user_id="user-1",
        )
        csv_export = handler.handle(
            _button(detail, "Экспорт плана · CSV"), user_id="user-1",
        )
        json_export = handler.handle(
            _button(detail, "Экспорт плана · JSON"), user_id="user-1",
        )
        assert csv_export["error"] is False and csv_export["export_kind"] == "saved_plan"
        assert json_export["error"] is False and json_export["export_kind"] == "saved_plan"

        picker = handler.handle(_button(detail, "Сравнить варианты"), user_id="user-1")
        option_button = next(
            button["callback"] for button in picker["keyboard"]["buttons"]
            if button["text"].startswith("Fallback option ·")
        )
        comparison = handler.handle(option_button, user_id="user-1")
        assert comparison["status"] in {
            "PLANNING_COMPARISON_READY", "PLANNING_COMPARISON_PARTIAL",
        }
        comparison_export = handler.handle(_button(comparison, "CSV"), user_id="user-1")
        assert comparison_export["error"] is False
        assert comparison_export["export_kind"] == "plan_comparison"

        readiness = handler.handle(_button(detail, "Готовность плана"), user_id="user-1")
        edit_button = next(
            button["callback"] for button in readiness["keyboard"]["buttons"]
            if button["text"].startswith("Исправить ·")
        )
        edit_prompt = handler.handle(edit_button, user_id="user-1")
        assert edit_prompt["status"] == "UNIT_PRICE_SCENARIO_INPUT_PENDING"
        edited = handler.handle_text("125", user_id="user-1")
        update_callback = _button(edited, "💾 Сохранить изменения в этот план")
        saved_update = handler.handle(update_callback, user_id="user-1")
        assert saved_update["status"] == "PLANNING_DOCUMENT_UPDATED"
        current_document = service.get_document(document["document_id"])["document"]
        assert current_document["current_revision"] == 3
        assert current_document["store_id"] == ""
        assert current_document["payload"]["items"][0]["inputs"]["cost"] == "125"
        assert current_document["payload"]["sales_mix"]["quantities"]["sku-1"] is None

        latest_listing = handler.handle("upp:m", user_id="user-1")
        latest_detail = handler.handle(
            _button(latest_listing, "Fallback plan · v3"), user_id="user-1",
        )
        latest_readiness = handler.handle(
            _button(latest_detail, "Готовность плана"), user_id="user-1",
        )
        quantity_prompt = handler.handle(
            _button(latest_readiness, "Задать количество · Тестовый товар"), user_id="user-1",
        )
        assert quantity_prompt["status"] == "SALES_MIX_QUANTITY_EDIT_REQUIRED"
        preview = handler.handle_text("0", user_id="user-1")
        confirmed = handler.handle(
            _button(preview, "Подтвердить и сохранить ревизию"), user_id="user-1",
        )
        assert confirmed["status"] == "PLANNING_DOCUMENT_DETAILS"
        final_document = service.get_document(document["document_id"])["document"]
        assert final_document["current_revision"] == 4
        assert final_document["payload"]["sales_mix"]["quantities"]["sku-1"] == 0

        other_scope = set_current_tenant_user_id("user-1::ozon::other-store")
        try:
            other_listing = handler.handle("upp:m", user_id="user-1")
            assert other_listing["status"] == "PLANNING_DOCUMENT_LIST"
            assert "Пока нет сохранённых планов." in other_listing["message"]
        finally:
            reset_current_tenant_user_id(other_scope)
    finally:
        reset_current_tenant_user_id(tenant)
    assert len(source.calls) == 1


def test_single_target_margin_survives_apply_back_save_and_restore(tmp_path):
    saved_runtime, single, source, service = _setup(tmp_path)
    handler = AssistantButtonHandlerService(
        assistant=None, saved_planning_plan_runtime_service=saved_runtime,
        unit_price_calculator_runtime_service=single,
    )
    tenant = _activate()
    try:
        saved_ids = []
        for transition in ("apply", "back"):
            current = _select_single(single)
            prompt = single.handle_callback(
                _button(current, "Цена для целевой маржи") , user_id="user-1",
            )
            result = single.handle_text("25", user_id="user-1")
            assert prompt["status"] == "UNIT_PRICE_SCENARIO_INPUT_PENDING"
            assert result["status"] == "UNIT_PRICE_TARGET_MARGIN_RESULT"
            if transition == "apply":
                current = single.handle_callback(
                    _button(result, "Подставить цену для цели"), user_id="user-1",
                )
            else:
                current = single.handle_callback(
                    _button(result, "Назад к расчёту"), user_id="user-1",
                )
            save_prompt = handler.handle(
                _button(current, "💾 Сохранить план"), user_id="user-1",
            )
            saved = handler.handle_text("Goal " + transition, user_id="user-1")
            assert save_prompt["status"] == "PLANNING_TITLE_REQUIRED"
            assert saved["status"] == "PLANNING_DOCUMENT_SAVED"
            saved_ids.append(saved["document_id"])
            document = service.get_document(saved["document_id"])["document"]
            assert document["payload"]["target_margin_percent"] in {"25", "25.00"}

            listing = handler.handle("upp:m", user_id="user-1")
            detail = handler.handle(
                _button(listing, "Goal " + transition + " · v1"), user_id="user-1",
            )
            cap = handler.handle(
                _button(detail, "Рекламный предел (сохранённые допущения)"), user_id="user-1",
            )
            assert "цель 25%:" in cap["message"]

        # Reopen a saved recipe into a fresh transient session and save a copy;
        # the explicit goal must survive that round trip too.
        listing = handler.handle("upp:m", user_id="user-1")
        detail = handler.handle(_button(listing, "Goal apply · v1"), user_id="user-1")
        restored = handler.handle(
            _button(detail, "Продолжить по сохранённым допущениям"), user_id="user-1",
        )
        save_prompt = handler.handle(
            _button(restored, "💾 Сохранить план"), user_id="user-1",
        )
        copy = handler.handle_text("Goal restored copy", user_id="user-1")
        assert save_prompt["status"] == "PLANNING_TITLE_REQUIRED"
        assert copy["status"] == "PLANNING_DOCUMENT_SAVED"
        copied = service.get_document(copy["document_id"])["document"]
        assert copied["payload"]["target_margin_percent"] in {"25", "25.00"}
        assert len(saved_ids) == 2
    finally:
        reset_current_tenant_user_id(tenant)
    assert len(source.calls) == 2


def test_advertising_target_survives_back_save_restart_and_historical_cap(tmp_path):
    saved_runtime, single, source, service = _setup(tmp_path)
    handler = AssistantButtonHandlerService(
        assistant=None, saved_planning_plan_runtime_service=saved_runtime,
        unit_price_calculator_runtime_service=single,
    )
    tenant = _activate()
    try:
        current = _select_single(single)
        prompt = handler.handle(
            _button(current, "Сколько можно тратить на рекламу?"), user_id="user-1",
        )
        cap = handler.handle_text("25", user_id="user-1")
        returned = handler.handle(_button(cap, "Назад к расчёту"), user_id="user-1")
        save_prompt = handler.handle(
            _button(returned, "💾 Сохранить план"), user_id="user-1",
        )
        saved = handler.handle_text("Advertising target", user_id="user-1")
        document = service.get_document(saved["document_id"])["document"]
        assert document["payload"]["target_margin_percent"] in {"25", "25.00"}

        # The saved target remains available after constructing fresh runtimes,
        # just like a process restart in the user's normal workflow.
        restarted_single = TelegramUnitPriceCalculatorRuntimeService(
            source=source, scenario_service=single.scenario_service,
            keyboard_service=single.keyboard_service,
            target_planning_service=single.target_planning_service,
            advertising_cap_service=single.advertising_cap_service,
        )
        restarted_service = SavedPlanningPlanService(
            PlanningWorkspaceRepository(db_path=service.repository.db_path),
            single.scenario_service,
        )
        restarted_runtime = TelegramSavedPlanningPlanRuntimeService(
            restarted_service, restarted_single, None, single.keyboard_service,
        )
        restarted_handler = AssistantButtonHandlerService(
            assistant=None, saved_planning_plan_runtime_service=restarted_runtime,
        )
        listing = restarted_handler.handle("upp:m", user_id="user-1")
        detail = restarted_handler.handle(
            _button(listing, "Advertising target · v1"), user_id="user-1",
        )
        historical = restarted_handler.handle(
            _button(detail, "Рекламный предел (сохранённые допущения)"), user_id="user-1",
        )
    finally:
        reset_current_tenant_user_id(tenant)

    assert prompt["status"] == "UNIT_PRICE_ADVERTISING_CAP_TARGET_REQUIRED"
    assert cap["status"] == "UNIT_PRICE_ADVERTISING_CAP_RESULT"
    assert returned["status"] == "UNIT_PRICE_SCENARIO_READY"
    assert save_prompt["status"] == "PLANNING_TITLE_REQUIRED"
    assert saved["status"] == "PLANNING_DOCUMENT_SAVED"
    assert historical["status"] == "PLANNING_HISTORICAL_ADVERTISING_CAP"
    assert "цель 25%:" in historical["message"]
    assert source.calls == [("sku-1", "user-1", False)]


def test_latest_advertising_target_overrides_price_goal_and_is_saved_in_update(tmp_path):
    saved_runtime, single, _source, service = _setup(tmp_path)
    handler = AssistantButtonHandlerService(
        assistant=None, saved_planning_plan_runtime_service=saved_runtime,
        unit_price_calculator_runtime_service=single,
    )
    tenant = _activate()
    try:
        current = _select_single(single)
        price_prompt = handler.handle(
            _button(current, "Цена для целевой маржи"), user_id="user-1",
        )
        price_result = handler.handle_text("25", user_id="user-1")
        returned = handler.handle(
            _button(price_result, "Назад к расчёту"), user_id="user-1",
        )
        ad_prompt = handler.handle(
            _button(returned, "Сколько можно тратить на рекламу?"), user_id="user-1",
        )
        ad_result = handler.handle_text("30", user_id="user-1")
        applied = handler.handle(
            _button(ad_result, "Подставить предел целевой маржи"), user_id="user-1",
        )
        save_prompt = handler.handle(
            _button(applied, "💾 Сохранить план"), user_id="user-1",
        )
        saved = handler.handle_text("Latest target", user_id="user-1")
        initial = service.get_document(saved["document_id"])["document"]

        listing = handler.handle("upp:m", user_id="user-1")
        detail = handler.handle(
            _button(listing, "Latest target · v1"), user_id="user-1",
        )
        refreshed = handler.handle(
            _button(detail, "Обновить источники"), user_id="user-1",
        )
        update = handler.handle(
            _button(refreshed, "💾 Сохранить изменения в этот план"), user_id="user-1",
        )
        final = service.get_document(saved["document_id"])["document"]
    finally:
        reset_current_tenant_user_id(tenant)

    assert price_prompt["status"] == "UNIT_PRICE_SCENARIO_INPUT_PENDING"
    assert price_result["status"] == "UNIT_PRICE_TARGET_MARGIN_RESULT"
    assert ad_prompt["status"] == "UNIT_PRICE_ADVERTISING_CAP_TARGET_REQUIRED"
    assert ad_result["status"] == "UNIT_PRICE_ADVERTISING_CAP_RESULT"
    assert applied["status"] == "UNIT_PRICE_SCENARIO_READY"
    assert initial["payload"]["target_margin_percent"] in {"30", "30.00"}
    assert refreshed["status"] == "UNIT_PRICE_SCENARIO_READY"
    assert update["status"] == "PLANNING_DOCUMENT_UPDATED"
    assert update["revision"] == 2
    assert final["payload"]["target_margin_percent"] in {"30", "30.00"}


@pytest.mark.parametrize(
    ("changed_identity_field", "expected_code"),
    [
        ("product_id", "UNIT_PRICE_SCENARIO_IDENTITY_CHANGED"),
        ("offer_id", "UNIT_PRICE_SCENARIO_IDENTITY_CHANGED"),
        ("store_id", None),
    ],
)
def test_saved_single_refresh_rejects_identity_change_without_transferring_cost(
    tmp_path, changed_identity_field, expected_code,
):
    saved_runtime, single, source, service = _setup(tmp_path)
    handler = AssistantButtonHandlerService(
        assistant=None, saved_planning_plan_runtime_service=saved_runtime,
        unit_price_calculator_runtime_service=single,
    )
    tenant = _activate()
    try:
        current = _select_single(single)
        cost_prompt = handler.handle(_button(current, "Себестоимость"), user_id="user-1")
        cost_entry = handler.handle_text("125", user_id="user-1")
        save_prompt = handler.handle(
            _button(cost_entry, "💾 Сохранить план"), user_id="user-1",
        )
        saved = handler.handle_text("Identity guard", user_id="user-1")
        before = service.get_document(saved["document_id"])["document"]

        if changed_identity_field in {"product_id", "offer_id"}:
            setattr(source.product_service, changed_identity_field, "new-" + changed_identity_field)
        else:
            source.store_id = "store-b"
        listing = handler.handle("upp:m", user_id="user-1")
        detail = handler.handle(
            _button(listing, "Identity guard · v1"), user_id="user-1",
        )
        refreshed = handler.handle(
            _button(detail, "Обновить источники"), user_id="user-1",
        )
        after = service.get_document(saved["document_id"])["document"]
    finally:
        reset_current_tenant_user_id(tenant)

    assert cost_prompt["status"] == "UNIT_PRICE_SCENARIO_INPUT_PENDING"
    assert save_prompt["status"] == "PLANNING_TITLE_REQUIRED"
    assert saved["status"] == "PLANNING_DOCUMENT_SAVED"
    if expected_code is None:
        assert refreshed["status"] == "UNIT_PRICE_SCENARIO_STALE"
    else:
        assert refreshed["error"] is True
        assert refreshed["code"] == expected_code
    assert after["current_revision"] == before["current_revision"] == 1
    assert after["payload"]["items"][0]["identity"] == before["payload"]["items"][0]["identity"]
    assert after["payload"]["items"][0]["inputs"]["cost"] == "125"
    assert len(source.calls) == 2


def test_saved_context_rejects_changed_identity_without_sales_mix():
    old_identity = {
        "product_id": "product-1", "offer_id": "offer-1", "sku": "sku-1",
        "store_id": "store-a",
    }
    new_identity = {**old_identity, "product_id": "product-new"}
    document = {
        "payload": {"plan_kind": "single", "items": [{
            "row_id": "sku-1", "identity": old_identity,
        }]},
    }
    capture = {"payload": {"plan_kind": "single", "items": [{
        "row_id": "sku-1", "identity": new_identity,
    }]}}

    result = TelegramSavedPlanningPlanRuntimeService._preserve_saved_plan_context(
        document, capture,
    )

    assert result["error"] is True
    assert result["code"] == "PLANNING_PLAN_IDENTITY_CHANGED"
