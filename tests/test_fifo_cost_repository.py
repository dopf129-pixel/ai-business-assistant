import sqlite3

import pytest

from services.fifo_cost_repository import FifoCostRepository
from services.ozon_account_repository import make_store_tenant_scope
from services.tenant_context import (
    reset_current_tenant_user_id,
    set_current_tenant_user_id,
)


def _insert_stream(connection, *, stream_id, store_id, sku):
    connection.execute(
        """INSERT INTO fifo_cost_streams (
            stream_id, store_id, product_id, offer_id, sku,
            identity_fingerprint, policy_version, state, revision,
            created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, 1, 'LEGACY', 0, 'now', 'now')""",
        (stream_id, store_id, "product", "offer", sku, f"identity-{sku}"),
    )


def test_additive_schema_preserves_legacy_cost_and_planning_data(tmp_path):
    db = tmp_path / "legacy.sqlite"
    connection = sqlite3.connect(db)
    connection.execute("PRAGMA user_version=41")
    connection.execute(
        "CREATE TABLE planning_schema(singleton INTEGER PRIMARY KEY, version INTEGER NOT NULL)"
    )
    connection.execute("INSERT INTO planning_schema VALUES (1, 12)")
    connection.execute(
        "CREATE TABLE product_costs (sku TEXT PRIMARY KEY, cost TEXT NOT NULL)"
    )
    connection.execute("INSERT INTO product_costs VALUES ('sku-old', '12.34')")
    connection.execute(
        "CREATE TABLE product_cost_history (sku TEXT, effective_from TEXT, cost TEXT)"
    )
    connection.execute(
        "INSERT INTO product_cost_history VALUES ('sku-old', '2025-01-01', '11.00')"
    )
    connection.commit()
    connection.close()

    fifo = FifoCostRepository(db_path=db)
    connection = fifo.get_connection()
    try:
        assert connection.execute(
            "SELECT version FROM fifo_cost_schema WHERE singleton=1"
        ).fetchone()[0] == fifo.SCHEMA_VERSION
        assert connection.execute(
            "SELECT version FROM planning_schema WHERE singleton=1"
        ).fetchone()[0] == 12
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 41
        assert tuple(connection.execute(
            "SELECT sku, cost FROM product_costs"
        ).fetchone()) == ("sku-old", "12.34")
        assert tuple(connection.execute(
            "SELECT sku, effective_from, cost FROM product_cost_history"
        ).fetchone()) == ("sku-old", "2025-01-01", "11.00")
        assert connection.execute(
            "SELECT COUNT(*) FROM fifo_cost_streams"
        ).fetchone()[0] == 0
    finally:
        connection.close()


def test_repeated_initialization_is_idempotent_and_evidence_is_append_only(tmp_path):
    db = tmp_path / "repeat.sqlite"
    fifo = FifoCostRepository(db_path=db)
    connection = fifo.get_connection()
    try:
        connection.execute(
            """INSERT INTO fifo_cost_sources (
                source_id, store_id, source_kind, source_method, source_status,
                provenance, source_fingerprint, coverage_status, created_at
            ) VALUES ('source-1', 'store-a', 'OWNER', 'TELEGRAM',
                'OWNER_CONFIRMED', 'OWNER_CONFIRMED', 'fingerprint-1',
                'OWNER_CONFIRMED', 'now')"""
        )
        _insert_stream(connection, stream_id="stream-1", store_id="store-a", sku="sku-1")
        connection.execute(
            """INSERT INTO fifo_cost_events (
                event_id, stream_id, event_kind, event_schema_version, recorded_at,
                quantity, provenance, completeness, source_identity_digest, created_at
            ) VALUES ('sale-1', 'stream-1', 'PHYSICAL_SALE', 1, 'now', 1,
                'OZON_CONFIRMED_FIELD', 'COMPLETE', 'sale-digest', 'now')"""
        )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """INSERT INTO fifo_cost_events (
                    event_id, stream_id, event_kind, event_schema_version, recorded_at,
                    quantity, provenance, completeness, source_identity_digest, created_at
                ) VALUES ('sale-duplicate', 'stream-1', 'PHYSICAL_SALE', 1, 'later', 1,
                    'OZON_CONFIRMED_FIELD', 'COMPLETE', 'sale-digest', 'later')"""
            )
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute(
                "UPDATE fifo_cost_sources SET source_status='PARTIAL' "
                "WHERE source_id='source-1'"
            )
        table_names_before = {
            row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        trigger_names_before = {
            row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='trigger'"
            )
        }
    finally:
        connection.close()

    reopened = fifo.get_connection()
    try:
        assert {
            row[0] for row in reopened.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        } == table_names_before
        assert {
            row[0] for row in reopened.execute(
                "SELECT name FROM sqlite_master WHERE type='trigger'"
            )
        } == trigger_names_before
        assert reopened.execute(
            "SELECT version FROM fifo_cost_schema WHERE singleton=1"
        ).fetchone()[0] == fifo.SCHEMA_VERSION
    finally:
        reopened.close()


def test_mid_migration_failure_rolls_back_all_new_objects(tmp_path):
    db = tmp_path / "migration-failure.sqlite"
    connection = sqlite3.connect(db)
    connection.execute("CREATE TABLE legacy_marker (value TEXT NOT NULL)")
    connection.execute("INSERT INTO legacy_marker VALUES ('preserve')")
    # A malformed object with a FIFO-owned name makes the following index
    # creation fail after earlier DDL has run, exercising transaction rollback.
    connection.execute("CREATE TABLE fifo_cost_events (malformed INTEGER)")
    connection.commit()
    connection.close()

    with pytest.raises(sqlite3.OperationalError, match="no such column"):
        FifoCostRepository(db_path=db).get_connection()

    connection = sqlite3.connect(db)
    try:
        tables = {
            row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert tables == {"legacy_marker", "fifo_cost_events"}
        assert connection.execute(
            "SELECT value FROM legacy_marker"
        ).fetchone()[0] == "preserve"
        assert connection.execute(
            "PRAGMA user_version"
        ).fetchone()[0] == 0
    finally:
        connection.close()


def test_future_fifo_schema_is_rejected_without_partial_migration(tmp_path):
    db = tmp_path / "future.sqlite"
    connection = sqlite3.connect(db)
    connection.execute(
        "CREATE TABLE fifo_cost_schema(singleton INTEGER PRIMARY KEY, version INTEGER NOT NULL)"
    )
    connection.execute("INSERT INTO fifo_cost_schema VALUES (1, 99)")
    connection.execute("CREATE TABLE legacy_marker(value TEXT)")
    connection.execute("INSERT INTO legacy_marker VALUES ('keep')")
    connection.commit()
    connection.close()

    with pytest.raises(sqlite3.DatabaseError, match="unsupported FIFO"):
        FifoCostRepository(db_path=db).get_connection()

    connection = sqlite3.connect(db)
    try:
        tables = {
            row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert tables == {"fifo_cost_schema", "legacy_marker"}
        assert connection.execute(
            "SELECT version FROM fifo_cost_schema"
        ).fetchone()[0] == 99
        assert connection.execute("SELECT value FROM legacy_marker").fetchone()[0] == "keep"
    finally:
        connection.close()


def test_database_isolated_by_tenant_and_store_scope(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_ASSISTANT_STORAGE_ROOT", str(tmp_path))
    scopes = (
        make_store_tenant_scope("owner-1", "store-a"),
        make_store_tenant_scope("owner-1", "store-b"),
        make_store_tenant_scope("owner-2", "store-a"),
    )
    paths = []
    for index, tenant_scope in enumerate(scopes, start=1):
        token = set_current_tenant_user_id(tenant_scope)
        try:
            repository = FifoCostRepository()
            paths.append(repository.db_path.resolve())
            connection = repository.get_connection()
            try:
                _insert_stream(
                    connection, stream_id=f"stream-{index}",
                    store_id=tenant_scope, sku=f"sku-{index}",
                )
            finally:
                connection.close()
        finally:
            reset_current_tenant_user_id(token)

    assert len(set(paths)) == len(scopes)
    for index, tenant_scope in enumerate(scopes, start=1):
        token = set_current_tenant_user_id(tenant_scope)
        try:
            connection = FifoCostRepository().get_connection()
            try:
                rows = connection.execute(
                    "SELECT stream_id, store_id FROM fifo_cost_streams"
                ).fetchall()
                assert [tuple(row) for row in rows] == [
                    (f"stream-{index}", tenant_scope)
                ]
            finally:
                connection.close()
        finally:
            reset_current_tenant_user_id(token)
