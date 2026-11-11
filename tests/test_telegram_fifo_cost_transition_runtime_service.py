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
    StockBucket,
    TransitionMetadata,
    source_fingerprint,
)
from services.fifo_cost_physical_sales_evidence_service import (
    FifoCostPhysicalSalesEvidenceService,
)
from services.fifo_cost_physical_sales_import_service import (
    FifoCostPhysicalSalesImportService,
)
from services.ozon_account_repository import make_store_tenant_scope
from services.telegram_fifo_cost_history_service import TelegramFifoCostHistoryService
from services.telegram_fifo_cost_report_import_service import TelegramFifoCostReportImportService
from services.telegram_fifo_cost_physical_sales_import_service import (
    TelegramFifoCostPhysicalSalesImportService,
)
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


def test_owner_can_confirm_cutoff_receiving_quantity_without_adding_fifo_units(
    tmp_path, monkeypatch,
):
    monkeypatch.setenv(
        "OZON_CREDENTIAL_MASTER_KEY", Fernet.generate_key().decode("ascii"),
    )
    tenant = set_current_tenant_user_id(make_store_tenant_scope("owner-a", "store-a"))
    try:
        repository, history, transitions, _report_import, runtime = _services(tmp_path)
        started = runtime.start_new_case(101, IDENTITY, "Крючки", 0, "TOTAL_LANDED")
        assert "старую итоговую себестоимость" in started["message"].lower()
        _complete_owner_inputs(runtime)
        listed = transitions.list_cases(store_id="store-a", sku=IDENTITY["sku"])
        case_item = listed["cases"][0]
        case = transitions._case_from_payload(case_item["case"])
        stock_buckets = {bucket.value: 0 for bucket in StockBucket}
        stock_buckets.update({
            "available": 100,
            "reserved": 0,
            "supplier_receiving": None,
        })
        stock_report = ReportEvidence(
            metadata=TransitionMetadata(
                scope=case.metadata.scope,
                source_kind=EvidenceSourceKind.OWNER_IMPORTED,
                completeness=EvidenceCompleteness.COMPLETE,
                source_fingerprint=source_fingerprint("runtime-owner-stock"),
                store_timezone="Europe/Moscow",
            ),
            report_type=ReportType.STOCK_MANAGEMENT,
            period_from="2026-11-06",
            period_to="2026-11-06",
            period_provenance=PeriodProvenance.OWNER_CONFIRMED,
            captured_at="2026-11-07T18:00:00Z",
            file_sha256=source_fingerprint("runtime-owner-stock-file"),
            parser_version="stock-test-v1",
            cell_references=("A1",),
            normalized_fields={
                "stock_buckets": stock_buckets,
                "fbs_return_available_units": 0,
                "fbs_return_is_subset_of_available": True,
            },
        )
        saved_report = repository.append_report_evidence(
            case_id=case.case_id, report=stock_report,
            expected_case_revision=case_item["case_revision"],
            idempotency_key="runtime-owner-stock-report-1",
        )
        assert saved_report.get("error") is False, saved_report

        summary = runtime._show_summary("101")
        receiving_button = next(
            item["callback"] for item in summary["keyboard"]["buttons"]
            if item["text"] == "📦 Указать число на приёмке"
        )
        report_choices = runtime.handle_callback(101, receiving_button)
        report_choice = next(
            item["callback"] for item in report_choices["keyboard"]["buttons"]
            if item["text"].startswith("📅 2026-11-06")
        )
        quantity_prompt = runtime.handle_callback(101, report_choice)
        assert "ручное подтверждение владельца" in quantity_prompt["message"].lower()
        assert "не добавится к fifo-слоям" in quantity_prompt["message"].lower()

        invalid = runtime.handle_text(101, "не знаю")
        assert "введите точное целое число" in invalid["message"].lower()
        assert transitions.get_case(case_id=case.case_id, **IDENTITY)["case_revision"] == (
            saved_report["case_revision"]
        )
        preview = runtime.handle_text(101, "148")
        assert "не значение, полученное от ozon" in preview["message"].lower()
        assert "не войдёт в принятое fifo-наличие" in preview["message"].lower()
        confirmed = runtime.handle_callback(
            101, preview["keyboard"]["buttons"][0]["callback"],
        )
        assert confirmed.get("error") is False, confirmed
        assert "ручное подтверждение владельца" in confirmed["message"].lower()
        assert "148 шт." in confirmed["message"]

        cutoff = transitions.read_confirmed_cutoff_selection(
            case_id=case.case_id, **IDENTITY,
        )
        assert cutoff.get("error") is False, cutoff
        assert cutoff["descriptor"]["cutoff_date"] == "2026-11-06"
        assert cutoff["stock_report_fingerprint"] == stock_report.file_sha256
        assert cutoff["owner_confirmed_supplier_receiving_units"] == 148
        assert history.get_sku_history(**IDENTITY)["queue_initialized"] is False
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


def test_physical_sales_document_is_selected_previewed_saved_and_confirmed_separately(tmp_path, monkeypatch):
    monkeypatch.setenv("OZON_CREDENTIAL_MASTER_KEY", Fernet.generate_key().decode("ascii"))
    tenant = set_current_tenant_user_id(make_store_tenant_scope("101", "store-a"))
    try:
        repository, history, transitions, report_import, _runtime = _services(tmp_path)

        class Worker:
            def parse_physical_sales(self, *, filename, payload, scope):
                return FifoCostPhysicalSalesImportService().parse_csv(
                    filename=filename, payload=payload, scope=scope,
                )

        physical_import = TelegramFifoCostPhysicalSalesImportService(
            repository=repository,
            worker=Worker(),
            evidence_service=FifoCostPhysicalSalesEvidenceService(),
            now_provider=lambda: datetime(2026, 11, 9, 12, tzinfo=timezone.utc),
        )
        runtime = TelegramFifoCostTransitionRuntimeService(
            transitions, history, report_import,
            physical_sales_import_service=physical_import,
            now_provider=lambda: datetime(2026, 11, 9, 12, tzinfo=timezone.utc),
        )
        runtime.start_new_case(101, IDENTITY, "Крючки", 0, "TOTAL_LANDED")
        _complete_owner_inputs(runtime)
        supply_stage = runtime._show_supply_stage("101")
        skip = next(
            item["callback"] for item in supply_stage["keyboard"]["buttons"]
            if item["text"] == "Продолжить без списка поставок"
        )
        documents = runtime.handle_callback(101, skip)
        action = next(
            item["callback"] for item in documents["keyboard"]["buttons"]
            if item["text"].startswith("🧾 Добавить подтверждение физических продаж")
        )
        selected = runtime.handle_callback(101, action)
        assert selected["code"] == "FIFO_PHYSICAL_SALES_UPLOAD_SELECTED"
        assert runtime.has_physical_sales_document_selection(101) is True

        bad_file = runtime.preflight_physical_sales_document(
            101, "wrong.xlsx", 200,
        )
        assert bad_file["selected"] is True and bad_file["accepted"] is not True
        case_before = transitions.get_case(
            case_id=runtime._sessions["101"]["case_id"], **IDENTITY,
        )
        assert case_before["case_revision"] == 7

        content = (
            FifoCostPhysicalSalesImportService.TEMPLATE_HEADER + "\r\n"
            "posting-111;3921245627;2;2026-11-05;source-row-1\r\n"
            "posting-222;3921245627;3;2026-11-06;source-row-2\r\n"
        ).encode("utf-8")
        preflight = runtime.preflight_physical_sales_document(
            101, "physical-sales.csv", len(content),
        )
        assert preflight["accepted"] is True
        preview = runtime.handle_physical_sales_document(
            101, content, "physical-sales.csv",
        )
        assert preview["code"] == "FIFO_PHYSICAL_SALES_PREVIEW_READY"
        assert "Строк: 2 · единиц: 5" in preview["message"]
        assert "PARTIAL" in preview["message"]
        assert "posting-111" not in preview["message"]
        save_callback = preview["keyboard"]["buttons"][0]["callback"]
        assert len(save_callback.encode("utf-8")) <= 64
        assert "case_" not in save_callback and "posting-111" not in save_callback

        saved = runtime.handle_physical_sales_callback(101, save_callback)
        assert saved["code"] == "FIFO_PHYSICAL_SALES_DOCUMENT_SAVED", saved
        assert saved["error"] is False
        assert "Теперь отдельно подтвердите" in saved["message"]
        confirm_callback = saved["keyboard"]["buttons"][0]["callback"]
        assert len(confirm_callback.encode("utf-8")) <= 64
        assert "case_" not in confirm_callback and "posting-111" not in confirm_callback
        after_save = transitions.get_case(
            case_id=runtime._sessions["101"]["case_id"], **IDENTITY,
        )
        assert after_save["case_revision"] == 8
        assert after_save["state"] == "AWAITING_EVIDENCE"

        confirmed = runtime.handle_physical_sales_callback(101, confirm_callback)
        assert confirmed["code"] == "FIFO_PHYSICAL_SALES_CONFIRMED", confirmed
        assert "полнота всех продаж и движений" in confirmed["message"]
        replayed = runtime.handle_physical_sales_callback(101, confirm_callback)
        assert replayed["error"] is False and replayed["replayed"] is True
        after_confirm = transitions.get_case(
            case_id=runtime._sessions["101"]["case_id"], **IDENTITY,
        )
        assert after_confirm["case_revision"] == 9
        assert runtime._sessions["101"]["step"] == "documents"

        evidence = repository.read_transition_bridge_evidence(
            case_id=runtime._sessions["101"]["case_id"],
            **IDENTITY,
            evidence_kind="PHYSICAL_SALES_DOCUMENT",
            include_sensitive_payload=True,
        )
        assert evidence["error"] is False and len(evidence["items"]) == 1
        item = evidence["items"][0]
        assert item["completeness"] == "PARTIAL"
        assert item["confirmations"][-1]["confirmation_kind"] == "PHYSICAL_SALES"
        assert item["payload"]["semantics"] == "PHYSICAL_OUTFLOW"
        assert "posting-111" not in repr(item["payload"])
    finally:
        reset_current_tenant_user_id(tenant)


def test_switching_fifo_case_invalidates_old_physical_preview_without_closing_either_case(tmp_path, monkeypatch):
    monkeypatch.setenv("OZON_CREDENTIAL_MASTER_KEY", Fernet.generate_key().decode("ascii"))
    tenant = set_current_tenant_user_id(make_store_tenant_scope("101", "store-a"))
    try:
        repository, history, transitions, report_import, _runtime = _services(tmp_path)

        class Worker:
            def parse_physical_sales(self, *, filename, payload, scope):
                return FifoCostPhysicalSalesImportService().parse_csv(
                    filename=filename, payload=payload, scope=scope,
                )

        physical_import = TelegramFifoCostPhysicalSalesImportService(
            repository=repository,
            worker=Worker(),
            evidence_service=FifoCostPhysicalSalesEvidenceService(),
        )
        runtime = TelegramFifoCostTransitionRuntimeService(
            transitions, history, report_import,
            physical_sales_import_service=physical_import,
        )
        runtime.start_new_case(101, IDENTITY, "Крючки", 0, "TOTAL_LANDED")
        _complete_owner_inputs(runtime)
        stage = runtime._show_supply_stage("101")
        skip = next(
            item["callback"] for item in stage["keyboard"]["buttons"]
            if item["text"] == "Продолжить без списка поставок"
        )
        documents = runtime.handle_callback(101, skip)
        select = next(
            item["callback"] for item in documents["keyboard"]["buttons"]
            if item["callback"].startswith("fifo_transition:physical_sales:")
        )
        runtime.handle_callback(101, select)
        content = (
            FifoCostPhysicalSalesImportService.TEMPLATE_HEADER + "\r\n"
            "posting-111;3921245627;1;2026-11-05;source-row-1\r\n"
        ).encode("utf-8")
        preview = runtime.handle_physical_sales_document(
            101, content, "physical-sales.csv",
        )
        old_case_id = runtime._sessions["101"]["case_id"]
        save_callback = preview["keyboard"]["buttons"][0]["callback"]

        other_identity = {
            "store_id": "store-a", "product_id": "product-202",
            "offer_id": "hook-3", "sku": "3921245628",
        }
        started = runtime.start_new_case(
            101, other_identity, "Другой товар", 0, "TOTAL_LANDED",
        )
        assert started["error"] is False
        new_case_id = runtime._sessions["101"]["case_id"]
        assert new_case_id != old_case_id
        assert runtime.has_physical_sales_document_selection(101) is False

        stale = runtime.handle_physical_sales_callback(101, save_callback)
        assert stale["error"] is True
        assert runtime._sessions["101"]["case_id"] == new_case_id
        assert runtime._sessions["101"]["step"] == "old_unit_cost_rub"
        old_case = transitions.get_case(case_id=old_case_id, **IDENTITY)
        new_case = transitions.get_case(case_id=new_case_id, **other_identity)
        assert old_case["case_revision"] == 7 and old_case["state"] == "AWAITING_EVIDENCE"
        assert new_case["case_revision"] == 1 and new_case["state"] == "DRAFT"
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
        prepare_calls = []
        runtime.apply_service = SimpleNamespace(
            prepare=lambda **kwargs: prepare_calls.append(kwargs) or {
                "error": False,
                "code": "FIFO_TRANSITION_NOT_READY",
                "requirements": ("FINANCIAL_PERIOD_SUMMARY_MISSING",),
                "candidate_total_cogs_rub": "92.30",
            },
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
        assert "Seal не создан: FIFO_TRANSITION_NOT_READY" in preview["message"]
        assert "кандидатная себестоимость" in preview["message"].lower()
        assert len(prepare_calls) == 1
        assert prepare_calls[0]["expected_case_revision"] == 8
        assert prepare_calls[0]["idempotency_key"].startswith("tg-fr25-prepare-")
        assert len(prepare_calls[0]["idempotency_key"]) <= 128
        retry_view = runtime._show_summary("101")
        retry_callback = next(
            button["callback"] for button in retry_view["keyboard"]["buttons"]
            if button["text"] == "📊 Посмотреть пересчёт"
        )
        runtime.handle_callback(101, retry_callback)
        assert len(prepare_calls) == 2
        assert prepare_calls[1]["idempotency_key"] == prepare_calls[0]["idempotency_key"]

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


def test_ready_case_reopens_saved_preview_after_restart_without_repreparing():
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
        preview_calls = []
        runtime._show_recalculation = lambda owner: preview_calls.append(owner) or {
            "error": False, "message": "same persisted seal",
        }

        result = runtime.resume_case(
            101,
            identity=IDENTITY,
            display_name="Крючки",
            case_id="case-ready-restart",
            expected_case_revision=9,
        )

        assert result["message"] == "same persisted seal"
        assert preview_calls == ["101"]
        session = runtime._sessions["101"]
        assert session["state"] == "READY_TO_CONFIRM"
        assert "step" not in session
    finally:
        reset_current_tenant_user_id(tenant)


def test_ready_preview_ticket_binds_exact_persisted_seal_and_replays_commit(tmp_path):
    tenant = set_current_tenant_user_id(make_store_tenant_scope("owner-a", "store-a"))
    try:
        preview_id = "preview-12345678"
        preview_fingerprint = "a" * 64
        preview = {
            "case_revision": 8,
            "effective_date": "2026-11-07",
            "complete_through": "2026-11-06",
            "allocation_preview": {"total_cogs_rub": "92.30"},
            "impact_preview": {
                "error": False,
                "complete": True,
                "candidate_only": False,
                "related_return_count": 2,
                "non_sale_outflow_count": 1,
                "periods": [{
                    "period": "2026-11",
                    "before_profit_rub": "240.00",
                    "after_profit_rub": "252.70",
                    "delta_profit_rub": "12.70",
                    "before_tax_rub": "60.00",
                    "after_tax_rub": "60.00",
                }],
            },
            "idempotency_key": "tg-fr25-prepare-012345678901234567890123456789012345678901234567",
        }
        state = {
            "case_revision": 9,
            "state": "READY_TO_CONFIRM",
            "case": {
                "metadata": {"scope": dict(IDENTITY)},
                "last_preview": {
                    "preview_id": preview_id,
                    "preview_fingerprint": preview_fingerprint,
                },
            },
        }

        class ReadyTransitions:
            def get_case(self, *, case_id, **identity):
                return {"error": False, "case_id": case_id, **state}

        class ExactApply:
            def __init__(self):
                self.apply_calls = []
                self.read_calls = []
                self.expired = False

            def prepare(self, **kwargs):
                raise AssertionError("READY restart must read, never prepare a new seal")

            def read_preview(self, *, case_id, identity, preview_id):
                self.read_calls.append((case_id, dict(identity), preview_id))
                return {
                    "error": False,
                    "case_revision": 9,
                    "basis_case_revision": 8,
                    "preview_id": preview_id,
                    "preview_fingerprint": preview_fingerprint,
                    "current_case_revision": state["case_revision"],
                    "current_case_state": state["state"],
                    "is_current": True,
                    "expired": self.expired,
                    "preview": preview,
                    "read_only": True,
                }

            def apply(self, **kwargs):
                self.apply_calls.append(kwargs)
                state["case_revision"] = 10
                state["state"] = "APPLIED"
                return {
                    "error": False,
                    "code": "FIFO_TRANSITION_APPLIED",
                    "commit_id": "transcommit_1234567890",
                    "preview_id": preview_id,
                    "case_revision": 10,
                    "complete_through": "2026-11-06",
                    "committed_at": "2026-11-10T12:00:00Z",
                }

            def read_commit(self, *, case_id, identity):
                return {
                    "error": False,
                    "code": "FIFO_TRANSITION_APPLIED",
                    "commit_id": "transcommit_1234567890",
                    "preview_id": preview_id,
                    "case_revision": 10,
                    "complete_through": "2026-11-06",
                }

        service = ExactApply()
        runtime = TelegramFifoCostTransitionRuntimeService(
            ReadyTransitions(), history_service=None, apply_service=service,
        )
        opened = runtime.resume_case(
            101, identity=IDENTITY, display_name="Крючки",
            case_id="case-ready-12345678", expected_case_revision=9,
        )
        assert "Подтверждённый предпросмотр FIFO" in opened["message"]
        assert "2026-11: прибыль 240.00 → 252.70 ₽" in opened["message"]
        assert "Покрытие финансовых данных до: 2026-11-06" in opened["message"]
        assert len(service.read_calls) == 1

        readiness_bindings = []

        class ReadyReview:
            def assess(self, *, case_id, identity, sealed_preview_id=None):
                readiness_bindings.append((case_id, sealed_preview_id))
                return {
                    "error": False,
                    "case_revision": 8,
                    "readiness": SimpleNamespace(
                        status="PREVIEW_READY", ready_to_apply=True,
                        source_data_through="2026-11-06",
                        candidate_data_through=None,
                        complete_through="2026-11-06",
                        requirements=(),
                    ),
                }

        runtime.review_service = ReadyReview()
        readiness_button = runtime._issue_ticket(
            "101", runtime._sessions["101"], "check_readiness",
        )
        readiness = runtime.handle_callback(101, readiness_button)
        assert "Состояние: PREVIEW_READY" in readiness["message"]
        assert "Проверка только читает" in readiness["message"]
        assert readiness_bindings == [("case-ready-12345678", preview_id)]

        restart_runtime = TelegramFifoCostTransitionRuntimeService(
            ReadyTransitions(), history_service=None, apply_service=service,
        )
        restarted = restart_runtime.resume_case(
            101, identity=IDENTITY, display_name="Крючки",
            case_id="case-ready-12345678", expected_case_revision=9,
        )
        assert restarted["message"] == opened["message"]

        service.expired = True
        expired_runtime = TelegramFifoCostTransitionRuntimeService(
            ReadyTransitions(), history_service=None, apply_service=service,
        )
        expired_preview = expired_runtime.resume_case(
            101, identity=IDENTITY, display_name="Крючки",
            case_id="case-ready-12345678", expected_case_revision=9,
        )
        assert "2026-11: прибыль 240.00 → 252.70 ₽" in expired_preview["message"]
        assert "Срок подтверждения seal истёк" in expired_preview["message"]
        assert all(
            button["text"] != "Продолжить к подтверждению"
            for button in expired_preview["keyboard"]["buttons"]
        )
        service.expired = False
        first_apply_ticket = next(
            button["callback"] for button in opened["keyboard"]["buttons"]
            if button["text"] == "Продолжить к подтверждению"
        )
        first_apply_token = first_apply_ticket.rsplit(":", 1)[-1]
        first_ticket = runtime._ticket("101", first_apply_token)
        assert first_ticket["preview_id"] == preview_id
        assert first_ticket["preview_fingerprint"] == preview_fingerprint
        assert first_ticket["expected_preview_case_revision"] == 9
        assert preview_id not in first_apply_ticket
        assert preview_fingerprint not in first_apply_ticket

        prompt = runtime.handle_callback(101, first_apply_ticket)
        confirm_callback = prompt["keyboard"]["buttons"][0]["callback"]
        confirm_token = confirm_callback.rsplit(":", 1)[-1]
        confirm_ticket = runtime._ticket("101", confirm_token)
        assert confirm_ticket["preview_id"] == preview_id
        assert confirm_ticket["preview_fingerprint"] == preview_fingerprint
        assert confirm_ticket["expected_preview_case_revision"] == 9
        assert confirm_ticket["idempotency_key"] == first_ticket["idempotency_key"]

        changed_fingerprint = "b" * 64
        state["case"]["last_preview"]["preview_fingerprint"] = changed_fingerprint
        rejected = runtime.handle_callback(101, confirm_callback)
        assert rejected["error"] is True
        assert service.apply_calls == []

        state["case"]["last_preview"]["preview_fingerprint"] = preview_fingerprint
        applied = runtime.handle_callback(101, confirm_callback)
        assert "Commit: transcommit_1234567890" in applied["message"]
        assert "Покрытие подтверждено до: 2026-11-06" in applied["message"]
        assert service.apply_calls == [{
            "case_id": "case-ready-12345678",
            "identity": IDENTITY,
            "expected_case_revision": 9,
            "expected_preview_id": preview_id,
            "expected_preview_fingerprint": preview_fingerprint,
            "idempotency_key": confirm_ticket["idempotency_key"],
        }]
        replayed = runtime.handle_callback(101, confirm_callback)
        assert replayed == applied
        assert len(service.apply_calls) == 1

        applied_restart_runtime = TelegramFifoCostTransitionRuntimeService(
            ReadyTransitions(), history_service=None, apply_service=service,
        )
        applied_restart = applied_restart_runtime.resume_case(
            101, identity=IDENTITY, display_name="Крючки",
            case_id="case-ready-12345678", expected_case_revision=10,
        )
        assert "Commit: transcommit_1234567890" in applied_restart["message"]
        assert "Покрытие подтверждено до: 2026-11-06" in applied_restart["message"]
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


def test_documents_menu_routes_owner_opening_composition_to_bound_preview(tmp_path):
    tenant = set_current_tenant_user_id(make_store_tenant_scope("owner-a", "store-a"))
    try:
        _repository, _history, transitions, _report_import, runtime = _services(tmp_path)
        runtime.start_new_case(101, IDENTITY, "Крючки", 0, "TOTAL_LANDED")
        _complete_owner_inputs(runtime)
        transitions.read_confirmed_cutoff_selection = lambda **_kwargs: {
            "error": False,
            "evidence_id": "evidence-cutoff-1",
            "evidence_fingerprint": "a" * 64,
            "stock_report_fingerprint": "b" * 64,
            "descriptor": {"cutoff_date": "2026-11-04"},
        }

        menu = runtime._documents_prompt("101")
        opening_button = next(
            item for item in menu["keyboard"]["buttons"]
            if item["text"] == "🧾 Задать начальный состав FIFO"
        )
        opened = runtime.handle_callback(101, opening_button["callback"])
        assert "Сколько упаковок старой партии" in opened["message"]

        prompts = []
        for value in ("0", "3", "0", "0", "0", "0"):
            response = runtime.handle_text(101, value)
            prompts.append(response)
        preview = prompts[-1]
        assert "cutoff 2026-11-04" in preview["message"]
        assert "новой партии по 14.65 ₽/шт.: Ozon 3" in preview["message"]
        assert "Сохранить состав" in preview["message"]
        # The preview is only a draft: no opening composition was persisted.
        assert transitions.read_confirmed_opening_composition(
            case_id=runtime._sessions["101"]["case_id"], **IDENTITY,
        )["error"] is True
    finally:
        reset_current_tenant_user_id(tenant)


def test_old_opening_composition_save_button_cannot_save_the_next_draft(tmp_path):
    tenant = set_current_tenant_user_id(make_store_tenant_scope("owner-a", "store-a"))
    try:
        _repository, _history, transitions, _report_import, runtime = _services(tmp_path)
        runtime.start_new_case(101, IDENTITY, "Крючки", 0, "TOTAL_LANDED")
        _complete_owner_inputs(runtime)
        transitions.read_confirmed_cutoff_selection = lambda **_kwargs: {
            "error": False,
            "evidence_id": "evidence-cutoff-1",
            "evidence_fingerprint": "a" * 64,
            "stock_report_fingerprint": "b" * 64,
            "descriptor": {"cutoff_date": "2026-11-04"},
        }
        saved_calls = []
        transitions.record_opening_composition = lambda **kwargs: (
            saved_calls.append(kwargs) or {"error": True, "code": "MUST_NOT_SAVE"}
        )
        session = runtime._sessions["101"]

        first = runtime._start_opening_composition("101", session)
        for value in ("3", "0", "0", "0", "0", "0"):
            first = runtime.handle_text(101, value)
        stale_save = next(
            item["callback"] for item in first["keyboard"]["buttons"]
            if "Сохранить состав" in item["text"]
        )
        stale_cancel = next(
            item["callback"] for item in first["keyboard"]["buttons"]
            if "Отменить ввод" in item["text"]
        )

        second = runtime._start_opening_composition("101", session)
        assert second.get("error") is False
        for value in ("0", "3", "0", "0", "0", "0"):
            second = runtime.handle_text(101, value)
        assert "новой партии по 14.65 ₽/шт.: Ozon 3" in second["message"]

        rejected = runtime.handle_callback(101, stale_save)

        assert rejected.get("error") is True
        assert saved_calls == []
        rejected_cancel = runtime.handle_callback(101, stale_cancel)
        assert rejected_cancel.get("error") is True
        assert session["opening_composition_preview"][0]["ozon_units"] == 3
        assert session["opening_composition_preview"][0]["unit_cost_rub"] == "14.65"
    finally:
        reset_current_tenant_user_id(tenant)


def test_cancelled_opening_composition_clears_preview_and_invalidates_save_button(tmp_path):
    tenant = set_current_tenant_user_id(make_store_tenant_scope("owner-a", "store-a"))
    try:
        _repository, _history, transitions, _report_import, runtime = _services(tmp_path)
        runtime.start_new_case(101, IDENTITY, "Крючки", 0, "TOTAL_LANDED")
        _complete_owner_inputs(runtime)
        transitions.read_confirmed_cutoff_selection = lambda **_kwargs: {
            "error": False,
            "evidence_id": "evidence-cutoff-1",
            "evidence_fingerprint": "a" * 64,
            "stock_report_fingerprint": "b" * 64,
            "descriptor": {"cutoff_date": "2026-11-04"},
        }
        saved_calls = []
        transitions.record_opening_composition = lambda **kwargs: (
            saved_calls.append(kwargs) or {"error": True, "code": "MUST_NOT_SAVE"}
        )
        runtime._start_opening_composition("101", runtime._sessions["101"])
        for value in ("0", "3", "0", "0", "0", "0"):
            preview = runtime.handle_text(101, value)
        save_callback = next(
            item["callback"] for item in preview["keyboard"]["buttons"]
            if "Сохранить состав" in item["text"]
        )
        cancel_callback = next(
            item["callback"] for item in preview["keyboard"]["buttons"]
            if "Отменить ввод" in item["text"]
        )

        runtime.handle_callback(101, cancel_callback)
        session = runtime._sessions["101"]
        assert not any(key.startswith("opening_composition_") for key in session)
        assert session.get("step") is None

        rejected = runtime.handle_callback(101, save_callback)

        assert rejected.get("error") is True
        assert saved_calls == []
    finally:
        reset_current_tenant_user_id(tenant)


def test_opening_composition_accepts_unknown_new_home_quantity_without_counting_it(tmp_path):
    tenant = set_current_tenant_user_id(make_store_tenant_scope("owner-a", "store-a"))
    try:
        _repository, _history, transitions, _report_import, runtime = _services(tmp_path)
        runtime.start_new_case(101, IDENTITY, "Крючки", 0, "TOTAL_LANDED")
        _complete_owner_inputs(runtime)
        transitions.read_confirmed_cutoff_selection = lambda **_kwargs: {
            "error": False,
            "evidence_id": "evidence-cutoff-1",
            "evidence_fingerprint": "a" * 64,
            "stock_report_fingerprint": "b" * 64,
            "descriptor": {"cutoff_date": "2026-11-04"},
        }
        saved_calls = []
        transitions.record_opening_composition = lambda **kwargs: (
            saved_calls.append(kwargs) or {"error": True, "code": "STOP_AFTER_CAPTURE"}
        )

        runtime._start_opening_composition("101", runtime._sessions["101"])
        result = None
        for value in ("0", "3", "0", "0", "0"):
            result = runtime.handle_text(101, value)
        result = runtime.handle_text(101, "не знаю")

        assert "дома неизвестно" in result["message"]
        assert "не включено в конечный остаток" in result["message"]
        assert runtime._sessions["101"]["opening_composition_draft"]["values"][-1] is None
        save_callback = next(
            item["callback"] for item in result["keyboard"]["buttons"]
            if "Сохранить состав" in item["text"]
        )
        runtime.handle_callback(101, save_callback)

        assert len(saved_calls) == 1
        assert saved_calls[0]["unknown_new_home_quantity"] is True
        assert saved_calls[0]["layers"][-1]["home_units"] == 0
    finally:
        reset_current_tenant_user_id(tenant)


def test_documents_menu_routes_bounded_finance_collection_without_saving_unavailable_source(tmp_path):
    tenant = set_current_tenant_user_id(make_store_tenant_scope("owner-a", "store-a"))
    try:
        _repository, _history, _transitions, _report_import, runtime = _services(tmp_path)
        runtime.start_new_case(101, IDENTITY, "Крючки", 0, "TOTAL_LANDED")
        _complete_owner_inputs(runtime)

        class SourceCollection:
            def __init__(self):
                self.calls = []

            def collect_finance_identity_snapshot(self, **kwargs):
                self.calls.append(kwargs)
                return SimpleNamespace(
                    status="UNAVAILABLE", finance_identity_snapshots=(),
                    continuation_token=None, issue_codes=("OZON_HTTP_404",),
                    actual_http_attempts=1, source_fingerprint=None,
                )

        class Evidence:
            def __init__(self):
                self.write_calls = []

            def record_finance_identity_batches(self, **kwargs):
                self.write_calls.append(kwargs)
                return {"error": False}

        source = SourceCollection()
        evidence = Evidence()
        runtime.source_collection_service = source
        runtime.evidence_service = evidence

        menu = runtime._documents_prompt("101")
        finance_button = next(
            item for item in menu["keyboard"]["buttons"]
            if item["text"] == "🔗 Собрать финансовые привязки"
        )
        prompt = runtime.handle_callback(101, finance_button["callback"])
        assert "первый и последний месяц" in prompt["message"]
        result = runtime.handle_text(101, "2026-08 — 2026-08")

        assert "Финансовые привязки не сохранены" in result["message"]
        assert source.calls[0]["period_from"] == "2026-08-01"
        assert source.calls[0]["period_to"] == "2026-08-31"
        assert source.calls[0]["max_pages_per_call"] == 2
        assert source.calls[0]["http_attempt_budget"] == 10
        assert source.calls[0]["time_budget_seconds"] == 20.0
        assert evidence.write_calls == []
    finally:
        reset_current_tenant_user_id(tenant)


def test_documents_menu_routes_period_summary_collection_as_read_only_action(tmp_path):
    tenant = set_current_tenant_user_id(make_store_tenant_scope("owner-a", "store-a"))
    try:
        _repository, _history, _transitions, _report_import, runtime = _services(tmp_path)
        runtime.start_new_case(101, IDENTITY, "Крючки", 0, "TOTAL_LANDED")
        _complete_owner_inputs(runtime)

        class Apply:
            def __init__(self):
                self.calls = []

            def collect_period_summaries(self, **kwargs):
                self.calls.append(kwargs)
                return {
                    "error": True,
                    "code": "FIFO_TRANSITION_EVIDENCE_INCOMPLETE",
                    "requirements": ["MOVEMENT_COVERAGE_MISSING"],
                }

        apply = Apply()
        runtime.apply_service = apply
        runtime.period_summary_collection_service = object()
        runtime.period_profit_service = object()

        menu = runtime._documents_prompt("101")
        summary_button = next(
            item for item in menu["keyboard"]["buttons"]
            if item["text"] == "📊 Собрать месячные итоги Period Profit"
        )
        result = runtime.handle_callback(101, summary_button["callback"])

        assert "MOVEMENT_COVERAGE_MISSING" in result["message"]
        assert "FIFO и прибыль не изменены" in result["message"]
        assert len(apply.calls) == 1
        assert apply.calls[0]["case_id"] == runtime._sessions["101"]["case_id"]
        assert apply.calls[0]["continuation_token"] is None
    finally:
        reset_current_tenant_user_id(tenant)
