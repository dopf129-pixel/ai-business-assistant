from datetime import datetime, timezone
import json
import sqlite3

from services.ozon_account_repository import make_store_tenant_scope
from services.planning_workspace_repository import PlanningWorkspaceRepository
from services.tenant_context import reset_current_tenant_user_id, set_current_tenant_user_id
from services.unit_price_tariff_resolver import UnitPriceTariffResolver


def _context(owner="user-1", store="store-a"):
    return set_current_tenant_user_id(make_store_tenant_scope(owner, store))


def _payload(*, sku="sku-1", product_id="product-1", offer_id="offer-1", rate="11.5"):
    return {
        "identity": {"product_id": product_id, "offer_id": offer_id, "sku": sku},
        "sale_schema": "FBO",
        "effective_from": "2026-10-01",
        "effective_to": None,
        "confirmed_by_owner": True,
        "bands": [
            {"price_from_cents": 10000, "price_to_cents": 19999, "commission_rate": rate},
            {"price_from_cents": 20000, "price_to_cents": 30000, "commission_rate": "22"},
        ],
    }


def _create(repo, payload=None, key="tariff-create-0001"):
    return repo.create_tariff_profile(payload or _payload(), idempotency_key=key)


def test_manual_profile_persists_across_repository_restart_and_resolves_exact_range(tmp_path):
    db = tmp_path / "planning.sqlite"
    repo = PlanningWorkspaceRepository(db_path=db, clock=lambda: datetime(2026, 10, 27, tzinfo=timezone.utc))
    token = _context()
    try:
        created = _create(repo)
        assert created["error"] is False
        assert created["revision"] == created["state_revision"] == 1
        assert created["profile"]["owner_id"] == "user-1"
        assert created["profile"]["store_id"] == "store-a"
        reopened = PlanningWorkspaceRepository(db_path=db).get_tariff_profile(created["profile_id"])
        assert reopened["error"] is False
        profile = reopened["profile"]
        assert profile["identity"] == _payload()["identity"]
        assert profile["bands"][0]["commission_rate"] == "11.5"
        result = UnitPriceTariffResolver().resolve(
            seller_price_cents=15000,
            identity={"owner_id": "user-1", "store_id": "store-a", **profile["identity"]},
            sale_schema="FBO", effective_date="2026-10-27", profiles=[profile],
        )
        assert result["error"] is False
        assert result["available"] is True
        assert result["status"] == "MANUAL_RANGE"
        assert result["commission_rate"] == "11.5"
    finally:
        reset_current_tenant_user_id(token)


def test_create_is_idempotent_and_update_is_cas_with_immutable_identity(tmp_path):
    repo = PlanningWorkspaceRepository(db_path=tmp_path / "planning.sqlite")
    token = _context()
    try:
        created = _create(repo)
        assert _create(repo, _payload(rate="99"), key="tariff-create-0001") == created
        edited = _payload(rate="12")
        updated = repo.update_tariff_profile(
            created["profile_id"], edited, expected_revision=1, expected_state_revision=1,
            idempotency_key="tariff-update-0001",
        )
        assert updated["error"] is False
        assert updated["revision"] == updated["state_revision"] == 2
        assert repo.update_tariff_profile(
            created["profile_id"], edited, expected_revision=1, expected_state_revision=1,
            idempotency_key="tariff-update-0001",
        ) == updated
        assert repo.update_tariff_profile(
            created["profile_id"], edited, expected_revision=1, expected_state_revision=1,
            idempotency_key="tariff-stale-edit-001",
        )["code"] == "PLANNING_TARIFF_PROFILE_STATE_CONFLICT"
        changed_identity = _payload(rate="12", sku="sku-other")
        assert repo.update_tariff_profile(
            created["profile_id"], changed_identity, expected_revision=2, expected_state_revision=2,
            idempotency_key="tariff-identity-001",
        )["code"] == "PLANNING_TARIFF_PROFILE_IDENTITY_IMMUTABLE"
        old = repo.get_tariff_profile(created["profile_id"], revision=1)
        current = repo.get_tariff_profile(created["profile_id"])
        assert old["profile"]["bands"][0]["commission_rate"] == "11.5"
        assert current["profile"]["bands"][0]["commission_rate"] == "12"
    finally:
        reset_current_tenant_user_id(token)


def test_profile_scope_isolated_by_owner_and_store(tmp_path):
    repo = PlanningWorkspaceRepository(db_path=tmp_path / "planning.sqlite")
    token = _context("alice", "store-a")
    try:
        created = _create(repo)
    finally:
        reset_current_tenant_user_id(token)
    token = _context("alice", "store-b")
    try:
        assert repo.get_tariff_profile(created["profile_id"])["code"] == "PLANNING_TARIFF_PROFILE_NOT_FOUND"
        assert repo.list_tariff_profiles()["items"] == []
    finally:
        reset_current_tenant_user_id(token)
    token = _context("bob", "store-a")
    try:
        assert repo.get_tariff_profile(created["profile_id"])["code"] == "PLANNING_TARIFF_PROFILE_NOT_FOUND"
    finally:
        reset_current_tenant_user_id(token)


def test_archive_advances_state_only_and_lists_archived_only_when_requested(tmp_path):
    repo = PlanningWorkspaceRepository(db_path=tmp_path / "planning.sqlite")
    token = _context()
    try:
        created = _create(repo)
        archived = repo.archive_tariff_profile(
            created["profile_id"], expected_revision=1, expected_state_revision=1,
            idempotency_key="tariff-archive-01",
        )
        assert archived["error"] is False
        assert archived["revision"] == 1 and archived["state_revision"] == 2
        assert repo.get_tariff_profile(created["profile_id"])["state_revision"] == 2
        assert repo.list_tariff_profiles()["items"] == []
        listing = repo.list_tariff_profiles(include_archived=True)
        assert len(listing["items"]) == 1 and listing["items"][0]["status"] == "ARCHIVED"
        assert repo.archive_tariff_profile(
            created["profile_id"], expected_revision=1, expected_state_revision=1,
            idempotency_key="tariff-stale-arch-1",
        )["code"] == "PLANNING_TARIFF_PROFILE_STATE_CONFLICT"
    finally:
        reset_current_tenant_user_id(token)


def test_invalid_profiles_fail_closed_without_writing(tmp_path):
    repo = PlanningWorkspaceRepository(db_path=tmp_path / "planning.sqlite")
    token = _context()
    try:
        cases = []
        unconfirmed = _payload(); unconfirmed["confirmed_by_owner"] = False; cases.append(unconfirmed)
        fbs = _payload(); fbs["sale_schema"] = "FBS"; cases.append(fbs)
        bool_cents = _payload(); bool_cents["bands"][0]["price_from_cents"] = True; cases.append(bool_cents)
        bool_rate = _payload(); bool_rate["bands"][0]["commission_rate"] = True; cases.append(bool_rate)
        overlap = _payload(); overlap["bands"][1]["price_from_cents"] = 19999; cases.append(overlap)
        invalid_date = _payload(); invalid_date["effective_from"] = "2026-02-30"; cases.append(invalid_date)
        for index, payload in enumerate(cases):
            result = _create(repo, payload, key=f"tariff-invalid-{index:02d}")
            assert result["code"] == "PLANNING_TARIFF_PROFILE_INPUT_INVALID"
        assert repo.list_tariff_profiles()["items"] == []
    finally:
        reset_current_tenant_user_id(token)


def test_profile_and_revision_quotas_do_not_partially_mutate(tmp_path, monkeypatch):
    repo = PlanningWorkspaceRepository(db_path=tmp_path / "planning.sqlite")
    token = _context()
    try:
        monkeypatch.setattr(repo, "MAX_TARIFF_PROFILES_PER_STORE", 1)
        created = _create(repo)
        assert _create(repo, _payload(sku="sku-2"), key="tariff-create-0002")["code"] == "PLANNING_TARIFF_PROFILE_QUOTA_REACHED"
        monkeypatch.setattr(repo, "MAX_TARIFF_REVISIONS_PER_PROFILE", 1)
        result = repo.update_tariff_profile(
            created["profile_id"], _payload(rate="12"), expected_revision=1, expected_state_revision=1,
            idempotency_key="tariff-update-overquota",
        )
        assert result["code"] == "PLANNING_TARIFF_PROFILE_REVISION_QUOTA_REACHED"
        assert repo.get_tariff_profile(created["profile_id"])["revision"] == 1
    finally:
        reset_current_tenant_user_id(token)


def test_profile_create_rolls_back_profile_revision_and_idempotency_together(tmp_path):
    db = tmp_path / "planning.sqlite"
    repo = PlanningWorkspaceRepository(db_path=db)
    repo.get_connection().close()
    connection = sqlite3.connect(db)
    connection.execute("""CREATE TRIGGER abort_tariff_revision BEFORE INSERT ON planning_tariff_profile_revisions
                          BEGIN SELECT RAISE(ABORT, 'synthetic rollback'); END""")
    connection.commit()
    connection.close()
    token = _context()
    try:
        result = _create(repo)
        assert result["code"] == "PLANNING_STORAGE_UNAVAILABLE"
    finally:
        reset_current_tenant_user_id(token)
    connection = sqlite3.connect(db)
    assert connection.execute("SELECT COUNT(*) FROM planning_tariff_profiles").fetchone()[0] == 0
    assert connection.execute("SELECT COUNT(*) FROM planning_tariff_profile_revisions").fetchone()[0] == 0
    assert connection.execute("SELECT COUNT(*) FROM planning_tariff_profile_idempotency").fetchone()[0] == 0
    connection.close()


def test_v2_schema_migration_rolls_back_additive_tables_on_failure(tmp_path):
    db = tmp_path / "legacy.sqlite"
    connection = sqlite3.connect(db)
    connection.execute("CREATE TABLE planning_schema(singleton INTEGER PRIMARY KEY, version INTEGER NOT NULL)")
    connection.execute("INSERT INTO planning_schema VALUES(1, 2)")
    connection.execute("""CREATE TABLE planning_documents (
        document_id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, store_id TEXT NOT NULL,
        title TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN ('ACTIVE','ARCHIVED')),
        revision INTEGER NOT NULL CHECK(revision >= 1), state_revision INTEGER NOT NULL DEFAULT 1,
        schema_version INTEGER NOT NULL, calculation_version INTEGER NOT NULL,
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
        UNIQUE(document_id, owner_id, store_id))""")
    connection.execute("""CREATE TRIGGER abort_schema_upgrade BEFORE UPDATE ON planning_schema
                          BEGIN SELECT RAISE(ABORT, 'synthetic migration rollback'); END""")
    connection.commit(); connection.close()
    repo = PlanningWorkspaceRepository(db_path=db)
    token = _context()
    try:
        assert repo.list_documents()["code"] == "PLANNING_STORAGE_UNAVAILABLE"
    finally:
        reset_current_tenant_user_id(token)
    connection = sqlite3.connect(db)
    tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    version = connection.execute("SELECT version FROM planning_schema").fetchone()[0]
    triggers = {row[0] for row in connection.execute(
        "SELECT name FROM sqlite_master WHERE type='trigger'"
    )}
    connection.close()
    assert version == 2
    assert "planning_tariff_profiles" not in tables
    assert "planning_tariff_profile_revisions" not in tables
    assert "planning_tariff_profile_idempotency" not in tables
    assert "planning_unit_price_observations" not in tables
    assert "planning_unit_price_observation_results" not in tables
    assert "planning_unit_price_observation_idempotency" not in tables
    assert "trg_unit_price_observation_results_no_update" not in triggers
    assert "trg_unit_price_observation_results_no_delete" not in triggers
