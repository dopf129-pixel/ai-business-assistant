from dataclasses import replace
from types import SimpleNamespace
from copy import deepcopy
from decimal import Decimal

from services.fifo_cost_provisional_summary_service import FifoCostProvisionalSummaryService
from services.telegram_fifo_cost_provisional_service import TelegramFifoCostProvisionalService
from services.telegram_fifo_cost_history_service import TelegramFifoCostHistoryService
from telegram_app_layer.seller_cost_telegram_adapter import SellerCostTelegramAdapter
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


def test_report_switch_clears_only_dependent_assumptions_and_labels_fit_telegram():
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
                    "period_from": report.period_from,
                    "period_to": report.period_to,
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
        response = runtime.handle_callback(
            "101", runtime._issue_ticket("101", session, "provisional_start"),
        )
        snapshot_labels = [button["text"] for button in response["keyboard"]["buttons"]
                           if ":provisional_snapshot:" in button["callback"]]
        assert len(snapshot_labels) == len(set(snapshot_labels)) == 2
        assert all(len(label) <= 64 and "Z" in label for label in snapshot_labels)
        assert all(label.startswith("Снимок ") for label in snapshot_labels)

        response = runtime.handle_callback(
            "101", _ticket_for_fingerprint(
                runtime, "101", response, "provisional_snapshot", request.snapshot.file_sha256,
            ),
        )
        movement_labels = [button["text"] for button in response["keyboard"]["buttons"]
                           if ":provisional_movement:" in button["callback"]]
        assert len(movement_labels) == len(set(movement_labels)) == 2
        assert all(len(label) <= 64 and "Z" in label for label in movement_labels)
        assert all(label.startswith("Движения ") for label in movement_labels)
        assert all(label.rsplit("·", 1)[-1].strip() in {
            request.movement_report.file_sha256[:8], movement_variant_sha[:8],
        } for label in movement_labels)
        response = runtime.handle_callback(
            "101", _ticket_for_fingerprint(
                runtime, "101", response, "provisional_movement", request.movement_report.file_sha256,
            ),
        )
        response = runtime.handle_callback("101", _ticket_for(runtime, response, "provisional_opening_yes"))
        response = runtime.handle_callback("101", _ticket_for(runtime, response, "provisional_receipts_yes"))
        response = runtime.handle_callback("101", _ticket_for(runtime, response, "provisional_closing_exact"))
        flow = session["provisional_flow"]
        stale_summary = object()
        stale_timeline = object()
        flow["result"] = stale_summary
        flow["timeline_result"] = stale_timeline
        invalid = runtime.handle_text("101", "not-an-integer")
        assert invalid["error"] is False
        assert flow["result"] is stale_summary
        assert flow["timeline_result"] is stale_timeline
        response = runtime.handle_text("101", "21")
        assert flow["result"] is None
        assert flow["timeline_result"] is None

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
        assert flow["snapshot_fingerprint"] == snapshot_variant_sha
        assert flow["movement_fingerprint"] is None
        assert flow["opening_all_old"] is None
        assert flow["all_period_supply_receipts_new"] is None
        assert flow["closing_old_min"] is flow["closing_old_max"] is None
        assert flow["result"] is None
        assert transition.writes == 0
    finally:
        reset_current_tenant_user_id(tenant)


def test_regular_transition_flow_saves_only_fresh_provisional_preview(tmp_path):
    request = _case()
    reports = [request.snapshot, request.movement_report]

    class ReadOnlyTransition:
        writes = 0
        state = "DRAFT"
        case_revision = 1

        def get_case(self, **_kwargs):
            return {
                "error": False, "case_revision": self.case_revision, "state": self.state,
                "case": {
                    "old_unit_cost_rub": "21.00", "new_unit_cost_rub": "14.65",
                    "metadata": {
                        "scope": {"owner_id": "owner-test", **IDENTITY},
                        "store_timezone": "Europe/Moscow",
                    },
                },
            }

        repository = None

        def get_supply_manifest(self, **_kwargs):
            return {"error": False, "known_assigned_units": 0, "owner_declared_total": 0}

        def read_transition_evidence(self, **_kwargs):
            return {"error": False, "items": []}

        def read_confirmed_cutoff_selection(self, **_kwargs):
            return {
                "error": False, "descriptor": {"cutoff_date": "2026-11-05"},
                "owner_confirmed_supplier_receiving_units": None,
            }

    class SavedReports:
        def list_turnover_reports(self, **_kwargs):
            return {
                "error": False, "read_only": True,
                "reports": tuple({
                    "file_fingerprint": report.file_sha256,
                    "period_from": report.period_from, "period_to": report.period_to,
                    "report": report,
                } for report in reports),
            }

    class SavedEstimates:
        def __init__(self):
            self.rows = {}
            self.calls = []

        def append_provisional_preview(self, **kwargs):
            self.calls.append(kwargs)
            key = kwargs["idempotency_key"]
            if key not in self.rows:
                self.rows[key] = {
                    "preview_id": kwargs["preview_id"],
                    "store_id": kwargs["store_id"],
                    "product_id": kwargs["product_id"],
                    "offer_id": kwargs["offer_id"],
                    "sku": kwargs["sku"],
                    "case_revision": kwargs["case_revision"],
                    "created_at_utc": f"2026-11-22T00:00:{len(self.rows):02d}Z",
                    "schema_version": 1,
                    "input_fingerprint": kwargs["input_fingerprint"],
                    "payload": kwargs["payload"],
                }
                return {"error": False, "created": True, "item": self.rows[key]}
            return {"error": False, "created": False, "item": self.rows[key]}

        def read_provisional_preview_history(self, **kwargs):
            rows = [item for item in self.rows.values() if (
                item["store_id"] == kwargs["store_id"]
                and item["product_id"] == kwargs["product_id"]
                and item["offer_id"] == kwargs["offer_id"]
                and item["sku"] == kwargs["sku"]
            )]
            rows.sort(key=lambda item: item["created_at_utc"], reverse=True)
            offset, limit = kwargs["offset"], kwargs["limit"]
            return {
                "error": False, "items": rows[offset:offset + limit],
                "total": len(rows), "offset": offset, "limit": limit,
            }

    transition = ReadOnlyTransition()
    transition.repository = transition
    estimate_repository = SavedEstimates()
    provisional = TelegramFifoCostProvisionalService(
        evidence_reader=SavedReports(), summary_service=FifoCostProvisionalSummaryService(),
        estimate_repository=estimate_repository,
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
        assert "Условная прибыль до налога (не факт)" not in response["message"]
        assert "нет подтверждённой базы владельца" in response["message"]
        assert not any("apply_transition" in button["callback"] for button in response["keyboard"]["buttons"])
        profit_button = _ticket_for(runtime, response, "provisional_profit_base")
        response = runtime.handle_callback("101", profit_button)
        assert "по несовпадающим датам начисления" in response["message"]
        response = runtime.handle_text("101", "130000")
        assert "до сторно возвратов" in response["message"]
        assert "110,187.30–110,403.20 ₽" in response["message"]
        assert "не сверяет сумму с отдельным финансовым отчётом" in response["message"]
        assert "Условная прибыль до налога (не факт)" not in response["message"]
        confirm_profit = _ticket_for(runtime, response, "provisional_profit_base_confirm")
        response = runtime.handle_callback("101", confirm_profit)
        assert "Условная прибыль до налога (не факт)" in response["message"]
        assert "19,596.80–19,812.70 ₽" in response["message"]
        assert len(response["message"]) < 4000
        assert not any("apply_transition" in button["callback"] for button in response["keyboard"]["buttons"])
        save_button = _ticket_for(runtime, response, "provisional_save")
        assert estimate_repository.calls == []
        response = runtime.handle_callback("101", save_button)
        assert response["error"] is False, response
        assert len(estimate_repository.rows) == 1
        saved_payload = next(iter(estimate_repository.rows.values()))["payload"]
        assert saved_payload["model_kind"] == "SUMMARY_RANGE"
        assert saved_payload["schema_version"] == 2
        assert saved_payload["conditional_profit"]["source"] == "OWNER_CONFIRMED_MANUAL"
        assert saved_payload["conditional_profit"]["profit_low_rub"] == "19596.80"
        assert saved_payload["conditional_profit"]["profit_high_rub"] == "19812.70"
        assert saved_payload["evidence_fingerprints"] == sorted({
            request.snapshot.file_sha256, request.movement_report.file_sha256,
        })
        assert not any(key in str(saved_payload).lower() for key in (
            "posting_number", "raw_csv", "buyer", "address",
        ))
        assert "Оценка сохранена отдельно" in response["message"]
        assert len(estimate_repository.calls) == 1

        flow = session["provisional_flow"]
        candidate = provisional._profit_scenario_candidate(session, flow)
        assert candidate is not None
        flow["timeline_evidence_fingerprints"] = ["e" * 64]
        flow["profit_base_rub"] = "130000.00"
        flow["profit_base_confirmed"] = True
        flow["profit_model_kind"] = "SUMMARY_RANGE"
        flow["profit_scenario_fingerprint"] = candidate["input_fingerprint"]
        saved_preview_id = flow["saved_preview_id"]
        saved_row = next(iter(estimate_repository.rows.values()))
        for index in range(1, provisional.PAGE_SIZE + 1):
            history_row = deepcopy(saved_row)
            history_row["preview_id"] = f"preview-nav-{index}"
            history_row["created_at_utc"] = f"2026-11-22T00:00:{index:02d}Z"
            estimate_repository.rows[f"history-nav-{index}"] = history_row

        def assert_scenario_preserved():
            assert flow["timeline_evidence_fingerprints"] == ["e" * 64]
            assert flow["profit_base_rub"] == "130000.00"
            assert flow["profit_base_confirmed"] is True
            assert flow["profit_scenario_fingerprint"] == candidate["input_fingerprint"]
            assert flow["saved_preview_id"] == saved_preview_id

        response = runtime.handle_callback(
            "101", _ticket_for(runtime, response, "provisional_history"),
        )
        assert_scenario_preserved()
        response = runtime.handle_callback(
            "101", _ticket_for(runtime, response, "provisional_history_page"),
        )
        assert flow["history_page"] == 1
        assert_scenario_preserved()
        response = runtime.handle_callback(
            "101", _ticket_for(runtime, response, "provisional_history_view"),
        )
        assert_scenario_preserved()
        response = runtime.handle_callback(
            "101", _ticket_for(runtime, response, "provisional_history_detail_back"),
        )
        assert_scenario_preserved()
        response = runtime.handle_callback(
            "101", _ticket_for(runtime, response, "provisional_history_compare"),
        )
        assert_scenario_preserved()
        response = runtime.handle_callback(
            "101", _ticket_for(runtime, response, "provisional_history_compare"),
        )
        assert "Сравнение предварительных оценок" in response["message"]
        assert_scenario_preserved()
        response = runtime.handle_callback(
            "101", _ticket_for(runtime, response, "provisional_history_detail_back"),
        )
        assert_scenario_preserved()
        response = runtime.handle_callback(
            "101", _ticket_for(runtime, response, "provisional_history_to_calculator"),
        )
        assert_scenario_preserved()
        assert "Условная прибыль до налога (не факт)" in response["message"]
        assert "19,596.80–19,812.70 ₽" in response["message"]

        # Current navigation tickets still cannot save after selected evidence disappears.
        # The already-saved fingerprint correctly hides a duplicate-save button.
        # Recreate the callback against the current candidate to verify that it
        # still fails safely if evidence disappears after the calculator is shown.
        current_candidate = provisional._saved_candidate(session, flow)
        assert current_candidate is not None
        save_button = runtime._issue_ticket(
            "101", session, "provisional_save",
            input_fingerprint=current_candidate["input_fingerprint"],
            model_kind=current_candidate["payload"]["model_kind"],
        )
        reports.pop()
        response = runtime.handle_callback("101", save_button)
        assert response["code"] == "FIFO_PROVISIONAL_INPUT_STALE"
        assert len(estimate_repository.calls) == 1
        assert saved_preview_id in {
            item["preview_id"] for item in estimate_repository.rows.values()
        }
        assert transition.writes == 0
        assert "provisional_flow" in runtime._sessions["101"]

        # Saved history remains reachable from read-only case cards even when
        # the short-lived calculator flow is gone.
        class AppliedReceipt:
            def read_commit(self, **_kwargs):
                return {
                    "error": False, "code": "FIFO_TRANSITION_APPLIED",
                    "commit_id": "commit-test", "complete_through": "2026-11-20",
                    "case_revision": transition.case_revision,
                }

        runtime.apply_service = AppliedReceipt()
        for state in ("READY_TO_CONFIRM", "APPLIED", "CANCELLED"):
            transition.state = state
            transition.case_revision += 1
            assert runtime._set_session(
                "101", TENANT, IDENTITY, "Тестовый товар", "case-test",
                transition.case_revision,
            )
            session = runtime._sessions["101"]
            assert "provisional_flow" not in session
            if state == "READY_TO_CONFIRM":
                case_card = runtime._show_sealed_preview("101", session, {
                    "preview": {
                        "impact_preview": {
                            "error": False, "complete": True, "candidate_only": False,
                            "periods": [], "related_return_count": 0,
                            "non_sale_outflow_count": 0,
                        },
                        "allocation_preview": {"total_cogs_rub": "1.00"},
                        "effective_date": "2026-11-21",
                        "complete_through": "2026-11-20",
                    },
                    "expired": True, "case_revision": transition.case_revision,
                    "preview_id": "preview-test", "preview_fingerprint": "f" * 64,
                })
            else:
                case_card = runtime._show_summary("101")
            history_button = _ticket_for(runtime, case_card, "provisional_history")
            response = runtime.handle_callback("101", history_button)
            assert "Сохранённые предварительные оценки" in response["message"]
            assert session.get("provisional_history_readonly") is True
            open_button = _ticket_for(runtime, response, "provisional_history_view")
            response = runtime.handle_callback("101", open_button)
            assert "Сохранённая предварительная оценка" in response["message"]
            assert "Актуальность источников не сверена" in response["message"]
            assert "110,187.30–110,403.20 ₽" in response["message"]
            assert "19,596.80–19,812.70 ₽" in response["message"]
            assert not any(
                "provisional_history_to_calculator" in button["callback"]
                for button in response["keyboard"]["buttons"]
            )
            back_to_list = _ticket_for(runtime, response, "provisional_history_detail_back")
            response = runtime.handle_callback("101", back_to_list)
            card_button = _ticket_for(runtime, response, "provisional_back")
            response = runtime.handle_callback("101", card_button)
            assert "provisional_flow" not in session
            assert "provisional_history_readonly" not in session
            assert response["error"] is False
            if state == "CANCELLED":
                assert "FIFO отменено" in response["message"]
                resumed = runtime.resume_case(
                    "101", identity=IDENTITY, display_name="Тестовый товар",
                    case_id="case-test", expected_case_revision=transition.case_revision,
                )
                assert "FIFO отменено" in resumed["message"]
                assert _ticket_for(runtime, resumed, "provisional_history")
            elif state == "APPLIED":
                assert "FIFO применён" in response["message"]

        assert len(estimate_repository.calls) == 1
        # A stale pre-transition read ticket may refresh only the read-only
        # history session revision; factual transition writes remain untouched.
        transition.state = "APPLIED"
        transition.case_revision += 1
        assert runtime._set_session(
            "101", TENANT, IDENTITY, "Тестовый товар", "case-test",
            transition.case_revision,
        )
        session = runtime._sessions["101"]
        session["case_revision"] -= 1
        old_revision_ticket = runtime._issue_ticket(
            "101", session, "provisional_history",
        )
        transition.case_revision += 1
        response = runtime.handle_callback("101", old_revision_ticket)
        assert response["error"] is False, response
        assert session["case_revision"] == transition.case_revision
        assert runtime.period_profit_service is None
        assert transition.writes == 0
    finally:
        reset_current_tenant_user_id(tenant)


def test_provisional_screen_has_no_entry_when_service_is_not_composed():
    runtime = TelegramFifoCostTransitionRuntimeService(SimpleNamespace(), object())
    assert runtime.provisional_service is None


def test_saved_estimate_comparison_requires_same_basis_and_uses_interval_difference():
    first = {
        "model_kind": "SUMMARY_RANGE", "currency": "RUB",
        "period_from": "2026-11-01", "period_to": "2026-11-30",
        "method": "AGGREGATE_SUMMARY_V1", "policy_version": "fifo-provisional-summary-v1",
        "evidence_fingerprints": ["1" * 64, "2" * 64],
        "result": {
            "redeemed_units": 5931, "gross_cogs_low_rub": "100.00",
            "gross_cogs_high_rub": "120.00",
        },
    }
    second = deepcopy(first)
    second["result"]["gross_cogs_low_rub"] = "130.00"
    second["result"]["gross_cogs_high_rub"] = "160.00"
    service = TelegramFifoCostProvisionalService(
        evidence_reader=object(), summary_service=FifoCostProvisionalSummaryService(),
    )

    compatible, same_coverage = service._saved_estimates_comparable(first, second)
    first_interval = service._saved_cost_interval(first)
    second_interval = service._saved_cost_interval(second)
    assert compatible and same_coverage
    assert (second_interval[0] - first_interval[1]).quantize(Decimal("0.01")) == Decimal("10.00")
    assert (second_interval[1] - first_interval[0]).quantize(Decimal("0.01")) == Decimal("60.00")

    different_coverage = deepcopy(second)
    different_coverage["evidence_fingerprints"] = ["3" * 64, "4" * 64]
    compatible, same_coverage = service._saved_estimates_comparable(first, different_coverage)
    assert compatible and not same_coverage

    different_basis = deepcopy(second)
    different_basis["result"]["redeemed_units"] = 5930
    compatible, _ = service._saved_estimates_comparable(first, different_basis)
    assert not compatible


def test_conditional_profit_allows_negative_owner_confirmed_base():
    payload = {
        "model_kind": "SUMMARY_RANGE", "currency": "RUB",
        "period_from": "2026-11-01", "period_to": "2026-11-30",
        "result": {
            "redeemed_units": 5, "gross_cogs_low_rub": "100.00",
            "gross_cogs_high_rub": "120.00",
        },
    }

    profit = TelegramFifoCostProvisionalService._make_conditional_profit("-100", payload)

    assert profit["source"] == "OWNER_CONFIRMED_MANUAL"
    assert profit["base_rub"] == "-100.00"
    assert profit["profit_low_rub"] == "-220.00"
    assert profit["profit_high_rub"] == "-200.00"
    assert TelegramFifoCostProvisionalService._parse_money("-1250,50") == Decimal("-1250.50")


def test_conditional_profit_comparison_withholds_different_financial_perimeter():
    first = {
        "model_kind": "SUMMARY_RANGE", "currency": "RUB",
        "period_from": "2026-11-01", "period_to": "2026-11-30",
        "method": "AGGREGATE_SUMMARY_V1", "policy_version": "fifo-provisional-summary-v1",
        "evidence_fingerprints": ["1" * 64],
        "result": {
            "redeemed_units": 5, "gross_cogs_low_rub": "100.00",
            "gross_cogs_high_rub": "120.00",
        },
        "conditional_profit": {
            "status": "CONDITIONAL_BEFORE_TAX", "source": "OWNER_CONFIRMED_MANUAL",
            "currency": "RUB", "period_from": "2026-11-01", "period_to": "2026-11-30",
            "redeemed_units": 5, "perimeter": "SKU_PERIOD_REDEEMED_UNITS",
            "profit_stage": "BEFORE_PRODUCT_COGS_AND_TAX", "return_reversal": "EXCLUDED",
            "base_rub": "1000.00", "profit_low_rub": "880.00", "profit_high_rub": "900.00",
        },
    }
    second = deepcopy(first)
    second["conditional_profit"]["profit_low_rub"] = "980.00"
    second["conditional_profit"]["profit_high_rub"] = "1000.00"
    service = TelegramFifoCostProvisionalService(
        evidence_reader=object(), summary_service=FifoCostProvisionalSummaryService(),
    )

    comparable, _ = service._saved_profit_comparable(first, second)
    assert comparable

    second["conditional_profit"]["return_reversal"] = "INCLUDED"
    comparable, reason = service._saved_profit_comparable(first, second)
    assert not comparable
    assert "сторно" in reason

    second["conditional_profit"]["return_reversal"] = "EXCLUDED"
    second["conditional_profit"]["profit_stage"] = "AFTER_TAX"
    comparable, reason = service._saved_profit_comparable(first, second)
    assert not comparable
    assert "стадия налога" in reason

    second["conditional_profit"]["profit_stage"] = "BEFORE_PRODUCT_COGS_AND_TAX"
    second["conditional_profit"]["source"] = "UNVERIFIED"
    comparable, reason = service._saved_profit_comparable(first, second)
    assert not comparable
    assert "не подтверждены" in reason


def test_history_comparison_screen_only_shows_delta_for_matching_dimensions():
    first_payload = {
        "schema_version": 1, "model_kind": "SUMMARY_RANGE", "currency": "RUB",
        "period_from": "2026-11-01", "period_to": "2026-11-30",
        "method": "AGGREGATE_SUMMARY_V1", "policy_version": "fifo-provisional-summary-v1",
        "evidence_fingerprints": ["1" * 64],
        "rates": {"old_unit_cost_rub": "21.00", "new_unit_cost_rub": "14.65"},
        "assumptions": {},
        "result": {
            "redeemed_units": 5931, "old_sold_min": 3669, "old_sold_max": 3703,
            "new_sold_min": 2228, "new_sold_max": 2262,
            "gross_cogs_low_rub": "100.00", "gross_cogs_high_rub": "120.00",
        },
    }
    second_payload = deepcopy(first_payload)
    second_payload["evidence_fingerprints"] = ["2" * 64]
    second_payload["result"]["gross_cogs_low_rub"] = "130.00"
    second_payload["result"]["gross_cogs_high_rub"] = "160.00"
    items = [
        {"preview_id": "preview-first", "created_at_utc": "2026-11-22T00:00:00Z", "payload": first_payload},
        {"preview_id": "preview-second", "created_at_utc": "2026-11-23T00:00:00Z", "payload": second_payload},
    ]

    class History:
        def read_provisional_preview_history(self, **_kwargs):
            return {"error": False, "items": items, "total": len(items), "offset": 0, "limit": 100}

    service = TelegramFifoCostProvisionalService(
        evidence_reader=object(), summary_service=FifoCostProvisionalSummaryService(),
        estimate_repository=History(),
    )
    runtime = SimpleNamespace(
        _result=lambda message, **kwargs: {"message": message, **kwargs},
        _keyboard=lambda buttons: {"buttons": buttons},
        _issue_ticket=lambda *_args, **_kwargs: "opaque-ticket",
    )
    session = {
        "case_id": "case", "identity": IDENTITY,
        "provisional_flow": {
            "history_compare_first_id": "preview-first",
            "history_compare_second_id": "preview-second",
        },
    }
    result = service.show_history_comparison(runtime, "101", session)
    assert "Возможная разница себестоимости второй минус первой: 10.00–60.00 ₽" in result["message"]
    assert "Покрытие источников различается" in result["message"]

    second_payload["period_to"] = "2026-12-31"
    result = service.show_history_comparison(runtime, "101", session)
    assert "Общая дельта не рассчитана" in result["message"]
    assert "Возможная разница себестоимости" not in result["message"]


def test_saved_estimates_are_reachable_from_fresh_fifo_card_for_applied_and_cancelled_cases():
    class CostHistory:
        def get_sku_history(self, **_kwargs):
            return {
                "error": False, "revision": 4, "queue_initialized": True,
                "cutoff_date": None, "next_unit_cost_rub": "14.65",
                "next_unit_cost_basis": "UNKNOWN", "next_planned_rate": None,
                "remaining_status": "NO_CUTOFF", "movement_count": 0,
                "latest_allocation": None, "cutoff_mapping_status": None,
                "complete_through": None, "cutoff_mapping_revision": None,
                "active_rate": None, "layers": [], "rates": [],
            }

    class ReadOnlyTransition:
        writes = 0
        state = "APPLIED"
        case_revision = 1
        case_id = "case-applied"

        def _payload(self):
            return {
                "old_unit_cost_rub": "21.00", "new_unit_cost_rub": "14.65",
                "dispatch_date": "2026-11-05",
                "metadata": {
                    "scope": {"owner_id": "owner-test", **IDENTITY},
                    "store_timezone": "Europe/Moscow",
                },
            }

        def list_cases(self, *, states, **_kwargs):
            cases = []
            if self.state in states:
                cases.append({
                    "case_id": self.case_id, "case_revision": self.case_revision,
                    "state": self.state, "case": self._payload(),
                })
            return {"error": False, "cases": cases}

        def get_case(self, *, case_id, **_kwargs):
            if case_id != self.case_id:
                return {"error": True, "code": "CASE_NOT_FOUND"}
            return {
                "error": False, "case_revision": self.case_revision,
                "state": self.state, "case": self._payload(),
            }

    class AppliedReceipt:
        def read_commit(self, **_kwargs):
            return {
                "error": False, "code": "FIFO_TRANSITION_APPLIED",
                "commit_id": "commit-test", "complete_through": "2026-11-20",
                "case_revision": transition.case_revision,
            }

    class SavedEstimates:
        def __init__(self):
            self.reads = []

        def read_provisional_preview_history(self, **kwargs):
            self.reads.append(dict(kwargs))
            row = {
                "preview_id": f"estimate-{transition.state}",
                "created_at_utc": "2026-11-22T12:00:00Z",
                "payload": {
                    "schema_version": 2, "model_kind": "SUMMARY_RANGE",
                    "currency": "RUB", "period_from": "2026-11-01",
                    "period_to": "2026-11-22", "method": "AGGREGATE_SUMMARY_V1",
                    "policy_version": "fifo-provisional-summary-v1",
                    "result": {"redeemed_units": 10}, "rates": {},
                    "assumptions": {}, "evidence_fingerprints": ["a" * 64],
                },
            }
            return {"error": False, "items": [row], "total": 1, "offset": 0, "limit": 8}

    transition = ReadOnlyTransition()
    estimates = SavedEstimates()
    provisional = TelegramFifoCostProvisionalService(
        evidence_reader=object(), summary_service=FifoCostProvisionalSummaryService(),
        estimate_repository=estimates,
    )
    runtime = TelegramFifoCostTransitionRuntimeService(
        transition, CostHistory(), apply_service=AppliedReceipt(),
        provisional_service=provisional,
    )
    history = TelegramFifoCostHistoryService(
        history_service=CostHistory(), transition_service=transition,
    )
    adapter = SellerCostTelegramAdapter(
        assistant=object(), keyboard_service=object(), button_handler=object(),
        fifo_history_service=history, fifo_transition_runtime_service=runtime,
    )
    tenant_token = set_current_tenant_user_id(TENANT)
    try:
        for index, state in enumerate(("APPLIED", "CANCELLED"), start=1):
            transition.state = state
            transition.case_id = f"case-{state.lower()}"
            transition.case_revision = index
            runtime.clear_pending("owner-test")
            history = TelegramFifoCostHistoryService(
                history_service=CostHistory(), transition_service=transition,
            )
            adapter.fifo_history_service = history
            opened = history.create_sku_callback(
                user_id="owner-test", **IDENTITY, display_name="Тестовый товар",
            )
            card = adapter.handle_button(opened["callback"], user_id="owner-test")
            assert card["error"] is False, card
            cases_button = _ticket_for(runtime, card, "transition_cases")
            case_list = adapter.handle_button(cases_button, user_id="owner-test")
            saved_button = next((
                button["callback"] for button in case_list["keyboard"]["buttons"]
                if ":resume:" in button["callback"] and state in button["text"]
            ))
            summary = adapter.handle_button(saved_button, user_id="owner-test")
            assert summary["error"] is False, summary
            saved_history_button = _ticket_for(runtime, summary, "provisional_history")
            history_list = adapter.handle_button(saved_history_button, user_id="owner-test")
            assert "Сохранённые предварительные оценки" in history_list["message"]
            assert "2026-11-01–2026-11-22" in history_list["message"]
            assert runtime._sessions["owner-test"]["state"] == state
        assert len(estimates.reads) == 2
        assert transition.writes == 0

        transition.state = "APPLIED"
        transition.case_id = "case-stale"
        transition.case_revision += 1
        runtime.clear_pending("owner-test")
        history = TelegramFifoCostHistoryService(
            history_service=CostHistory(), transition_service=transition,
        )
        adapter.fifo_history_service = history
        opened = history.create_sku_callback(
            user_id="owner-test", **IDENTITY, display_name="Тестовый товар",
        )
        card = adapter.handle_button(opened["callback"], user_id="owner-test")
        case_list = adapter.handle_button(
            _ticket_for(runtime, card, "transition_cases"), user_id="owner-test",
        )
        stale_button = next((
            button["callback"] for button in case_list["keyboard"]["buttons"]
            if ":resume:" in button["callback"]
        ))
        transition.case_revision += 1
        stale = adapter.handle_button(stale_button, user_id="owner-test")
        assert stale["error"] is True
        assert transition.writes == 0
    finally:
        reset_current_tenant_user_id(tenant_token)
