import sqlite3
from datetime import datetime, timezone

import pytest

from services.ozon_account_repository import make_store_tenant_scope
from services.planning_workspace_repository import PlanningWorkspaceRepository
from services.tenant_context import reset_current_tenant_user_id, set_current_tenant_user_id


IDENTITY = {
    "product_id": "product-1", "offer_id": "offer-1", "sku": "sku-1",
    "sale_schema": "FBO",
}


def _payload(store_id="store-a", sku="sku-1"):
    return {
        "plan_kind": "single", "schema_version": 1, "calculation_version": 1,
        "target_margin_percent": "25.00", "items": [{
            "identity": {
                "product_id": "product-1", "offer_id": "offer-1", "sku": sku,
                "product_name": "Synthetic", "store_id": store_id, "scheme": "FBO",
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
                           "invalid_inputs": [], "revenue": "100.00", "profit": "60.00"},
        }],
    }


def _context(owner="owner-1", store="store-a"):
    return set_current_tenant_user_id(make_store_tenant_scope(owner, store))


def _repo(tmp_path):
    return PlanningWorkspaceRepository(
        db_path=tmp_path / "planning.sqlite",
        clock=lambda: datetime(2026, 10, 27, 10, 0, tzinfo=timezone.utc),
    )


def _plan(repo):
    return repo.save_document(
        title="Synthetic plan", payload=_payload(), idempotency_key="obs-plan-create01",
    )


def _start(repo, plan, **overrides):
    request = {
        "identity": dict(IDENTITY), "seller_price_cents": 10_000,
        "source_document_id": plan["document_id"], "source_document_revision": 1,
        "effective_from": "2026-10-27T09:30:00Z", "window_timezone": "Europe/Moscow",
        "owner_confirmed": True, "idempotency_key": "obs-start-key-0001",
        "note": "campaign A",
    }
    request.update(overrides)
    return repo.start_unit_price_observation(**request)


def _result(**overrides):
    payload = {
        "schema_version": 1,
        "identity": {
            "store_id": "store-a", "product_id": "product-1",
            "offer_id": "offer-1", "sku": "sku-1", "sale_schema": "FBO",
        },
        "seller_price_cents": 10_000,
        "status": "INSUFFICIENT_DATA",
        "evidence_basis": "MODELLED_FROM_OBSERVED_INPUTS",
        "window": {
            "from": "2026-10-19", "to": "2026-10-25",
            "timezone": "Europe/Moscow", "date_basis": "LOCAL_CALENDAR_DATE",
        },
        "sources": [{"name": "finance", "status": "PARTIAL", "complete": False,
                     "row_count": 12, "as_of": "2026-10-27T09:00:00Z"}],
        "metrics": {"cpc_spend": "120.00", "successful_sale_units": None},
        "completeness": {"price_history": "PRICE_HISTORY_UNCONFIRMED"},
        "reasons": ["PRICE_HISTORY_UNCONFIRMED"],
        "warnings": [],
    }
    payload.update(overrides)
    return payload


def test_observation_is_durable_tenant_scoped_and_idempotent(tmp_path):
    repo = _repo(tmp_path)
    token = _context()
    try:
        plan = _plan(repo)
        effective_from = "2026-10-27T12:30:00+03:00"
        created = _start(repo, plan, effective_from=effective_from)
        replay = _start(repo, plan, effective_from=effective_from)
        assert created["error"] is False
        assert replay == created
        conflicting_replay = _start(
            repo, plan, seller_price_cents=9_500, effective_from=effective_from,
        )
        assert conflicting_replay["code"] == "PLANNING_OBSERVATION_IDEMPOTENCY_CONFLICT"
    finally:
        reset_current_tenant_user_id(token)

    reopened = PlanningWorkspaceRepository(db_path=repo.db_path)
    token = _context("owner-1", "store-b")
    try:
        assert reopened.get_unit_price_observation(created["observation_id"])["code"] == "PLANNING_OBSERVATION_NOT_FOUND"
        assert reopened.list_unit_price_observations()["items"] == []
    finally:
        reset_current_tenant_user_id(token)

    token = _context()
    try:
        value = reopened.get_unit_price_observation(created["observation_id"])
        observation = value["observation"]
        assert value["error"] is False
        assert observation["seller_price_cents"] == 10_000
        assert observation["price_evidence_kind"] == "OWNER_DECLARED_PRICE_CHANGE"
        assert observation["effective_from"] == "2026-10-27T12:30:00+03:00"
        assert observation["recorded_at"] == observation["started_at"]
        assert observation["price_evidence_source"] == "USER"
        assert observation["source_plan"] == {"document_id": plan["document_id"], "revision": 1}
        assert observation["state_revision"] == 1
        assert observation["result_revision"] == 0
    finally:
        reset_current_tenant_user_id(token)


def test_active_sku_guard_cas_note_finish_and_archive(tmp_path):
    repo = _repo(tmp_path)
    token = _context()
    try:
        plan = _plan(repo)
        first = _start(repo, plan)
        second = _start(repo, plan, idempotency_key="obs-start-key-0002")
        assert second["code"] == "PLANNING_OBSERVATION_ALREADY_ACTIVE"

        noted = repo.set_unit_price_observation_note(
            first["observation_id"], "  CPC   promotion  ",
            expected_state_revision=1, idempotency_key="obs-note-key-00001",
        )
        assert noted["state_revision"] == 2
        stale = repo.finish_unit_price_observation(
            first["observation_id"], expected_state_revision=1,
            idempotency_key="obs-stale-finish01",
        )
        assert stale["code"] == "PLANNING_OBSERVATION_STATE_CONFLICT"

        finished = repo.finish_unit_price_observation(
            first["observation_id"], expected_state_revision=2,
            idempotency_key="obs-finish-key-001",
        )
        assert finished["status"] == "FINISHED"
        assert finished["state_revision"] == 3
        archived = repo.archive_unit_price_observation(
            first["observation_id"], expected_state_revision=3,
            idempotency_key="obs-archive-key-01",
        )
        assert archived["status"] == "ARCHIVED"
        assert repo.get_unit_price_observation(first["observation_id"])["observation"]["note"] == "CPC promotion"
        next_observation = _start(repo, plan, idempotency_key="obs-start-key-0003")
        assert next_observation["error"] is False
    finally:
        reset_current_tenant_user_id(token)


def test_observation_requires_exact_saved_plan_identity_and_owner_confirmation(tmp_path):
    repo = _repo(tmp_path)
    token = _context()
    try:
        plan = _plan(repo)
        assert _start(repo, plan, owner_confirmed=False)["code"] == "PLANNING_OBSERVATION_INPUT_INVALID"
        assert _start(repo, plan, effective_from="2026-10-27T11:00:00Z")["code"] == "PLANNING_OBSERVATION_EFFECTIVE_TIME_FUTURE"
        assert _start(repo, plan, effective_from="2026-10-27T09:00:00")["code"] == "PLANNING_OBSERVATION_INPUT_INVALID"
        assert _start(repo, plan, window_timezone="Unknown/Zone")["code"] == "PLANNING_OBSERVATION_INPUT_INVALID"
        wrong_identity = dict(IDENTITY, sku="other-sku")
        assert _start(repo, plan, identity=wrong_identity)["code"] == "PLANNING_OBSERVATION_SOURCE_PLAN_SCOPE_MISMATCH"
        assert _start(repo, plan, source_document_revision=2)["code"] == "PLANNING_OBSERVATION_SOURCE_PLAN_NOT_FOUND"
        assert _start(repo, plan, seller_price_cents=True)["code"] == "PLANNING_OBSERVATION_INPUT_INVALID"
    finally:
        reset_current_tenant_user_id(token)


def test_observation_quota_is_bounded_per_store(tmp_path, monkeypatch):
    repo = _repo(tmp_path)
    token = _context()
    try:
        monkeypatch.setattr(repo, "MAX_UNIT_PRICE_OBSERVATIONS_PER_STORE", 1)
        plan = _plan(repo)
        assert _start(repo, plan)["error"] is False
        over_quota = _start(repo, plan, idempotency_key="obs-start-overquota1")
        assert over_quota["code"] == "PLANNING_OBSERVATION_QUOTA_REACHED"
        assert len(repo.list_unit_price_observations()["items"]) == 1
    finally:
        reset_current_tenant_user_id(token)


def test_result_versions_are_immutable_versioned_and_idempotent(tmp_path):
    repo = _repo(tmp_path)
    token = _context()
    try:
        plan = _plan(repo)
        observation = _start(repo, plan)
        first = repo.append_unit_price_observation_result(
            observation["observation_id"], _result(), expected_state_revision=1,
            expected_result_revision=0, idempotency_key="obs-result-key-0001",
        )
        assert first == repo.append_unit_price_observation_result(
            observation["observation_id"], _result(), expected_state_revision=1,
            expected_result_revision=0, idempotency_key="obs-result-key-0001",
        )
        assert first["result_revision"] == 1
        mismatched = repo.append_unit_price_observation_result(
            observation["observation_id"], _result(identity=dict(
                _result()["identity"], sku="sku-other",
            )), expected_state_revision=1, expected_result_revision=1,
            idempotency_key="obs-result-wrong-sku1",
        )
        assert mismatched["code"] == "PLANNING_OBSERVATION_RESULT_IDENTITY_MISMATCH"
        second_payload = _result(status="SOURCE_UNAVAILABLE")
        second = repo.append_unit_price_observation_result(
            observation["observation_id"], second_payload, expected_state_revision=1,
            expected_result_revision=1, idempotency_key="obs-result-key-0002",
        )
        assert second["result_revision"] == 2
        assert repo.get_unit_price_observation(
            observation["observation_id"], result_revision=1,
        )["result"]["payload"]["status"] == "INSUFFICIENT_DATA"
        assert repo.get_unit_price_observation(
            observation["observation_id"], result_revision=2,
        )["result"]["payload"]["status"] == "SOURCE_UNAVAILABLE"
        history = repo.list_unit_price_observation_results(observation["observation_id"])
        assert [item["revision"] for item in history["items"]] == [2, 1]
        assert repo.append_unit_price_observation_result(
            observation["observation_id"], _result(), expected_state_revision=1,
            expected_result_revision=1, idempotency_key="obs-stale-result01",
        )["code"] == "PLANNING_OBSERVATION_RESULT_CONFLICT"
    finally:
        reset_current_tenant_user_id(token)


def test_result_source_preserves_unknown_api_field_names_and_types_without_values(tmp_path):
    repo = _repo(tmp_path)
    token = _context()
    try:
        plan = _plan(repo)
        observation = _start(repo, plan)
        payload = _result(sources=[{
            "name": "FINANCE",
            "status": "PARTIAL",
            "complete": False,
            "unknown_field_count": 1,
            "unknown_fields": [{"name": "new_flag", "type": "bool"}],
            "unsupported_types": ["type_id:777"],
        }])
        stored = repo.append_unit_price_observation_result(
            observation["observation_id"], payload,
            expected_state_revision=1, expected_result_revision=0,
            idempotency_key="obs-schema-evidence-01",
        )
        assert stored["error"] is False
        readback = repo.get_unit_price_observation(observation["observation_id"])
        source = readback["result"]["payload"]["sources"][0]
        assert source["unknown_fields"] == [{"name": "new_flag", "type": "bool"}]
        assert source["unsupported_types"] == ["type_id:777"]
        assert "value" not in source["unknown_fields"][0]

        payload["sources"][0]["unknown_fields"] = [{
            "name": "new_flag", "type": "bool", "value": "must-not-be-stored",
        }]
        invalid = repo.append_unit_price_observation_result(
            observation["observation_id"], payload,
            expected_state_revision=1, expected_result_revision=1,
            idempotency_key="obs-schema-evidence-02",
        )
        assert invalid["code"] == "PLANNING_OBSERVATION_RESULT_INVALID"
    finally:
        reset_current_tenant_user_id(token)


def test_results_allow_correction_versions_after_finish_but_not_archive(tmp_path):
    repo = _repo(tmp_path)
    token = _context()
    try:
        plan = _plan(repo)
        observation = _start(repo, plan)
        finished = repo.finish_unit_price_observation(
            observation["observation_id"], expected_state_revision=1,
            idempotency_key="obs-finish-first01",
        )
        result = repo.append_unit_price_observation_result(
            observation["observation_id"], _result(), expected_state_revision=2,
            expected_result_revision=0, idempotency_key="obs-result-finished1",
        )
        assert result["error"] is False
        archived = repo.archive_unit_price_observation(
            observation["observation_id"], expected_state_revision=2,
            idempotency_key="obs-archive-finished1",
        )
        assert archived["error"] is False
        blocked = repo.append_unit_price_observation_result(
            observation["observation_id"], _result(), expected_state_revision=2,
            expected_result_revision=1, idempotency_key="obs-result-archived1",
        )
        assert blocked["code"] == "PLANNING_OBSERVATION_ARCHIVED"
    finally:
        reset_current_tenant_user_id(token)


def test_result_validation_rejects_unknown_version_secrets_floats_and_large_window(tmp_path):
    repo = _repo(tmp_path)
    token = _context()
    try:
        plan = _plan(repo)
        observation = _start(repo, plan)
        invalid_payloads = [
            _result(schema_version=2),
            _result(metrics={"api_key": "synthetic-secret"}),
            _result(metrics={"cpc_spend": 1.25}),
            _result(status=[]),
            _result(evidence_basis=[]),
            _result(window={"from": "2026-08-01", "to": "2026-08-02",
                            "timezone": "Europe/Moscow", "date_basis": []}),
            _result(metrics={"raw_posting_number": "sensitive"}),
            _result(window={"from": "2026-08-01", "to": "2026-10-27",
                            "timezone": "Europe/Moscow", "date_basis": "LOCAL_CALENDAR_DATE"}),
        ]
        for index, payload in enumerate(invalid_payloads):
            result = repo.append_unit_price_observation_result(
                observation["observation_id"], payload, expected_state_revision=1,
                expected_result_revision=0,
                idempotency_key=f"obs-result-invalid{index:02d}",
            )
            assert result["code"] == "PLANNING_OBSERVATION_RESULT_INVALID"
        assert repo.get_unit_price_observation(observation["observation_id"])["observation"]["result_revision"] == 0
    finally:
        reset_current_tenant_user_id(token)


def test_overlapping_completed_windows_are_retained_separately_as_incomparable(tmp_path):
    repo = _repo(tmp_path)
    token = _context()
    try:
        plan = _plan(repo)
        first_observation = _start(repo, plan)
        first_result = repo.append_unit_price_observation_result(
            first_observation["observation_id"], _result(status="INCOMPARABLE"),
            expected_state_revision=1, expected_result_revision=0,
            idempotency_key="obs-overlap-result1",
        )
        assert first_result["error"] is False
        finished = repo.finish_unit_price_observation(
            first_observation["observation_id"], expected_state_revision=1,
            idempotency_key="obs-overlap-finish1",
        )
        assert finished["error"] is False
        second_observation = _start(
            repo, plan, idempotency_key="obs-overlap-start02",
        )
        second_result = repo.append_unit_price_observation_result(
            second_observation["observation_id"], _result(status="INCOMPARABLE"),
            expected_state_revision=1, expected_result_revision=0,
            idempotency_key="obs-overlap-result2",
        )
        assert second_result["error"] is False
        assert repo.get_unit_price_observation(
            first_observation["observation_id"],
        )["result"]["payload"]["window"] == _result()["window"]
        assert repo.get_unit_price_observation(
            second_observation["observation_id"],
        )["result"]["payload"]["window"] == _result()["window"]
    finally:
        reset_current_tenant_user_id(token)


def test_result_history_is_database_immutable_and_future_corruption_fails_closed(tmp_path):
    repo = _repo(tmp_path)
    token = _context()
    try:
        plan = _plan(repo)
        observation = _start(repo, plan)
        repo.append_unit_price_observation_result(
            observation["observation_id"], _result(), expected_state_revision=1,
            expected_result_revision=0, idempotency_key="obs-immutable-result1",
        )
        connection = sqlite3.connect(repo.db_path)
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "UPDATE planning_unit_price_observation_results SET payload_json='{}'"
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("DELETE FROM planning_unit_price_observation_results")
        connection.execute("DROP TRIGGER trg_unit_price_observation_results_no_update")
        connection.execute("DROP TRIGGER trg_unit_price_observation_results_no_delete")
        tampered = _result(identity=dict(_result()["identity"], sku="sku-other"))
        connection.execute(
            "UPDATE planning_unit_price_observation_results SET payload_json=?",
            (repo._encode(tampered),),
        )
        connection.commit()
        connection.close()
        assert repo.get_unit_price_observation(
            observation["observation_id"],
        )["code"] == "PLANNING_OBSERVATION_RESULT_IDENTITY_MISMATCH"
    finally:
        reset_current_tenant_user_id(token)

    assert PlanningWorkspaceRepository._decode_observation_result(
        '{"schema_version":2}'
    )["code"] == "PLANNING_OBSERVATION_RESULT_VERSION_UNSUPPORTED"
    assert PlanningWorkspaceRepository._decode_observation_result(
        "not-json"
    )["code"] == "PLANNING_OBSERVATION_RESULT_CORRUPT"


def test_result_quota_and_database_rollback_are_atomic(tmp_path, monkeypatch):
    repo = _repo(tmp_path)
    token = _context()
    try:
        plan = _plan(repo)
        observation = _start(repo, plan)
        connection = sqlite3.connect(repo.db_path)
        connection.execute("""CREATE TRIGGER abort_observation_result BEFORE INSERT ON
            planning_unit_price_observation_results BEGIN SELECT RAISE(ABORT, 'synthetic rollback'); END""")
        connection.commit()
        connection.close()
        failed = repo.append_unit_price_observation_result(
            observation["observation_id"], _result(), expected_state_revision=1,
            expected_result_revision=0, idempotency_key="obs-result-rollback1",
        )
        assert failed["code"] == "PLANNING_STORAGE_UNAVAILABLE"
        snapshot = repo.get_unit_price_observation(observation["observation_id"])
        assert snapshot["observation"]["result_revision"] == 0
        connection = sqlite3.connect(repo.db_path)
        assert connection.execute(
            "SELECT COUNT(*) FROM planning_unit_price_observation_idempotency "
            "WHERE idempotency_key='obs-result-rollback1'"
        ).fetchone()[0] == 0
        connection.close()

        connection = sqlite3.connect(repo.db_path)
        connection.execute("DROP TRIGGER abort_observation_result")
        connection.commit()
        connection.close()
        monkeypatch.setattr(repo, "MAX_UNIT_PRICE_OBSERVATION_RESULTS", 1)
        saved = repo.append_unit_price_observation_result(
            observation["observation_id"], _result(), expected_state_revision=1,
            expected_result_revision=0, idempotency_key="obs-result-quota-01",
        )
        assert saved["error"] is False
        exceeded = repo.append_unit_price_observation_result(
            observation["observation_id"], _result(status="INCOMPARABLE"), expected_state_revision=1,
            expected_result_revision=1, idempotency_key="obs-result-quota-02",
        )
        assert exceeded["code"] == "PLANNING_OBSERVATION_RESULT_QUOTA_REACHED"
    finally:
        reset_current_tenant_user_id(token)


def test_v3_database_migration_adds_observation_and_comparison_tables_preserving_plan(tmp_path):
    db = tmp_path / "v3.sqlite"
    repo = PlanningWorkspaceRepository(
        db_path=db, clock=lambda: datetime(2026, 10, 27, 10, 0, tzinfo=timezone.utc),
    )
    token = _context()
    try:
        plan = _plan(repo)
    finally:
        reset_current_tenant_user_id(token)


    connection = sqlite3.connect(db)
    connection.execute("UPDATE planning_schema SET version=3 WHERE singleton=1")
    connection.execute("DROP TABLE planning_unit_price_observation_results")
    connection.execute("DROP TABLE planning_unit_price_observation_idempotency")
    connection.execute("DROP TABLE planning_unit_price_observations")
    connection.commit()
    connection.close()

    migrated = PlanningWorkspaceRepository(db_path=db)
    connection = migrated.get_connection()
    try:
        version = connection.execute("SELECT version FROM planning_schema").fetchone()[0]
        tables = {row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        triggers = {row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger'"
        )}
    finally:
        connection.close()
    assert version == 6
    assert {
        "planning_unit_price_observations",
        "planning_unit_price_observation_results",
        "planning_unit_price_observation_idempotency",
    } <= tables
    assert {
        "trg_unit_price_observation_results_no_update",
        "trg_unit_price_observation_results_no_delete",
    } <= triggers
    assert {
        "planning_unit_price_comparisons",
        "planning_unit_price_comparison_idempotency",
        "planning_unit_economics_snapshots",
        "planning_price_experiments",
        "planning_price_experiment_revisions",
        "planning_price_experiment_phases",
        "planning_price_experiment_phase_revisions",
        "planning_price_experiment_results",
        "planning_price_experiment_idempotency",
    } <= tables
    assert {
        "trg_unit_price_comparisons_no_update",
        "trg_unit_price_comparisons_no_delete",
    } <= triggers
    token = _context()
    try:
        assert migrated.get_document(plan["document_id"])["error"] is False
    finally:
        reset_current_tenant_user_id(token)


def test_v4_migration_preserves_observation_result_and_adds_comparison_history(tmp_path):
    db = tmp_path / "v4.sqlite"
    repo = PlanningWorkspaceRepository(
        db_path=db, clock=lambda: datetime(2026, 10, 27, 10, 0, tzinfo=timezone.utc),
    )
    token = _context()
    try:
        plan = _plan(repo)
        observation = _start(repo, plan)
        saved_result = repo.append_unit_price_observation_result(
            observation["observation_id"], _result(), expected_state_revision=1,
            expected_result_revision=0, idempotency_key="obs-v4-migration-result",
        )
        assert saved_result["error"] is False
    finally:
        reset_current_tenant_user_id(token)

    connection = sqlite3.connect(db)
    connection.execute("UPDATE planning_schema SET version=4 WHERE singleton=1")
    connection.execute("DROP TRIGGER trg_unit_price_comparisons_no_update")
    connection.execute("DROP TRIGGER trg_unit_price_comparisons_no_delete")
    connection.execute("DROP TABLE planning_unit_price_comparison_idempotency")
    connection.execute("DROP TABLE planning_unit_price_comparisons")
    connection.commit()
    connection.close()

    migrated = PlanningWorkspaceRepository(db_path=db)
    connection = migrated.get_connection()
    try:
        assert connection.execute(
            "SELECT version FROM planning_schema WHERE singleton=1",
        ).fetchone()[0] == 6
        tables = {row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'",
        )}
        assert {
            "planning_unit_price_comparisons",
            "planning_unit_price_comparison_idempotency",
            "planning_unit_economics_snapshots",
            "planning_price_experiments",
            "planning_price_experiment_phases",
            "planning_price_experiment_results",
        } <= tables
    finally:
        connection.close()

    token = _context()
    try:
        reopened = migrated.get_unit_price_observation(observation["observation_id"])
        assert reopened["error"] is False
        assert reopened["result"]["revision"] == 1
        assert reopened["result"]["payload"] == _result()
    finally:
        reset_current_tenant_user_id(token)
