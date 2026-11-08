from datetime import datetime, timezone
from types import SimpleNamespace

from cryptography.fernet import Fernet

from services.fifo_cost_history_service import FifoCostHistoryService
from services.fifo_cost_repository import FifoCostRepository
from services.fifo_cost_transition_service import FifoCostTransitionService
from services.fifo_cost_transition_review_service import FifoCostTransitionReviewService
from services.fifo_cost_report_import_service import FifoCostReportImportService
from services.fifo_cost_stock_management_import_service import FifoCostStockManagementImportService
from services.fifo_cost_transition_contracts import (
    EvidenceCompleteness,
    EvidenceSourceKind,
    PeriodProvenance,
    ReportEvidence,
    ReportType,
    ScopeIdentity,
    TransitionMetadata,
)
from services.ozon_account_repository import make_store_tenant_scope
from services.telegram_fifo_cost_history_service import TelegramFifoCostHistoryService
from services.telegram_fifo_cost_report_import_service import TelegramFifoCostReportImportService
from services.telegram_fifo_cost_transition_runtime_service import (
    TelegramFifoCostTransitionRuntimeService,
)
from services.tenant_context import reset_current_tenant_user_id, set_current_tenant_user_id


IDENTITY = {
    "store_id": "store-a",
    "product_id": "product-101",
    "offer_id": "hook-2",
    "sku": "3921245627",
}


def _services(tmp_path):
    now = lambda: datetime(2026, 11, 8, 12, tzinfo=timezone.utc)
    repository = FifoCostRepository(
        db_path=tmp_path / "telegram-fifo-transition-runtime.sqlite",
        now_provider=now,
    )
    history = FifoCostHistoryService(repository)
    transitions = FifoCostTransitionService(repository, now_provider=now)
    report_import = TelegramFifoCostReportImportService(repository=repository)
    runtime = TelegramFifoCostTransitionRuntimeService(
        transitions,
        history,
        report_import,
        now_provider=now,
    )
    return repository, history, transitions, report_import, runtime


def _confirm_text(runtime, text):
    preview = runtime.handle_text(101, text)
    assert preview["error"] is False, preview
    confirm = preview["keyboard"]["buttons"][0]["callback"]
    assert len(confirm.encode("utf-8")) <= 64
    return runtime.handle_callback(101, confirm)


def _complete_owner_inputs(runtime):
    messages = []
    for value in ("21", "14.65", "05.11.2026", "0", "0", "6982"):
        response = _confirm_text(runtime, value)
        assert response["error"] is False, response
        messages.append(response)
    return messages[-1]


def test_transition_wizard_saves_confirmed_fields_and_resumes_after_runtime_restart(tmp_path):
    tenant = set_current_tenant_user_id(make_store_tenant_scope("owner-a", "store-a"))
    try:
        repository, history, transitions, report_import, runtime = _services(tmp_path)
        card_service = TelegramFifoCostHistoryService(
            history, transition_service=transitions,
        )
        sku_ticket = card_service.create_sku_callback(
            user_id=101, **IDENTITY, display_name="Крючки",
        )
        card = card_service.handle_callback(101, sku_ticket["callback"])
        late = next(
            item["callback"] for item in card["keyboard"]["buttons"]
            if item["callback"].startswith("fifo_history:late:")
        )
        mode_prompt = card_service.handle_callback(101, late)
        total_mode = next(
            item["callback"] for item in mode_prompt["keyboard"]["buttons"]
            if item["callback"].startswith("fifo_history:late_total:")
        )
        mode_action = card_service.handle_callback(101, total_mode)
        assert mode_action["action"] == "start_transition_wizard"
        assert mode_action["cost_input_mode"] == "TOTAL_LANDED"

        started = runtime.start_new_case(
            101,
            mode_action["identity"],
            mode_action["display_name"],
            mode_action["expected_revision"],
            mode_action["cost_input_mode"],
        )
        assert "старую итоговую себестоимость" in started["message"].lower()
        last = _complete_owner_inputs(runtime)
        assert "Всего новой партии: 6982 шт." in last["message"]
        assert "остаётся неизвестным" in last["message"]

        listed = transitions.list_cases(store_id="store-a", sku=IDENTITY["sku"])
        case_item = listed["cases"][0]
        case = case_item["case"]
        assert case_item["state"] == "AWAITING_EVIDENCE"
        assert case_item["case_revision"] == 7
        assert case["old_unit_cost_rub"] == "21.00"
        assert case["new_unit_cost_rub"] == "14.65"
        assert case["dispatch_date"] == "2026-11-05"
        assert case["owner_old_home_units"] == 0
        assert case["owner_old_transit_units"] == 0
        assert case["declared_shipped_units"] == 6982
        assert case["new_home_quantity"] is None
        assert case["cost_components"] is None

        restarted = TelegramFifoCostTransitionRuntimeService(
            transitions, history, report_import,
            now_provider=lambda: datetime(2026, 11, 8, 12, tzinfo=timezone.utc),
        )
        assert restarted.handle_text(101, "999") == {
            "error": False, "handled": False, "read_only_ozon": True,
        }
        resumed = restarted.resume_case(
            101,
            identity=IDENTITY,
            display_name="Крючки",
            case_id=case_item["case_id"],
            expected_case_revision=7,
        )
        assert "Сведения о партии сохранены" in resumed["message"]
        assert history.get_sku_history(**IDENTITY)["queue_initialized"] is False
    finally:
        reset_current_tenant_user_id(tenant)


def test_components_mode_saves_exact_total_without_inventing_components(tmp_path):
    tenant = set_current_tenant_user_id(make_store_tenant_scope("owner-a", "store-a"))
    try:
        _repository, _history, transitions, _reports, runtime = _services(tmp_path)
        started = runtime.start_new_case(101, IDENTITY, "Крючки", 0, "COMPONENTS")
        assert "старую итоговую себестоимость" in started["message"].lower()
        component_prompt = _confirm_text(runtime, "21")
        assert "закупочную стоимость" in component_prompt["message"].lower()
        delivery = runtime.handle_text(101, "10")
        assert "доставка" in delivery["message"].lower()
        packaging = runtime.handle_text(101, "3")
        assert "упаковка" in packaging["message"].lower()
        preview = runtime.handle_text(101, "1.65")
        assert "10.00 + доставка 3.00 + упаковка 1.65 = 14.65" in preview["message"]
        saved = runtime.handle_callback(101, preview["keyboard"]["buttons"][0]["callback"])
        assert saved["error"] is False, saved

        case_item = transitions.list_cases(store_id="store-a", sku=IDENTITY["sku"])["cases"][0]
        case = case_item["case"]
        assert case["cost_input_mode"] == "COMPONENTS"
        assert case["new_unit_cost_rub"] == "14.65"
        assert case["cost_components"] == {
            "purchase_cost_rub": "10.00",
            "delivery_cost_rub": "3.00",
            "packaging_cost_rub": "1.65",
        }
        assert case["case_revision"] == 3
    finally:
        reset_current_tenant_user_id(tenant)


def test_confirmed_supply_declarations_are_typed_and_report_import_is_case_bound(tmp_path):
    tenant = set_current_tenant_user_id(make_store_tenant_scope("101", "store-a"))
    try:
        _repository, history, transitions, report_import, runtime = _services(tmp_path)
        runtime.start_new_case(101, IDENTITY, "Крючки", 0, "TOTAL_LANDED")
        _complete_owner_inputs(runtime)

        totals = (("ORDER", "supply_order", "6234"), ("ORDER", "supply_order", "600"), ("SUPPLY", "supply_supply", "148"))
        references = ("700001", "700002", "700003")
        for (reference_kind, callback_suffix, units), reference in zip(totals, references):
            stage = runtime._show_supply_stage("101")
            add_callback = next(
                item["callback"] for item in stage["keyboard"]["buttons"]
                if item["text"] == "📦 Добавить поставку"
            )
            kind_prompt = runtime.handle_callback(101, add_callback)
            kind_callback = next(
                item["callback"] for item in kind_prompt["keyboard"]["buttons"]
                if item["callback"].startswith(f"fifo_transition:{callback_suffix}:")
            )
            id_prompt = runtime.handle_callback(101, kind_callback)
            quantity_prompt = runtime.handle_text(101, reference)
            assert "количество" in quantity_prompt["message"].lower()
            confirm_prompt = runtime.handle_text(101, units)
            confirm_callback = confirm_prompt["keyboard"]["buttons"][0]["callback"]
            assert reference not in confirm_callback
            saved = runtime.handle_callback(101, confirm_callback)
            assert saved["error"] is False, saved

        case_item = transitions.list_cases(
            store_id="store-a", sku=IDENTITY["sku"],
        )["cases"][0]
        manifest = transitions.get_supply_manifest(
            case_id=case_item["case_id"], **IDENTITY,
        )
        assert manifest["owner_declared_total"] == 6982
        assert manifest["known_assigned_units"] == 6982
        assert manifest["undistributed_units"] == 0
        assert len(manifest["declarations"]) == 3
        assert all("reference_id" not in item for item in manifest["declarations"])

        stage = runtime._show_supply_stage("101")
        skip = next(
            item["callback"] for item in stage["keyboard"]["buttons"]
            if item["text"] == "Продолжить без списка поставок"
        )
        documents = runtime.handle_callback(101, skip)
        report_callback = next(
            item["callback"] for item in documents["keyboard"]["buttons"]
            if item["text"] == "📄 Добавить оборотную ведомость"
        )
        selection = runtime.handle_callback(101, report_callback)
        choose_case = selection["keyboard"]["buttons"][0]["callback"]
        assert len(choose_case.encode("utf-8")) <= 64
        assert "case_" not in choose_case
        selected = report_import.handle_callback(101, choose_case)
        assert "Теперь отправьте соответствующий XLSX" in selected["message"]
    finally:
        reset_current_tenant_user_id(tenant)


def test_unconfirmed_value_and_cross_store_callback_never_write_transition_case(tmp_path):
    tenant = set_current_tenant_user_id(make_store_tenant_scope("owner-a", "store-a"))
    try:
        _repository, history, transitions, _reports, runtime = _services(tmp_path)
        started = runtime.start_new_case(101, IDENTITY, "Крючки", 0, "TOTAL_LANDED")
        candidate = runtime.handle_text(101, "21")
        confirm = candidate["keyboard"]["buttons"][0]["callback"]
        store_b = set_current_tenant_user_id(make_store_tenant_scope("owner-a", "store-b"))
        try:
            rejected_text = runtime.handle_text(101, "99")
            rejected = runtime.handle_callback(101, confirm)
        finally:
            reset_current_tenant_user_id(store_b)

        case_item = transitions.list_cases(store_id="store-a", sku=IDENTITY["sku"])["cases"][0]
        assert rejected_text["error"] is True
        assert rejected["error"] is True
        assert case_item["case_revision"] == 1
        assert case_item["case"]["old_unit_cost_rub"] is None
        assert history.get_sku_history(**IDENTITY)["queue_initialized"] is False
    finally:
        reset_current_tenant_user_id(tenant)


def test_distinct_review_actions_fail_closed_before_ready_and_do_not_write(tmp_path):
    tenant = set_current_tenant_user_id(make_store_tenant_scope("owner-a", "store-a"))
    try:
        _repository, history, transitions, report_import, runtime = _services(tmp_path)
        runtime.review_service = FifoCostTransitionReviewService(transitions, history)
        runtime.start_new_case(101, IDENTITY, "Крючки", 0, "TOTAL_LANDED")
        _complete_owner_inputs(runtime)
        case_id = runtime._sessions["101"]["case_id"]
        scope = ScopeIdentity(
            owner_id="owner-a", store_id=IDENTITY["store_id"],
            product_id=IDENTITY["product_id"], offer_id=IDENTITY["offer_id"],
            sku=IDENTITY["sku"],
        )
        file_digest = "b" * 64
        stock_report = ReportEvidence(
            metadata=TransitionMetadata(
                scope=scope, source_kind=EvidenceSourceKind.OWNER_IMPORTED,
                completeness=EvidenceCompleteness.PARTIAL,
                source_fingerprint=FifoCostStockManagementImportService._source_fingerprint(
                    file_digest, scope,
                ),
            ),
            report_type=ReportType.STOCK_MANAGEMENT,
            period_from="2026-11-07", period_to="2026-11-07",
            period_provenance=PeriodProvenance.OWNER_CONFIRMED,
            captured_at="2026-11-08T12:00:00Z", file_sha256=file_digest,
            parser_version="fifo-stock-management-v1", cell_references=("M5",),
            normalized_fields={"stock_buckets": {"available": 1191}},
        )
        saved_report = transitions.repository.append_report_evidence(
            case_id=case_id, report=stock_report, expected_case_revision=7,
            idempotency_key="telegram-preview-stock-report",
        )
        assert saved_report["error"] is False, saved_report
        runtime.resume_case(
            101, identity=IDENTITY, display_name="Крючки", case_id=case_id,
            expected_case_revision=saved_report["case_revision"],
        )
        before = transitions.list_cases(store_id="store-a", sku=IDENTITY["sku"])["cases"][0]

        summary = runtime._show_summary("101")
        labels = {item["text"] for item in summary["keyboard"]["buttons"]}
        assert "🔄 Обновить данные поставок" in labels
        assert "📄 Добавить отчёт" in labels
        assert "🔍 Проверить готовность" in labels
        assert "📊 Посмотреть пересчёт" in labels
        assert "✅ Применить подтверждённую историю" not in labels

        readiness_callback = next(
            item["callback"] for item in summary["keyboard"]["buttons"]
            if item["text"] == "🔍 Проверить готовность"
        )
        readiness = runtime.handle_callback(101, readiness_callback)
        assert "Можно применить: нет" in readiness["message"]
        preview_callback = next(
            item["callback"] for item in readiness["keyboard"]["buttons"]
            if item["text"] == "📊 Посмотреть пересчёт"
        )
        preview = runtime.handle_callback(101, preview_callback)
        assert "Подтверждённый FIFO cutoff: отсутствует" in preview["message"]
        assert "Старая очередь FIFO не инициализирована" in preview["message"]
        assert "Новая стоимость введена итогом; разбивка компонентов отсутствует" in preview["message"]
        assert "Изменение себестоимости новой партии к старой: -6.35 ₽/шт." in preview["message"]
        assert "Подтверждённые данные источников до" in readiness["message"]
        assert "Кандидатные данные до" in readiness["message"]
        assert "Срезы остатков: 1" in preview["message"]
        assert "период OWNER_CONFIRMED" in preview["message"]
        assert "снимок 2026-11-08" in preview["message"]
        assert "прибыли" in preview["message"].lower()

        apply_calls = []
        runtime.apply_service = SimpleNamespace(apply=lambda **kwargs: apply_calls.append(kwargs))
        forged_apply = runtime._issue_ticket(
            "101", runtime._sessions["101"], "apply_transition",
        )
        denied_apply = runtime.handle_callback(101, forged_apply)
        assert denied_apply["error"] is True
        assert "нет актуального READY" in denied_apply["message"]
        assert apply_calls == []

        after = transitions.list_cases(store_id="store-a", sku=IDENTITY["sku"])["cases"][0]
        assert after["case_revision"] == before["case_revision"] == 8
        assert after["state"] == "AWAITING_EVIDENCE"
        assert history.get_sku_history(**IDENTITY)["queue_initialized"] is False
    finally:
        reset_current_tenant_user_id(tenant)


def test_components_cost_mode_preview_shows_components_without_reinterpreting_profit(tmp_path):
    tenant = set_current_tenant_user_id(make_store_tenant_scope("owner-a", "store-a"))
    try:
        _repository, history, transitions, _report_import, runtime = _services(tmp_path)
        runtime.review_service = FifoCostTransitionReviewService(transitions, history)
        runtime.start_new_case(101, IDENTITY, "Крючки", 0, "COMPONENTS")
        _confirm_text(runtime, "21")
        assert "Доставка до вас" in runtime.handle_text(101, "10")["message"]
        assert "Упаковка" in runtime.handle_text(101, "3")["message"]
        _confirm_text(runtime, "1.65")
        for value in ("05.11.2026", "0", "0", "6982"):
            _confirm_text(runtime, value)
        readiness = runtime._show_readiness("101")
        preview_callback = next(
            item["callback"] for item in readiness["keyboard"]["buttons"]
            if item["text"] == "📊 Посмотреть пересчёт"
        )
        preview = runtime.handle_callback(101, preview_callback)
        assert "Новая стоимость · ввод владельца: 14.65 ₽/шт. · режим COMPONENTS" in preview["message"]
        assert "Компоненты новой стоимости: закупка 10.00 + доставка 3.00 + упаковка 1.65 ₽/шт." in preview["message"]
        assert "Это разница затрат, не расчёт прибыли." in preview["message"]
        assert "Влияние на фактическую прибыль пока не рассчитано" in preview["message"]
    finally:
        reset_current_tenant_user_id(tenant)


def test_ready_case_can_be_reopened_after_restart_as_read_only_summary():
    tenant = set_current_tenant_user_id(make_store_tenant_scope("owner-a", "store-a"))
    try:
        class ReadyTransitions:
            def get_case(self, *, case_id, **identity):
                return {
                    "error": False,
                    "case_id": case_id,
                    "case_revision": 9,
                    "state": "READY_TO_CONFIRM",
                    "case": {"metadata": {"scope": dict(identity)}},
                }

        runtime = TelegramFifoCostTransitionRuntimeService(
            ReadyTransitions(), history_service=None,
        )
        summary_calls = []
        runtime._show_summary = lambda owner: summary_calls.append(owner) or {
            "error": False, "message": "sealed READY summary",
        }

        result = runtime.resume_case(
            101,
            identity=IDENTITY,
            display_name="Крючки",
            case_id="case-ready-restart",
            expected_case_revision=9,
        )

        assert result["message"] == "sealed READY summary"
        assert summary_calls == ["101"]
        session = runtime._sessions["101"]
        assert session["state"] == "READY_TO_CONFIRM"
        assert "step" not in session
    finally:
        reset_current_tenant_user_id(tenant)


def test_supply_refresh_picker_is_paginated_and_callback_has_no_reference_ids(tmp_path):
    tenant = set_current_tenant_user_id(make_store_tenant_scope("owner-a", "store-a"))
    try:
        _repository, _history, transitions, _report_import, runtime = _services(tmp_path)
        runtime.start_new_case(101, IDENTITY, "Крючки", 0, "TOTAL_LANDED")
        current = transitions.list_cases(store_id="store-a", sku=IDENTITY["sku"])["cases"][0]
        case_id = current["case_id"]
        revision = current["case_revision"]
        references = [str(700100 + index) for index in range(10)]
        for reference in references:
            created = transitions.declare_supply(
                case_id=case_id, **IDENTITY, reference_kind="SUPPLY",
                reference_id=reference, declared_shipped_units=1,
                expected_case_revision=revision,
                idempotency_key=f"tg-refresh-page-{reference}",
            )
            assert created["error"] is False, created
            revision = created["case_revision"]
        assert runtime.resume_case(
            101, identity=IDENTITY, display_name="Крючки", case_id=case_id,
            expected_case_revision=revision,
        )["error"] is False

        first = runtime._refresh_supplies_prompt("101", page=0)
        first_buttons = first["keyboard"]["buttons"]
        assert len(first_buttons) == 9
        assert "страница 1 из 2" in first["message"]
        assert all(reference not in first["message"] for reference in references)
        assert all(reference not in button["callback"] for button in first_buttons for reference in references)
        assert all(len(button["callback"].encode("utf-8")) <= 64 for button in first_buttons)
        next_page = next(button["callback"] for button in first_buttons if button["text"] == "➡️ Далее")

        second = runtime.handle_callback(101, next_page)
        second_buttons = second["keyboard"]["buttons"]
        assert "страница 2 из 2" in second["message"]
        assert len(second_buttons) == 3
        assert [button["text"] for button in second_buttons][-1] == "⬅️ Назад"
        previous_page = second_buttons[-1]["callback"]
        back = runtime.handle_callback(101, previous_page)
        assert "страница 1 из 2" in back["message"]
    finally:
        reset_current_tenant_user_id(tenant)


def test_supply_refresh_requires_exact_declared_id_and_never_exposes_it(tmp_path, monkeypatch):
    tenant = set_current_tenant_user_id(make_store_tenant_scope("owner-a", "store-a"))
    monkeypatch.setenv("OZON_CREDENTIAL_MASTER_KEY", Fernet.generate_key().decode("ascii"))
    try:
        _repository, history, transitions, report_import, runtime = _services(tmp_path)
        class FakeRefresh:
            def __init__(self):
                self.calls = []

            def refresh(self, **kwargs):
                self.calls.append(kwargs)
                return SimpleNamespace(
                    status="COMPLETE", source_status="COMPLETE",
                    actual_http_attempts=2, http_attempt_cap=10,
                    elapsed_seconds=0.1, case_revision=8,
                    source_fingerprint="a" * 64, issue_codes=(),
                    status_snapshot=None, act_snapshot=None,
                    continuation_token=None,
                )

        fake_refresh = FakeRefresh()
        runtime.supply_refresh_service = fake_refresh
        runtime.start_new_case(101, IDENTITY, "Крючки", 0, "TOTAL_LANDED")
        _complete_owner_inputs(runtime)
        case_id = runtime._sessions["101"]["case_id"]
        saved = transitions.declare_supply(
            case_id=case_id, **IDENTITY,
            reference_kind="SUPPLY", reference_id="700003",
            declared_shipped_units=6982, dispatch_date="2026-11-05",
            expected_case_revision=7, idempotency_key="tg-refresh-supply-1",
        )
        assert saved["error"] is False, saved
        opened = runtime.resume_case(
            101, identity=IDENTITY, display_name="Крючки", case_id=case_id,
            expected_case_revision=saved["case_revision"],
        )
        summary = runtime._show_summary("101")
        refresh_callback = next(
            item["callback"] for item in summary["keyboard"]["buttons"]
            if item["text"] == "🔄 Обновить данные поставок"
        )
        choose = runtime.handle_callback(101, refresh_callback)
        select = choose["keyboard"]["buttons"][0]["callback"]
        assert "700003" not in select
        prompt = runtime.handle_callback(101, select)
        assert "700003" not in prompt["message"]

        rejected = runtime.handle_text(101, "700004")
        assert "Ozon не запрашивался" in rejected["message"]
        assert fake_refresh.calls == []

        refreshed = runtime.handle_text(101, "700003")
        assert fake_refresh.calls[0]["reference_id"] == "700003"
        assert "700003" not in refreshed["message"]
        assert "COMPLETE" in refreshed["message"]
        assert history.get_sku_history(**IDENTITY)["queue_initialized"] is False
    finally:
        reset_current_tenant_user_id(tenant)
