import json
import sqlite3
from datetime import datetime, timezone

from services.ozon_account_repository import make_store_tenant_scope
from services.planning_workspace_repository import PlanningWorkspaceRepository
from services.tenant_context import reset_current_tenant_user_id, set_current_tenant_user_id


IDENTITY = {
    "store_id": "store-a", "product_id": "product-1", "offer_id": "offer-1",
    "sku": "sku-1", "sale_schema": "FBO",
}


def _scope(owner="owner-1", store="store-a"):
    return set_current_tenant_user_id(make_store_tenant_scope(owner, store))


def _repo(path):
    return PlanningWorkspaceRepository(
        db_path=path,
        clock=lambda: datetime(2026, 10, 27, 10, 0, tzinfo=timezone.utc),
    )


def _plan_payload():
    return {
        "plan_kind": "single", "schema_version": 1, "calculation_version": 1,
        "target_margin_percent": "25.00", "items": [{
            "identity": {
                "product_id": "product-1", "offer_id": "offer-1", "sku": "sku-1",
                "product_name": "Synthetic", "store_id": "store-a", "scheme": "FBO",
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


def _source_record(repo, *, result_revisions=1):
    plan = repo.save_document(
        title="Comparison source plan", payload=_plan_payload(),
        idempotency_key="comparison-source-plan-01",
    )
    observation = repo.start_unit_price_observation(
        identity={
            "product_id": IDENTITY["product_id"], "offer_id": IDENTITY["offer_id"],
            "sku": IDENTITY["sku"], "sale_schema": "FBO",
        },
        seller_price_cents=10_000, source_document_id=plan["document_id"],
        source_document_revision=1, effective_from="2026-10-27T09:30:00Z",
        window_timezone="Europe/Moscow", owner_confirmed=True,
        idempotency_key="comparison-source-observation-01",
    )
    assert observation["error"] is False
    source = {
        "observation_id": observation["observation_id"],
        "source_document_id": plan["document_id"],
        "source_document_revision": 1,
        "result_revision": 0,
    }
    for revision in range(1, result_revisions + 1):
        result = repo.append_unit_price_observation_result(
            source["observation_id"], {
                "schema_version": 1,
                "identity": {
                    "store_id": "store-a", "product_id": "product-1",
                    "offer_id": "offer-1", "sku": "sku-1", "sale_schema": "FBO",
                },
                "seller_price_cents": 10_000, "status": "INSUFFICIENT_DATA",
                "evidence_basis": "MODELLED_FROM_OBSERVED_INPUTS",
                "window": {"from": "2026-10-19", "to": "2026-10-25",
                           "timezone": "Europe/Moscow", "date_basis": "LOCAL_CALENDAR_DATE"},
                "sources": [{"name": "FINANCE", "status": "PARTIAL", "complete": False,
                             "row_count": 0, "as_of": "2026-10-27T09:00:00Z"}],
                "metrics": {"cpc_spend": "0.00", "successful_sale_units": None},
                "completeness": {"price_history": "PRICE_HISTORY_UNCONFIRMED"},
                "reasons": ["PRICE_HISTORY_UNCONFIRMED"], "warnings": [],
            },
            expected_state_revision=1, expected_result_revision=revision - 1,
            idempotency_key=f"comparison-source-result-v{revision:02d}",
        )
        assert result["error"] is False
        source["result_revision"] = revision
    return source


def _payload(source, result_revision=None, profit="15.00"):
    revision = result_revision or source["result_revision"]
    quality = {
        "error": False, "status": "NOT_READY",
        "evidence_basis": "MODELLED_FROM_OBSERVED_INPUTS", "verified": False,
        "candidate_count": 1,
        "candidates": [{
            "index": 0, "result_revision": revision, "status": "INCOMPARABLE",
            "window_days": 7, "successful_units": 100, "price_cents": 10_000,
            "evidence_age_days": 1, "reasons": ["AT_LEAST_TWO_PRICE_VARIANTS_REQUIRED"],
            "warnings": [],
        }],
        "reasons": ["AT_LEAST_TWO_PRICE_VARIANTS_REQUIRED"], "warnings": [],
        "thresholds": {
            "recommended_window_days": 7, "small_sample_units": 30,
            "max_evidence_age_days": 14,
        },
        "read_only": True, "executed": False,
    }
    ranking = {
        "error": False, "kind": "UNIT_PRICE_OBSERVATION_RANKING",
        "status": "NOT_READY", "evidence_basis": "MODELLED_FROM_OBSERVED_INPUTS",
        "verified": False, "baseline_index": 0, "checked_candidate_count": 1,
        "quality_assessment": quality, "ranking": [], "best_indices": [],
        "best_profit_per_unit": None, "read_only": True, "executed": False,
        "omitted_candidate_count": 0, "omitted_repeated_price_count": 0,
    }
    # Preserve a metric string in the frozen payload to prove revisions do not
    # silently replace earlier values, even for a not-ready comparison.
    ranking["quality_assessment"]["candidates"][0]["warnings"] = [profit]
    return {
        "schema_version": 1, "identity": dict(IDENTITY), "ranking": ranking,
        "source_references": [{
            "index": 0, "observation_id": source["observation_id"],
            "result_revision": revision, "source_document_id": source["source_document_id"],
            "source_document_revision": source["source_document_revision"],
        }],
        "known_source_references": [{
            "observation_id": source["observation_id"], "result_revision": revision,
            "source_document_id": source["source_document_id"],
            "source_document_revision": source["source_document_revision"],
        }],
    }


def test_comparison_revisions_are_immutable_idempotent_and_store_scoped(tmp_path):
    repo = _repo(tmp_path / "planning.sqlite")
    token = _scope()
    try:
        source = _source_record(repo)
        first_payload = _payload(source)
        created = repo.create_unit_price_comparison(
            first_payload, idempotency_key="cmp-create-key-01",
        )
        replay = repo.create_unit_price_comparison(
            first_payload, idempotency_key="cmp-create-key-01",
        )
        assert created["error"] is False
        assert replay == created
        assert repo.create_unit_price_comparison(
            _payload(source, profit="21.00"), idempotency_key="cmp-create-key-01",
        )["code"] == "PLANNING_COMPARISON_IDEMPOTENCY_CONFLICT"

        latest_source = repo.get_unit_price_observation(
            source["observation_id"], owner_id="owner-1", store_id="store-a",
        )["observation"]
        correction = repo.append_unit_price_observation_result(
            source["observation_id"], {
                "schema_version": 1,
                "identity": {
                    "store_id": "store-a", "product_id": "product-1",
                    "offer_id": "offer-1", "sku": "sku-1", "sale_schema": "FBO",
                },
                "seller_price_cents": 10_000, "status": "INCOMPARABLE",
                "evidence_basis": "MODELLED_FROM_OBSERVED_INPUTS",
                "window": {"from": "2026-10-19", "to": "2026-10-25",
                           "timezone": "Europe/Moscow", "date_basis": "LOCAL_CALENDAR_DATE"},
                "sources": [{"name": "FINANCE", "status": "PARTIAL", "complete": False,
                             "row_count": 1, "as_of": "2026-10-27T09:30:00Z"}],
                "metrics": {"cpc_spend": "1.00", "successful_sale_units": None},
                "completeness": {"price_history": "PRICE_HISTORY_UNCONFIRMED"},
                "reasons": ["PRICE_HISTORY_UNCONFIRMED"], "warnings": [],
            },
            expected_state_revision=latest_source["state_revision"],
            expected_result_revision=1, idempotency_key="comparison-source-result-v02",
        )
        assert correction["error"] is False
        refreshed_source = dict(source, result_revision=2)
        updated_payload = _payload(refreshed_source, profit="16.00")
        appended = repo.append_unit_price_comparison_revision(
            created["comparison_id"], updated_payload, expected_revision=1,
            idempotency_key="cmp-refresh-key-01",
        )
        assert appended == {
            "error": False, "comparison_id": created["comparison_id"], "revision": 2,
        }
        assert repo.append_unit_price_comparison_revision(
            created["comparison_id"], updated_payload, expected_revision=1,
            idempotency_key="cmp-refresh-key-01",
        ) == appended
        assert repo.append_unit_price_comparison_revision(
            created["comparison_id"], updated_payload, expected_revision=1,
            idempotency_key="cmp-refresh-key-02",
        )["code"] == "PLANNING_COMPARISON_REVISION_CONFLICT"

        old = repo.get_unit_price_comparison(created["comparison_id"], revision=1)
        latest = repo.get_unit_price_comparison(created["comparison_id"])
        assert old["superseded"] is True
        assert latest["revision"] == latest["latest_revision"] == 2
        assert old["payload"] == first_payload
        assert latest["payload"] == updated_payload
        history = repo.list_unit_price_comparisons()
        assert len(history["items"]) == 1
        assert history["items"][0]["revision"] == 2
    finally:
        reset_current_tenant_user_id(token)

    reopened = _repo(repo.db_path)
    token = _scope("owner-1", "store-b")
    try:
        assert reopened.get_unit_price_comparison(created["comparison_id"])["code"] == "PLANNING_COMPARISON_NOT_FOUND"
        assert reopened.list_unit_price_comparisons()["items"] == []
    finally:
        reset_current_tenant_user_id(token)

    token = _scope()
    try:
        connection = reopened.get_connection()
        try:
            connection.execute(
                "UPDATE planning_unit_price_comparisons SET payload_json='{}' "
                "WHERE comparison_id=? AND revision=1", (created["comparison_id"],),
            )
        except sqlite3.IntegrityError:
            pass
        else:
            raise AssertionError("comparison revision updates must be blocked")
        try:
            connection.execute(
                "DELETE FROM planning_unit_price_comparisons WHERE comparison_id=?",
                (created["comparison_id"],),
            )
        except sqlite3.IntegrityError:
            pass
        else:
            raise AssertionError("comparison revisions must not be deleted")
        finally:
            connection.close()
    finally:
        reset_current_tenant_user_id(token)


def test_comparison_payload_rejects_cross_store_and_unsupported_values(tmp_path):
    repo = _repo(tmp_path / "planning.sqlite")
    token = _scope()
    try:
        source = _source_record(repo)
        wrong_store = _payload(source)
        wrong_store["identity"]["store_id"] = "store-b"
        assert repo.create_unit_price_comparison(
            wrong_store, idempotency_key="cmp-invalid-store-01",
        )["code"] == "PLANNING_COMPARISON_INPUT_INVALID"

        unsupported = _payload(source)
        unsupported["ranking"]["quality_assessment"]["candidates"][0]["warnings"] = [1.5]
        assert repo.create_unit_price_comparison(
            unsupported, idempotency_key="cmp-invalid-float-01",
        )["code"] == "PLANNING_COMPARISON_INPUT_INVALID"

        missing_result_revision = _payload(source, result_revision=2)
        assert repo.create_unit_price_comparison(
            missing_result_revision, idempotency_key="cmp-invalid-source-revision-01",
        )["code"] == "PLANNING_COMPARISON_SOURCE_REFERENCE_INVALID"

        missing_reference = _payload(source)
        missing_reference["source_references"] = []
        assert repo.create_unit_price_comparison(
            missing_reference, idempotency_key="cmp-invalid-ref-01",
        )["code"] == "PLANNING_COMPARISON_INPUT_INVALID"
    finally:
        reset_current_tenant_user_id(token)


def test_comparison_snapshot_round_trips_as_json_without_unlisted_fields(tmp_path):
    repo = _repo(tmp_path / "planning.sqlite")
    token = _scope()
    try:
        source = _source_record(repo)
        saved = repo.create_unit_price_comparison(
            _payload(source), idempotency_key="cmp-json-key-0001",
        )
        loaded = repo.get_unit_price_comparison(saved["comparison_id"])
        assert loaded["error"] is False
        assert json.loads(json.dumps(loaded["payload"])) == loaded["payload"]
        assert set(loaded["payload"]) == {
            "schema_version", "identity", "ranking", "source_references",
            "known_source_references",
        }
    finally:
        reset_current_tenant_user_id(token)


def test_failed_comparison_append_keeps_old_revision_and_does_not_consume_key(tmp_path):
    repo = _repo(tmp_path / "planning.sqlite")
    token = _scope()
    try:
        source = _source_record(repo, result_revisions=2)
        old_source = dict(source, result_revision=1)
        created = repo.create_unit_price_comparison(
            _payload(old_source), idempotency_key="cmp-rollback-create-01",
        )
        connection = repo.get_connection()
        connection.execute("""CREATE TRIGGER synthetic_comparison_insert_failure
            BEFORE INSERT ON planning_unit_price_comparisons WHEN NEW.revision=2
            BEGIN SELECT RAISE(ABORT, 'synthetic failure'); END""")
        connection.close()
        failed = repo.append_unit_price_comparison_revision(
            created["comparison_id"], _payload(source), expected_revision=1,
            idempotency_key="cmp-rollback-refresh-01",
        )
        assert failed["code"] == "PLANNING_COMPARISON_CONFLICT"
        assert repo.get_unit_price_comparison(created["comparison_id"])["revision"] == 1
        connection = repo.get_connection()
        count = connection.execute(
            "SELECT COUNT(*) FROM planning_unit_price_comparison_idempotency "
            "WHERE idempotency_key='cmp-rollback-refresh-01'",
        ).fetchone()[0]
        connection.execute("DROP TRIGGER synthetic_comparison_insert_failure")
        connection.close()
        assert count == 0
        saved = repo.append_unit_price_comparison_revision(
            created["comparison_id"], _payload(source), expected_revision=1,
            idempotency_key="cmp-rollback-refresh-01",
        )
        assert saved["error"] is False
        assert saved["revision"] == 2
    finally:
        reset_current_tenant_user_id(token)
