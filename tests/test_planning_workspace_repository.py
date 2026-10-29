import sqlite3
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from decimal import Decimal
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


def _cross_docking_payload():
    payload = _payload()
    payload["schema_version"] = 2
    payload["calculation_version"] = 2
    item = payload["items"][0]
    item["inputs"]["cross_docking_per_unit"] = "12.00"
    item["provenance"]["cross_docking_per_unit"] = "ozon_cross_docking_sku_average"
    item["sources"]["periods"]["cross_docking"] = {
        "from": "2026-08-24", "to": "2026-10-18", "calendar_days": 56,
        "timezone": "Europe/Moscow",
    }
    item["sources"]["completeness"]["cross_docking"] = {
        "complete": True, "rate_available": True, "status": "SKU_SUPPLY_PERIOD_AVERAGE",
    }
    item["sources"]["cross_docking"] = {
        "evidence_complete": True,
        "rate_available": True,
        "status": "SKU_SUPPLY_PERIOD_AVERAGE", "reason": None,
        "method": "sku_accrual_cost_per_delivered_crossdock_unit",
        "amount_per_unit": "12.00", "applicable_to_sku": True,
        "denominator_kind": "DELIVERED_CROSSDOCK_UNITS",
        "expense_total": "1200.00", "expense_by_sku": "1200.00",
        "supplied_units_sku": 100, "supplied_units_store": 100,
        "days_complete": 56, "days_expected": 56,
        "date_from": "2026-08-24", "date_to": "2026-10-18",
        "as_of": "2026-10-19T12:00:00Z", "timezone": "Europe/Moscow",
        "financial_date_basis": "ACCRUAL_DATE",
        "supply_date_basis": "COMPLETED_SINGLE_CROSSDOCK_ORDER_STATE_UPDATED_DATE",
        "model_version": 1,
    }
    item["projection"]["cross_docking"] = "12.00"
    return payload


def _complete_window_without_cross_docking_rate_payload():
    payload = _cross_docking_payload()
    item = payload["items"][0]
    item["inputs"]["cross_docking_per_unit"] = None
    item["projection"]["cross_docking"] = None
    item["sources"]["completeness"]["cross_docking"] = {
        "complete": True, "rate_available": False,
        "status": "NO_CROSSDOCK_SUPPLIES", "reason": "NO_CROSSDOCK_SUPPLIES",
    }
    item["sources"]["cross_docking"] = {
        "evidence_complete": True, "rate_available": False,
        "status": "NO_CROSSDOCK_SUPPLIES", "reason": "NO_CROSSDOCK_SUPPLIES",
        "method": None, "amount_per_unit": None, "applicable_to_sku": False,
        "denominator_kind": "DELIVERED_CROSSDOCK_UNITS",
        "expense_total": "0.00", "expense_by_sku": "0.00",
        "supplied_units_sku": 0, "supplied_units_store": 0,
        "days_complete": 56, "days_expected": 56,
        "date_from": "2026-08-24", "date_to": "2026-10-18",
        "as_of": "2026-10-19T12:00:00Z", "timezone": "Europe/Moscow",
        "financial_date_basis": "ACCRUAL_DATE",
        "supply_date_basis": "COMPLETED_SINGLE_CROSSDOCK_ORDER_STATE_UPDATED_DATE",
        "model_version": 1,
    }
    return payload


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
        assert first == {
            "error": False, "document_id": first["document_id"],
            "revision": 1, "state_revision": 1,
        }
        item = repo.get_document(first["document_id"])
        assert item["error"] is False
        assert item["document"]["payload"]["items"][0]["inputs"]["cost"] is None
        assert item["document"]["payload"]["items"][0]["projection"]["profit"] is None
        assert repo.list_revisions(first["document_id"])["items"][0]["revision"] == 1
        repo.save_document(
            title="Обновлённый план", payload=_payload(), document_id=first["document_id"],
            expected_revision=1, expected_state_revision=1,
            idempotency_key="save-edit-000001",
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
            expected_revision=1, expected_state_revision=1,
            idempotency_key="idem-edit-000001",
        )
        assert updated["revision"] == 2
        assert updated["state_revision"] == 2
        conflict = repo.save_document(
            title="stale overwrite", payload=_payload(), document_id=created["document_id"],
            expected_revision=1, expected_state_revision=1,
            idempotency_key="idem-edit-000002",
        )
        assert conflict["code"] == "PLANNING_DOCUMENT_REVISION_CONFLICT"
        assert repo.get_document(created["document_id"])["document"]["revision"] == 2
        missing_state = repo.save_document(
            title="missing state", payload=_payload(), document_id=created["document_id"],
            expected_revision=2, idempotency_key="idem-missing-state",
        )
        assert missing_state["code"] == "PLANNING_DOCUMENT_STATE_REVISION_REQUIRED"
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
                expected_revision=1, expected_state_revision=1, idempotency_key=key,
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
        archived = repo.set_archived(
            created["document_id"], True, expected_revision=1, expected_state_revision=1,
            idempotency_key="archive-change01",
        )
        assert archived["error"] is False and archived["state_revision"] == 2
        assert repo.list_documents()["items"] == []
        assert repo.list_documents(include_archived=True)["items"][0]["status"] == "ARCHIVED"
        restored = repo.set_archived(
            created["document_id"], False, expected_revision=1, expected_state_revision=2,
            idempotency_key="archive-restore1",
        )
        assert restored["error"] is False and restored["state_revision"] == 3
        assert repo.delete_document(created["document_id"], expected_revision=1,
                                    expected_state_revision=3, confirmed=False,
                                    idempotency_key="delete-denied01")["code"] == "PLANNING_DOCUMENT_CONFIRMATION_REQUIRED"
        assert repo.delete_document(created["document_id"], expected_revision=1,
                                    expected_state_revision=3, confirmed=True,
                                    idempotency_key="delete-confirm1")["deleted"] is True
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
    connection = sqlite3.connect(db)
    try:
        assert connection.execute("SELECT version FROM planning_schema").fetchone()[0] == 99
        tables = {row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'",
        )}
        assert tables == {"planning_schema"}
    finally:
        connection.close()
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
        assert {"planning_documents", "planning_revisions", "planning_idempotency", "planning_tariff_profiles", "planning_tariff_profile_revisions", "planning_tariff_profile_idempotency"} <= tables
    finally:
        reset_current_tenant_user_id(token)


def test_first_concurrent_connections_initialize_one_schema_and_allow_reopen(tmp_path):
    repo = PlanningWorkspaceRepository(db_path=tmp_path / "fresh.sqlite")
    gate = Barrier(2)

    def connect(_):
        gate.wait(timeout=3)
        connection = repo.get_connection()
        try:
            return connection.execute(
                "SELECT singleton, version FROM planning_schema"
            ).fetchall()
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(connect, range(2)))
        assert all(len(rows) == 1 and tuple(rows[0]) == (1, 10) for rows in outcomes)

    token = _context()
    try:
        created = _save(repo, "schema-race-save-01")
        reopened = PlanningWorkspaceRepository(db_path=repo.db_path).get_document(
            created["document_id"],
        )
        assert reopened["error"] is False
        assert reopened["document"]["state_revision"] == 1
    finally:
        reset_current_tenant_user_id(token)


def test_legacy_schema_migrates_atomically_and_keeps_existing_document_state(tmp_path):
    db = tmp_path / "legacy.sqlite"
    connection = sqlite3.connect(db)
    connection.execute("CREATE TABLE planning_schema(version INTEGER NOT NULL)")
    connection.executemany("INSERT INTO planning_schema VALUES (1)", [(), ()])
    connection.execute("""CREATE TABLE planning_documents (
        document_id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, store_id TEXT NOT NULL,
        title TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN ('ACTIVE','ARCHIVED')),
        revision INTEGER NOT NULL CHECK(revision >= 1), schema_version INTEGER NOT NULL,
        calculation_version INTEGER NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
        UNIQUE(document_id, owner_id, store_id))""")
    connection.execute(
        "INSERT INTO planning_documents VALUES ('legacy-doc','user-1','store-a','Legacy','ACTIVE',1,1,1,'now','now')"
    )
    connection.commit()
    connection.close()

    repo = PlanningWorkspaceRepository(db_path=db)
    connection = repo.get_connection()
    try:
        schema_rows = connection.execute(
            "SELECT singleton, version FROM planning_schema"
        ).fetchall()
        document = connection.execute(
            "SELECT state_revision FROM planning_documents WHERE document_id='legacy-doc'"
        ).fetchone()
    finally:
        connection.close()
    assert [tuple(row) for row in schema_rows] == [(1, 10)]
    assert document["state_revision"] == 1


def test_metadata_change_invalidates_previous_delete_confirmation(tmp_path):
    repo = PlanningWorkspaceRepository(db_path=tmp_path / "plans.sqlite")
    token = _context()
    try:
        created = _save(repo, "stale-delete-create01")
        renamed = repo.rename_document(
            created["document_id"], "Renamed", expected_revision=1,
            expected_state_revision=1, idempotency_key="stale-delete-rename1",
        )
        assert renamed["error"] is False and renamed["state_revision"] == 2
        stale = repo.delete_document(
            created["document_id"], expected_revision=1, expected_state_revision=1,
            confirmed=True, idempotency_key="stale-delete-old-confirm",
        )
        assert stale["code"] == "PLANNING_DOCUMENT_STATE_CONFLICT"
        current = repo.get_document(created["document_id"])
        assert current["error"] is False
        assert current["document"]["title"] == "Renamed"
        assert current["document"]["current_revision"] == 1
    finally:
        reset_current_tenant_user_id(token)


def test_persistence_enforces_new_sales_mix_bounds_but_reads_and_preserves_legacy_mix(tmp_path):
    repo = PlanningWorkspaceRepository(db_path=tmp_path / "sales-mix-limits.sqlite")
    token = _context()
    try:
        payload = _payload()
        payload["sales_mix"] = {
            "period_label": "2025-01-01 - 2026-12-31",
            "quantities": {"sku-1": 500_000},
            "expenses": [{"name": f"legacy-{index}", "amount": "1.00"} for index in range(21)],
            "confirmed": True,
        }
        created = _save(repo, "legacy-plan-create01", payload=_payload())
        connection = sqlite3.connect(repo.db_path)
        connection.execute(
            "UPDATE planning_revisions SET payload_json=? WHERE document_id=? AND revision=1",
            (json.dumps(payload), created["document_id"]),
        )
        connection.commit()
        connection.close()

        legacy = repo.get_document(created["document_id"])
        assert legacy["error"] is False
        assert legacy["document"]["payload"]["sales_mix"] == payload["sales_mix"]
        updated = repo.save_document(
            title="Preserved legacy plan", payload=legacy["document"]["payload"],
            document_id=created["document_id"], expected_revision=1,
            expected_state_revision=1, idempotency_key="legacy-plan-preserve01",
        )
        assert updated["error"] is False
        assert repo.get_document(created["document_id"])["document"]["payload"]["sales_mix"] == payload["sales_mix"]

        too_many_units = _payload()
        too_many_units["sales_mix"] = {
            "period_label": "2026-08-01 - 2026-08-31",
            "quantities": {"sku-1": 100_001}, "expenses": [], "confirmed": True,
        }
        assert _save(repo, "sales-mix-q-limit01", payload=too_many_units)["code"] == "PLANNING_DOCUMENT_INPUT_INVALID"
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


def test_v2_cross_docking_evidence_is_frozen_and_identifier_allowlisted(tmp_path):
    repo = PlanningWorkspaceRepository(db_path=tmp_path / "seller.sqlite")
    token = _context()
    try:
        created = _save(repo, "crossdock-save-0001", payload=_cross_docking_payload())
        assert created["error"] is False
        saved = repo.get_document(created["document_id"])["document"]["payload"]
        item = saved["items"][0]
        assert saved["calculation_version"] == 2
        assert item["inputs"]["cross_docking_per_unit"] == "12.00"
        assert item["sources"]["cross_docking"]["supplied_units_sku"] == 100
        assert "sku" not in item["sources"]["cross_docking"]
        assert "supply_id" not in item["sources"]["cross_docking"]

        unsafe = _cross_docking_payload()
        unsafe["items"][0]["sources"]["cross_docking"]["supply_id"] = "private-id"
        assert _save(repo, "crossdock-save-0002", payload=unsafe)["code"] == "PLANNING_DOCUMENT_INPUT_INVALID"
    finally:
        reset_current_tenant_user_id(token)


def test_v2_cross_docking_accepts_equal_decimal_values_with_different_scales(tmp_path):
    repo = PlanningWorkspaceRepository(db_path=tmp_path / "seller.sqlite")
    token = _context()
    try:
        for index, rate in enumerate((12.0, 12.5, 0.0), start=1):
            payload = _cross_docking_payload()
            amount = f"{rate:.2f}"
            item = payload["items"][0]
            item["inputs"]["cross_docking_per_unit"] = rate
            item["sources"]["cross_docking"]["amount_per_unit"] = amount
            item["sources"]["cross_docking"]["model_version"] = (
                "cross_docking_unit_cost_v1"
            )
            item["projection"]["cross_docking"] = amount
            created = _save(
                repo,
                f"crossdock-scale-{index:02}",
                payload=payload,
            )
            assert created["error"] is False
            saved = repo.get_document(created["document_id"])["document"]["payload"]
            assert Decimal(
                saved["items"][0]["inputs"]["cross_docking_per_unit"]
            ) == Decimal(amount)
            assert saved["items"][0]["sources"]["cross_docking"]["model_version"] == (
                "cross_docking_unit_cost_v1"
            )
        mismatch = _cross_docking_payload()
        mismatch["items"][0]["inputs"]["cross_docking_per_unit"] = 12.5
        assert _save(
            repo,
            "crossdock-scale-invalid",
            payload=mismatch,
        )["code"] == "PLANNING_DOCUMENT_INPUT_INVALID"
    finally:
        reset_current_tenant_user_id(token)


def test_v2_saves_complete_window_even_when_sku_rate_is_unavailable(tmp_path):
    repo = PlanningWorkspaceRepository(db_path=tmp_path / "seller.sqlite")
    token = _context()
    try:
        result = _save(
            repo, "crossdock-no-rate-001", payload=_complete_window_without_cross_docking_rate_payload(),
        )

        assert result["error"] is False
        saved = repo.get_document(result["document_id"])["document"]["payload"]["items"][0]
        assert saved["inputs"]["cross_docking_per_unit"] is None
        assert saved["sources"]["cross_docking"]["evidence_complete"] is True
        assert saved["sources"]["cross_docking"]["rate_available"] is False
        assert saved["sources"]["cross_docking"]["amount_per_unit"] is None
    finally:
        reset_current_tenant_user_id(token)


def test_v1_plan_cannot_persist_automatic_cross_docking(tmp_path):
    repo = PlanningWorkspaceRepository(db_path=tmp_path / "seller.sqlite")
    token = _context()
    try:
        legacy = _payload()
        legacy["items"][0]["inputs"]["cross_docking_per_unit"] = "12.00"
        assert _save(repo, "crossdock-save-0003", payload=legacy)["code"] == "PLANNING_DOCUMENT_INPUT_INVALID"
    finally:
        reset_current_tenant_user_id(token)
