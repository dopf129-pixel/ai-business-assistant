import sqlite3
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Barrier

from services.ozon_account_repository import make_store_tenant_scope
from services.planning_workspace_repository import PlanningWorkspaceRepository
from services.tenant_context import reset_current_tenant_user_id, set_current_tenant_user_id


def _payload(store_id="store-a", sku="sku-1", name="Крючок"):
    return {
        "plan_kind": "single",
        "schema_version": 1,
        "calculation_version": 1,
        "target_margin_percent": "25.00",
        "items": [{
            "identity": {
                "product_id": "product-1", "offer_id": "offer-1", "sku": sku,
                "product_name": name, "store_id": store_id, "scheme": "FBO",
            },
            "inputs": {
                "price": "500.00", "cost": None, "commission_rate": "20",
                "advertising_rate": "10", "discount_points_rate": "20",
                "logistics_per_unit": "25", "last_mile_per_unit": "5",
                "acquiring_per_unit": "5", "tax_mode": "USN_INCOME",
                "tax_rate": "6", "minimum_tax_rate": None,
            },
            "provenance": {"price": "ozon_current_seller_price", "cost": "unknown"},
            "sources": {
                "periods": {"seller_price_as_of": "2026-10-19T12:00:00+00:00"},
                "as_of": "2026-10-19T12:00:00+00:00",
                "loaded_at": "2026-10-19T12:00:00+00:00",
                "completeness": {"catalog_identity": {"complete": True}},
            },
            "projection": {
                "available": False, "missing_inputs": ["cost"], "invalid_inputs": [],
                "revenue": "500.00", "profit": None,
            },
        }],
    }


def _context(owner="user-1", store="store-a"):
    return set_current_tenant_user_id(make_store_tenant_scope(owner, store))


def _save(repository, key, **kwargs):
    return repository.save_document(
        title=kwargs.pop("title", "Сценарий"), payload=kwargs.pop("payload", _payload()),
        idempotency_key=key, **kwargs,
    )


def test_create_read_and_revision_history_preserve_legacy_tables(tmp_path):
    db = tmp_path / "seller.sqlite"
    connection = sqlite3.connect(db)
    connection.execute("CREATE TABLE seller_costs (sku TEXT PRIMARY KEY, amount REAL)")
    connection.execute("INSERT INTO seller_costs VALUES ('sku-user', 123.45)")
    connection.commit()
    connection.close()
    repo = PlanningWorkspaceRepository(db_path=db)
    token = _context()
    try:
        first = _save(repo, "save-create-0001")
        assert first == {"error": False, "document_id": first["document_id"], "revision": 1}
        item = repo.get_document(first["document_id"])
        assert item["error"] is False
        assert item["document"]["payload"]["items"][0]["inputs"]["cost"] is None
        assert item["document"]["payload"]["items"][0]["projection"]["profit"] is None
        assert repo.list_revisions(first["document_id"])["items"][0]["revision"] == 1
        repo.save_document(
            title="Обновлённый план", payload=_payload(), document_id=first["document_id"],
            expected_revision=1, idempotency_key="save-edit-000001",
        )
        revisions = repo.list_revisions(first["document_id"])
        assert [item["revision"] for item in revisions["items"]] == [2, 1]
    finally:
        reset_current_tenant_user_id(token)
    connection = sqlite3.connect(db)
    assert connection.execute("SELECT amount FROM seller_costs WHERE sku='sku-user'").fetchone()[0] == 123.45
    connection.close()


def test_scope_isolated_by_owner_and_store(tmp_path):
    repo = PlanningWorkspaceRepository(db_path=tmp_path / "seller.sqlite")
    token = _context("alice", "store-a")
    try:
        created = _save(repo, "scope-save-0001")
    finally:
        reset_current_tenant_user_id(token)
    token = _context("alice", "store-b")
    try:
        assert repo.get_document(created["document_id"])["code"] == "PLANNING_DOCUMENT_NOT_FOUND"
        assert _save(repo, "scope-save-0002", payload=_payload(store_id="store-a"))["code"] == "PLANNING_DOCUMENT_INPUT_INVALID"
    finally:
        reset_current_tenant_user_id(token)
    token = _context("bob", "store-a")
    try:
        assert repo.list_documents()["items"] == []
    finally:
        reset_current_tenant_user_id(token)


def test_repeated_save_is_idempotent_and_stale_revision_conflicts(tmp_path):
    repo = PlanningWorkspaceRepository(db_path=tmp_path / "seller.sqlite")
    token = _context()
    try:
        created = _save(repo, "idem-create-0001")
        assert _save(repo, "idem-create-0001", title="must not duplicate") == created
        updated = repo.save_document(
            title="Revision 2", payload=_payload(), document_id=created["document_id"],
            expected_revision=1, idempotency_key="idem-edit-000001",
        )
        assert updated["revision"] == 2
        conflict = repo.save_document(
            title="stale overwrite", payload=_payload(), document_id=created["document_id"],
            expected_revision=1, idempotency_key="idem-edit-000002",
        )
        assert conflict["code"] == "PLANNING_DOCUMENT_REVISION_CONFLICT"
        assert repo.get_document(created["document_id"])["document"]["revision"] == 2
    finally:
        reset_current_tenant_user_id(token)


def test_concurrent_compare_and_swap_has_one_winner(tmp_path):
    repo = PlanningWorkspaceRepository(db_path=tmp_path / "seller.sqlite")
    token = _context()
    try:
        created = _save(repo, "cas-create-0001")
    finally:
        reset_current_tenant_user_id(token)
    gate = Barrier(2)

    def update(title, key):
        local_token = _context()
        try:
            gate.wait(timeout=3)
            return repo.save_document(
                title=title, payload=_payload(), document_id=created["document_id"],
                expected_revision=1, idempotency_key=key,
            )
        finally:
            reset_current_tenant_user_id(local_token)

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda pair: update(*pair), [
            ("Первый", "cas-edit-000001"), ("Второй", "cas-edit-000002"),
        ]))
    assert sum(result.get("error") is False for result in outcomes) == 1
    assert sum(result.get("code") == "PLANNING_DOCUMENT_REVISION_CONFLICT" for result in outcomes) == 1


def test_archive_restore_and_confirmed_delete_are_scoped_and_explicit(tmp_path):
    repo = PlanningWorkspaceRepository(db_path=tmp_path / "seller.sqlite")
    token = _context()
    try:
        created = _save(repo, "archive-create01")
        assert repo.set_archived(created["document_id"], True, expected_revision=1,
                                 idempotency_key="archive-change01")["error"] is False
        assert repo.list_documents()["items"] == []
        assert repo.list_documents(include_archived=True)["items"][0]["status"] == "ARCHIVED"
        assert repo.set_archived(created["document_id"], False, expected_revision=1,
                                 idempotency_key="archive-restore1")["error"] is False
        assert repo.delete_document(created["document_id"], expected_revision=1,
                                    confirmed=False, idempotency_key="delete-denied01")["code"] == "PLANNING_DOCUMENT_CONFIRMATION_REQUIRED"
        assert repo.delete_document(created["document_id"], expected_revision=1,
                                    confirmed=True, idempotency_key="delete-confirm1")["deleted"] is True
        assert repo.get_document(created["document_id"])["code"] == "PLANNING_DOCUMENT_NOT_FOUND"
    finally:
        reset_current_tenant_user_id(token)


def test_payload_rejects_unallowlisted_fields_nonfinite_values_and_bad_timestamps(tmp_path):
    repo = PlanningWorkspaceRepository(db_path=tmp_path / "seller.sqlite")
    token = _context()
    try:
        payload = _payload()
        payload["api_key"] = "do-not-persist"
        assert _save(repo, "invalid-secret01", payload=payload)["error"] is True
        payload = _payload()
        payload["items"][0]["inputs"]["price"] = "NaN"
        assert _save(repo, "invalid-nan-0001", payload=payload)["error"] is True
        payload = _payload()
        payload["items"][0]["sources"]["loaded_at"] = "2026-10-19T12:00:00"
        assert _save(repo, "invalid-time001", payload=payload)["error"] is True
        payload = _payload()
        payload["items"][0]["identity"]["sku"] = "sku-2"
        payload["items"].append(payload["items"][0])
        payload["plan_kind"] = "batch"
        assert _save(repo, "invalid-dup-0001", payload=payload)["error"] is True
    finally:
        reset_current_tenant_user_id(token)


def test_future_schema_and_storage_errors_fail_closed(tmp_path):
    db = tmp_path / "future.sqlite"
    connection = sqlite3.connect(db)
    connection.execute("CREATE TABLE planning_schema(version INTEGER NOT NULL)")
    connection.execute("INSERT INTO planning_schema VALUES (99)")
    connection.commit()
    connection.close()
    repo = PlanningWorkspaceRepository(db_path=db)
    token = _context()
    try:
        assert _save(repo, "future-schema01")["code"] == "PLANNING_STORAGE_UNAVAILABLE"
    finally:
        reset_current_tenant_user_id(token)
    bad_path = tmp_path / "not-a-directory" / "db.sqlite"
    bad_path.parent.write_text("file blocks directory creation", encoding="utf-8")
    repo = PlanningWorkspaceRepository(db_path=bad_path)
    token = _context()
    try:
        assert _save(repo, "bad-storage-001")["code"] == "PLANNING_STORAGE_UNAVAILABLE"
    finally:
        reset_current_tenant_user_id(token)


def test_clock_is_timezone_aware_and_payload_schema_stays_additive(tmp_path):
    repo = PlanningWorkspaceRepository(
        db_path=tmp_path / "seller.sqlite",
        clock=lambda: datetime(2026, 10, 19, 12, tzinfo=timezone.utc),
    )
    token = _context()
    try:
        created = _save(repo, "clock-save-0001")
        assert created["error"] is False
        connection = sqlite3.connect(repo.db_path)
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        connection.close()
        assert {"planning_documents", "planning_revisions", "planning_idempotency"} <= tables
    finally:
        reset_current_tenant_user_id(token)


def test_corrupt_and_future_document_versions_fail_closed_without_hiding_other_rows(tmp_path):
    repo = PlanningWorkspaceRepository(db_path=tmp_path / "plans.sqlite")
    token = _context()
    try:
        first = _save(repo, "corrupt-plan-001")
        second = _save(repo, "future-plan-001")
        connection = sqlite3.connect(repo.db_path)
        connection.execute(
            "UPDATE planning_revisions SET payload_json=? WHERE document_id=? AND revision=1",
            ("{broken", first["document_id"]),
        )
        connection.execute(
            "UPDATE planning_revisions SET payload_json=? WHERE document_id=? AND revision=1",
            (json.dumps({"schema_version": 99}), second["document_id"]),
        )
        connection.commit()
        connection.close()

        assert repo.get_document(first["document_id"])["code"] == "PLANNING_DOCUMENT_CORRUPT"
        assert repo.get_document(second["document_id"])["code"] == "PLANNING_DOCUMENT_SCHEMA_UNSUPPORTED"
        listed = repo.list_documents()
        assert listed["error"] is False
        assert {item["document_id"] for item in listed["items"]} == {
            first["document_id"], second["document_id"],
        }
    finally:
        reset_current_tenant_user_id(token)


def test_invalid_clock_does_not_create_a_successful_empty_plan(tmp_path):
    repo = PlanningWorkspaceRepository(
        db_path=tmp_path / "plans.sqlite",
        clock=lambda: datetime(2026, 10, 19, 12),
    )
    token = _context()
    try:
        result = _save(repo, "bad-clock-0001")
        assert result == {"error": True, "code": "PLANNING_CLOCK_UNAVAILABLE"}
        listed = repo.list_documents()
        assert listed["error"] is False
        assert listed["items"] == []
    finally:
        reset_current_tenant_user_id(token)


def test_sales_mix_persists_explicit_unknown_quantity_and_rejects_bad_scope(tmp_path):
    repo = PlanningWorkspaceRepository(db_path=tmp_path / "seller.sqlite")
    token = _context()
    try:
        payload = _payload()
        payload["sales_mix"] = {
            "period_label": "2026-08-01 - 2026-08-31",
            "quantities": {"sku-1": None},
            "expenses": [],
            "confirmed": True,
        }
        created = _save(repo, "sales-mix-valid-001", payload=payload)
        read = repo.get_document(created["document_id"])
        assert read["document"]["payload"]["sales_mix"]["quantities"]["sku-1"] is None

        mismatch = _payload()
        mismatch["sales_mix"] = {**payload["sales_mix"], "quantities": {}}
        assert _save(repo, "sales-mix-invalid-01", payload=mismatch)["code"] == "PLANNING_DOCUMENT_INPUT_INVALID"

        negative = _payload()
        negative["sales_mix"] = {
            **payload["sales_mix"],
            "quantities": {"sku-1": 0},
            "expenses": [{"name": "Скидка", "amount": "-1"}],
        }
        assert _save(repo, "sales-mix-invalid-02", payload=negative)["code"] == "PLANNING_DOCUMENT_INPUT_INVALID"
    finally:
        reset_current_tenant_user_id(token)
