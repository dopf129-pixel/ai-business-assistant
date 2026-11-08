from datetime import datetime, timezone

from services.fifo_cost_history_service import FifoCostHistoryService
from services.fifo_cost_repository import FifoCostRepository
from services.fifo_cost_transition_service import FifoCostTransitionService
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
