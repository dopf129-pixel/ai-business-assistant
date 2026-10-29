import json
import sqlite3
from datetime import datetime, timezone

from services.ozon_account_repository import make_store_tenant_scope
from services.planning_workspace_repository import PlanningWorkspaceRepository
from services.tenant_context import reset_current_tenant_user_id, set_current_tenant_user_id


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


def test_schema_v6_additive_migration_preserves_existing_plan_and_old_tables(tmp_path):
    repo = PlanningWorkspaceRepository(db_path=tmp_path / "planning.sqlite")
    saved, snapshot, _ = _seed(repo)
    reopened = PlanningWorkspaceRepository(db_path=repo.db_path)
    token = _context()
    try:
        assert reopened.get_document(saved["document_id"])["error"] is False
        assert reopened.get_unit_economics_expense_snapshot(snapshot["snapshot_id"])["error"] is False
    finally:
        reset_current_tenant_user_id(token)
    connection = sqlite3.connect(repo.db_path)
    try:
        assert connection.execute("SELECT version FROM planning_schema").fetchone() == (6,)
        tables = {row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'",
        )}
        assert {
            "planning_documents", "planning_revisions", "planning_tariff_profiles",
            "planning_unit_price_observations", "planning_unit_price_comparisons",
            "planning_unit_economics_snapshots", "planning_price_experiments",
            "planning_price_experiment_phases", "planning_price_experiment_results",
        } <= tables
    finally:
        connection.close()


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
        reopened = repo.get_price_experiment(created["experiment_id"])["experiment"]
        assert reopened["config"]["source_references"]["tariff"] == {
            "profile_id": tariff["profile_id"], "revision": 1,
        }
        assert reopened["config"]["source_references"]["observation"] == {
            "observation_id": observation["observation_id"], "result_revision": 1,
        }
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

