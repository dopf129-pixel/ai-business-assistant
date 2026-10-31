from datetime import datetime, timezone
from types import SimpleNamespace

from services.ozon_account_repository import make_store_tenant_scope
from services.planning_workspace_repository import PlanningWorkspaceRepository
from services.tenant_context import reset_current_tenant_user_id, set_current_tenant_user_id
from services.assistant_button_handler_service import AssistantButtonHandlerService
from services.assistant_keyboard_service import AssistantKeyboardService
from services.analytics_export_service import AnalyticsExportService
from services.unit_economics_experiment_history_export_service import (
    UnitEconomicsExperimentHistoryExportService,
)
from services.unit_economics_experiment_phase_collection_service import (
    UnitEconomicsExperimentPhaseCollectionService,
)
from services.unit_economics_experiment_phase_comparison_service import (
    UnitEconomicsExperimentPhaseComparisonService,
)
from services.unit_economics_experiment_phase_readiness_service import (
    UnitEconomicsExperimentPhaseReadinessService,
)
from services.telegram_unit_economics_experiment_runtime_service import (
    TelegramUnitEconomicsExperimentRuntimeService,
)
from test_unit_economics_experiment_phase_readiness_service import _mature_evidence


def _identity():
    return {
        "owner_id": "owner-1", "store_id": "store-a", "product_id": "product-1",
        "offer_id": "offer-1", "sku": "sku-1", "sale_schema": "FBO",
    }


def _plan_payload():
    return {
        "plan_kind": "single", "schema_version": 1, "calculation_version": 1,
        "target_margin_percent": "25.00", "items": [{
            "identity": {
                "product_id": "product-1", "offer_id": "offer-1", "sku": "sku-1",
                "product_name": "Item", "store_id": "store-a", "scheme": "FBO",
            },
            "inputs": {
                "price": "100.00", "cost": "20.00", "commission_rate": "14",
                "advertising_rate": "0", "discount_points_rate": "0",
                "logistics_per_unit": "10", "last_mile_per_unit": "3",
                "acquiring_per_unit": "2", "tax_mode": "USN_INCOME",
                "tax_rate": "6", "minimum_tax_rate": None,
            },
            "provenance": {"price": "owner_input", "cost": "owner_input"},
            "sources": {
                "periods": {}, "as_of": "2026-10-29T12:00:00Z",
                "loaded_at": "2026-10-29T12:00:00Z", "completeness": {},
            },
            "projection": {"available": True, "missing_inputs": [], "invalid_inputs": [],
                           "revenue": "100.00", "profit": "45.00"},
        }],
    }


def _snapshot_payload():
    return {
        "schema_version": 1, "identity": _identity(),
        "readiness": {
            "error": False, "schema_version": 1, "status": "COMPLETE",
            "scope_kind": "REFERENCE_56_COMPLETED_LOCAL_DAYS",
            "window": {
                "from_date": "2026-08-01", "to_date": "2026-09-25",
                "date_basis": "LOCAL_CALENDAR_DAY", "timezone": "Europe/Moscow",
            },
            "coverage_status": "COMPLETE", "coverage_complete": True,
            "denominator": {"units": 10, "kind": "ORDERED_UNITS_WINDOW"},
            "component_counts": {"INCLUDED": 0, "EXCLUDED": 0, "UNKNOWN": 0},
            "components": [], "read_only": True, "api_calls": 0,
        },
    }


def _enter_context(owner="owner-1", store="store-a"):
    return set_current_tenant_user_id(make_store_tenant_scope(owner, store))


def _button(result, prefix):
    return next(
        button["callback"] for button in result["keyboard"]["buttons"]
        if button["callback"].startswith(prefix)
    )


def _button_text(result, text):
    return next(
        button["callback"] for button in result["keyboard"]["buttons"]
        if text in button["text"]
    )


def _button_action(result, runtime, kind, prefix, *, predicate=None):
    scope = runtime._scope("owner-1")
    for button in result["keyboard"]["buttons"]:
        callback = button["callback"]
        if not callback.startswith(prefix):
            continue
        action = runtime._get_action(callback.rsplit(":", 1)[-1], scope)
        if (isinstance(action, dict) and action.get("kind") == kind
                and (predicate is None or predicate(action))):
            return callback
    raise AssertionError(f"button action not found: {kind}")


class _PartialReferenceSnapshotCollector:
    def __init__(self):
        self.calls = []

    def collect(self, identity, *, owner_id, store_id, timezone_name):
        self.calls.append((identity, owner_id, store_id, timezone_name))
        return {
            "error": False, "status": "PARTIAL", "reason_code": "RETURNS_PARTIAL",
            "read_only": True, "source_io": True,
        }


class _RuntimePhaseEvidenceCollector:
    def __init__(self, clock):
        self.clock = clock
        self.prices = {}
        self.calls = []

    def collect_window(self, observation_id, *, date_from, date_to):
        self.calls.append((observation_id, date_from, date_to))
        evidence = _mature_evidence()
        evidence["seller_price_cents"] = self.prices[observation_id]
        evidence["window"] = {
            "from": date_from, "to": date_to, "timezone": "Europe/Moscow",
            "date_basis": "SOURCE_CALENDAR_DATE",
        }
        evidence["collected_at"] = self.clock.now.isoformat().replace("+00:00", "Z")
        return evidence


def _seed(repo, *, with_snapshot=True):
    saved = repo.save_document(
        title="SKU plan", payload=_plan_payload(), idempotency_key="uex-plan-save01",
    )
    assert saved["error"] is False
    snapshot = None
    if with_snapshot:
        snapshot = repo.create_unit_economics_expense_snapshot(_snapshot_payload())
        assert snapshot["error"] is False
    return saved, snapshot


def _activate_experiment(repo, runtime, user_id="owner-1"):
    plans = runtime.handle_callback("uex:new", user_id=user_id)
    selected_plan = runtime.handle_callback(_button(plans, "uex:a:"), user_id=user_id)
    selected_snapshot = runtime.handle_callback(
        _button(selected_plan, "uex:a:"), user_id=user_id,
    )
    runtime.handle_text("95; 105", user_id=user_id)
    controls = runtime.handle_text("100; 2026-10-29 12:00", user_id=user_id)
    preview = runtime.handle_callback(
        _button_text(controls, "Все условия без изменений"), user_id=user_id,
    )
    active = runtime.handle_callback(
        _button_text(preview, "Подтверждаю и начать"), user_id=user_id,
    )
    assert active["status"] == "UNIT_ECONOMICS_EXPERIMENT_BASELINE_ACTIVE"
    experiments = repo.list_price_experiments(
        owner_id="owner-1", store_id="store-a", limit=10,
    )
    experiment = experiments["items"][0]
    phase = repo.list_price_experiment_phases(
        experiment["experiment_id"], limit=10,
        owner_id="owner-1", store_id="store-a",
    )["items"][0]
    return experiment, phase, selected_snapshot


def _create_unconfirmed_baseline(repo, runtime, user_id="owner-1"):
    _seed(repo)
    plans = runtime.handle_callback("uex:new", user_id=user_id)
    selected_plan = runtime.handle_callback(_button(plans, "uex:a:"), user_id=user_id)
    runtime.handle_callback(_button(selected_plan, "uex:a:"), user_id=user_id)
    runtime.handle_text("95; 105", user_id=user_id)
    controls = runtime.handle_text("100; 2026-10-29 12:00", user_id=user_id)
    return runtime.handle_callback(
        _button_text(controls, "Все условия без изменений"), user_id=user_id,
    )


def test_guided_wizard_creates_and_activates_owner_confirmed_baseline(tmp_path):
    repo = PlanningWorkspaceRepository(db_path=tmp_path / "planning.sqlite")
    now = datetime(2026, 10, 29, 12, 0, tzinfo=timezone.utc)
    runtime = TelegramUnitEconomicsExperimentRuntimeService(
        repository=repo, clock=lambda: now, monotonic_clock=lambda: 100.0,
    )
    token = _enter_context()
    try:
        _seed(repo)
        menu = runtime.open_menu("owner-1")
        assert menu["status"] == "UNIT_ECONOMICS_EXPERIMENT_MENU"
        plans = runtime.handle_callback("uex:new", user_id="owner-1")
        selected_plan = runtime.handle_callback(
            _button(plans, "uex:a:"), user_id="owner-1",
        )
        assert selected_plan["status"] == "UNIT_ECONOMICS_EXPERIMENT_SNAPSHOT_SELECTION"
        prices_prompt = runtime.handle_callback(
            _button(selected_plan, "uex:a:"), user_id="owner-1",
        )
        assert prices_prompt["status"] == "UNIT_ECONOMICS_EXPERIMENT_PRICES_REQUIRED"
        baseline_prompt = runtime.handle_text("95; 99,90; 105", user_id="owner-1")
        assert baseline_prompt["status"] == "UNIT_ECONOMICS_EXPERIMENT_BASELINE_INPUT_REQUIRED"
        controls = runtime.handle_text(
            "100; 2026-10-29 12:00", user_id="owner-1",
        )
        assert controls["status"] == "UNIT_ECONOMICS_EXPERIMENT_CONTROL_CONFIRMATION_REQUIRED"
        preview = runtime.handle_callback(
            _button_text(controls, "Все условия без изменений"), user_id="owner-1",
        )
        assert preview["status"] == "UNIT_ECONOMICS_EXPERIMENT_CONFIRMATION_REQUIRED"
        assert "2026-10-30 — 2026-11-05" in preview["message"]
        active = runtime.handle_callback(
            _button(preview, "uex:a:"), user_id="owner-1",
        )
        assert active["status"] == "UNIT_ECONOMICS_EXPERIMENT_BASELINE_ACTIVE"
        experiments = repo.list_price_experiments(
            owner_id="owner-1", store_id="store-a", limit=10,
        )
        assert experiments["error"] is False
        assert len(experiments["items"]) == 1
        experiment = experiments["items"][0]
        assert experiment["status"] == "BASELINE_ACTIVE"
        assert experiment["config"]["candidate_prices_cents"] == [9500, 9990, 10500]
        assert experiment["config"]["control_flags"] == {
            key: "UNCHANGED" for key in (
                "inventory", "promotion", "advertising", "card", "cost", "tariff",
            )
        }
    finally:
        reset_current_tenant_user_id(token)


def test_wizard_blocks_when_no_full_reference_snapshot_exists(tmp_path):
    repo = PlanningWorkspaceRepository(db_path=tmp_path / "planning.sqlite")
    runtime = TelegramUnitEconomicsExperimentRuntimeService(repository=repo)
    token = _enter_context()
    try:
        _seed(repo, with_snapshot=False)
        plans = runtime.handle_callback("uex:new", user_id="owner-1")
        selected_plan = runtime.handle_callback(
            _button(plans, "uex:a:"), user_id="owner-1",
        )
        assert selected_plan["status"] == (
            "UNIT_ECONOMICS_EXPERIMENT_REFERENCE_SNAPSHOT_REQUIRED"
        )
        assert "CPC" in selected_plan["message"]
        assert "56" in selected_plan["message"]
        experiments = repo.list_price_experiments(
            owner_id="owner-1", store_id="store-a", limit=10,
        )
        assert experiments["items"] == []
    finally:
        reset_current_tenant_user_id(token)


def test_wizard_exposes_and_runs_first_reference_collection_action(tmp_path):
    repo = PlanningWorkspaceRepository(db_path=tmp_path / "planning.sqlite")
    collector = _PartialReferenceSnapshotCollector()
    runtime = TelegramUnitEconomicsExperimentRuntimeService(
        repository=repo, reference_snapshot_collection_service=collector,
    )
    token = _enter_context()
    try:
        _seed(repo, with_snapshot=False)
        plans = runtime.handle_callback("uex:new", user_id="owner-1")
        selected_plan = runtime.handle_callback(
            _button(plans, "uex:a:"), user_id="owner-1",
        )
        assert selected_plan["status"] == (
            "UNIT_ECONOMICS_EXPERIMENT_REFERENCE_SNAPSHOT_REQUIRED"
        )
        collect_callback = _button_text(selected_plan, "Собрать снимок за 56 дней")

        partial = runtime.handle_callback(collect_callback, user_id="owner-1")

        assert partial["status"] == (
            "UNIT_ECONOMICS_EXPERIMENT_REFERENCE_COLLECTION_PARTIAL"
        )
        assert collector.calls == [(_identity(), "owner-1", "store-a", "Europe/Moscow")]
        assert _button_text(partial, "Повторить сбор").startswith("uex:a:")
        experiments = repo.list_price_experiments(
            owner_id="owner-1", store_id="store-a", limit=10,
        )
        assert experiments["items"] == []
    finally:
        reset_current_tenant_user_id(token)


def test_telegram_exposes_complete_baseline_candidate_and_owner_decision_lifecycle(tmp_path):
    now = SimpleNamespace(now=datetime(2026, 10, 29, 12, 0, tzinfo=timezone.utc))
    repo = PlanningWorkspaceRepository(
        db_path=tmp_path / "planning.sqlite", clock=lambda: now.now,
    )
    evidence_collector = _RuntimePhaseEvidenceCollector(now)
    phase_collection = UnitEconomicsExperimentPhaseCollectionService(
        repo, evidence_collector, clock=lambda: now.now,
    )
    phase_readiness = UnitEconomicsExperimentPhaseReadinessService(
        repo, clock=lambda: now.now,
    )
    phase_comparison = UnitEconomicsExperimentPhaseComparisonService(
        repo, clock=lambda: now.now,
    )
    runtime = TelegramUnitEconomicsExperimentRuntimeService(
        repository=repo, phase_collection_service=phase_collection,
        phase_readiness_service=phase_readiness,
        phase_comparison_service=phase_comparison,
        clock=lambda: now.now, monotonic_clock=lambda: 100.0,
    )
    token = _enter_context()
    try:
        _seed(repo)
        experiment, baseline, _ = _activate_experiment(repo, runtime)
        evidence_collector.prices[baseline["observation_id"]] = 10_000
        now.now = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)

        experiment_list = runtime.handle_callback("uex:experiments:0", user_id="owner-1")
        experiment_detail = runtime.handle_callback(
            _button(experiment_list, "uex:read:"), user_id="owner-1",
        )
        baseline_detail = runtime.handle_callback(
            _button_action(experiment_detail, runtime, "phase", "uex:read:"),
            user_id="owner-1",
        )
        controls_updated = runtime.handle_callback(
            _button_action(
                baseline_detail, runtime, "phase_control_update", "uex:read:",
                predicate=lambda action: set(action["control_flags"].values()) == {"UNCHANGED"},
            ), user_id="owner-1",
        )
        assert controls_updated["status"] == "UNIT_ECONOMICS_EXPERIMENT_CONTROLS_UPDATED"
        collected = runtime.handle_callback(
            _button_action(controls_updated, runtime, "phase_collect", "uex:read:"),
            user_id="owner-1",
        )
        assert collected["status"] == "UNIT_ECONOMICS_EXPERIMENT_PHASE_COLLECTION_SAVED"
        now.now = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)
        evaluated = runtime.handle_callback(
            _button_action(collected, runtime, "phase_evaluate", "uex:read:"),
            user_id="owner-1",
        )
        assert evaluated["status"] == "UNIT_ECONOMICS_EXPERIMENT_PHASE_EVALUATED"
        baseline_finished = runtime.handle_callback(
            _button_action(evaluated, runtime, "phase_finish", "uex:read:"),
            user_id="owner-1",
        )
        assert baseline_finished["status"] == "UNIT_ECONOMICS_EXPERIMENT_PHASE_FINISHED"
        candidate_action = _button_action(
            baseline_finished, runtime, "start_candidate", "uex:a:",
            predicate=lambda action: action.get("price_cents") == 9500,
        )

        now.now = datetime(2026, 11, 14, 13, 0, tzinfo=timezone.utc)
        runtime.handle_callback(candidate_action, user_id="owner-1")
        candidate_controls = runtime.handle_text(
            "95; 2026-11-14 15:00", user_id="owner-1",
        )
        candidate_confirmation = runtime.handle_callback(
            _button_action(
                candidate_controls, runtime, "candidate_controls", "uex:a:",
                predicate=lambda action: set(action["control_flags"].values()) == {"UNCHANGED"},
            ), user_id="owner-1",
        )
        candidate_started = runtime.handle_callback(
            _button_action(candidate_confirmation, runtime, "confirm", "uex:a:"),
            user_id="owner-1",
        )
        assert candidate_started["status"] == "UNIT_ECONOMICS_EXPERIMENT_CANDIDATE_ACTIVE"

        phases = repo.list_price_experiment_phases(
            experiment["experiment_id"], limit=10,
            owner_id="owner-1", store_id="store-a",
        )
        candidate = next(item for item in phases["items"] if item["kind"] == "CANDIDATE")
        evidence_collector.prices[candidate["observation_id"]] = 9_500
        now.now = datetime(2026, 11, 29, 12, 0, tzinfo=timezone.utc)
        experiment_list = runtime.handle_callback("uex:experiments:0", user_id="owner-1")
        experiment_detail = runtime.handle_callback(
            _button(experiment_list, "uex:read:"), user_id="owner-1",
        )
        candidate_detail = runtime.handle_callback(
            _button_action(
                experiment_detail, runtime, "phase", "uex:read:",
                predicate=lambda action: action.get("phase_id") == candidate["phase_id"],
            ), user_id="owner-1",
        )
        candidate_controls_updated = runtime.handle_callback(
            _button_action(
                candidate_detail, runtime, "phase_control_update", "uex:read:",
                predicate=lambda action: set(action["control_flags"].values()) == {"UNCHANGED"},
            ), user_id="owner-1",
        )
        late_control_update = _button_action(
            candidate_controls_updated, runtime, "phase_control_update", "uex:read:",
            predicate=lambda action: set(action["control_flags"].values()) == {"UNKNOWN"},
        )
        candidate_collected = runtime.handle_callback(
            _button_action(candidate_controls_updated, runtime, "phase_collect", "uex:read:"),
            user_id="owner-1",
        )
        now.now = datetime(2026, 11, 29, 12, 0, tzinfo=timezone.utc)
        candidate_evaluated = runtime.handle_callback(
            _button_action(candidate_collected, runtime, "phase_evaluate", "uex:read:"),
            user_id="owner-1",
        )
        candidate_results = repo.list_price_experiment_results(
            experiment["experiment_id"], candidate["phase_id"], limit=1,
            owner_id="owner-1", store_id="store-a",
        )
        latest_candidate = candidate_results["items"][0]["payload"]
        assert latest_candidate["status"] == "READY", [
            (gate["gate"], gate["status"], gate["reason_code"])
            for gate in latest_candidate["quality_gates"]
        ]
        candidate_finished = runtime.handle_callback(
            _button_action(candidate_evaluated, runtime, "phase_finish", "uex:read:"),
            user_id="owner-1",
        )
        assert candidate_finished["status"] == "UNIT_ECONOMICS_EXPERIMENT_PHASE_FINISHED"

        candidate_detail = runtime.handle_callback(
            _button_action(
                candidate_finished, runtime, "phase", "uex:read:",
                predicate=lambda action: action.get("phase_id") == candidate["phase_id"],
            ), user_id="owner-1",
        )
        comparison = runtime.handle_callback(
            _button_action(candidate_detail, runtime, "phase_compare", "uex:read:"),
            user_id="owner-1",
        )
        assert comparison["status"] == "UNIT_ECONOMICS_EXPERIMENT_RESULT_DETAIL"
        stale_selection = _button_action(
            comparison, runtime, "owner_decision", "uex:read:",
            predicate=lambda action: action.get("decision_type") == "SELECT_EVALUATED_CANDIDATE",
        )
        conditions_changed = runtime.handle_callback(
            late_control_update, user_id="owner-1",
        )
        assert conditions_changed["status"] == "UNIT_ECONOMICS_EXPERIMENT_CONTROLS_UPDATED"
        phase_results = runtime.handle_callback(
            _button_action(conditions_changed, runtime, "phase_results", "uex:read:"),
            user_id="owner-1",
        )
        stale_selection_action = runtime._get_action(
            stale_selection.rsplit(":", 1)[-1], runtime._scope("owner-1"),
        )
        reopened_old_comparison = runtime.handle_callback(
            _button_action(
                phase_results, runtime, "result", "uex:read:",
                predicate=lambda action: action.get("result_revision")
                == stale_selection_action["result_revision"],
            ), user_id="owner-1",
        )
        assert "Сравнение устарело" in reopened_old_comparison["message"]
        reopened_actions = [
            runtime._get_action(
                button["callback"].rsplit(":", 1)[-1], runtime._scope("owner-1"),
            )
            for button in reopened_old_comparison["keyboard"]["buttons"]
            if button["callback"].startswith("uex:read:")
        ]
        assert not any(
            isinstance(action, dict) and action.get("kind") == "owner_decision"
            for action in reopened_actions
        )
        rejected_selection = runtime.handle_callback(stale_selection, user_id="owner-1")
        assert rejected_selection["status"] == "UNIT_ECONOMICS_EXPERIMENT_ACTION_STALE"
        refreshed_comparison = runtime.handle_callback(
            _button_action(conditions_changed, runtime, "phase_compare", "uex:read:"),
            user_id="owner-1",
        )
        assert refreshed_comparison["status"] == "UNIT_ECONOMICS_EXPERIMENT_RESULT_DETAIL"
        completed = runtime.handle_callback(
            _button_action(
                refreshed_comparison, runtime, "owner_decision", "uex:read:",
                predicate=lambda action: action.get("decision_type") == "STOP_WITHOUT_PRICE_CHANGE",
            ), user_id="owner-1",
        )
        assert completed["status"] == "UNIT_ECONOMICS_EXPERIMENT_OWNER_DECISION_SAVED"
        stored = repo.get_price_experiment(
            experiment["experiment_id"], owner_id="owner-1", store_id="store-a",
        )["experiment"]
        assert stored["status"] == "COMPLETED"
        assert len(evidence_collector.calls) == 2
    finally:
        reset_current_tenant_user_id(token)


def test_old_finish_button_cannot_finish_a_newer_result_revision(tmp_path):
    now = SimpleNamespace(now=datetime(2026, 10, 29, 12, 0, tzinfo=timezone.utc))
    repo = PlanningWorkspaceRepository(
        db_path=tmp_path / "planning.sqlite", clock=lambda: now.now,
    )
    evidence_collector = _RuntimePhaseEvidenceCollector(now)
    collection_service = UnitEconomicsExperimentPhaseCollectionService(
        repo, evidence_collector, clock=lambda: now.now,
    )
    readiness_service = UnitEconomicsExperimentPhaseReadinessService(
        repo, clock=lambda: now.now,
    )
    runtime = TelegramUnitEconomicsExperimentRuntimeService(
        repository=repo, phase_collection_service=collection_service,
        phase_readiness_service=readiness_service,
        clock=lambda: now.now, monotonic_clock=lambda: 100.0,
    )
    token = _enter_context()
    try:
        _seed(repo)
        experiment, phase, _ = _activate_experiment(repo, runtime)
        evidence_collector.prices[phase["observation_id"]] = 10_000
        now.now = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)
        experiment_list = runtime.handle_callback("uex:experiments:0", user_id="owner-1")
        experiment_detail = runtime.handle_callback(
            _button(experiment_list, "uex:read:"), user_id="owner-1",
        )
        phase_detail = runtime.handle_callback(
            _button_action(experiment_detail, runtime, "phase", "uex:read:"),
            user_id="owner-1",
        )
        collected = runtime.handle_callback(
            _button_action(phase_detail, runtime, "phase_collect", "uex:read:"),
            user_id="owner-1",
        )
        evaluated = runtime.handle_callback(
            _button_action(collected, runtime, "phase_evaluate", "uex:read:"),
            user_id="owner-1",
        )
        assert evaluated["status"] == "UNIT_ECONOMICS_EXPERIMENT_PHASE_EVALUATED"
        old_finish_callback = _button_action(
            evaluated, runtime, "phase_finish", "uex:read:",
        )

        current_experiment = repo.get_price_experiment(
            experiment["experiment_id"], owner_id="owner-1", store_id="store-a",
        )["experiment"]
        current_phase = repo.list_price_experiment_phases(
            experiment["experiment_id"], owner_id="owner-1", store_id="store-a",
        )["items"][0]
        newer_result = readiness_service.evaluate_latest(
            experiment["experiment_id"], phase["phase_id"],
            expected_state_revision=current_experiment["state_revision"],
            expected_phase_state_revision=current_phase["state_revision"],
            expected_result_revision=current_phase["result_revision"],
            idempotency_key="w41-newer-ready-result01",
            owner_id="owner-1", store_id="store-a",
        )
        assert newer_result["error"] is False
        assert newer_result["status"] == "READY"

        stale_finish = runtime.handle_callback(old_finish_callback, user_id="owner-1")
        assert stale_finish["status"] == "UNIT_ECONOMICS_EXPERIMENT_ACTION_STALE"
        phase_after = repo.list_price_experiment_phases(
            experiment["experiment_id"], owner_id="owner-1", store_id="store-a",
        )["items"][0]
        assert phase_after["status"] == "ACTIVE"
        assert phase_after["result_revision"] == newer_result["result_revision"]
    finally:
        reset_current_tenant_user_id(token)


def test_invalid_candidate_prices_keep_wizard_draft_open(tmp_path):
    repo = PlanningWorkspaceRepository(db_path=tmp_path / "planning.sqlite")
    runtime = TelegramUnitEconomicsExperimentRuntimeService(repository=repo)
    token = _enter_context()
    try:
        _seed(repo)
        plans = runtime.handle_callback("uex:new", user_id="owner-1")
        selected_plan = runtime.handle_callback(
            _button(plans, "uex:a:"), user_id="owner-1",
        )
        runtime.handle_callback(_button(selected_plan, "uex:a:"), user_id="owner-1")
        invalid = runtime.handle_text("95; 95; 105", user_id="owner-1")
        assert invalid["status"] == "UNIT_ECONOMICS_EXPERIMENT_PRICES_INVALID"
        valid = runtime.handle_text("95; 105", user_id="owner-1")
        assert valid["status"] == "UNIT_ECONOMICS_EXPERIMENT_BASELINE_INPUT_REQUIRED"
    finally:
        reset_current_tenant_user_id(token)


def test_plan_action_is_invalidated_when_owner_switches_store(tmp_path):
    repo = PlanningWorkspaceRepository(db_path=tmp_path / "planning.sqlite")
    runtime = TelegramUnitEconomicsExperimentRuntimeService(repository=repo)
    token = _enter_context()
    try:
        _seed(repo)
        plans = runtime.handle_callback("uex:new", user_id="owner-1")
        callback = _button(plans, "uex:a:")
        store_token = set_current_tenant_user_id(
            make_store_tenant_scope("owner-1", "store-b")
        )
        try:
            result = runtime.handle_callback(callback, user_id="owner-1")
            assert result["status"] == "UNIT_ECONOMICS_EXPERIMENT_ACTION_STALE"
        finally:
            reset_current_tenant_user_id(store_token)
    finally:
        reset_current_tenant_user_id(token)


def test_cancel_invalidates_confirmation_and_cancels_unstarted_experiment(tmp_path):
    repo = PlanningWorkspaceRepository(db_path=tmp_path / "planning.sqlite")
    now = datetime(2026, 10, 29, 12, 0, tzinfo=timezone.utc)
    runtime = TelegramUnitEconomicsExperimentRuntimeService(
        repository=repo, clock=lambda: now, monotonic_clock=lambda: 100.0,
    )
    token = _enter_context()
    try:
        _seed(repo)
        plans = runtime.handle_callback("uex:new", user_id="owner-1")
        selected_plan = runtime.handle_callback(
            _button(plans, "uex:a:"), user_id="owner-1",
        )
        runtime.handle_callback(_button(selected_plan, "uex:a:"), user_id="owner-1")
        runtime.handle_text("95; 105", user_id="owner-1")
        controls = runtime.handle_text(
            "100; 2026-10-29 12:00", user_id="owner-1",
        )
        preview = runtime.handle_callback(
            _button_text(controls, "Все условия без изменений"), user_id="owner-1",
        )
        confirm_callback = _button_text(preview, "Подтверждаю и начать")
        cancelled = runtime.handle_callback("uex:c", user_id="owner-1")
        assert "Отменён" in cancelled["message"]
        stale = runtime.handle_callback(confirm_callback, user_id="owner-1")
        assert stale["status"] == "UNIT_ECONOMICS_EXPERIMENT_ACTION_STALE"
        experiments = repo.list_price_experiments(
            owner_id="owner-1", store_id="store-a", limit=10,
        )
        assert experiments["items"][0]["status"] == "CANCELLED"
    finally:
        reset_current_tenant_user_id(token)


def test_public_button_handler_routes_experiment_callback_and_text(tmp_path):
    repo = PlanningWorkspaceRepository(db_path=tmp_path / "planning.sqlite")
    runtime = TelegramUnitEconomicsExperimentRuntimeService(repository=repo)
    product_service = SimpleNamespace(load_products=lambda: [{"sku": "sku-1"}])
    handler = AssistantButtonHandlerService(
        assistant=None, keyboard_service=AssistantKeyboardService(),
        unit_economics_query=SimpleNamespace(product_service=product_service),
        unit_economics_experiment_runtime_service=runtime,
    )
    token = _enter_context()
    try:
        opened = handler.handle("uex:m", user_id="owner-1")
        assert opened["status"] == "UNIT_ECONOMICS_EXPERIMENT_MENU"
        assert handler.handle_text("95; 105", user_id="owner-1") is None
        unit_economics = handler._open_unit_economics_menu(user_id="owner-1")
        assert any(
            button["callback"] == "uex:m"
            for button in unit_economics["keyboard"]["buttons"]
        )
    finally:
        reset_current_tenant_user_id(token)


def test_candidate_prices_require_semicolon_list_and_exact_cents():
    parse = TelegramUnitEconomicsExperimentRuntimeService._parse_price_list
    assert parse("95; 99,90; 105") == [9500, 9990, 10500]
    assert parse("95; 95") is None
    assert parse("95; 0") is None
    assert parse("95; 99,999") is None
    assert parse("95") is None


def test_experiment_callbacks_stay_within_telegram_limit():
    callback = "uex:a:" + ("a" * 16)
    assert len(callback.encode("utf-8")) <= 64


def test_unit_economics_keyboard_exposes_experiment_entry():
    keyboard = AssistantKeyboardService().build_unit_economics_keyboard(
        ["sku-1"], experiment_callback="uex:m",
    )
    assert any(
        button["callback"] == "uex:m"
        and button["text"] == "🧪 Эксперименты цен"
        for button in keyboard["buttons"]
    )


def test_experiment_history_reopens_after_runtime_restart_and_links_observation(tmp_path):
    repo = PlanningWorkspaceRepository(db_path=tmp_path / "planning.sqlite")
    now = datetime(2026, 10, 29, 12, 0, tzinfo=timezone.utc)
    first_runtime = TelegramUnitEconomicsExperimentRuntimeService(
        repository=repo, clock=lambda: now, monotonic_clock=lambda: 100.0,
        observation_runtime_service=object(),
    )
    token = _enter_context()
    try:
        _seed(repo)
        _activate_experiment(repo, first_runtime)
        old_menu = first_runtime.open_menu("owner-1")
        stale_action = _button(old_menu, "uex:read:")

        restarted_runtime = TelegramUnitEconomicsExperimentRuntimeService(
            repository=repo, clock=lambda: now, monotonic_clock=lambda: 101.0,
            observation_runtime_service=object(),
        )
        stale = restarted_runtime.handle_callback(stale_action, user_id="owner-1")
        assert stale["status"] == "UNIT_ECONOMICS_EXPERIMENT_ACTION_STALE"

        reopened_menu = restarted_runtime.open_menu("owner-1")
        detail = restarted_runtime.handle_callback(
            _button(reopened_menu, "uex:read:"), user_id="owner-1",
        )
        assert detail["status"] == "UNIT_ECONOMICS_EXPERIMENT_DETAIL"
        assert "базовая фаза" in detail["message"]
        assert any(button["callback"].startswith("upo:o:")
                   for button in detail["keyboard"]["buttons"])

        snapshot = restarted_runtime.handle_callback(
            _button_text(detail, "Сохранённые исходные"), user_id="owner-1",
        )
        assert snapshot["status"] == "UNIT_ECONOMICS_EXPERIMENT_FROZEN_SNAPSHOT"
        assert "данные Ozon не запрашивались" in snapshot["message"]
        assert all(len(button["callback"].encode("utf-8")) <= 64
                   for button in detail["keyboard"]["buttons"])
    finally:
        reset_current_tenant_user_id(token)


def test_unconfirmed_phase_can_resume_or_cancel_after_runtime_restart(tmp_path):
    now = datetime(2026, 10, 29, 12, 0, tzinfo=timezone.utc)
    repo = PlanningWorkspaceRepository(
        db_path=tmp_path / "planning.sqlite", clock=lambda: now,
    )
    first_runtime = TelegramUnitEconomicsExperimentRuntimeService(
        repository=repo, clock=lambda: now, monotonic_clock=lambda: 100.0,
    )
    token = _enter_context()
    try:
        preview = _create_unconfirmed_baseline(repo, first_runtime)
        assert preview["status"] == "UNIT_ECONOMICS_EXPERIMENT_CONFIRMATION_REQUIRED"

        restarted = TelegramUnitEconomicsExperimentRuntimeService(
            repository=repo, clock=lambda: now, monotonic_clock=lambda: 101.0,
        )
        menu = restarted.open_menu("owner-1")
        experiment_detail = restarted.handle_callback(
            _button(menu, "uex:read:"), user_id="owner-1",
        )
        cancel_prompt = restarted.handle_callback(
            _button_text(experiment_detail, "Отменить незапущенный"),
            user_id="owner-1",
        )
        assert cancel_prompt["status"] == (
            "UNIT_ECONOMICS_EXPERIMENT_CANCELLATION_CONFIRMATION_REQUIRED"
        )
        assert "Отменить весь эксперимент" in cancel_prompt["message"]
        experiment_detail = restarted.handle_callback(
            _button_text(cancel_prompt, "Назад"), user_id="owner-1",
        )
        phase_detail = restarted.handle_callback(
            _button_action(experiment_detail, restarted, "phase", "uex:read:"),
            user_id="owner-1",
        )
        resume = restarted.handle_callback(
            _button_text(phase_detail, "Продолжить подтверждение"),
            user_id="owner-1",
        )
        assert resume["status"] == "UNIT_ECONOMICS_EXPERIMENT_CONFIRMATION_INPUT_REQUIRED"
        assert "100,00 ₽" in resume["message"]

        confirmation = restarted.handle_text(
            "100; 2026-10-29 12:00", user_id="owner-1",
        )
        assert confirmation["status"] == "UNIT_ECONOMICS_EXPERIMENT_CONFIRMATION_REQUIRED"
        assert "2026-10-30" in confirmation["message"]
        started = restarted.handle_callback(
            _button_text(confirmation, "Подтверждаю и начать"), user_id="owner-1",
        )
        assert started["status"] == "UNIT_ECONOMICS_EXPERIMENT_BASELINE_ACTIVE"
    finally:
        reset_current_tenant_user_id(token)


def test_unconfirmed_experiment_can_be_explicitly_cancelled_from_reopened_card(tmp_path):
    now = datetime(2026, 10, 29, 12, 0, tzinfo=timezone.utc)
    repo = PlanningWorkspaceRepository(
        db_path=tmp_path / "planning.sqlite", clock=lambda: now,
    )
    runtime = TelegramUnitEconomicsExperimentRuntimeService(
        repository=repo, clock=lambda: now, monotonic_clock=lambda: 100.0,
    )
    token = _enter_context()
    try:
        _create_unconfirmed_baseline(repo, runtime)
        menu = runtime.open_menu("owner-1")
        detail = runtime.handle_callback(_button(menu, "uex:read:"), user_id="owner-1")
        prompt = runtime.handle_callback(
            _button_text(detail, "Отменить незапущенный"), user_id="owner-1",
        )
        cancelled = runtime.handle_callback(
            _button_text(prompt, "Да, отменить эксперимент"), user_id="owner-1",
        )
        assert cancelled["status"] == "UNIT_ECONOMICS_EXPERIMENT_CANCELLED"
        experiments = repo.list_price_experiments(
            owner_id="owner-1", store_id="store-a", limit=10,
        )
        assert experiments["items"][0]["status"] == "CANCELLED"
        phases = repo.list_price_experiment_phases(
            experiments["items"][0]["experiment_id"], owner_id="owner-1",
            store_id="store-a", limit=10,
        )
        assert phases["items"][0]["status"] == "PLANNED"
    finally:
        reset_current_tenant_user_id(token)


def test_late_result_appears_after_refresh_and_reason_is_explained(tmp_path):
    repo = PlanningWorkspaceRepository(db_path=tmp_path / "planning.sqlite")
    now = datetime(2026, 10, 29, 12, 0, tzinfo=timezone.utc)
    runtime = TelegramUnitEconomicsExperimentRuntimeService(
        repository=repo, clock=lambda: now, monotonic_clock=lambda: 100.0,
    )
    token = _enter_context()
    try:
        _saved_plan, snapshot = _seed(repo)
        experiment, phase, _ = _activate_experiment(repo, runtime)
        before = runtime.open_menu("owner-1")
        detail = runtime.handle_callback(
            _button(before, "uex:read:"), user_id="owner-1",
        )
        assert "Сохранённые результаты: ещё нет" not in detail["message"]
        assert not any("Результаты" in button["text"]
                       for button in detail["keyboard"]["buttons"])

        current_experiment = repo.get_price_experiment(
            experiment["experiment_id"], owner_id="owner-1", store_id="store-a",
        )["experiment"]
        current_phase = repo.list_price_experiment_phases(
            experiment["experiment_id"], limit=10,
            owner_id="owner-1", store_id="store-a",
        )["items"][0]
        payload = {
            "schema_version": 1, "status": "INSUFFICIENT_DATA",
            "source_as_of": "2026-10-29T12:00:00Z",
            "snapshot_refs": [snapshot["snapshot_id"]],
            "baseline_profit_per_unit_rub": None,
            "candidate_profit_per_unit_rub": None,
            "delta_profit_per_unit_rub": None, "quantity_basis": None,
            "window": {
                "from_date": "2026-10-22", "to_date": "2026-10-28",
                "timezone": "Europe/Moscow",
            },
            "quality_gates": [{
                "gate": "QUANTITY", "status": "UNKNOWN",
                "reason_code": "SOLD_UNIT_DENOMINATOR_UNCONFIRMED",
            }],
            "limitations": [], "outcome": "FIX_DATA_OR_CONDITIONS",
        }
        appended = repo.append_price_experiment_result(
            experiment["experiment_id"], phase["phase_id"], payload,
            expected_state_revision=current_experiment["state_revision"],
            expected_phase_state_revision=current_phase["state_revision"],
            expected_result_revision=current_phase["result_revision"],
            idempotency_key="w32-late-result-append01",
            owner_id="owner-1", store_id="store-a",
        )
        assert appended["error"] is False

        refreshed = runtime.handle_callback(
            _button_text(detail, "Обновить карточку"), user_id="owner-1",
        )
        assert refreshed["status"] == "UNIT_ECONOMICS_EXPERIMENT_DETAIL"
        results_callback = _button_text(refreshed, "Результаты:")
        results = runtime.handle_callback(results_callback, user_id="owner-1")
        assert results["status"] == "UNIT_ECONOMICS_EXPERIMENT_RESULT_HISTORY"
        result_detail = runtime.handle_callback(
            _button(results, "uex:read:"), user_id="owner-1",
        )
        assert result_detail["status"] == "UNIT_ECONOMICS_EXPERIMENT_RESULT_DETAIL"
        assert "число проданных единиц не подтверждено" in result_detail["message"]
        assert "не доказывает причинность" in result_detail["message"]
    finally:
        reset_current_tenant_user_id(token)


def test_experiment_history_export_includes_revisions_results_and_hides_identity(tmp_path):
    repo = PlanningWorkspaceRepository(db_path=tmp_path / "planning.sqlite")
    now = datetime(2026, 10, 29, 12, 0, tzinfo=timezone.utc)
    exporter = UnitEconomicsExperimentHistoryExportService(
        repository=repo, analytics_export_service=AnalyticsExportService(),
    )
    runtime = TelegramUnitEconomicsExperimentRuntimeService(
        repository=repo, history_export_service=exporter,
        clock=lambda: now, monotonic_clock=lambda: 100.0,
    )
    token = _enter_context()
    try:
        _seed(repo)
        experiment, phase, _ = _activate_experiment(repo, runtime)
        current_experiment = repo.get_price_experiment(
            experiment["experiment_id"], owner_id="owner-1", store_id="store-a",
        )["experiment"]
        payload = {
            "schema_version": 1, "status": "INSUFFICIENT_DATA",
            "source_as_of": "2026-10-29T12:00:00Z",
            "snapshot_refs": [experiment["config"]["source_references"]["expense_snapshot_id"]],
            "baseline_profit_per_unit_rub": None,
            "candidate_profit_per_unit_rub": None,
            "delta_profit_per_unit_rub": None, "quantity_basis": None,
            "window": {
                "from_date": "2026-10-22", "to_date": "2026-10-28",
                "timezone": "Europe/Moscow",
            },
            "quality_gates": [{
                "gate": "QUANTITY", "status": "UNKNOWN",
                "reason_code": "SOLD_UNIT_DENOMINATOR_UNCONFIRMED",
            }],
            "limitations": [], "outcome": "FIX_DATA_OR_CONDITIONS",
        }
        appended = repo.append_price_experiment_result(
            experiment["experiment_id"], phase["phase_id"], payload,
            expected_state_revision=current_experiment["state_revision"],
            expected_phase_state_revision=phase["state_revision"],
            expected_result_revision=phase["result_revision"],
            idempotency_key="w33-export-result001",
            owner_id="owner-1", store_id="store-a",
        )
        assert appended["error"] is False

        menu = runtime.open_menu("owner-1")
        detail = runtime.handle_callback(
            _button(menu, "uex:read:"), user_id="owner-1",
        )
        export_menu = runtime.handle_callback(
            _button_text(detail, "Выгрузить историю"), user_id="owner-1",
        )
        assert export_menu["status"] == "UNIT_ECONOMICS_EXPERIMENT_EXPORT_FORMAT"
        json_result = runtime.handle_callback(
            _button_text(export_menu, "JSON"), user_id="owner-1",
        )
        assert json_result["error"] is False
        assert json_result["document_kind"] == "analytics_export"
        assert json_result["export_kind"] == "unit_economics_experiment_history"
        document = __import__("json").loads(json_result["file_content"])
        assert document["metadata"]["source_reads"] is False
        assert document["metadata"]["recalculated_on_export"] is False
        record_types = {row["record_type"] for row in document["rows"]}
        assert {"EXPERIMENT_CURRENT", "EXPERIMENT_REVISION", "PHASE_REVISION", "PHASE_RESULT"} <= record_types
        exported_result = next(row for row in document["rows"] if row["record_type"] == "PHASE_RESULT")
        assert exported_result["payload"]["snapshot_refs"] == payload["snapshot_refs"]
        encoded = json_result["file_content"].decode("utf-8")
        for private_value in ("owner-1", "product-1", "offer-1", "sku-1", experiment["experiment_id"], phase["phase_id"]):
            assert private_value not in encoded

        csv_result = exporter.export(
            experiment["experiment_id"], "csv", owner_id="owner-1", store_id="store-a",
        )
        assert csv_result["error"] is False
        assert csv_result["mime_type"] == "text/csv"
        assert b"PHASE_RESULT" in csv_result["file_content"]
        foreign = exporter.export(
            experiment["experiment_id"], "json", owner_id="owner-1", store_id="store-b",
        )
        assert foreign["error"] is True
        assert foreign["source_io"] is False

        limited = UnitEconomicsExperimentHistoryExportService(
            repository=repo, analytics_export_service=AnalyticsExportService(),
        )
        limited.MAX_TOTAL_ROWS = 1
        quota_result = limited.export(
            experiment["experiment_id"], "json", owner_id="owner-1", store_id="store-a",
        )
        assert quota_result["error"] is True
        assert quota_result["code"] == "UNIT_ECONOMICS_EXPERIMENT_EXPORT_QUOTA_EXCEEDED"
    finally:
        reset_current_tenant_user_id(token)


def test_history_export_result_projection_retains_exact_comparison_hashes():
    phase_money = {
        "quantity_basis": "SOLD_UNITS_WINDOW", "sold_units": 2,
        "tax_mode": "NONE", "tax_rate_percent": None,
        "minimum_tax_rate_percent": None,
        "gross_seller_revenue_rub": "60.00", "discount_points_rub": "0.00",
        "acquiring_rub": "1.00", "commission_rub": "10.00",
        "logistics_rub": "5.00", "other_fees_rub": "4.00",
        "performance_cpc_reconciliation_rub": "0.00",
        "saved_cogs_per_unit_rub": "5.00", "saved_cogs_total_rub": "10.00",
        "tax_rub": "0.00", "profit_before_tax_rub": "30.00",
        "profit_total_rub": "30.00", "profit_per_unit_rub": "15.00",
    }
    baseline = {
        "window": {"from_date": "2026-10-05", "to_date": "2026-10-07", "timezone": "Europe/Moscow"},
        "source_as_of": "2026-10-15T00:00:00Z", "seller_price_cents": 10000,
        "finance_net_rub": "40.00", **phase_money,
    }
    candidate = {
        **baseline,
        "window": {"from_date": "2026-10-12", "to_date": "2026-10-14", "timezone": "Europe/Moscow"},
        "source_as_of": "2026-10-22T00:00:00Z",
        "seller_price_cents": 9500, "finance_net_rub": "42.00",
        "profit_before_tax_rub": "32.00", "profit_total_rub": "32.00",
        "profit_per_unit_rub": "16.00",
    }
    comparison = {
        "schema_version": 1, "decision_threshold_rub": "0.50",
        "profit_basis": "FINANCE_NET_MINUS_SAVED_COGS_AND_TAX",
        "relative_delta_percent": "6.67",
        "baseline_collection_hash": "a" * 64, "candidate_collection_hash": "b" * 64,
        "baseline_readiness_revision": 1, "candidate_readiness_revision": 1,
        "baseline_phase_state_revision": 2, "candidate_phase_state_revision": 2,
        "baseline_control_event_revision": 0, "candidate_control_event_revision": 0,
        "baseline": baseline, "candidate": candidate,
    }
    payload = {
        "schema_version": 2, "status": "BETTER", "source_as_of": "2026-10-22T00:00:00Z",
        "snapshot_refs": ["c" * 64], "baseline_profit_per_unit_rub": "15.00",
        "candidate_profit_per_unit_rub": "16.00", "delta_profit_per_unit_rub": "1.00",
        "quantity_basis": "SOLD_UNITS_WINDOW",
        "window": candidate["window"], "quality_gates": [], "limitations": [],
        "outcome": "CANDIDATE_BETTER_IN_MODEL", "comparison": comparison,
    }
    projected = UnitEconomicsExperimentHistoryExportService._result(payload)
    assert projected is not None
    assert projected["comparison"] == comparison
    assert projected["snapshot_refs"] == payload["snapshot_refs"]
