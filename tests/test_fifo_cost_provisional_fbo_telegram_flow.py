from __future__ import annotations

from dataclasses import replace

from services.fifo_cost_provisional_fbo_csv_import_service import (
    FifoCostProvisionalFboCsvImportService,
)
from services.fifo_cost_provisional_movements_import_service import (
    FifoCostProvisionalMovementsImportService,
)
from services.fifo_cost_provisional_summary_service import FifoCostProvisionalSummaryService
from services.telegram_fifo_cost_provisional_service import TelegramFifoCostProvisionalService
from services.fifo_cost_transition_contracts import ScopeIdentity
from services.ozon_account_repository import make_store_tenant_scope
from services.tenant_context import reset_current_tenant_user_id, set_current_tenant_user_id
from services.telegram_fifo_cost_transition_runtime_service import TelegramFifoCostTransitionRuntimeService
from telegram_app_layer.seller_cost_telegram_adapter import SellerCostTelegramAdapter
from test_fifo_cost_provisional_summary_service import _case

IDENTITY = {"store_id": "store-test", "product_id": "1", "offer_id": None, "sku": "3921245627"}
SCOPE = ScopeIdentity(owner_id="owner-test", **IDENTITY)
TENANT = make_store_tenant_scope("owner-test", "store-test")
CSV = (
    "Номер отправления;SKU;Количество;Статус;Дата передачи в доставку;Дата доставки;Адрес покупателя\r\n"
    "posting-old-window;3921245627;1319;Доставлен;2026-11-05;2026-11-07;secret-address\r\n"
    "posting-new-window;3921245627;4610;Доставлен;2026-11-06 10:00:00;2026-11-07 12:00:00;private-address\r\n"
    "posting-missing-dispatch;3921245627;3;Доставлен;;2026-11-08;missing-address\r\n"
    "posting-unknown-status;3921245627;5;Unknown seller state;2026-11-08;2026-11-09;unknown-address\r\n"
    "posting-old-late;3921245627;2;Доставлен;2026-11-05;2026-11-21;later-address\r\n"
    "posting-old-transit;3921245627;19;В пути;2026-11-05;;transit-address\r\n"
    "posting-private-other-sku;9999999999;8;Доставлен;2026-11-06;2026-11-07;another-address\r\n"
).encode("utf-8")


def _button(runtime, response, action):
    return next(
        item["callback"] for item in response["keyboard"]["buttons"]
        if f":{action}:" in item["callback"]
    )


class _Transitions:
    writes = 0

    def __init__(self, request):
        self.request = request

    def get_case(self, **_kwargs):
        return {
            "error": False, "case_revision": 1, "state": "DRAFT",
            "case": {
                "old_unit_cost_rub": "21.00", "new_unit_cost_rub": "14.65",
                "metadata": {
                    "scope": dict(IDENTITY),
                    "store_timezone": "Europe/Moscow",
                },
            },
        }


class _Reports:
    def __init__(self, request):
        self.request = request

    def list_turnover_reports(self, **_kwargs):
        return {
            "error": False, "read_only": True,
            "reports": tuple({
                "file_fingerprint": report.file_sha256,
                "period_from": report.period_from, "period_to": report.period_to,
                "report": report,
            } for report in (self.request.snapshot, self.request.movement_report)),
        }


class _CsvWorker:
    def __init__(self):
        self.parser = FifoCostProvisionalFboCsvImportService()
        self.movements_parser = FifoCostProvisionalMovementsImportService()
        self.calls = []

    def parse_provisional_fbo_csv(self, **kwargs):
        self.calls.append(kwargs)
        return self.parser.parse_csv(**kwargs)

    def parse_provisional_movements_csv(self, **kwargs):
        self.calls.append(kwargs)
        return self.movements_parser.parse_csv(**kwargs)


def _runtime():
    base = _case()
    snapshot = replace(
        base.snapshot,
        metadata=replace(base.snapshot.metadata, scope=SCOPE),
    )
    movement = replace(
        base.movement_report,
        metadata=replace(base.movement_report.metadata, scope=SCOPE),
    )
    request = replace(base, scope=SCOPE, snapshot=snapshot, movement_report=movement)
    transition = _Transitions(request)
    worker = _CsvWorker()
    provisional = TelegramFifoCostProvisionalService(
        evidence_reader=_Reports(request),
        summary_service=FifoCostProvisionalSummaryService(),
        fbo_worker=worker,
        monotonic_clock=lambda: 100.0,
    )
    runtime = TelegramFifoCostTransitionRuntimeService(
        transition, object(), provisional_service=provisional,
        monotonic_clock=lambda: 100.0,
    )
    assert runtime._set_session("owner-test", TENANT, IDENTITY, "Тест", "case-1", 1)
    return runtime, worker, transition


def test_starting_either_csv_replacement_invalidates_timeline_confirmation_and_result():
    tenant_token = set_current_tenant_user_id(TENANT)
    try:
        for action in ("provisional_fbo_upload", "provisional_movements_upload"):
            runtime, _worker, _transition = _runtime()
            session = runtime._sessions["owner-test"]
            response = runtime.handle_callback(
                "owner-test", runtime._issue_ticket("owner-test", session, "provisional_start"),
            )
            response = runtime.handle_callback(
                "owner-test", _button(runtime, response, "provisional_snapshot"),
            )
            response = runtime.handle_callback(
                "owner-test", _button(runtime, response, "provisional_movement"),
            )
            flow = session["provisional_flow"]
            flow["timeline_coverage_confirmed"] = True
            flow["timeline_result"] = object()

            runtime.handle_callback("owner-test", _button(runtime, response, action))

            assert flow["timeline_coverage_confirmed"] is None
            assert flow["timeline_result"] is None
    finally:
        reset_current_tenant_user_id(tenant_token)


def test_fbo_csv_dialog_preflights_parses_and_keeps_statement_T_for_calculation():
    tenant_token = set_current_tenant_user_id(TENANT)
    try:
        runtime, worker, transition = _runtime()
        response = runtime.handle_callback(
            "owner-test", _button(runtime, {"keyboard": {"buttons": [{
                "callback": runtime._issue_ticket(
                    "owner-test", runtime._sessions["owner-test"], "provisional_start",
                )
            }]}}, "provisional_start"),
        )
        response = runtime.handle_callback(
            "owner-test", _button(runtime, response, "provisional_snapshot"),
        )
        response = runtime.handle_callback(
            "owner-test", _button(runtime, response, "provisional_movement"),
        )
        response = runtime.handle_callback(
            "owner-test", _button(runtime, response, "provisional_fbo_upload"),
        )
        assert response["error"] is False
        assert "YYYY-MM-DD" in response["message"]
        assert runtime.has_provisional_fbo_document_selection("owner-test") is True
        early = runtime.preflight_provisional_fbo_document("owner-test", "orders.csv", len(CSV))
        assert early["selected"] is True and early["accepted"] is False
        assert early["code"] == "FIFO_PROVISIONAL_FBO_PERIOD_REQUIRED"
        assert runtime.handle_text("owner-test", "2026-11-06 - 2026-11-20")["code"] == "FIFO_PROVISIONAL_FBO_PERIOD_SET"
        assert runtime.has_provisional_fbo_document_selection("owner-test") is True
        preflight = runtime.preflight_provisional_fbo_document(
            "owner-test", "orders.csv", len(CSV),
        )
        assert preflight["selected"] and preflight["accepted"]
        result = runtime.handle_provisional_fbo_document("owner-test", CSV, "orders.csv")
        assert result["code"] == "FIFO_PROVISIONAL_FBO_PREVIEW_READY", result
        assert len(result["message"]) < 4000
        assert "5932 шт." in result["message"]
        assert "1319 шт." in result["message"]
        assert "позже окна 2" in result["message"]
        assert "19 шт." in result["message"]
        assert "+1 шт." in result["message"]
        assert "posting-private-1" not in result["message"]
        assert "secret-address" not in result["message"]
        assert "private-address" not in result["message"]
        assert "later-address" not in result["message"]
        assert "transit-address" not in result["message"]
        assert "unknown-address" not in result["message"]
        assert "Нераспознанных строк: 1" in result["message"]
        upload_preview = runtime._sessions["owner-test"]["provisional_flow"]["fbo_upload"]["preview"]
        assert upload_preview["delivered_units_in_window"] == 5932
        assert upload_preview["statement_redeemed_units"] == 5931
        assert upload_preview["old_dispatch_delivered_after_snapshot"] == 1321
        assert upload_preview["old_dispatch_delivered_in_window"] == 1319
        assert upload_preview["old_dispatch_delivered_after_window"] == 2
        assert upload_preview["old_dispatch_in_transit_at_export"] == 19
        assert upload_preview["missing_dispatch_date_rows"] == 1
        assert len(worker.calls) == 1
        adapter = SellerCostTelegramAdapter(
            None, None, None,
            fifo_transition_runtime_service=runtime,
        )
        pending = adapter.handle_document(CSV, "owner-test", "orders.csv")
        assert pending["code"] == "FIFO_PROVISIONAL_FBO_PREVIEW_PENDING"
        assert len(worker.calls) == 1

        response = runtime.handle_callback(
            "owner-test", _button(runtime, result, "provisional_fbo_confirm"),
        )
        assert "\u0440\u0430\u0437\u043d\u0438\u0446\u0430 CSV \u2212 \u0432\u0435\u0434\u043e\u043c\u043e\u0441\u0442\u044c: +1 \u0448\u0442." in response["message"]
        assert "\u0432\u044b\u043a\u0443\u043f\u044b T \u0432 \u0432\u0435\u0434\u043e\u043c\u043e\u0441\u0442\u0438: 5931 \u0448\u0442." in response["message"]
        assert "1319" in response["message"] and "2" in response["message"] and "19" in response["message"]
        for action in ("provisional_opening_yes", "provisional_receipts_yes"):
            response = runtime.handle_callback(
                "owner-test", _button(runtime, response, action),
            )
        assert runtime._sessions["owner-test"]["provisional_flow"]["opening_all_old"] is True
        assert runtime._sessions["owner-test"]["provisional_flow"]["all_period_supply_receipts_new"] is True
        response = runtime.handle_callback(
            "owner-test", _button(runtime, response, "provisional_closing_exact"),
        )
        response = runtime.handle_text("owner-test", "21")
        summary = runtime.handle_callback(
            "owner-test", _button(runtime, response, "provisional_calculate"),
        )
        assert len(summary["message"]) < 4000
        estimate = runtime._sessions["owner-test"]["provisional_flow"]["result"]
        assert estimate.redeemed_units == 5931
        assert estimate.old_sold_min == 3669 and estimate.old_sold_max == 3703
        assert "\u0434\u0438\u0430\u0433\u043d\u043e\u0441\u0442\u0438\u0447\u0435\u0441\u043a\u0430\u044f \u0440\u0430\u0437\u043d\u0438\u0446\u0430 CSV" in summary["message"]
        assert transition.writes == 0
    finally:
        reset_current_tenant_user_id(tenant_token)


def test_fbo_upload_expired_or_changed_case_is_rejected_before_worker():
    tenant_token = set_current_tenant_user_id(TENANT)
    try:
        runtime, worker, _transition = _runtime()
        session = runtime._sessions["owner-test"]
        session["provisional_flow"] = {
            "movement_fingerprint": "f" * 64,
            "fbo_upload": {
                "token": "token", "case_id": "case-1", "case_revision": 1,
                "identity": dict(IDENTITY), "movement_fingerprint": "f" * 64,
                "expires_at": 99.0,
            },
        }
        session["step"] = "provisional_fbo_file"
        preflight = runtime.preflight_provisional_fbo_document(
            "owner-test", "orders.csv", len(CSV),
        )
        assert preflight["selected"] is True
        assert preflight["accepted"] is False
        assert preflight["code"] == "FIFO_PROVISIONAL_FBO_SELECTION_STALE"
        result = runtime.handle_provisional_fbo_document("owner-test", CSV, "orders.csv")
        assert result["code"] == "FIFO_PROVISIONAL_FBO_SELECTION_STALE"
        assert worker.calls == []
    finally:
        reset_current_tenant_user_id(tenant_token)


def test_adapter_routes_selected_fbo_file_before_physical_or_legacy_csv():
    class Runtime:
        def __init__(self):
            self.calls = []

        def has_provisional_fbo_document_selection(self, user_id):
            return user_id == "owner"

        def handle_provisional_fbo_document(self, user_id, content, filename):
            self.calls.append(("fbo", user_id, content, filename))
            return {"error": False, "handled": True, "code": "FBO_ROUTE"}

        def has_physical_sales_document_selection(self, user_id):
            return True

        def handle_physical_sales_document(self, *args):
            self.calls.append(("physical", *args))
            return {"error": False, "handled": True, "code": "PHYSICAL_ROUTE"}

        def preflight_provisional_fbo_document(self, user_id, filename, file_size):
            self.calls.append(("fbo-preflight", user_id, filename, file_size))
            return {
                "error": False, "selected": True, "accepted": False,
                "code": "FIFO_PROVISIONAL_FBO_FORMAT_UNSUPPORTED",
            }

        def preflight_physical_sales_document(self, *args):
            self.calls.append(("physical-preflight", *args))
            return {"error": False, "selected": True, "accepted": True}

    runtime = Runtime()
    legacy = type("Legacy", (), {
        "import_table_for_user": lambda self, *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("selected FBO CSV must not fall through to legacy cost import")
        ),
    })()
    adapter = SellerCostTelegramAdapter(
        None, None, None, seller_cost_service=legacy,
        fifo_transition_runtime_service=runtime,
    )
    preflight = adapter.preflight_document_upload("owner", "wrong.xlsx", 10)
    result = adapter.handle_document(b"not-a-csv", "owner", "wrong.xlsx")
    assert preflight["accepted"] is False
    assert preflight["code"] == "FIFO_PROVISIONAL_FBO_FORMAT_UNSUPPORTED"
    assert result["code"] == "FBO_ROUTE"
    assert [call[0] for call in runtime.calls] == ["fbo-preflight", "fbo"]


def test_owner_movements_csv_and_timeline_gap_are_presented_without_promoting_summary():
    tenant_token = set_current_tenant_user_id(TENANT)
    try:
        runtime, worker, transition = _runtime()
        adapter = SellerCostTelegramAdapter(
            None, None, None,
            fifo_transition_runtime_service=runtime,
        )
        response = runtime.handle_callback(
            "owner-test", runtime._issue_ticket(
                "owner-test", runtime._sessions["owner-test"], "provisional_start",
            ),
        )
        response = runtime.handle_callback("owner-test", _button(runtime, response, "provisional_snapshot"))
        response = runtime.handle_callback("owner-test", _button(runtime, response, "provisional_movement"))
        response = runtime.handle_callback("owner-test", _button(runtime, response, "provisional_fbo_upload"))
        runtime.handle_text("owner-test", "2026-11-06 - 2026-11-20")
        fbo_preview = adapter.handle_document(CSV, "owner-test", "orders.csv")
        assert fbo_preview["code"] == "FIFO_PROVISIONAL_FBO_PREVIEW_READY"
        flow = runtime._sessions["owner-test"]["provisional_flow"]
        flow["timeline_coverage_confirmed"] = True
        flow["timeline_result"] = object()
        response = runtime.handle_callback(
            "owner-test", _button(runtime, fbo_preview, "provisional_fbo_confirm"),
        )
        assert flow["timeline_coverage_confirmed"] is None
        assert flow["timeline_result"] is None

        response = runtime.handle_callback(
            "owner-test", _button(runtime, response, "provisional_movements_upload"),
        )
        movement_csv = (
            ";".join(FifoCostProvisionalMovementsImportService.HEADER) + "\n"
            "SUPPLY_RECEIVED;receipt-1;2026-11-07T10:00:00+03:00;3921245627;1;;available;;source-1\n"
        ).encode()
        preflight = adapter.preflight_document_upload(
            "owner-test", "movements.csv", len(movement_csv),
        )
        assert preflight["selected"] is True and preflight["accepted"] is True
        movements_preview = adapter.handle_document(movement_csv, "owner-test", "movements.csv")
        assert movements_preview["code"] == "FIFO_PROVISIONAL_MOVEMENTS_PREVIEW_READY"
        assert "receipt-1" not in movements_preview["message"]
        assert "source-1" not in movements_preview["message"]
        flow["timeline_coverage_confirmed"] = True
        flow["timeline_result"] = object()
        response = runtime.handle_callback(
            "owner-test", _button(runtime, movements_preview, "provisional_movements_confirm"),
        )
        assert flow["timeline_coverage_confirmed"] is None
        assert flow["timeline_result"] is None
        assert "строк 1" in response["message"]
        for action in (
            "provisional_opening_yes", "provisional_receipts_yes",
            "provisional_timeline_coverage_yes",
        ):
            response = runtime.handle_callback("owner-test", _button(runtime, response, action))
        response = runtime.handle_callback(
            "owner-test", _button(runtime, response, "provisional_closing_exact"),
        )
        response = runtime.handle_text("owner-test", "21")
        response = runtime.handle_callback(
            "owner-test", _button(runtime, response, "provisional_timeline_calculate"),
        )
        flow = runtime._sessions["owner-test"]["provisional_flow"]
        assert flow["timeline_result"].status.value == "TIMELINE_GAP"
        assert flow["result"].status.value == "SUMMARY_RANGE"
        assert "Хронологическая модель не построена" in response["message"]
        assert "сводный диапазон" in response["message"]
        assert "TIMELINE_GAP" not in response["message"]
        assert "READY" not in response["message"]
        assert len(response["message"]) < 4000
        assert transition.writes == 0
        assert len(worker.calls) == 2
    finally:
        reset_current_tenant_user_id(tenant_token)
