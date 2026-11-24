from dataclasses import replace
from types import SimpleNamespace

from services.fifo_cost_provisional_summary_service import FifoCostProvisionalSummaryService
from services.telegram_fifo_cost_provisional_service import TelegramFifoCostProvisionalService
from services.ozon_account_repository import make_store_tenant_scope
from services.tenant_context import reset_current_tenant_user_id, set_current_tenant_user_id
from services.telegram_fifo_cost_transition_runtime_service import TelegramFifoCostTransitionRuntimeService
from test_fifo_cost_provisional_summary_service import _case


IDENTITY = {"store_id": "store-test", "product_id": "1", "offer_id": None, "sku": "SKU-TEST"}
TENANT = make_store_tenant_scope("owner-test", "store-test")


def _ticket_for(runtime, response, action):
    return next(button["callback"] for button in response["keyboard"]["buttons"]
                if f":{action}:" in button["callback"])


def _ticket_for_fingerprint(runtime, owner, response, action, fingerprint):
    for button in response["keyboard"]["buttons"]:
        if f":{action}:" not in button["callback"]:
            continue
        token = button["callback"].rsplit(":", 1)[1]
        ticket = runtime._tickets[(owner, token)]
        if ticket.get("fingerprint") == fingerprint:
            return button["callback"]
    raise AssertionError(f"ticket not found: {action} {fingerprint}")


def test_regular_transition_callback_runs_summary_preview_without_persisting_fifo(tmp_path):
    request = _case()
    snapshot_variant_sha = "c" * 64
    movement_variant_sha = "d" * 64
    reports = (
        request.snapshot,
        request.movement_report,
        replace(
            request.snapshot,
            file_sha256=snapshot_variant_sha,
            metadata=replace(request.snapshot.metadata, source_fingerprint=snapshot_variant_sha),
        ),
        replace(
            request.movement_report,
            file_sha256=movement_variant_sha,
            metadata=replace(request.movement_report.metadata, source_fingerprint=movement_variant_sha),
        ),
    )

    class ReadOnlyTransition:
        writes = 0

        def get_case(self, **_kwargs):
            return {
                "error": False, "case_revision": 1, "state": "DRAFT",
                "case": {
                    "old_unit_cost_rub": "21.00", "new_unit_cost_rub": "14.65",
                    "metadata": {
                        "scope": {"owner_id": "owner-test", **IDENTITY},
                        "store_timezone": "Europe/Moscow",
                    },
                },
            }

    class SavedReports:
        def list_turnover_reports(self, **_kwargs):
            return {
                "error": False, "read_only": True,
                "reports": tuple({
                    "file_fingerprint": report.file_sha256,
                    "period_from": report.period_from, "period_to": report.period_to,
                    "captured_at": report.captured_at,
                    "report": report,
                } for report in reports),
            }

    transition = ReadOnlyTransition()
    provisional = TelegramFifoCostProvisionalService(
        evidence_reader=SavedReports(), summary_service=FifoCostProvisionalSummaryService(),
    )
    runtime = TelegramFifoCostTransitionRuntimeService(
        transition, object(), provisional_service=provisional,
    )
    tenant = set_current_tenant_user_id(TENANT)
    try:
        assert runtime._set_session("101", TENANT, IDENTITY, "Тестовый товар", "case-test", 1)
        session = runtime._sessions["101"]
        start = runtime._issue_ticket("101", session, "provisional_start")
        assert runtime._identity("101") == ("101", TENANT)
        token = start.rsplit(":", 1)[1]
        assert runtime._ticket_matches_session(runtime._tickets[("101", token)], session)
        assert runtime._tickets[("101", token)]["action"] == "provisional_start"
        assert runtime._read_case("case-test", IDENTITY)["state"] == "DRAFT"
        assert runtime._read_case("case-test", IDENTITY)["case_revision"] == session["case_revision"]
        response = runtime.handle_callback("101", start)
        assert response["error"] is False, response
        assert "только сценарий" in response["message"]
        assert len(response["message"]) < 4000

        snapshot_button = next(button["callback"] for button in response["keyboard"]["buttons"]
                               if ":provisional_snapshot:" in button["callback"])
        response = runtime.handle_callback("101", snapshot_button)
        assert runtime.handle_callback("101", start)["error"] is True
        movement_button = next(button["callback"] for button in response["keyboard"]["buttons"]
                               if ":provisional_movement:" in button["callback"])
        response = runtime.handle_callback("101", movement_button)
        for action in ("provisional_opening_yes", "provisional_receipts_yes"):
            response = runtime.handle_callback("101", _ticket_for(runtime, response, action))
        response = runtime.handle_callback("101", _ticket_for(runtime, response, "provisional_closing_exact"))
        response = runtime.handle_text("101", "21")
        response = runtime.handle_callback("101", _ticket_for(runtime, response, "provisional_calculate"))

        assert response["error"] is False, response
        assert len(response["message"]) < 4000
        assert "3,669" in response["message"] and "3,703" in response["message"], (session["provisional_flow"]["result"], response["message"])
        assert "110,187.30" in response["message"] and "110,403.20 ₽" in response["message"]
        assert "не являются FIFO фактом" in response["message"]
        assert not any("apply_transition" in button["callback"] for button in response["keyboard"]["buttons"])

        snapshot_labels = [button["text"] for button in response["keyboard"]["buttons"]
                           if ":provisional_snapshot:" in button["callback"]]
        movement_labels = [button["text"] for button in response["keyboard"]["buttons"]
                           if ":provisional_movement:" in button["callback"]]
        assert len(snapshot_labels) == len(set(snapshot_labels)) == 2
        assert len(movement_labels) == len(set(movement_labels)) == 2
        assert all(len(label) <= 64 and "Z" in label for label in snapshot_labels + movement_labels)
        assert all(label.startswith("Снимок ") for label in snapshot_labels)
        assert all(label.startswith("Движения ") for label in movement_labels)
        assert all(label.rsplit("·", 1)[-1].strip() in {request.snapshot.file_sha256[:8],
                                                        reports[2].file_sha256[:8],
                                                        request.movement_report.file_sha256[:8],
                                                        reports[3].file_sha256[:8]}
                   for label in snapshot_labels + movement_labels)

        response = runtime.handle_callback(
            "101", _ticket_for_fingerprint(
                runtime, "101", response, "provisional_movement", movement_variant_sha,
            ),
        )
        flow = session["provisional_flow"]
        assert flow["snapshot_fingerprint"] == request.snapshot.file_sha256
        assert flow["movement_fingerprint"] == movement_variant_sha
        assert flow["opening_all_old"] is True
        assert flow["all_period_supply_receipts_new"] is None
        assert flow["closing_old_min"] is flow["closing_old_max"] is None
        assert flow["result"] is None

        response = runtime.handle_callback("101", _ticket_for(runtime, response, "provisional_receipts_yes"))
        response = runtime.handle_callback("101", _ticket_for(runtime, response, "provisional_closing_exact"))
        response = runtime.handle_text("101", "21")
        response = runtime.handle_callback(
            "101", _ticket_for_fingerprint(
                runtime, "101", response, "provisional_snapshot", snapshot_variant_sha,
            ),
        )
        flow = session["provisional_flow"]
        assert flow["snapshot_fingerprint"] == snapshot_variant_sha
        assert flow["movement_fingerprint"] is None
        assert flow["opening_all_old"] is None
        assert flow["all_period_supply_receipts_new"] is None
        assert flow["closing_old_min"] is flow["closing_old_max"] is None
        assert flow["result"] is None
        assert transition.writes == 0
        assert "provisional_flow" in runtime._sessions["101"]
    finally:
        reset_current_tenant_user_id(tenant)


def test_provisional_screen_has_no_entry_when_service_is_not_composed():
    runtime = TelegramFifoCostTransitionRuntimeService(SimpleNamespace(), object())
    assert runtime.provisional_service is None
