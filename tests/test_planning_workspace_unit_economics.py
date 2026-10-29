import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timezone

import pytest

from services.ozon_account_repository import make_store_tenant_scope
from services.planning_workspace_repository import PlanningWorkspaceRepository
from services.tenant_context import reset_current_tenant_user_id, set_current_tenant_user_id
from services.unit_economics_experiment_snapshot_view_service import (
    UnitEconomicsExperimentSnapshotViewService,
)


def _identity(owner="owner-1", store="store-a", sku="sku-1"):
    return {
        "owner_id": owner, "store_id": store, "product_id": "product-1",
        "offer_id": "offer-1", "sku": sku, "sale_schema": "FBO",
    }


def _plan_payload(store="store-a", sku="sku-1"):
    return {
        "plan_kind": "single", "schema_version": 1, "calculation_version": 1,
        "target_margin_percent": "25.00", "items": [{
            "identity": {
                "product_id": "product-1", "offer_id": "offer-1", "sku": sku,
                "product_name": "Item", "store_id": store, "scheme": "FBO",
            },
            "inputs": {
                "price": "500.00", "cost": "100.00", "commission_rate": "20",
                "advertising_rate": "0", "discount_points_rate": "0",
                "logistics_per_unit": "25", "last_mile_per_unit": "5",
                "acquiring_per_unit": "5", "tax_mode": "USN_INCOME",
                "tax_rate": "6", "minimum_tax_rate": None,
            },
            "provenance": {"price": "owner_input", "cost": "owner_input"},
            "sources": {
                "periods": {}, "as_of": "2026-10-29T12:00:00Z",
                "loaded_at": "2026-10-29T12:00:00Z", "completeness": {},
            },
            "projection": {"available": True, "missing_inputs": [], "invalid_inputs": [],
                           "revenue": "500.00", "profit": "200.00"},
        }],
    }


def _readiness(start="2026-08-01", end="2026-09-25"):
    return {
        "error": False, "schema_version": 1, "status": "COMPLETE",
        "scope_kind": "REFERENCE_56_COMPLETED_LOCAL_DAYS",
        "window": {
            "from_date": start, "to_date": end,
            "date_basis": "LOCAL_CALENDAR_DAY", "timezone": "Europe/Moscow",
        },
        "coverage_status": "COMPLETE", "coverage_complete": True,
        "denominator": {"units": 10, "kind": "ORDERED_UNITS_WINDOW"},
        "component_counts": {"INCLUDED": 0, "EXCLUDED": 0, "UNKNOWN": 0},
        "components": [], "read_only": True, "api_calls": 0,
    }


def _snapshot_payload(identity=None):
    return {
        "schema_version": 1,
        "identity": identity or _identity(),
        "readiness": _readiness(),
    }


def _experiment_payload(plan_id, snapshot_id, identity=None):
    return {
        "schema_version": 1, "identity": identity or _identity(),
        "title": "Price experiment", "metric": "MAX_RUB_PER_UNIT",
        "calculation_mode": "WINDOW_COST_ALLOCATION",
        "source_references": {
            "plan": {"document_id": plan_id, "revision": 1},
            "expense_snapshot_id": snapshot_id, "tariff": None, "observation": None,
        },
        "candidate_prices_cents": [9900, 10000], "decision_threshold_rub": "0.01",
        "planned_duration_days": 7, "currency": "RUB",
        "control_flags": {
            key: "UNCHANGED" for key in (
                "inventory", "promotion", "advertising", "card", "cost", "tariff",
            )
        },
    }


def _incomplete_experiment_plan(payload):
    payload = dict(payload)
    payload["candidate_prices_cents"] = []
    payload.update({
        "plan_schema_version": 1,
        "candidate_price_bounds_cents": None,
        "maturity_min_days": 7,
        "maturity_min_units": 30,
    })
    return payload


def _phase_payload(snapshot_id, *, kind="BASELINE", segment=1, price=10000):
    return {
        "schema_version": 1, "kind": kind, "segment_number": segment,
        "planned_price_cents": price, "expense_snapshot_id": snapshot_id,
        "planned_from_date": "2026-10-30", "planned_to_date": "2026-11-05",
        "timezone": "Europe/Moscow",
        "control_flags": {
            key: "UNCHANGED" for key in (
                "inventory", "promotion", "advertising", "card", "cost", "tariff",
            )
        },
    }


def _ready_baseline_phase(repo, saved, snapshot, experiment):
    plan = _experiment_payload(saved["document_id"], snapshot["snapshot_id"])
    plan.update({
        "plan_schema_version": 1,
        "candidate_price_bounds_cents": {
            "min_price_cents": 9500, "max_price_cents": 10500,
        },
        "maturity_min_days": 7, "maturity_min_units": 30,
    })
    updated = repo.update_price_experiment_draft(
        experiment["experiment_id"], plan, expected_state_revision=1,
        idempotency_key="w24-plan-edit01",
    )
    assert updated["error"] is False
    phase = repo.create_price_experiment_phase(
        experiment["experiment_id"], _phase_payload(snapshot["snapshot_id"], price=10000),
        expected_state_revision=2, idempotency_key="w24-phase-create01",
    )
    assert phase["error"] is False
    ready = repo.transition_price_experiment(
        experiment["experiment_id"], "mark_ready", expected_state_revision=3,
        idempotency_key="w24-ready-stage01",
    )
    assert ready["error"] is False
    return phase


def _confirm_baseline_phase(repo, experiment, phase, *, key="w24-confirm-baseline01",
                            effective_from="2026-10-29T12:00:00+03:00",
                            expected_state_revision=4, owner_confirmed=True):
    return repo.confirm_price_experiment_phase(
        experiment["experiment_id"], phase["phase_id"], seller_price_cents=10000,
        effective_from=effective_from, owner_confirmed=owner_confirmed,
        expected_state_revision=expected_state_revision,
        expected_phase_state_revision=1, idempotency_key=key,
    )


def _result_payload(snapshot_id, *, baseline="10.00", candidate="11.50", delta="1.50"):
    return {
        "schema_version": 1, "status": "BETTER",
        "source_as_of": "2026-11-06T12:00:00Z", "snapshot_refs": [snapshot_id],
        "baseline_profit_per_unit_rub": baseline,
        "candidate_profit_per_unit_rub": candidate,
        "delta_profit_per_unit_rub": delta,
        "quantity_basis": "ORDERED_UNITS_WINDOW",
        "window": {
            "from_date": "2026-10-30", "to_date": "2026-11-05",
            "timezone": "Europe/Moscow",
        },
        "quality_gates": [{"gate": "QUANTITY", "status": "PASS",
                            "reason_code": "COMPLETE"}],
        "limitations": [], "outcome": "CANDIDATE_BETTER_IN_MODEL",
    }


def _context(owner="owner-1", store="store-a"):
    return set_current_tenant_user_id(make_store_tenant_scope(owner, store))


def _seed(repo):
    token = _context()
    try:
        saved = repo.save_document(
            title="Plan", payload=_plan_payload(), idempotency_key="w17-plan-save01",
        )
        assert saved["error"] is False
        snapshot = repo.create_unit_economics_expense_snapshot(_snapshot_payload())
        assert snapshot["error"] is False
        experiment = repo.create_price_experiment(
            _experiment_payload(saved["document_id"], snapshot["snapshot_id"]),
            idempotency_key="w17-experiment01",
        )
        assert experiment["error"] is False
        return saved, snapshot, experiment
    finally:
        reset_current_tenant_user_id(token)


def test_schema_v9_additive_migration_preserves_existing_plan_and_backfills_active_guard(tmp_path):
    repo = PlanningWorkspaceRepository(db_path=tmp_path / "planning.sqlite")
    saved, snapshot, _ = _seed(repo)
    token = _context()
    try:
        observation = repo.start_unit_price_observation(
            identity={"product_id": "product-1", "offer_id": "offer-1", "sku": "sku-1",
                      "sale_schema": "FBO"},
            seller_price_cents=10000, source_document_id=saved["document_id"],
            source_document_revision=1, effective_from="2026-10-27T09:30:00Z",
            window_timezone="Europe/Moscow", owner_confirmed=True,
            idempotency_key="w21-migrationobs",
        )
        assert observation["error"] is False
    finally:
        reset_current_tenant_user_id(token)
    connection = sqlite3.connect(repo.db_path)
    try:
        connection.execute("DROP TABLE planning_active_sku_guards")
        connection.execute("UPDATE planning_schema SET version=6")
        connection.commit()
    finally:
        connection.close()
    reopened = PlanningWorkspaceRepository(db_path=repo.db_path)
    initialized = reopened.get_connection()
    initialized.close()
    token = _context()
    try:
        assert reopened.get_document(saved["document_id"])["error"] is False
        assert reopened.get_unit_economics_expense_snapshot(snapshot["snapshot_id"])["error"] is False
        assert reopened.get_unit_price_observation(observation["observation_id"])[
            "observation"
        ]["status"] == "ACTIVE"
    finally:
        reset_current_tenant_user_id(token)
    connection = sqlite3.connect(repo.db_path)
    try:
        assert connection.execute(
            "SELECT version FROM planning_schema",
        ).fetchone()[0] == 10
        guard = connection.execute(
            "SELECT operation_kind, operation_id FROM planning_active_sku_guards"
        ).fetchone()
        assert tuple(guard) == ("OBSERVATION", observation["observation_id"])
        tables = {row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'",
        )}
        assert {
            "planning_documents", "planning_revisions", "planning_tariff_profiles",
            "planning_unit_price_observations", "planning_unit_price_comparisons",
            "planning_unit_economics_snapshots", "planning_price_experiments",
            "planning_price_experiment_phases", "planning_price_experiment_results",
            "planning_active_sku_guards",
        } <= tables
    finally:
        connection.close()


def test_phase_confirmation_preview_and_atomic_owner_confirm_link_exact_observation(tmp_path):
    repo = PlanningWorkspaceRepository(
        db_path=tmp_path / "planning.sqlite",
        clock=lambda: datetime(2026, 10, 29, 9, 0, tzinfo=timezone.utc),
    )
    saved, snapshot, experiment = _seed(repo)
    token = _context()
    try:
        phase = _ready_baseline_phase(repo, saved, snapshot, experiment)
        preview = repo.preview_price_experiment_phase_confirmation(
            experiment["experiment_id"], phase["phase_id"],
            seller_price_cents=10000,
            effective_from="2026-10-29T12:00:00+03:00",
        )
        assert preview["error"] is False
        assert preview["status"] == "PREVIEW_ONLY"
        assert preview["first_full_local_day"] == "2026-10-30"
        assert preview["price_history_verified"] is False
        assert preview["experiment_state_revision"] == 4
        assert preview["phase_state_revision"] == 1
        assert repo.get_price_experiment(experiment["experiment_id"])[
            "experiment"
        ]["status"] == "READY"
        assert repo.list_price_experiment_phases(
            experiment["experiment_id"],
        )["items"][0]["observation_id"] is None

        confirmed = _confirm_baseline_phase(repo, experiment, phase)
        assert confirmed["error"] is False
        assert confirmed["status"] == "BASELINE_ACTIVE"
        assert confirmed["phase_status"] == "ACTIVE"
        assert confirmed["first_full_local_day"] == "2026-10-30"
        assert confirmed["price_evidence_kind"] == "OWNER_DECLARED"
        assert confirmed["price_history_verified"] is False
        assert repo.confirm_price_experiment_phase(
            experiment["experiment_id"], phase["phase_id"],
            seller_price_cents=10000,
            effective_from="2026-10-29T12:00:00+03:00", owner_confirmed=True,
            expected_state_revision=4, expected_phase_state_revision=1,
            idempotency_key="w24-confirm-baseline01",
        ) == confirmed
        changed_replay = _confirm_baseline_phase(
            repo, experiment, phase,
            key="w24-confirm-baseline01",
            effective_from="2026-10-29T13:00:00+03:00",
        )
        assert changed_replay["code"] == (
            "PLANNING_PRICE_EXPERIMENT_IDEMPOTENCY_CONFLICT"
        )
        stale = _confirm_baseline_phase(
            repo, experiment, phase, key="w24-confirm-stale001",
            expected_state_revision=4,
        )
        assert stale["code"] == "PLANNING_PRICE_EXPERIMENT_STATE_CONFLICT"

        phase_record = repo.list_price_experiment_phases(
            experiment["experiment_id"],
        )["items"][0]
        assert phase_record["status"] == "ACTIVE"
        assert phase_record["observation_id"] == confirmed["observation_id"]
        assert phase_record["confirmation"]["price_history_verified"] is False
        history = repo.list_price_experiment_phase_revisions(
            experiment["experiment_id"], phase["phase_id"], limit=10,
        )
        assert history["error"] is False
        assert history["items"][0]["confirmation"][
            "first_full_local_day"
        ] == "2026-10-30"
        observation = repo.get_unit_price_observation(confirmed["observation_id"])
        assert observation["error"] is False
        assert observation["observation"]["seller_price_cents"] == 10000
        assert observation["observation"]["effective_from"] == (
            "2026-10-29T12:00:00+03:00"
        )
        assert observation["observation"]["source_plan"] == {
            "document_id": saved["document_id"], "revision": 1,
        }
        assert observation["observation"]["price_evidence_kind"] == (
            "OWNER_DECLARED_PRICE_CHANGE"
        )
        standalone = repo.start_unit_price_observation(
            identity={"product_id": "product-1", "offer_id": "offer-1",
                      "sku": "sku-1", "sale_schema": "FBO"},
            seller_price_cents=10000, source_document_id=saved["document_id"],
            source_document_revision=1, effective_from="2026-10-29T12:00:00+03:00",
            window_timezone="Europe/Moscow", owner_confirmed=True,
            idempotency_key="w24-standalone01",
        )
        assert standalone["code"] == "PLANNING_PRICE_EXPERIMENT_ALREADY_ACTIVE"
    finally:
        reset_current_tenant_user_id(token)


def test_phase_confirmation_rolls_back_observation_guard_and_revisions_together(tmp_path):
    repo = PlanningWorkspaceRepository(
        db_path=tmp_path / "planning.sqlite",
        clock=lambda: datetime(2026, 10, 29, 9, 0, tzinfo=timezone.utc),
    )
    saved, snapshot, experiment = _seed(repo)
    token = _context()
    try:
        phase = _ready_baseline_phase(repo, saved, snapshot, experiment)
        connection = repo.get_connection()
        connection.execute("""CREATE TRIGGER abort_w24_phase_revision
            BEFORE INSERT ON planning_price_experiment_phase_revisions
            WHEN NEW.state_revision=2
            BEGIN SELECT RAISE(ABORT, 'synthetic W24 rollback'); END""")
        connection.close()
        failed = _confirm_baseline_phase(repo, experiment, phase)
        assert failed["code"] == "PLANNING_PRICE_EXPERIMENT_CONFIRMATION_CONFLICT"
        assert repo.get_price_experiment(experiment["experiment_id"])[
            "experiment"
        ]["status"] == "READY"
        assert repo.list_price_experiment_phases(
            experiment["experiment_id"],
        )["items"][0]["status"] == "PLANNED"
        connection = sqlite3.connect(repo.db_path)
        try:
            assert connection.execute(
                "SELECT COUNT(*) FROM planning_unit_price_observations",
            ).fetchone()[0] == 0
            assert connection.execute(
                "SELECT COUNT(*) FROM planning_active_sku_guards",
            ).fetchone()[0] == 0
            assert connection.execute(
                "SELECT COUNT(*) FROM planning_price_experiment_idempotency "
                "WHERE idempotency_key='w24-confirm-baseline01'",
            ).fetchone()[0] == 0
        finally:
            connection.close()
        connection = repo.get_connection()
        connection.execute("DROP TRIGGER abort_w24_phase_revision")
        connection.close()
        retry = _confirm_baseline_phase(repo, experiment, phase)
        assert retry["error"] is False
    finally:
        reset_current_tenant_user_id(token)


def test_phase_confirmation_obeys_existing_observation_quota(tmp_path, monkeypatch):
    repo = PlanningWorkspaceRepository(
        db_path=tmp_path / "planning.sqlite",
        clock=lambda: datetime(2026, 10, 29, 9, 0, tzinfo=timezone.utc),
    )
    saved, snapshot, experiment = _seed(repo)
    token = _context()
    try:
        phase = _ready_baseline_phase(repo, saved, snapshot, experiment)
        monkeypatch.setattr(repo, "MAX_UNIT_PRICE_OBSERVATIONS_PER_STORE", 0)
        blocked = _confirm_baseline_phase(repo, experiment, phase)
        assert blocked["code"] == "PLANNING_OBSERVATION_QUOTA_REACHED"
        assert repo.get_price_experiment(experiment["experiment_id"])[
            "experiment"
        ]["status"] == "READY"
        assert repo.list_price_experiment_phases(
            experiment["experiment_id"],
        )["items"][0]["status"] == "PLANNED"
        connection = sqlite3.connect(repo.db_path)
        try:
            assert connection.execute(
                "SELECT COUNT(*) FROM planning_unit_price_observations",
            ).fetchone()[0] == 0
            assert connection.execute(
                "SELECT COUNT(*) FROM planning_active_sku_guards",
            ).fetchone()[0] == 0
        finally:
            connection.close()
    finally:
        reset_current_tenant_user_id(token)


def test_experiment_control_pause_and_resume_preserve_old_segment_evidence(tmp_path):
    repo = PlanningWorkspaceRepository(
        db_path=tmp_path / "planning.sqlite",
        clock=lambda: datetime(2026, 10, 29, 9, 0, tzinfo=timezone.utc),
    )
    saved, snapshot, experiment = _seed(repo)
    token = _context()
    try:
        phase = _ready_baseline_phase(repo, saved, snapshot, experiment)
        confirmed = _confirm_baseline_phase(repo, experiment, phase)
        assert confirmed["error"] is False
        original = repo.list_price_experiment_phases(
            experiment["experiment_id"],
        )["items"][0]
        flags = dict(original["config"]["control_flags"])
        flags["promotion"] = "CHANGED"
        update = repo.record_price_experiment_control_update(
            experiment["experiment_id"], phase["phase_id"], flags,
            expected_state_revision=confirmed["state_revision"],
            idempotency_key="w25-control-update01",
        )
        assert update["error"] is False
        assert update["compatibility"] == {
            "status": "INCOMPATIBLE",
            "reason_codes": ["EXPERIMENT_CONTROL_CHANGED_PROMOTION"],
        }
        assert repo.record_price_experiment_control_update(
            experiment["experiment_id"], phase["phase_id"], flags,
            expected_state_revision=confirmed["state_revision"],
            idempotency_key="w25-control-update01",
        ) == update
        assert repo.record_price_experiment_control_update(
            experiment["experiment_id"], phase["phase_id"], flags,
            expected_state_revision=confirmed["state_revision"],
            idempotency_key="w25-control-update02",
        )["code"] == "PLANNING_PRICE_EXPERIMENT_STATE_CONFLICT"

        paused = repo.pause_price_experiment_phase(
            experiment["experiment_id"], phase["phase_id"],
            expected_state_revision=update["state_revision"],
            expected_phase_state_revision=confirmed["phase_state_revision"],
            idempotency_key="w25-pause-phase001",
        )
        assert paused["error"] is False
        assert paused["status"] == "PAUSED"
        assert paused["resume_target"] == "READY"
        connection = repo.get_connection()
        try:
            assert connection.execute(
                "SELECT COUNT(*) FROM planning_active_sku_guards "
                "WHERE owner_id='owner-1' AND store_id='store-a'",
            ).fetchone()[0] == 0
        finally:
            connection.close()
        stored_experiment = repo.get_price_experiment(experiment["experiment_id"])[
            "experiment"
        ]
        assert stored_experiment["resume_target"] == "READY"
        assert repo.list_price_experiment_phases(
            experiment["experiment_id"],
        )["items"][0]["confirmation"] == original["confirmation"]
        assert repo.list_price_experiment_phases(
            experiment["experiment_id"],
        )["items"][0]["config"] == original["config"]
        closed_observation = repo.get_unit_price_observation(
            confirmed["observation_id"],
        )
        assert closed_observation["observation"]["status"] == "FINISHED"
        assert repo.list_price_experiment_phases(
            experiment["experiment_id"],
        )["items"][0]["status"] == "PAUSED"

        resumed_config = _phase_payload(
            snapshot["snapshot_id"], kind="BASELINE", segment=2, price=10000,
        )
        resumed = repo.prepare_price_experiment_resume(
            experiment["experiment_id"], resumed_config,
            expected_state_revision=paused["state_revision"],
            idempotency_key="w25-resume-prepared01",
        )
        assert resumed["error"] is False
        assert resumed["status"] == "PAUSED"
        assert resumed["phase_status"] == "PLANNED"
        assert resumed["requires_fresh_confirmation"] is True
        assert repo.confirm_price_experiment_phase(
            experiment["experiment_id"], resumed["phase_id"],
            seller_price_cents=10000, effective_from="2026-10-29T12:00:00+03:00",
            owner_confirmed=True, expected_state_revision=resumed["state_revision"],
            expected_phase_state_revision=1, idempotency_key="w25-resume-confirm01",
        )["status"] == "BASELINE_ACTIVE"
        reopened_phases = repo.list_price_experiment_phases(
            experiment["experiment_id"],
        )
        assert reopened_phases["error"] is False
        by_segment = {item["segment_number"]: item for item in reopened_phases["items"]}
        assert by_segment[1]["status"] == "PAUSED"
        assert by_segment[1]["config"] == original["config"]
        assert by_segment[1]["confirmation"] == original["confirmation"]
        assert by_segment[2]["status"] == "ACTIVE"
        assert by_segment[2]["observation_id"] != confirmed["observation_id"]
        events = repo.list_price_experiment_events(
            experiment["experiment_id"], limit=10,
        )
        assert events["error"] is False
        assert [item["event_kind"] for item in events["items"]] == [
            "RESUME_SEGMENT_PREPARED", "PAUSE", "CONTROL_UPDATE",
        ]
        assert events["items"][2]["payload"]["compatibility"]["status"] == (
            "INCOMPATIBLE"
        )
        guard = repo.get_connection()
        try:
            guarded = guard.execute(
                "SELECT operation_kind, operation_id FROM planning_active_sku_guards "
                "WHERE owner_id='owner-1' AND store_id='store-a'",
            ).fetchone()
            assert tuple(guarded) == ("EXPERIMENT", experiment["experiment_id"])
            with pytest.raises(sqlite3.IntegrityError):
                guard.execute(
                    "DELETE FROM planning_price_experiment_events WHERE experiment_id=?",
                    (experiment["experiment_id"],),
                )
        finally:
            guard.close()
    finally:
        reset_current_tenant_user_id(token)


@pytest.mark.parametrize("terminal_action", ["cancel", "archive"])
def test_paused_experiment_terminal_transition_clears_resume_target(
    tmp_path, terminal_action,
):
    repo = PlanningWorkspaceRepository(db_path=tmp_path / f"{terminal_action}.sqlite")
    saved, snapshot, experiment = _seed(repo)
    token = _context()
    try:
        phase = _ready_baseline_phase(repo, saved, snapshot, experiment)
        confirmed = _confirm_baseline_phase(repo, experiment, phase)
        paused = repo.pause_price_experiment_phase(
            experiment["experiment_id"], phase["phase_id"],
            expected_state_revision=confirmed["state_revision"],
            expected_phase_state_revision=confirmed["phase_state_revision"],
            idempotency_key=f"w25-pause-terminal-{terminal_action}",
        )
        assert paused["error"] is False
        if terminal_action == "cancel":
            terminal = repo.transition_price_experiment(
                experiment["experiment_id"], "cancel",
                expected_state_revision=paused["state_revision"],
                idempotency_key="w25-cancel-paused01",
            )
        else:
            terminal = repo.archive_price_experiment(
                experiment["experiment_id"],
                expected_state_revision=paused["state_revision"],
                idempotency_key="w25-archive-paused01",
            )
        assert terminal["error"] is False
        stored = repo.get_price_experiment(experiment["experiment_id"])
        assert stored["error"] is False
        assert stored["experiment"]["resume_target"] is None
        assert stored["experiment"]["status"] == terminal["status"]
    finally:
        reset_current_tenant_user_id(token)


def test_experiment_event_page_fails_closed_on_phase_binding_mismatch(tmp_path):
    repo = PlanningWorkspaceRepository(db_path=tmp_path / "planning.sqlite")
    saved, snapshot, experiment = _seed(repo)
    token = _context()
    try:
        phase = _ready_baseline_phase(repo, saved, snapshot, experiment)
        confirmed = _confirm_baseline_phase(repo, experiment, phase)
        flags = dict(_phase_payload(snapshot["snapshot_id"])["control_flags"])
        recorded = repo.record_price_experiment_control_update(
            experiment["experiment_id"], phase["phase_id"], flags,
            expected_state_revision=confirmed["state_revision"],
            idempotency_key="w25-event-binding001",
        )
        assert recorded["error"] is False
        connection = sqlite3.connect(repo.db_path)
        try:
            connection.execute("DROP TRIGGER trg_price_experiment_events_no_update")
            connection.execute(
                "UPDATE planning_price_experiment_events SET phase_id=? WHERE event_id=?",
                ("f" * 32, recorded["event_id"]),
            )
            connection.commit()
        finally:
            connection.close()
        assert repo.list_price_experiment_events(
            experiment["experiment_id"],
        )["code"] == "PLANNING_PRICE_EXPERIMENT_EVENT_CORRUPT"
    finally:
        reset_current_tenant_user_id(token)


def test_event_quota_failure_rolls_back_pause_and_keeps_active_guard(tmp_path, monkeypatch):
    repo = PlanningWorkspaceRepository(
        db_path=tmp_path / "planning.sqlite",
        clock=lambda: datetime(2026, 10, 29, 9, 0, tzinfo=timezone.utc),
    )
    monkeypatch.setattr(PlanningWorkspaceRepository, "MAX_PRICE_EXPERIMENT_EVENTS", 1)
    saved, snapshot, experiment = _seed(repo)
    token = _context()
    try:
        phase = _ready_baseline_phase(repo, saved, snapshot, experiment)
        confirmed = _confirm_baseline_phase(repo, experiment, phase)
        flags = dict(_phase_payload(snapshot["snapshot_id"])["control_flags"])
        update = repo.record_price_experiment_control_update(
            experiment["experiment_id"], phase["phase_id"], flags,
            expected_state_revision=confirmed["state_revision"],
            idempotency_key="w25-event-quota-control",
        )
        assert update["error"] is False
        rejected = repo.pause_price_experiment_phase(
            experiment["experiment_id"], phase["phase_id"],
            expected_state_revision=update["state_revision"],
            expected_phase_state_revision=confirmed["phase_state_revision"],
            idempotency_key="w25-event-quota-pause",
        )
        assert rejected["code"] == "PLANNING_PRICE_EXPERIMENT_EVENT_QUOTA_REACHED"
        assert repo.get_price_experiment(experiment["experiment_id"])[
            "experiment"]["status"] == "BASELINE_ACTIVE"
        assert repo.list_price_experiment_phases(
            experiment["experiment_id"],
        )["items"][0]["status"] == "ACTIVE"
        assert repo.get_unit_price_observation(
            confirmed["observation_id"],
        )["observation"]["status"] == "ACTIVE"
        connection = repo.get_connection()
        try:
            assert connection.execute(
                "SELECT COUNT(*) FROM planning_active_sku_guards "
                "WHERE owner_id='owner-1' AND store_id='store-a'",
            ).fetchone()[0] == 1
            assert connection.execute(
                "SELECT COUNT(*) FROM planning_price_experiment_events",
            ).fetchone()[0] == 1
        finally:
            connection.close()
    finally:
        reset_current_tenant_user_id(token)


def test_schema_v8_to_v10_preserves_planned_phase_history(tmp_path):
    repo = PlanningWorkspaceRepository(db_path=tmp_path / "planning.sqlite")
    saved, snapshot, experiment = _seed(repo)
    token = _context()
    try:
        phase = repo.create_price_experiment_phase(
            experiment["experiment_id"], _phase_payload(snapshot["snapshot_id"]),
            expected_state_revision=1, idempotency_key="w24-migrate-phase01",
        )
        assert phase["error"] is False
    finally:
        reset_current_tenant_user_id(token)
    connection = sqlite3.connect(repo.db_path)
    try:
        connection.execute(
            "DROP INDEX IF EXISTS idx_price_experiment_phase_observation",
        )
        connection.execute(
            "ALTER TABLE planning_price_experiment_phases DROP COLUMN confirmation_json",
        )
        connection.execute(
            "ALTER TABLE planning_price_experiment_phases DROP COLUMN observation_id",
        )
        connection.execute(
            "DROP INDEX IF EXISTS idx_price_experiment_first_baseline",
        )
        connection.execute(
            "CREATE UNIQUE INDEX idx_price_experiment_one_baseline "
            "ON planning_price_experiment_phases(experiment_id, owner_id, store_id) "
            "WHERE kind='BASELINE'",
        )
        connection.execute("ALTER TABLE planning_price_experiments DROP COLUMN resume_target")
        connection.execute("DROP TABLE planning_price_experiment_events")
        connection.execute("UPDATE planning_schema SET version=8")
        connection.commit()
    finally:
        connection.close()

    reopened = PlanningWorkspaceRepository(db_path=repo.db_path)
    connection = reopened.get_connection()
    try:
        assert connection.execute(
            "SELECT version FROM planning_schema",
        ).fetchone()[0] == 10
        columns = {row[1] for row in connection.execute(
            "PRAGMA table_info(planning_price_experiment_phases)",
        )}
        assert {"observation_id", "confirmation_json"} <= columns
        experiment_columns = {row[1] for row in connection.execute(
            "PRAGMA table_info(planning_price_experiments)",
        )}
        assert "resume_target" in experiment_columns
        assert connection.execute(
            "SELECT COUNT(*) FROM planning_price_experiment_events",
        ).fetchone()[0] == 0
        index_names = {row[1] for row in connection.execute(
            "PRAGMA index_list(planning_price_experiment_phases)",
        )}
        assert "idx_price_experiment_first_baseline" in index_names
        assert "idx_price_experiment_one_baseline" not in index_names
        assert connection.execute(
            "SELECT COUNT(*) FROM planning_price_experiment_phase_revisions "
            "WHERE phase_id=?", (phase["phase_id"],),
        ).fetchone()[0] == 1
    finally:
        connection.close()
    token = _context()
    try:
        restored = reopened.list_price_experiment_phases(experiment["experiment_id"])
        assert restored["error"] is False
        assert restored["items"][0]["phase_id"] == phase["phase_id"]
        assert restored["items"][0]["status"] == "PLANNED"
        assert restored["items"][0]["confirmation"] is None
        assert restored["items"][0]["observation_id"] is None
    finally:
        reset_current_tenant_user_id(token)


def test_incomplete_experiment_draft_can_be_revised_but_cannot_become_ready_early(tmp_path):
    repo = PlanningWorkspaceRepository(db_path=tmp_path / "planning.sqlite")
    saved, snapshot, _ = _seed(repo)
    token = _context()
    try:
        draft_payload = _incomplete_experiment_plan(
            _experiment_payload(saved["document_id"], snapshot["snapshot_id"]),
        )
        created = repo.create_price_experiment(
            draft_payload, idempotency_key="w22-draft-create01",
        )
        assert created["error"] is False
        assert created["status"] == "DRAFT"
        readiness = repo.get_price_experiment_plan_readiness(
            created["experiment_id"],
        )
        assert readiness["error"] is False
        assert readiness["status"] == "INCOMPLETE"
        assert readiness["eligible_for_ready"] is False
        blocked = repo.transition_price_experiment(
            created["experiment_id"], "mark_ready", expected_state_revision=1,
            idempotency_key="w22-ready-too-early",
        )
        assert blocked["code"] == "PLANNING_PRICE_EXPERIMENT_PLAN_INCOMPLETE"
        assert blocked["reason_codes"] == [
            "EXPERIMENT_CANDIDATES_REQUIRED", "EXPERIMENT_PRICE_BOUNDS_REQUIRED",
        ]

        completed_plan = dict(draft_payload)
        completed_plan["candidate_price_bounds_cents"] = {
            "min_price_cents": 9500, "max_price_cents": 10500,
        }
        completed_plan["candidate_prices_cents"] = [9700, 10000, 10300]
        updated = repo.update_price_experiment_draft(
            created["experiment_id"], completed_plan,
            expected_state_revision=1, idempotency_key="w22-draft-edit01",
        )
        assert updated["error"] is False
        assert updated["state_revision"] == 2
        assert updated["plan_status"] == "READY"
        assert repo.update_price_experiment_draft(
            created["experiment_id"], completed_plan,
            expected_state_revision=1, idempotency_key="w22-draft-edit01",
        ) == updated

        ready = repo.transition_price_experiment(
            created["experiment_id"], "mark_ready", expected_state_revision=2,
            idempotency_key="w22-ready-confirm01",
        )
        assert ready["error"] is False
        assert ready["status"] == "READY"
        assert ready["state_revision"] == 3
        frozen = repo.update_price_experiment_draft(
            created["experiment_id"], completed_plan,
            expected_state_revision=3, idempotency_key="w22-edit-after-ready",
        )
        assert frozen["code"] == "PLANNING_PRICE_EXPERIMENT_DRAFT_FROZEN"
        connection = repo.get_connection()
        try:
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(
                    "UPDATE planning_price_experiments SET config_json='{}' "
                    "WHERE experiment_id=?", (created["experiment_id"],),
                )
            connection.rollback()
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(
                    "UPDATE planning_price_experiments SET product_id='other' "
                    "WHERE experiment_id=?", (created["experiment_id"],),
                )
            connection.rollback()
        finally:
            connection.close()
        history = repo.list_price_experiment_revisions(
            created["experiment_id"], limit=10,
        )
        assert history["error"] is False
        assert [row["status"] for row in reversed(history["items"])] == [
            "DRAFT", "DRAFT", "READY",
        ]
    finally:
        reset_current_tenant_user_id(token)


def test_impossible_experiment_price_bounds_are_not_saved(tmp_path):
    repo = PlanningWorkspaceRepository(db_path=tmp_path / "planning.sqlite")
    saved, snapshot, _ = _seed(repo)
    token = _context()
    try:
        invalid_plan = _incomplete_experiment_plan(
            _experiment_payload(saved["document_id"], snapshot["snapshot_id"]),
        )
        invalid_plan["candidate_price_bounds_cents"] = {
            "min_price_cents": 10001, "max_price_cents": 10000,
        }
        result = repo.create_price_experiment(
            invalid_plan, idempotency_key="w22-impossible-bounds",
        )
        assert result["code"] == "PLANNING_PRICE_EXPERIMENT_INPUT_INVALID"
        connection = repo.get_connection()
        try:
            assert connection.execute(
                "SELECT COUNT(*) FROM planning_price_experiments",
            ).fetchone()[0] == 1
        finally:
            connection.close()
    finally:
        reset_current_tenant_user_id(token)


def test_incomplete_draft_can_be_cancelled_and_archived_without_losing_history(tmp_path):
    repo = PlanningWorkspaceRepository(db_path=tmp_path / "planning.sqlite")
    saved, snapshot, _ = _seed(repo)
    token = _context()
    try:
        created = repo.create_price_experiment(
            _incomplete_experiment_plan(
                _experiment_payload(saved["document_id"], snapshot["snapshot_id"]),
            ),
            idempotency_key="w22-incomplete-terminal01",
        )
        assert created["error"] is False
        cancelled = repo.transition_price_experiment(
            created["experiment_id"], "cancel", expected_state_revision=1,
            idempotency_key="w22-incomplete-cancel01",
        )
        assert cancelled["error"] is False
        reopened = repo.get_price_experiment(created["experiment_id"])
        assert reopened["error"] is False
        assert reopened["experiment"]["status"] == "CANCELLED"
        archived = repo.archive_price_experiment(
            created["experiment_id"], expected_state_revision=2,
            idempotency_key="w22-incomplete-archive01",
        )
        assert archived["error"] is False
        assert repo.get_price_experiment(created["experiment_id"])[
            "experiment"
        ]["status"] == "ARCHIVED"
        history = repo.list_price_experiment_revisions(
            created["experiment_id"], limit=10,
        )
        assert history["error"] is False
        assert {item["status"] for item in history["items"]} == {
            "DRAFT", "CANCELLED", "ARCHIVED",
        }
    finally:
        reset_current_tenant_user_id(token)


def test_active_experiment_and_observation_share_one_sku_guard(tmp_path):
    repo = PlanningWorkspaceRepository(db_path=tmp_path / "planning.sqlite")
    saved, _, experiment = _seed(repo)
    token = _context()
    identity = {"product_id": "product-1", "offer_id": "offer-1", "sku": "sku-1",
                "sale_schema": "FBO"}
    try:
        observation = repo.start_unit_price_observation(
            identity=identity, seller_price_cents=10000,
            source_document_id=saved["document_id"], source_document_revision=1,
            effective_from="2026-10-27T09:30:00Z", window_timezone="Europe/Moscow",
            owner_confirmed=True, idempotency_key="w21-guardobs01",
        )
        assert observation["error"] is False
        connection = repo.get_connection()
        try:
            connection.execute("BEGIN IMMEDIATE")
            assert repo._claim_active_sku_guard(
                connection, {"owner_id": "owner-1", "store_id": "store-a"},
                identity, "EXPERIMENT", experiment["experiment_id"], repo._timestamp(),
            ) is False
            connection.rollback()
        finally:
            connection.close()
        finished = repo.finish_unit_price_observation(
            observation["observation_id"], expected_state_revision=1,
            idempotency_key="w21-guardfinish",
        )
        assert finished["error"] is False
        connection = repo.get_connection()
        try:
            connection.execute("BEGIN IMMEDIATE")
            assert repo._claim_active_sku_guard(
                connection, {"owner_id": "owner-1", "store_id": "store-a"},
                identity, "EXPERIMENT", experiment["experiment_id"], repo._timestamp(),
            ) is True
            connection.commit()
        finally:
            connection.close()
        blocked = repo.start_unit_price_observation(
            identity=identity, seller_price_cents=10000,
            source_document_id=saved["document_id"], source_document_revision=1,
            effective_from="2026-10-28T09:30:00Z", window_timezone="Europe/Moscow",
            owner_confirmed=True, idempotency_key="w21-guardobs02",
        )
        assert blocked["code"] == "PLANNING_PRICE_EXPERIMENT_ALREADY_ACTIVE"
    finally:
        reset_current_tenant_user_id(token)


def test_v6_migration_marks_legacy_cross_type_overlap_and_release_keeps_remaining_lock(tmp_path):
    repo = PlanningWorkspaceRepository(db_path=tmp_path / "planning.sqlite")
    saved, _, experiment = _seed(repo)
    token = _context()
    identity = {"product_id": "product-1", "offer_id": "offer-1", "sku": "sku-1",
                "sale_schema": "FBO"}
    try:
        observation = repo.start_unit_price_observation(
            identity=identity, seller_price_cents=10000,
            source_document_id=saved["document_id"], source_document_revision=1,
            effective_from="2026-10-27T09:30:00Z", window_timezone="Europe/Moscow",
            owner_confirmed=True, idempotency_key="w21-overlapobs",
        )
        assert observation["error"] is False
    finally:
        reset_current_tenant_user_id(token)
    connection = sqlite3.connect(repo.db_path)
    try:
        connection.execute(
            "UPDATE planning_price_experiments SET status='BASELINE_ACTIVE' WHERE experiment_id=?",
            (experiment["experiment_id"],),
        )
        connection.execute("DROP TABLE planning_active_sku_guards")
        connection.execute("UPDATE planning_schema SET version=6")
        connection.commit()
    finally:
        connection.close()

    reopened = PlanningWorkspaceRepository(db_path=repo.db_path)
    initialized = reopened.get_connection()
    initialized.close()
    connection = sqlite3.connect(repo.db_path)
    try:
        assert connection.execute(
            "SELECT operation_kind, operation_id FROM planning_active_sku_guards"
        ).fetchone() == ("CONFLICT", None)
        assert connection.execute(
            "SELECT status FROM planning_price_experiments WHERE experiment_id=?",
            (experiment["experiment_id"],),
        ).fetchone() == ("BASELINE_ACTIVE",)
    finally:
        connection.close()

    token = _context()
    try:
        blocked = reopened.start_unit_price_observation(
            identity=identity, seller_price_cents=10000,
            source_document_id=saved["document_id"], source_document_revision=1,
            effective_from="2026-10-28T09:30:00Z", window_timezone="Europe/Moscow",
            owner_confirmed=True, idempotency_key="w21-overlapblock",
        )
        assert blocked["code"] == "PLANNING_ACTIVE_SKU_GUARD_CONFLICT"
        finished = reopened.finish_unit_price_observation(
            observation["observation_id"], expected_state_revision=1,
            idempotency_key="w21-overlapfinish",
        )
        assert finished["error"] is False
    finally:
        reset_current_tenant_user_id(token)
    connection = sqlite3.connect(repo.db_path)
    try:
        assert connection.execute(
            "SELECT operation_kind, operation_id FROM planning_active_sku_guards"
        ).fetchone() == ("EXPERIMENT", experiment["experiment_id"])
    finally:
        connection.close()


def test_shared_active_sku_guard_isolated_by_store(tmp_path):
    repo = PlanningWorkspaceRepository(db_path=tmp_path / "planning.sqlite")
    saved, _, _ = _seed(repo)
    identity = {"product_id": "product-1", "offer_id": "offer-1", "sku": "sku-1",
                "sale_schema": "FBO"}
    token = _context()
    try:
        first = repo.start_unit_price_observation(
            identity=identity, seller_price_cents=10000,
            source_document_id=saved["document_id"], source_document_revision=1,
            effective_from="2026-10-27T09:30:00Z", window_timezone="Europe/Moscow",
            owner_confirmed=True, idempotency_key="w21-storeaobs",
        )
        assert first["error"] is False
    finally:
        reset_current_tenant_user_id(token)

    token = _context(store="store-b")
    try:
        plan_b = repo.save_document(
            title="Plan B", payload=_plan_payload(store="store-b"),
            idempotency_key="w21-storebplan",
        )
        assert plan_b["error"] is False
        second = repo.start_unit_price_observation(
            identity=identity, seller_price_cents=10000,
            source_document_id=plan_b["document_id"], source_document_revision=1,
            effective_from="2026-10-27T09:30:00Z", window_timezone="Europe/Moscow",
            owner_confirmed=True, idempotency_key="w21-storebobs",
        )
        assert second["error"] is False
    finally:
        reset_current_tenant_user_id(token)

    connection = sqlite3.connect(repo.db_path)
    try:
        assert connection.execute(
            "SELECT COUNT(*) FROM planning_active_sku_guards WHERE sku='sku-1'"
        ).fetchone() == (2,)
    finally:
        connection.close()


def test_concurrent_same_sku_observation_starts_are_serialized(tmp_path):
    repo = PlanningWorkspaceRepository(db_path=tmp_path / "planning.sqlite")
    saved, _, _ = _seed(repo)
    identity = {"product_id": "product-1", "offer_id": "offer-1", "sku": "sku-1",
                "sale_schema": "FBO"}

    def start(index):
        token = _context()
        try:
            return repo.start_unit_price_observation(
                identity=identity, seller_price_cents=10000,
                source_document_id=saved["document_id"], source_document_revision=1,
                effective_from="2026-10-27T09:30:00Z", window_timezone="Europe/Moscow",
                owner_confirmed=True, idempotency_key=f"w21-concurrent{index:02d}",
            )
        finally:
            reset_current_tenant_user_id(token)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(start, (1, 2)))

    assert sum(result.get("error") is False for result in results) == 1
    failures = [result for result in results if result.get("error") is True]
    assert len(failures) == 1
    assert failures[0]["code"] == "PLANNING_OBSERVATION_ALREADY_ACTIVE"


def test_experiment_cancel_transition_is_cas_idempotent_and_store_scoped(tmp_path):
    repo = PlanningWorkspaceRepository(db_path=tmp_path / "planning.sqlite")
    _, _, experiment = _seed(repo)
    experiment_id = experiment["experiment_id"]
    token = _context()
    try:
        cancelled = repo.transition_price_experiment(
            experiment_id, "cancel", expected_state_revision=1,
            idempotency_key="w21-cancel001",
        )
        assert cancelled["error"] is False
        assert cancelled["status"] == "CANCELLED"
        assert cancelled["state_revision"] == 2
        assert repo.transition_price_experiment(
            experiment_id, "cancel", expected_state_revision=1,
            idempotency_key="w21-cancel001",
        ) == cancelled
        assert repo.transition_price_experiment(
            experiment_id, "cancel", expected_state_revision=1,
            idempotency_key="w21-stale001",
        )["code"] == "PLANNING_PRICE_EXPERIMENT_STATE_CONFLICT"
        other_store = _context(store="store-b")
        try:
            assert repo.get_price_experiment(experiment_id)["code"] == (
                "PLANNING_PRICE_EXPERIMENT_NOT_FOUND"
            )
            assert repo.transition_price_experiment(
                experiment_id, "cancel", expected_state_revision=2,
                idempotency_key="w21-otherstore",
            )["code"] == "PLANNING_PRICE_EXPERIMENT_NOT_FOUND"
        finally:
            reset_current_tenant_user_id(other_store)
        assert repo.get_price_experiment(experiment_id)["experiment"]["status"] == "CANCELLED"
    finally:
        reset_current_tenant_user_id(token)


def test_snapshot_content_addressing_privacy_and_store_scope(tmp_path):
    repo = PlanningWorkspaceRepository(db_path=tmp_path / "planning.sqlite")
    token = _context()
    try:
        first = repo.create_unit_economics_expense_snapshot(_snapshot_payload())
        replay = repo.create_unit_economics_expense_snapshot(_snapshot_payload())
        assert first["created"] is True
        assert replay == {**first, "created": False}
        read = repo.get_unit_economics_expense_snapshot(first["snapshot_id"])
        assert read["error"] is False
        assert read["payload"]["identity"] == _identity()
        assert "raw_response" not in json.dumps(read)
        assert repo.get_unit_economics_expense_snapshot("0" * 64)["code"] == (
            "PLANNING_EXPENSE_SNAPSHOT_NOT_FOUND"
        )
    finally:
        reset_current_tenant_user_id(token)
    token = _context(store="store-b")
    try:
        assert repo.get_unit_economics_expense_snapshot(first["snapshot_id"])["code"] == (
            "PLANNING_EXPENSE_SNAPSHOT_NOT_FOUND"
        )
    finally:
        reset_current_tenant_user_id(token)
    connection = sqlite3.connect(repo.db_path)
    try:
        try:
            connection.execute(
                "UPDATE planning_unit_economics_snapshots SET payload_json='{}' "
                "WHERE snapshot_id=?", (first["snapshot_id"],),
            )
            raise AssertionError("snapshot update unexpectedly succeeded")
        except sqlite3.IntegrityError:
            pass
    finally:
        connection.close()


def test_experiment_phase_result_replay_cas_and_append_only_history(tmp_path):
    repo = PlanningWorkspaceRepository(db_path=tmp_path / "planning.sqlite")
    saved, snapshot, experiment = _seed(repo)
    token = _context()
    try:
        payload = _phase_payload(snapshot["snapshot_id"])
        phase = repo.create_price_experiment_phase(
            experiment["experiment_id"], payload, expected_state_revision=1,
            idempotency_key="w17-phase-create01",
        )
        assert phase["error"] is False
        assert phase["experiment_state_revision"] == 2
        assert repo.create_price_experiment_phase(
            experiment["experiment_id"], payload, expected_state_revision=1,
            idempotency_key="w17-phase-create01",
        ) == phase
        changed_payload = {**payload, "planned_price_cents": 9999}
        assert repo.create_price_experiment_phase(
            experiment["experiment_id"], changed_payload, expected_state_revision=1,
            idempotency_key="w17-phase-create01",
        )["code"] == "PLANNING_PRICE_EXPERIMENT_IDEMPOTENCY_CONFLICT"
        assert repo.create_price_experiment_phase(
            experiment["experiment_id"], payload, expected_state_revision=1,
            idempotency_key="w17-phase-stale001",
        )["code"] == "PLANNING_PRICE_EXPERIMENT_STATE_CONFLICT"

        result_payload = _result_payload(snapshot["snapshot_id"])
        result = repo.append_price_experiment_result(
            experiment["experiment_id"], phase["phase_id"], result_payload,
            expected_state_revision=2, expected_phase_state_revision=1,
            expected_result_revision=0, idempotency_key="w17-result-append01",
        )
        assert result["error"] is False and result["result_revision"] == 1
        assert repo.append_price_experiment_result(
            experiment["experiment_id"], phase["phase_id"], result_payload,
            expected_state_revision=2, expected_phase_state_revision=1,
            expected_result_revision=0, idempotency_key="w17-result-append01",
        ) == result
        second = _result_payload(snapshot["snapshot_id"], candidate="12.00", delta="2.00")
        appended = repo.append_price_experiment_result(
            experiment["experiment_id"], phase["phase_id"], second,
            expected_state_revision=2, expected_phase_state_revision=1,
            expected_result_revision=1, idempotency_key="w17-result-append02",
        )
        assert appended["result_revision"] == 2
        stale = repo.append_price_experiment_result(
            experiment["experiment_id"], phase["phase_id"], second,
            expected_state_revision=1, expected_phase_state_revision=1,
            expected_result_revision=2, idempotency_key="w17-result-stale001",
        )
        assert stale["code"] == "PLANNING_PRICE_EXPERIMENT_STATE_CONFLICT"
        history = repo.list_price_experiment_results(
            experiment["experiment_id"], phase["phase_id"], limit=1,
        )
        assert history["error"] is False and history["has_more"] is True
        assert history["items"][0]["result_revision"] == 2
        old_history = repo.list_price_experiment_results(
            experiment["experiment_id"], phase["phase_id"], limit=1, offset=1,
        )
        assert old_history["items"][0]["result_revision"] == 1
        assert repo.get_price_experiment(experiment["experiment_id"])["experiment"][
            "state_revision"
        ] == 2
        assert repo.get_price_experiment(experiment["experiment_id"])["experiment"][
            "result_revision"
        ] == 2
        assert repo.list_price_experiment_phases(experiment["experiment_id"])[
            "items"
        ][0]["phase_id"] == phase["phase_id"]
        assert len(repo.list_price_experiment_revisions(
            experiment["experiment_id"], limit=1,
        )["items"]) == 1
        assert len(repo.list_price_experiment_phase_revisions(
            experiment["experiment_id"], phase["phase_id"], limit=10,
        )["items"]) == 3
        assert repo.archive_price_experiment(
            experiment["experiment_id"], expected_state_revision=2,
            idempotency_key="w17-exp-archive001",
        )["status"] == "ARCHIVED"
        assert repo.list_price_experiments(include_archived=True)["items"][0][
            "status"
        ] == "ARCHIVED"
        assert repo.list_price_experiments(include_archived=False)["items"] == []
    finally:
        reset_current_tenant_user_id(token)

    connection = sqlite3.connect(repo.db_path)
    try:
        try:
            connection.execute(
                "UPDATE planning_price_experiment_results SET payload_json='{}' "
                "WHERE experiment_id=?", (experiment["experiment_id"],),
            )
            raise AssertionError("result update unexpectedly succeeded")
        except sqlite3.IntegrityError:
            pass
        try:
            connection.execute(
                "DELETE FROM planning_price_experiment_results WHERE experiment_id=?",
                (experiment["experiment_id"],),
            )
            raise AssertionError("result deletion unexpectedly succeeded")
        except sqlite3.IntegrityError:
            pass
    finally:
        connection.close()


def test_invalid_references_versions_and_result_math_fail_closed(tmp_path):
    repo = PlanningWorkspaceRepository(db_path=tmp_path / "planning.sqlite")
    token = _context()
    try:
        saved = repo.save_document(
            title="Plan", payload=_plan_payload(), idempotency_key="w17-plan-save02",
        )
        snapshot = repo.create_unit_economics_expense_snapshot(_snapshot_payload())
        bad = _experiment_payload("missing-plan", snapshot["snapshot_id"])
        assert repo.create_price_experiment(
            bad, idempotency_key="w17-experimentbad1",
        )["code"] == "PLANNING_PRICE_EXPERIMENT_SOURCE_PLAN_NOT_FOUND"
        other_plan = repo.save_document(
            title="Other SKU", payload=_plan_payload(sku="sku-other"),
            idempotency_key="w17-plan-other001",
        )
        wrong_plan = _experiment_payload(other_plan["document_id"], snapshot["snapshot_id"])
        assert repo.create_price_experiment(
            wrong_plan, idempotency_key="w17-experimentbad2",
        )["code"] == "PLANNING_PRICE_EXPERIMENT_SOURCE_PLAN_SCOPE_MISMATCH"
        other_snapshot = repo.create_unit_economics_expense_snapshot(
            _snapshot_payload(_identity(sku="sku-other")),
        )
        wrong_snapshot = _experiment_payload(saved["document_id"], other_snapshot["snapshot_id"])
        assert repo.create_price_experiment(
            wrong_snapshot, idempotency_key="w17-experimentbad3",
        )["code"] == "PLANNING_PRICE_EXPERIMENT_SNAPSHOT_SCOPE_MISMATCH"
        future = _snapshot_payload()
        future["schema_version"] = 99
        assert repo.create_unit_economics_expense_snapshot(future)["code"] == (
            "PLANNING_EXPENSE_SNAPSHOT_INVALID"
        )
        experiment = repo.create_price_experiment(
            _experiment_payload(saved["document_id"], snapshot["snapshot_id"]),
            idempotency_key="w17-experiment02",
        )
        phase = repo.create_price_experiment_phase(
            experiment["experiment_id"], _phase_payload(snapshot["snapshot_id"]),
            expected_state_revision=1, idempotency_key="w17-phase-create02",
        )
        mismatch = _result_payload(snapshot["snapshot_id"], delta="1.49")
        assert repo.append_price_experiment_result(
            experiment["experiment_id"], phase["phase_id"], mismatch,
            expected_state_revision=2, expected_phase_state_revision=1,
            expected_result_revision=0, idempotency_key="w17-result-invalid1",
        )["code"] == "PLANNING_PRICE_EXPERIMENT_RESULT_INVALID"
        foreign = _result_payload("f" * 64)
        assert repo.append_price_experiment_result(
            experiment["experiment_id"], phase["phase_id"], foreign,
            expected_state_revision=2, expected_phase_state_revision=1,
            expected_result_revision=0, idempotency_key="w17-result-foreign01",
        )["code"] == "PLANNING_PRICE_EXPERIMENT_RESULT_SNAPSHOT_MISMATCH"
    finally:
        reset_current_tenant_user_id(token)


def test_experiment_freezes_exact_tariff_and_observation_revisions(tmp_path):
    repo = PlanningWorkspaceRepository(db_path=tmp_path / "planning.sqlite")
    token = _context()
    try:
        plan = repo.save_document(
            title="Plan", payload=_plan_payload(), idempotency_key="w17-plan-source01",
        )
        snapshot = repo.create_unit_economics_expense_snapshot(_snapshot_payload())
        tariff = repo.create_tariff_profile({
            "identity": {"product_id": "product-1", "offer_id": "offer-1", "sku": "sku-1"},
            "sale_schema": "FBO", "effective_from": "2026-10-01",
            "effective_to": None, "confirmed_by_owner": True,
            "bands": [{"price_from_cents": 9000, "price_to_cents": 12000,
                        "commission_rate": "12"}],
        }, idempotency_key="w17-tariff-save001")
        assert tariff["error"] is False
        observation = repo.start_unit_price_observation(
            identity={"product_id": "product-1", "offer_id": "offer-1", "sku": "sku-1",
                      "sale_schema": "FBO"},
            seller_price_cents=10000, source_document_id=plan["document_id"],
            source_document_revision=1, effective_from="2026-10-27T09:30:00Z",
            window_timezone="Europe/Moscow", owner_confirmed=True,
            idempotency_key="w17-observation01",
        )
        assert observation["error"] is False
        observation_result = {
            "schema_version": 1,
            "identity": {"store_id": "store-a", "product_id": "product-1",
                         "offer_id": "offer-1", "sku": "sku-1", "sale_schema": "FBO"},
            "seller_price_cents": 10000, "status": "INSUFFICIENT_DATA",
            "evidence_basis": "MODELLED_FROM_OBSERVED_INPUTS",
            "window": {"from": "2026-10-19", "to": "2026-10-25",
                        "timezone": "Europe/Moscow", "date_basis": "LOCAL_CALENDAR_DATE"},
            "sources": [{"name": "finance", "status": "PARTIAL", "complete": False,
                         "row_count": 3, "as_of": "2026-10-27T09:00:00Z"}],
            "metrics": {"cpc_spend": "10.00", "successful_sale_units": None},
            "completeness": {"price_history": "PRICE_HISTORY_UNCONFIRMED"},
            "reasons": ["PRICE_HISTORY_UNCONFIRMED"], "warnings": [],
        }
        saved_result = repo.append_unit_price_observation_result(
            observation["observation_id"], observation_result,
            expected_state_revision=1, expected_result_revision=0,
            idempotency_key="w17-observation-result01",
        )
        assert saved_result["error"] is False
        config = _experiment_payload(plan["document_id"], snapshot["snapshot_id"])
        config["source_references"]["tariff"] = {
            "profile_id": tariff["profile_id"], "revision": 1,
        }
        config["source_references"]["observation"] = {
            "observation_id": observation["observation_id"], "result_revision": 1,
        }
        created = repo.create_price_experiment(
            config, idempotency_key="w17-frozen-refs01",
        )
        assert created["error"] is False, created
        phase = repo.create_price_experiment_phase(
            created["experiment_id"], _phase_payload(snapshot["snapshot_id"]),
            expected_state_revision=1, idempotency_key="w18-phase-create01",
        )
        assert phase["error"] is False, phase
        first_result_payload = _result_payload(snapshot["snapshot_id"])
        first_result = repo.append_price_experiment_result(
            created["experiment_id"], phase["phase_id"], first_result_payload,
            expected_state_revision=phase["experiment_state_revision"],
            expected_phase_state_revision=1, expected_result_revision=0,
            idempotency_key="w18-result-append01",
        )
        assert first_result["error"] is False, first_result
        reopened = repo.get_price_experiment(created["experiment_id"])["experiment"]
        assert reopened["config"]["source_references"]["tariff"] == {
            "profile_id": tariff["profile_id"], "revision": 1,
        }
        assert reopened["config"]["source_references"]["observation"] == {
            "observation_id": observation["observation_id"], "result_revision": 1,
        }

        plan_v2 = deepcopy(_plan_payload())
        plan_v2["items"][0]["inputs"]["price"] = "600.00"
        plan_v2["items"][0]["inputs"]["cost"] = "125.00"
        updated_plan = repo.save_document(
            title="Plan refreshed", payload=plan_v2,
            document_id=plan["document_id"], expected_revision=1,
            expected_state_revision=1, idempotency_key="w18-plan-refresh01",
        )
        assert updated_plan["error"] is False and updated_plan["revision"] == 2
        updated_tariff = repo.update_tariff_profile(
            tariff["profile_id"], {
                "identity": {"product_id": "product-1", "offer_id": "offer-1", "sku": "sku-1"},
                "sale_schema": "FBO", "effective_from": "2026-10-01",
                "effective_to": None, "confirmed_by_owner": True,
                "bands": [{"price_from_cents": 9000, "price_to_cents": 12000,
                           "commission_rate": "13"}],
            }, expected_revision=1, expected_state_revision=1,
            idempotency_key="w18-tariff-refresh01",
        )
        assert updated_tariff["error"] is False and updated_tariff["revision"] == 2
        observation_result_v2 = deepcopy(observation_result)
        observation_result_v2["sources"][0]["row_count"] = 4
        observation_result_v2["sources"][0]["as_of"] = "2026-10-28T09:00:00Z"
        observation_result_v2["metrics"]["cpc_spend"] = "11.00"
        updated_observation = repo.append_unit_price_observation_result(
            observation["observation_id"], observation_result_v2,
            expected_state_revision=1, expected_result_revision=1,
            idempotency_key="w18-observation-refresh01",
        )
        assert updated_observation["error"] is False
        assert updated_observation["result_revision"] == 2
        snapshot_v2_payload = _snapshot_payload()
        snapshot_v2_payload["readiness"]["denominator"]["units"] = 12
        snapshot_v2 = repo.create_unit_economics_expense_snapshot(snapshot_v2_payload)
        assert snapshot_v2["error"] is False
        assert snapshot_v2["snapshot_id"] != snapshot["snapshot_id"]
        second_result_payload = _result_payload(
            snapshot_v2["snapshot_id"], baseline="10.00", candidate="12.00", delta="2.00",
        )
        second_result_payload["snapshot_refs"] = [
            snapshot["snapshot_id"], snapshot_v2["snapshot_id"],
        ]
        second_result_payload["source_as_of"] = "2026-11-07T12:00:00Z"
        second_result = repo.append_price_experiment_result(
            created["experiment_id"], phase["phase_id"], second_result_payload,
            expected_state_revision=phase["experiment_state_revision"],
            expected_phase_state_revision=1, expected_result_revision=1,
            idempotency_key="w18-result-append02",
        )
        assert second_result["error"] is False, second_result
        stored_results = repo.list_price_experiment_results(
            created["experiment_id"], phase["phase_id"],
        )
        assert [item["result_revision"] for item in stored_results["items"]] == [2, 1]
        assert stored_results["items"][1]["payload"] == first_result_payload
        assert stored_results["items"][0]["payload"]["snapshot_refs"] == [
            snapshot["snapshot_id"], snapshot_v2["snapshot_id"],
        ]

        frozen = repo.get_price_experiment_frozen_snapshot(created["experiment_id"])
        assert frozen["error"] is False, frozen
        assert frozen["source_io"] is False
        frozen_view = UnitEconomicsExperimentSnapshotViewService.project(frozen)
        assert frozen_view["error"] is False, frozen_view
        assert frozen_view["view"]["revisions"]["plan_revision"] == 1
        assert frozen_view["view"]["revisions"]["tariff_revision"] == 1
        assert frozen_view["view"]["revisions"]["quantity_result_revision"] == 1
        assert frozen_view["view"]["economics"]["inputs"]["cost"] == "100.00"
        assert frozen_view["view"]["source_io"] is False
        assert frozen["frozen_inputs"]["plan"]["revision"] == 1
        assert frozen["frozen_inputs"]["plan"]["payload"]["items"][0]["inputs"]["cost"] == "100.00"
        assert frozen["frozen_inputs"]["expense_snapshot"]["snapshot_id"] == snapshot["snapshot_id"]
        assert frozen["frozen_inputs"]["expense_snapshot"]["payload"]["readiness"][
            "denominator"]["units"] == 10
        assert frozen["frozen_inputs"]["tariff"]["revision"] == 1
        assert frozen["frozen_inputs"]["tariff"]["profile"]["bands"][0][
            "commission_rate"] == "12"
        assert frozen["frozen_inputs"]["quantity"]["result_revision"] == 1
        assert frozen["frozen_inputs"]["quantity"]["result"]["metrics"]["cpc_spend"] == "10.00"
        refreshed_config = deepcopy(config)
        refreshed_config["source_references"]["plan"]["revision"] = 2
        refreshed_config["source_references"]["expense_snapshot_id"] = snapshot_v2["snapshot_id"]
        refreshed_config["source_references"]["tariff"]["revision"] = 2
        refreshed_config["source_references"]["observation"]["result_revision"] = 2
        refreshed = repo.create_price_experiment(
            refreshed_config, idempotency_key="w18-experiment-refresh01",
        )
        assert refreshed["error"] is False, refreshed
        refreshed_inputs = repo.get_price_experiment_frozen_snapshot(
            refreshed["experiment_id"],
        )
        assert refreshed_inputs["error"] is False, refreshed_inputs
        assert refreshed_inputs["frozen_inputs"]["plan"]["revision"] == 2
        assert refreshed_inputs["frozen_inputs"]["plan"]["payload"]["items"][0][
            "inputs"]["cost"] == "125.00"
        assert refreshed_inputs["frozen_inputs"]["expense_snapshot"]["snapshot_id"] == (
            snapshot_v2["snapshot_id"]
        )
        assert refreshed_inputs["frozen_inputs"]["tariff"]["revision"] == 2
        assert refreshed_inputs["frozen_inputs"]["quantity"]["result_revision"] == 2
        assert repo.create_price_experiment(
            {**config, "source_references": {
                **config["source_references"],
                "tariff": {"profile_id": "0" * 32, "revision": 1},
            }},
            idempotency_key="w17-frozen-refs02",
        )["code"] == "PLANNING_PRICE_EXPERIMENT_TARIFF_REVISION_NOT_FOUND"
    finally:
        reset_current_tenant_user_id(token)


def test_create_experiment_transaction_rolls_back_revision_and_idempotency(tmp_path):
    repo = PlanningWorkspaceRepository(db_path=tmp_path / "planning.sqlite")
    token = _context()
    try:
        saved = repo.save_document(
            title="Plan", payload=_plan_payload(), idempotency_key="w17-plan-save03",
        )
        snapshot = repo.create_unit_economics_expense_snapshot(_snapshot_payload())
        payload = _experiment_payload(saved["document_id"], snapshot["snapshot_id"])
        connection = repo.get_connection()
        connection.execute("""CREATE TRIGGER abort_w17_revision
            BEFORE INSERT ON planning_price_experiment_revisions
            BEGIN SELECT RAISE(ABORT, 'synthetic rollback'); END""")
        connection.close()
        failed = repo.create_price_experiment(payload, idempotency_key="w17-rollback001")
        assert failed["code"] == "PLANNING_STORAGE_UNAVAILABLE"
        connection = sqlite3.connect(repo.db_path)
        try:
            assert connection.execute(
                "SELECT COUNT(*) FROM planning_price_experiments",
            ).fetchone()[0] == 0
            assert connection.execute(
                "SELECT COUNT(*) FROM planning_price_experiment_idempotency",
            ).fetchone()[0] == 0
        finally:
            connection.close()
        connection = repo.get_connection()
        connection.execute("DROP TRIGGER abort_w17_revision")
        connection.close()
        created = repo.create_price_experiment(payload, idempotency_key="w17-rollback001")
        assert created["error"] is False
    finally:
        reset_current_tenant_user_id(token)


def test_experiment_phase_result_and_snapshot_quotas_are_bounded(tmp_path, monkeypatch):
    repo = PlanningWorkspaceRepository(db_path=tmp_path / "planning.sqlite")
    monkeypatch.setattr(repo, "MAX_UNIT_ECONOMICS_SNAPSHOTS_PER_STORE", 1)
    monkeypatch.setattr(repo, "MAX_PRICE_EXPERIMENTS_PER_STORE", 1)
    monkeypatch.setattr(repo, "MAX_PRICE_EXPERIMENT_PHASES", 1)
    monkeypatch.setattr(repo, "MAX_PRICE_EXPERIMENT_RESULTS_PER_PHASE", 1)
    token = _context()
    try:
        saved = repo.save_document(
            title="Plan", payload=_plan_payload(), idempotency_key="w17-plan-save04",
        )
        snapshot = repo.create_unit_economics_expense_snapshot(_snapshot_payload())
        alternate = _snapshot_payload()
        alternate["readiness"] = _readiness("2026-08-02", "2026-09-26")
        assert repo.create_unit_economics_expense_snapshot(
            alternate,
        )["code"] == "PLANNING_EXPENSE_SNAPSHOT_QUOTA_REACHED"
        experiment = repo.create_price_experiment(
            _experiment_payload(saved["document_id"], snapshot["snapshot_id"]),
            idempotency_key="w17-experiment03",
        )
        assert repo.create_price_experiment(
            _experiment_payload(saved["document_id"], snapshot["snapshot_id"]),
            idempotency_key="w17-experiment04",
        )["code"] == "PLANNING_PRICE_EXPERIMENT_QUOTA_REACHED"
        phase = repo.create_price_experiment_phase(
            experiment["experiment_id"], _phase_payload(snapshot["snapshot_id"]),
            expected_state_revision=1, idempotency_key="w17-phase-create03",
        )
        second_phase = _phase_payload(
            snapshot["snapshot_id"], kind="CANDIDATE", segment=2, price=9900,
        )
        assert repo.create_price_experiment_phase(
            experiment["experiment_id"], second_phase, expected_state_revision=2,
            idempotency_key="w17-phase-quota001",
        )["code"] == "PLANNING_PRICE_EXPERIMENT_PHASE_QUOTA_REACHED"
        first_result = repo.append_price_experiment_result(
            experiment["experiment_id"], phase["phase_id"],
            _result_payload(snapshot["snapshot_id"]), expected_state_revision=2,
            expected_phase_state_revision=1, expected_result_revision=0,
            idempotency_key="w17-result-quota01",
        )
        assert first_result["error"] is False
        assert repo.append_price_experiment_result(
            experiment["experiment_id"], phase["phase_id"],
            _result_payload(snapshot["snapshot_id"], candidate="12.00", delta="2.00"),
            expected_state_revision=2, expected_phase_state_revision=1,
            expected_result_revision=1, idempotency_key="w17-result-quota02",
        )["code"] == "PLANNING_PRICE_EXPERIMENT_RESULT_QUOTA_REACHED"
    finally:
        reset_current_tenant_user_id(token)


def test_stored_future_or_corrupt_payload_fails_closed(tmp_path):
    repo = PlanningWorkspaceRepository(db_path=tmp_path / "planning.sqlite")
    saved, snapshot, experiment = _seed(repo)
    connection = sqlite3.connect(repo.db_path)
    try:
        connection.execute("DROP TRIGGER trg_price_experiments_immutable_config")
        connection.execute(
            "UPDATE planning_price_experiments SET config_json=? WHERE experiment_id=?",
            (json.dumps({"schema_version": 999}), experiment["experiment_id"]),
        )
        connection.commit()
    finally:
        connection.close()
    token = _context()
    try:
        assert repo.get_price_experiment(experiment["experiment_id"])["code"] == (
            "PLANNING_PRICE_EXPERIMENT_CORRUPT"
        )
    finally:
        reset_current_tenant_user_id(token)

