import hashlib
import json
import sqlite3

from services.planning_unit_economics_experiment_adapter import (
    PlanningUnitEconomicsExperimentAdapter,
)
from services.planning_workspace_repository import PlanningWorkspaceRepository
from services.tenant_context import reset_current_tenant_user_id
from test_planning_workspace_unit_economics import (
    _context,
    _identity,
    _phase_payload,
    _result_payload,
    _seed,
)
from test_unit_economics_experiment_phase_comparison_service import _evaluate


def _candidate_review_repository(repo):
    saved, snapshot, experiment = _seed(repo)
    baseline = repo.create_price_experiment_phase(
        experiment["experiment_id"], _phase_payload(snapshot["snapshot_id"]),
        expected_state_revision=1, idempotency_key="w29-baseline-phase01",
    )
    assert baseline["error"] is False
    candidate_id = "b" * 32
    candidate_payload = _phase_payload(
        snapshot["snapshot_id"], kind="CANDIDATE", segment=2, price=9900,
    )
    candidate = PlanningUnitEconomicsExperimentAdapter.normalize_phase(
        candidate_payload, _identity(),
    )
    encoded_candidate = repo._encode(candidate)
    connection = repo.get_connection()
    try:
        connection.execute("BEGIN IMMEDIATE")
        experiment_row = connection.execute(
            "SELECT * FROM planning_price_experiments WHERE experiment_id=?",
            (experiment["experiment_id"],),
        ).fetchone()
        connection.execute(
            """INSERT INTO planning_price_experiment_phases
               (phase_id, experiment_id, owner_id, store_id, product_id, offer_id,
                sku, sale_schema, segment_number, kind, status, state_revision,
                result_revision, expense_snapshot_id, payload_json, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 2, 'CANDIDATE', 'FINISHED', 1, 0, ?, ?, ?, ?)""",
            (candidate_id, experiment["experiment_id"], "owner-1", "store-a",
             "product-1", "offer-1", "sku-1", "FBO", snapshot["snapshot_id"],
             encoded_candidate, "2026-10-29T12:00:00Z", "2026-10-29T12:00:00Z"),
        )
        phase_revision = {
            "schema_version": 1, "phase_id": candidate_id,
            "experiment_id": experiment["experiment_id"], "state": "FINISHED",
            "state_revision": 1, "result_revision": 0, "phase": candidate,
        }
        connection.execute(
            """INSERT INTO planning_price_experiment_phase_revisions
               (phase_id, experiment_id, owner_id, store_id, revision, state_revision,
                result_revision, payload_json, created_at)
               VALUES (?, ?, ?, ?, 1, 1, 0, ?, ?)""",
            (candidate_id, experiment["experiment_id"], "owner-1", "store-a",
             repo._encode(phase_revision), "2026-10-29T12:00:00Z"),
        )
        connection.execute(
            "UPDATE planning_price_experiments SET status='CANDIDATE_REVIEW', "
            "state_revision=3 WHERE experiment_id=? AND owner_id='owner-1' AND store_id='store-a'",
            (experiment["experiment_id"],),
        )
        repo._insert_price_experiment_revision(
            connection, experiment["experiment_id"],
            {"owner_id": "owner-1", "store_id": "store-a"}, 3, 3,
            "CANDIDATE_REVIEW", json.loads(experiment_row["config_json"]),
            "2026-10-29T12:00:00Z",
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
    result = repo.append_price_experiment_result(
        experiment["experiment_id"], candidate_id,
        _result_payload(snapshot["snapshot_id"]), expected_state_revision=3,
        expected_phase_state_revision=1, expected_result_revision=0,
        idempotency_key="w29-candidate-result01",
    )
    assert result["error"] is False
    return experiment, snapshot, baseline["phase_id"], candidate_id, result


def _append_valid_comparison(repo, experiment, snapshot, baseline_id, candidate_id):
    baseline_collection, candidate_collection = "1" * 64, "2" * 64
    connection = repo.get_connection()
    payload_json = "{}"
    digest = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
    try:
        for phase_id, collection_id in (
            (baseline_id, baseline_collection), (candidate_id, candidate_collection),
        ):
            connection.execute(
                """INSERT INTO planning_price_experiment_phase_collections
                   (experiment_id, phase_id, owner_id, store_id, collection_revision,
                    collection_id, payload_json, content_hash, created_at)
                   VALUES (?, ?, 'owner-1', 'store-a', 1, ?, ?, ?, ?)""",
                (experiment["experiment_id"], phase_id, collection_id, payload_json,
                 digest, "2026-10-29T12:00:00Z"),
            )
        connection.commit()
    finally:
        connection.close()
    evaluated = _evaluate()
    comparison = dict(evaluated["comparison"])
    comparison.update({
        "baseline_collection_hash": baseline_collection,
        "candidate_collection_hash": candidate_collection,
    })
    payload = {
        "schema_version": 2, "status": evaluated["status"],
        "source_as_of": evaluated["source_as_of"],
        "snapshot_refs": sorted({snapshot["snapshot_id"], baseline_collection,
                                  candidate_collection}),
        "baseline_profit_per_unit_rub": evaluated["baseline_profit_per_unit_rub"],
        "candidate_profit_per_unit_rub": evaluated["candidate_profit_per_unit_rub"],
        "delta_profit_per_unit_rub": evaluated["delta_profit_per_unit_rub"],
        "quantity_basis": evaluated["quantity_basis"],
        "window": comparison["candidate"]["window"],
        "quality_gates": evaluated["quality_gates"],
        "limitations": evaluated["limitations"],
        "outcome": evaluated["outcome"], "comparison": comparison,
    }
    return repo.append_price_experiment_result(
        experiment["experiment_id"], candidate_id, payload,
        expected_state_revision=3, expected_phase_state_revision=1,
        expected_result_revision=1, idempotency_key="w29-v2-result01",
    )


def test_owner_decision_is_append_only_idempotent_and_completes_without_price_mutation(tmp_path):
    repo = PlanningWorkspaceRepository(db_path=tmp_path / "planning.sqlite")
    token = _context()
    try:
        experiment, _, baseline_id, candidate_id, result = _candidate_review_repository(repo)
        payload = {
            "schema_version": 1, "decision_type": "STOP_WITHOUT_PRICE_CHANGE",
            "result_phase_id": candidate_id, "result_revision": result["result_revision"],
            "selected_phase_id": None,
        }
        saved = repo.record_price_experiment_owner_decision(
            experiment["experiment_id"], payload, expected_state_revision=3,
            idempotency_key="w29-owner-decision01",
        )
        replay = repo.record_price_experiment_owner_decision(
            experiment["experiment_id"], payload, expected_state_revision=3,
            idempotency_key="w29-owner-decision01",
        )
        assert saved["error"] is False
        assert replay == saved
        listed = repo.list_price_experiment_owner_decisions(experiment["experiment_id"])
        assert listed["items"][0]["payload"] == payload
        assert listed["items"][0]["decision_revision"] == 1
        assert repo.list_price_experiment_owner_decisions(
            experiment["experiment_id"], owner_id="owner-1", store_id="store-other",
        )["code"] == "PLANNING_PRICE_EXPERIMENT_DECISION_INPUT_INVALID"

        completed = repo.transition_price_experiment(
            experiment["experiment_id"], "complete", expected_state_revision=3,
            idempotency_key="w29-complete-experiment01",
        )
        assert completed["error"] is False
        assert completed["status"] == "COMPLETED"
        assert repo.get_price_experiment(experiment["experiment_id"])["experiment"][
            "status"
        ] == "COMPLETED"
        phases = repo.list_price_experiment_phases(experiment["experiment_id"])
        assert next(item for item in phases["items"] if item["kind"] == "CANDIDATE")[
            "config"]["planned_price_cents"] == 9900
    finally:
        reset_current_tenant_user_id(token)


def test_decision_requires_latest_candidate_result_and_valid_selection(tmp_path):
    repo = PlanningWorkspaceRepository(db_path=tmp_path / "planning.sqlite")
    token = _context()
    try:
        experiment, snapshot, baseline_id, candidate_id, result = _candidate_review_repository(repo)
        stale = {
            "schema_version": 1, "decision_type": "STOP_WITHOUT_PRICE_CHANGE",
            "result_phase_id": candidate_id, "result_revision": 1,
            "selected_phase_id": None,
        }
        newer = _result_payload(snapshot["snapshot_id"], baseline="10.00", candidate="9.00",
                                delta="-1.00")
        appended = repo.append_price_experiment_result(
            experiment["experiment_id"], candidate_id, newer,
            expected_state_revision=3, expected_phase_state_revision=1,
            expected_result_revision=1, idempotency_key="w29-candidate-result02",
        )
        assert appended["error"] is False
        assert repo.record_price_experiment_owner_decision(
            experiment["experiment_id"], stale, expected_state_revision=3,
            idempotency_key="w29-stale-decision01",
        )["code"] == "PLANNING_PRICE_EXPERIMENT_DECISION_RESULT_STALE"

        invalid_selection = {
            "schema_version": 1, "decision_type": "SELECT_EVALUATED_CANDIDATE",
            "result_phase_id": candidate_id, "result_revision": 2,
            "selected_phase_id": candidate_id,
        }
        assert repo.record_price_experiment_owner_decision(
            experiment["experiment_id"], invalid_selection, expected_state_revision=3,
            idempotency_key="w29-invalid-selection01",
        )["code"] == "PLANNING_PRICE_EXPERIMENT_DECISION_SELECTION_INVALID"

        fresh_experiment, fresh_snapshot, fresh_baseline, fresh_candidate, _ = (
            _candidate_review_repository(PlanningWorkspaceRepository(
                db_path=tmp_path / "candidate-selection.sqlite",
            ))
        )
        candidate_result = _append_valid_comparison(
            PlanningWorkspaceRepository(db_path=tmp_path / "candidate-selection.sqlite"),
            fresh_experiment, fresh_snapshot, fresh_baseline, fresh_candidate,
        )
        assert candidate_result["error"] is False
        selected = PlanningWorkspaceRepository(
            db_path=tmp_path / "candidate-selection.sqlite",
        ).record_price_experiment_owner_decision(
            fresh_experiment["experiment_id"], {
                "schema_version": 1, "decision_type": "SELECT_EVALUATED_CANDIDATE",
                "result_phase_id": fresh_candidate, "result_revision": 2,
                "selected_phase_id": fresh_candidate,
            }, expected_state_revision=3, idempotency_key="w29-selected-candidate01",
        )
        assert selected["error"] is False

        baseline_choice = {
            "schema_version": 1, "decision_type": "KEEP_BASELINE_PRICE",
            "result_phase_id": candidate_id, "result_revision": 2,
            "selected_phase_id": baseline_id,
        }
        accepted = repo.record_price_experiment_owner_decision(
            experiment["experiment_id"], baseline_choice, expected_state_revision=3,
            idempotency_key="w29-baseline-decision01",
        )
        assert accepted["error"] is False
    finally:
        reset_current_tenant_user_id(token)


def test_continue_decision_does_not_allow_completion_and_decision_history_is_immutable(tmp_path):
    repo = PlanningWorkspaceRepository(db_path=tmp_path / "planning.sqlite")
    token = _context()
    try:
        experiment, _, _, candidate_id, result = _candidate_review_repository(repo)
        payload = {
            "schema_version": 1, "decision_type": "CONTINUE_TEST",
            "result_phase_id": candidate_id, "result_revision": result["result_revision"],
            "selected_phase_id": None,
        }
        decision = repo.record_price_experiment_owner_decision(
            experiment["experiment_id"], payload, expected_state_revision=3,
            idempotency_key="w29-continue01",
        )
        assert decision["error"] is False
        blocked = repo.transition_price_experiment(
            experiment["experiment_id"], "complete", expected_state_revision=3,
            idempotency_key="w29-continue-complete01",
        )
        assert blocked["code"] == "PLANNING_PRICE_EXPERIMENT_TRANSITION_NOT_ALLOWED"

        connection = repo.get_connection()
        try:
            try:
                connection.execute(
                    "UPDATE planning_price_experiment_decisions SET decision_type='KEEP_BASELINE_PRICE'",
                )
            except sqlite3.IntegrityError:
                pass
            else:
                raise AssertionError("decision history update was not blocked")
            try:
                connection.execute("DELETE FROM planning_price_experiment_decisions")
            except sqlite3.IntegrityError:
                pass
            else:
                raise AssertionError("decision history deletion was not blocked")
        finally:
            connection.close()
    finally:
        reset_current_tenant_user_id(token)


def test_schema_v11_to_v12_adds_decision_table_and_preserves_existing_plan(tmp_path):
    path = tmp_path / "planning.sqlite"
    repo = PlanningWorkspaceRepository(db_path=path)
    token = _context()
    try:
        saved, _, experiment = _seed(repo)
        assert saved["error"] is False
    finally:
        reset_current_tenant_user_id(token)
    connection = sqlite3.connect(path)
    try:
        connection.execute("DROP TRIGGER IF EXISTS trg_price_experiment_decisions_no_update")
        connection.execute("DROP TRIGGER IF EXISTS trg_price_experiment_decisions_no_delete")
        connection.execute("DROP TABLE planning_price_experiment_decisions")
        connection.execute("UPDATE planning_schema SET version=11")
        connection.commit()
    finally:
        connection.close()
    migrated = PlanningWorkspaceRepository(db_path=path)
    connection = migrated.get_connection()
    try:
        assert connection.execute("SELECT version FROM planning_schema").fetchone()[0] == 12
        assert connection.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' "
            "AND name='planning_price_experiment_decisions'",
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM planning_price_experiments WHERE experiment_id=?",
            (experiment["experiment_id"],),
        ).fetchone()[0] == 1
    finally:
        connection.close()


def test_owner_decision_adapter_is_strict_and_bounded():
    payload = {
        "schema_version": 1, "decision_type": "CONTINUE_TEST",
        "result_phase_id": "a" * 32, "result_revision": 1, "selected_phase_id": None,
    }
    assert PlanningUnitEconomicsExperimentAdapter.normalize_owner_decision(payload) == payload
    assert PlanningUnitEconomicsExperimentAdapter.normalize_owner_decision({
        **payload, "decision_type": "EXECUTE_OZON_PRICE_CHANGE",
    }) is None
    assert PlanningUnitEconomicsExperimentAdapter.normalize_owner_decision({
        **payload, "selected_phase_id": "b" * 32,
    }) is None
    assert PlanningUnitEconomicsExperimentAdapter.normalize_owner_decision({
        **payload, "result_revision": True,
    }) is None


def test_owner_decision_quota_failure_does_not_write(tmp_path, monkeypatch):
    repo = PlanningWorkspaceRepository(db_path=tmp_path / "planning.sqlite")
    token = _context()
    try:
        experiment, _, _, candidate_id, result = _candidate_review_repository(repo)
        monkeypatch.setattr(PlanningWorkspaceRepository, "MAX_PRICE_EXPERIMENT_DECISIONS", 0)
        payload = {
            "schema_version": 1, "decision_type": "STOP_WITHOUT_PRICE_CHANGE",
            "result_phase_id": candidate_id, "result_revision": result["result_revision"],
            "selected_phase_id": None,
        }
        response = repo.record_price_experiment_owner_decision(
            experiment["experiment_id"], payload, expected_state_revision=3,
            idempotency_key="w29-quota-decision01",
        )
        assert response["code"] == "PLANNING_PRICE_EXPERIMENT_DECISION_QUOTA_REACHED"
        assert repo.list_price_experiment_owner_decisions(
            experiment["experiment_id"],
        )["items"] == []
    finally:
        reset_current_tenant_user_id(token)
