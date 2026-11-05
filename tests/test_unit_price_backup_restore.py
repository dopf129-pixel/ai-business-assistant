"""Synthetic integration coverage for unit-price data backup and restore."""

from datetime import datetime, timezone
import sqlite3

from services.bot_backup_service import BotBackupService
from services.ozon_account_repository import make_store_tenant_scope
from services.planning_workspace_repository import PlanningWorkspaceRepository
from services.tenant_context import reset_current_tenant_user_id, set_current_tenant_user_id


OWNER = "synthetic-price-owner"
STORE = "synthetic-store-a"
IDENTITY = {
    "product_id": "synthetic-price-product",
    "offer_id": "synthetic-price-offer",
    "sku": "synthetic-price-sku",
    "sale_schema": "FBO",
}


def _plan_payload():
    return {
        "plan_kind": "single", "schema_version": 1, "calculation_version": 1,
        "target_margin_percent": "25.00", "items": [{
            "identity": {
                "product_id": IDENTITY["product_id"],
                "offer_id": IDENTITY["offer_id"], "sku": IDENTITY["sku"],
                "product_name": "Synthetic price product", "store_id": STORE,
                "scheme": "FBO",
            },
            "inputs": {
                "price": "100.00", "cost": "20.00", "commission_rate": "10",
                "advertising_rate": "0", "discount_points_rate": "0",
                "logistics_per_unit": "10", "last_mile_per_unit": "0",
                "acquiring_per_unit": "0", "tax_mode": "NONE", "tax_rate": "0",
                "minimum_tax_rate": None,
            },
            "provenance": {"price": "manual_seller_scenario"},
            "sources": {"periods": {}, "as_of": None, "loaded_at": None,
                        "completeness": {}},
            "projection": {"available": True, "missing_inputs": [],
                           "invalid_inputs": [], "revenue": "100.00",
                           "profit": "60.00"},
        }],
    }


def _result(*, spend):
    return {
        "schema_version": 1,
        "identity": {
            "store_id": STORE, "product_id": IDENTITY["product_id"],
            "offer_id": IDENTITY["offer_id"], "sku": IDENTITY["sku"],
            "sale_schema": "FBO",
        },
        "seller_price_cents": 10_000, "status": "INSUFFICIENT_DATA",
        "evidence_basis": "MODELLED_FROM_OBSERVED_INPUTS",
        "window": {
            "from": "2026-10-19", "to": "2026-10-25",
            "timezone": "Europe/Moscow", "date_basis": "LOCAL_CALENDAR_DATE",
        },
        "sources": [{"name": "FINANCE", "status": "PARTIAL", "complete": False,
                     "row_count": 1, "as_of": "2026-10-27T09:00:00Z"}],
        "metrics": {"cpc_spend": spend, "successful_unit_denominator": None},
        "completeness": {"price_history": "PRICE_HISTORY_UNCONFIRMED"},
        "reasons": ["PRICE_HISTORY_UNCONFIRMED"], "warnings": [],
    }


def _scope(store=STORE):
    return set_current_tenant_user_id(make_store_tenant_scope(OWNER, store))


def test_unit_price_records_survive_backup_verify_dry_run_and_new_root_restore(
    monkeypatch, tmp_path,
):
    project = tmp_path / "synthetic-project"
    source_storage = tmp_path / "synthetic-storage"
    project.mkdir()
    source_storage.mkdir()
    monkeypatch.setenv("AI_ASSISTANT_STORAGE_ROOT", str(source_storage))

    token = _scope()
    try:
        repo = PlanningWorkspaceRepository(
            clock=lambda: datetime(2026, 10, 27, 10, tzinfo=timezone.utc),
        )
        source_database = repo.db_path
        saved_plan = repo.save_document(
            title="Synthetic unit-price plan", payload=_plan_payload(),
            idempotency_key="unit-price-backup-plan-01",
        )
        assert saved_plan["error"] is False, saved_plan
        expected_plan_payload = repo.get_document(
            saved_plan["document_id"],
        )["document"]["payload"]

        tariff_payload = {
            "identity": {key: IDENTITY[key] for key in ("product_id", "offer_id", "sku")},
            "sale_schema": "FBO", "effective_from": "2026-10-01",
            "effective_to": None, "confirmed_by_owner": True,
            "bands": [{
                "price_from_cents": 1, "price_to_cents": 19_999,
                "commission_rate": "10",
            }, {
                "price_from_cents": 20_000, "price_to_cents": 50_000,
                "commission_rate": "12",
            }],
        }
        tariff = repo.create_tariff_profile(
            tariff_payload, idempotency_key="unit-price-backup-tariff-01",
        )
        assert tariff["error"] is False

        observation = repo.start_unit_price_observation(
            identity=IDENTITY, seller_price_cents=10_000,
            source_document_id=saved_plan["document_id"],
            source_document_revision=1, effective_from="2026-10-27T09:30:00Z",
            window_timezone="Europe/Moscow", owner_confirmed=True,
            idempotency_key="unit-price-backup-observation-01",
            note="Synthetic restore check",
        )
        assert observation["error"] is False
        observation_id = observation["observation_id"]

        first = repo.append_unit_price_observation_result(
            observation_id, _result(spend="25.00"), expected_state_revision=1,
            expected_result_revision=0,
            idempotency_key="unit-price-backup-result-v1",
        )
        second = repo.append_unit_price_observation_result(
            observation_id, _result(spend="30.00"), expected_state_revision=1,
            expected_result_revision=1,
            idempotency_key="unit-price-backup-result-v2",
        )
        assert first["error"] is False and first["result_revision"] == 1
        assert second["error"] is False and second["result_revision"] == 2

        rejected_raw_payload = repo.append_unit_price_observation_result(
            observation_id,
            {**_result(spend="999.00"), "raw_response": "SYNTHETIC-SECRET-RAW"},
            expected_state_revision=1, expected_result_revision=2,
            idempotency_key="unit-price-backup-result-raw",
        )
        assert rejected_raw_payload["error"] is True
        assert repo.get_document(saved_plan["document_id"])["error"] is False
        assert repo.get_tariff_profile(tariff["profile_id"])["error"] is False
        latest = repo.get_unit_price_observation(observation_id)
        assert latest["error"] is False
        assert latest["observation"]["result_revision"] == 2
        assert latest["result"]["payload"]["metrics"]["cpc_spend"] == "30.00"
        assert repo.get_unit_price_observation(
            observation_id, result_revision=1,
        )["result"]["payload"]["metrics"]["cpc_spend"] == "25.00"
    finally:
        reset_current_tenant_user_id(token)

    backup_service = BotBackupService(
        project_root=project, storage_root=source_storage,
        backup_directory=project / ".local-backups",
        lifecycle_token="synthetic-price-backup-token",
        lifecycle_inspector=lambda _token: {"state": "STOPPED"},
        revision_reader=lambda _root: "synthetic-price-revision",
    )
    backup = backup_service.backup()
    assert backup["error"] is False, backup
    assert backup_service.verify_archive(backup["backup_path"])["error"] is False

    target = tmp_path / "restored-price-root"
    dry_run = backup_service.restore_archive(
        backup["backup_path"], target, dry_run=True,
    )
    assert dry_run["error"] is False
    assert not target.exists()
    restored = backup_service.restore_archive(backup["backup_path"], target)
    assert restored["error"] is False, restored

    monkeypatch.setenv("AI_ASSISTANT_STORAGE_ROOT", str(target / "storage"))
    token = _scope()
    try:
        reopened = PlanningWorkspaceRepository(
            clock=lambda: datetime(2026, 10, 27, 10, tzinfo=timezone.utc),
        )
        restored_plan = reopened.get_document(saved_plan["document_id"])
        assert restored_plan["error"] is False
        assert restored_plan["document"]["payload"] == expected_plan_payload
        restored_tariff = reopened.get_tariff_profile(tariff["profile_id"])
        assert restored_tariff["error"] is False
        assert restored_tariff["revision"] == 1
        assert restored_tariff["profile"]["bands"] == tariff_payload["bands"]

        restored_observation = reopened.get_unit_price_observation(observation_id)
        assert restored_observation["error"] is False
        assert restored_observation["observation"]["result_revision"] == 2
        assert restored_observation["result"]["revision"] == 2
        assert restored_observation["result"]["payload"] == _result(spend="30.00")
        old_result = reopened.get_unit_price_observation(
            observation_id, result_revision=1,
        )
        assert old_result["error"] is False
        assert old_result["result"]["revision"] == 1
        assert old_result["result"]["payload"] == _result(spend="25.00")
        history = reopened.list_unit_price_observation_results(observation_id)
        assert [row["revision"] for row in history["items"]] == [2, 1]
    finally:
        reset_current_tenant_user_id(token)

    token = _scope("synthetic-store-b")
    try:
        other_store = PlanningWorkspaceRepository()
        assert other_store.get_document(saved_plan["document_id"])["error"] is True
        assert other_store.get_tariff_profile(tariff["profile_id"])["error"] is True
        assert other_store.get_unit_price_observation(observation_id)["error"] is True
    finally:
        reset_current_tenant_user_id(token)

    database_path = next((target / "storage").rglob("ozon_assistant.db"))
    database_bytes = database_path.read_bytes()
    assert b"SYNTHETIC-SECRET-RAW" not in database_bytes
    assert source_database.exists()
    assert (target / "storage").exists()


def test_experiment_phases_results_and_event_history_survive_new_root_restore(
    monkeypatch, tmp_path,
):
    from test_planning_workspace_unit_economics import (
        _confirm_baseline_phase,
        _context,
        _ready_baseline_phase,
        _seed,
    )
    from test_unit_economics_experiment_phase_collection_service import (
        PhaseEvidenceCollector,
        _service,
    )

    project = tmp_path / "experiment-project"
    source_storage = tmp_path / "experiment-storage"
    project.mkdir()
    source_storage.mkdir()
    monkeypatch.setenv("AI_ASSISTANT_STORAGE_ROOT", str(source_storage))

    token = _context()
    try:
        repo = PlanningWorkspaceRepository(
            clock=lambda: datetime(2026, 11, 6, 12, tzinfo=timezone.utc),
        )
        saved_plan, cost_snapshot, experiment = _seed(repo)
        tariff_payload = {
            "identity": {
                "product_id": "product-1", "offer_id": "offer-1", "sku": "sku-1",
            },
            "sale_schema": "FBO", "effective_from": "2026-10-01",
            "effective_to": None, "confirmed_by_owner": True,
            "bands": [{
                "price_from_cents": 1, "price_to_cents": 19_999,
                "commission_rate": "10",
            }],
        }
        tariff = repo.create_tariff_profile(
            tariff_payload, idempotency_key="w37-backup-tariff-01",
        )
        assert tariff["error"] is False

        phase = _ready_baseline_phase(repo, saved_plan, cost_snapshot, experiment)
        confirmed = _confirm_baseline_phase(
            repo, experiment, phase, key="w37-backup-confirm-01",
        )
        assert confirmed["error"] is False

        collection = _service(repo, PhaseEvidenceCollector()).collect_phase(
            experiment["experiment_id"], phase["phase_id"],
            expected_state_revision=confirmed["state_revision"],
            expected_phase_state_revision=confirmed["phase_state_revision"],
            expected_result_revision=0,
            idempotency_key="w37-backup-collection-01",
            owner_id="owner-1", store_id="store-a",
        )
        assert collection["error"] is False, collection

        flags = {
            key: "UNCHANGED" for key in (
                "inventory", "promotion", "advertising", "card", "cost", "tariff",
            )
        }
        event = repo.record_price_experiment_control_update(
            experiment["experiment_id"], phase["phase_id"], flags,
            expected_state_revision=collection["state_revision"],
            idempotency_key="w37-backup-control-01",
            owner_id="owner-1", store_id="store-a",
        )
        assert event["error"] is False, event

        expected_experiment = repo.get_price_experiment(
            experiment["experiment_id"], owner_id="owner-1", store_id="store-a",
        )
        expected_phases = repo.list_price_experiment_phases(
            experiment["experiment_id"], owner_id="owner-1", store_id="store-a",
        )
        expected_collections = repo.list_price_experiment_phase_collections(
            experiment["experiment_id"], phase["phase_id"],
            owner_id="owner-1", store_id="store-a",
        )
        expected_results = repo.list_price_experiment_results(
            experiment["experiment_id"], phase["phase_id"],
            owner_id="owner-1", store_id="store-a",
        )
        expected_events = repo.list_price_experiment_events(
            experiment["experiment_id"], owner_id="owner-1", store_id="store-a",
        )
        expected_cost = repo.get_unit_economics_expense_snapshot(
            cost_snapshot["snapshot_id"],
        )
        assert expected_experiment["error"] is False
        assert expected_phases["error"] is False
        assert expected_collections["error"] is False
        assert expected_results["error"] is False
        assert expected_events["error"] is False
        assert expected_cost["error"] is False
    finally:
        reset_current_tenant_user_id(token)

    backup_service = BotBackupService(
        project_root=project, storage_root=source_storage,
        backup_directory=project / ".local-backups",
        lifecycle_token="w37-synthetic-backup-token",
        lifecycle_inspector=lambda _token: {"state": "STOPPED"},
        revision_reader=lambda _root: "w37-synthetic-revision",
    )
    backup = backup_service.backup()
    assert backup["error"] is False, backup
    assert backup_service.verify_archive(backup["backup_path"])["error"] is False

    target = tmp_path / "restored-experiment-root"
    restored = backup_service.restore_archive(backup["backup_path"], target)
    assert restored["error"] is False, restored
    monkeypatch.setenv("AI_ASSISTANT_STORAGE_ROOT", str(target / "storage"))

    token = _context()
    try:
        reopened = PlanningWorkspaceRepository(
            clock=lambda: datetime(2026, 11, 6, 12, tzinfo=timezone.utc),
        )
        restored_database_path = reopened.db_path
        initialized = reopened.get_connection()
        schema_version = initialized.execute(
            "SELECT version FROM planning_schema",
        ).fetchone()[0]
        initialized.close()
        assert schema_version == reopened.DATABASE_SCHEMA_VERSION
        experiment_id = experiment["experiment_id"]
        phase_id = phase["phase_id"]
        assert reopened.get_document(saved_plan["document_id"])["error"] is False
        restored_cost = reopened.get_unit_economics_expense_snapshot(
            cost_snapshot["snapshot_id"],
        )
        assert restored_cost == expected_cost
        restored_tariff = reopened.get_tariff_profile(tariff["profile_id"])
        assert restored_tariff["error"] is False
        assert restored_tariff["profile"]["bands"] == tariff_payload["bands"]
        assert reopened.get_price_experiment(
            experiment_id, owner_id="owner-1", store_id="store-a",
        ) == expected_experiment
        assert reopened.list_price_experiment_phases(
            experiment_id, owner_id="owner-1", store_id="store-a",
        ) == expected_phases
        assert reopened.list_price_experiment_phase_collections(
            experiment_id, phase_id, owner_id="owner-1", store_id="store-a",
        ) == expected_collections
        assert reopened.list_price_experiment_results(
            experiment_id, phase_id, owner_id="owner-1", store_id="store-a",
        ) == expected_results
        assert reopened.list_price_experiment_events(
            experiment_id, owner_id="owner-1", store_id="store-a",
        ) == expected_events
    finally:
        reset_current_tenant_user_id(token)

    token = _context("owner-1", "store-b")
    try:
        other_store = PlanningWorkspaceRepository()
        assert other_store.get_document(saved_plan["document_id"])["error"] is True
        assert other_store.get_unit_economics_expense_snapshot(
            cost_snapshot["snapshot_id"],
        )["error"] is True
        assert other_store.get_tariff_profile(tariff["profile_id"])["error"] is True
        assert other_store.get_price_experiment(
            experiment["experiment_id"], owner_id="owner-1", store_id="store-b",
        )["error"] is True
    finally:
        reset_current_tenant_user_id(token)

    # Corrupt/future child payloads in the restored synthetic DB fail closed.
    connection = sqlite3.connect(restored_database_path)
    try:
        connection.execute("DROP TRIGGER IF EXISTS trg_price_experiments_immutable_config")
        connection.execute(
            "DROP TRIGGER IF EXISTS trg_price_experiment_phases_immutable_config",
        )
        connection.execute(
            "UPDATE planning_price_experiments SET config_json=? WHERE experiment_id=?",
            ('{"schema_version":99}', experiment["experiment_id"]),
        )
        connection.execute(
            "UPDATE planning_price_experiment_phases SET payload_json=? WHERE phase_id=?",
            ('{"schema_version":99}', phase["phase_id"]),
        )
        connection.commit()
    finally:
        connection.close()
    token = _context()
    try:
        assert reopened.get_price_experiment(
            experiment["experiment_id"], owner_id="owner-1", store_id="store-a",
        )["code"] == "PLANNING_PRICE_EXPERIMENT_CORRUPT"
        assert reopened.list_price_experiment_phases(
            experiment["experiment_id"], owner_id="owner-1", store_id="store-a",
        )["code"] == "PLANNING_PRICE_EXPERIMENT_PHASE_CORRUPT"
    finally:
        reset_current_tenant_user_id(token)

