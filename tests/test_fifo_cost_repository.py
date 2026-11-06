import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

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


def _tenant(store_id="store-a", owner="owner-1"):
    return make_store_tenant_scope(owner, store_id)


def _source(**overrides):
    source = {
        "kind": "OWNER_CONFIRMATION",
        "method": "OWNER_CONFIRMED_FIFO_CUTOFF",
        "status": "OWNER_CONFIRMED",
        "provenance": "OWNER_CONFIRMED",
        "coverage_status": "OWNER_CONFIRMED",
        "captured_at": "2026-11-06T12:00:00Z",
        "inventory_cutoff": "2026-11-01",
    }
    source.update(overrides)
    return source


def _event(*, kind="OPENING_FIFO_ANCHOR", quantity=5, unit_cost="10.00", **overrides):
    event = {
        "kind": kind,
        "quantity": quantity,
        "effective_date": "2026-11-01",
    }
    if kind in {"OPENING_FIFO_ANCHOR", "COST_LAYER_RECEIPT"}:
        event["unit_cost_rub"] = unit_cost
    if kind == "OPENING_FIFO_ANCHOR":
        event["location_to"] = "OZON"
    event.update(overrides)
    return event


def _preview(repo, *, sku="sku-1", events=None, source=None, store_id="store-a"):
    return repo.preview_command(
        store_id=store_id,
        product_id="product-1",
        offer_id="offer-1",
        sku=sku,
        events=events or [_event()],
        source=source or _source(),
    )


def _commit(repo, preview, *, key="fifo-confirm-0001"):
    return repo.commit_command(
        preview_id=preview["preview_id"],
        active_preview_id=preview["preview_id"],
        idempotency_key=key,
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


def test_fc06_schema_upgrades_atomically_to_latest_without_losing_existing_events(tmp_path):
    db = tmp_path / "schema-v1.sqlite"
    repo = FifoCostRepository(db_path=db)
    token = set_current_tenant_user_id(_tenant())
    try:
        preview = _preview(repo)
        committed = _commit(repo, preview, key="schema-v1-anchor")
        assert committed["error"] is False
    finally:
        reset_current_tenant_user_id(token)

    connection = sqlite3.connect(db)
    try:
        connection.execute("DROP TABLE fifo_cost_command_events")
        connection.execute("DROP TABLE fifo_cost_commands")
        connection.execute("UPDATE fifo_cost_schema SET version=1 WHERE singleton=1")
        connection.commit()
    finally:
        connection.close()

    upgraded = FifoCostRepository(db_path=db).get_connection()
    try:
        assert upgraded.execute(
            "SELECT version FROM fifo_cost_schema WHERE singleton=1"
        ).fetchone()[0] == FifoCostRepository.SCHEMA_VERSION
        assert upgraded.execute("SELECT COUNT(*) FROM fifo_cost_events").fetchone()[0] == 1
        assert upgraded.execute("SELECT COUNT(*) FROM fifo_cost_layers").fetchone()[0] == 1
        assert upgraded.execute("SELECT COUNT(*) FROM fifo_cost_idempotency").fetchone()[0] == 1
        assert upgraded.execute("SELECT COUNT(*) FROM fifo_cost_commands").fetchone()[0] == 0
        assert upgraded.execute("SELECT COUNT(*) FROM fifo_cost_command_events").fetchone()[0] == 0
    finally:
        upgraded.close()


def test_fc20_v8_schema_upgrade_adds_append_only_late_entry_drafts(tmp_path):
    db = tmp_path / "schema-v8.sqlite"
    repo = FifoCostRepository(db_path=db)
    connection = repo.get_connection()
    try:
        connection.execute(
            "CREATE TABLE legacy_marker(value TEXT NOT NULL)"
        )
        connection.execute("INSERT INTO legacy_marker VALUES ('preserved')")
        connection.execute("DROP TRIGGER trg_fifo_cost_late_entry_drafts_no_update")
        connection.execute("DROP TRIGGER trg_fifo_cost_late_entry_drafts_no_delete")
        connection.execute("DROP TABLE fifo_cost_late_entry_drafts")
        connection.execute("UPDATE fifo_cost_schema SET version=8 WHERE singleton=1")
    finally:
        connection.close()

    upgraded = repo.get_connection()
    try:
        assert upgraded.execute(
            "SELECT version FROM fifo_cost_schema WHERE singleton=1"
        ).fetchone()[0] == FifoCostRepository.SCHEMA_VERSION
        assert upgraded.execute(
            "SELECT value FROM legacy_marker"
        ).fetchone()[0] == "preserved"
        assert upgraded.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' "
            "AND name='fifo_cost_late_entry_drafts'"
        ).fetchone()[0] == 1
        assert upgraded.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='trigger' "
            "AND name='trg_fifo_cost_late_entry_drafts_no_delete'"
        ).fetchone()[0] == 1
    finally:
        upgraded.close()


def test_fc22_v9_schema_upgrade_adds_append_only_late_entry_corrections(tmp_path):
    db = tmp_path / "schema-v9.sqlite"
    repo = FifoCostRepository(db_path=db)
    connection = repo.get_connection()
    try:
        connection.execute("CREATE TABLE legacy_marker(value TEXT NOT NULL)")
        connection.execute("INSERT INTO legacy_marker VALUES ('preserved')")
        connection.execute(
            "DROP TRIGGER trg_fifo_cost_late_entry_corrections_no_update",
        )
        connection.execute(
            "DROP TRIGGER trg_fifo_cost_late_entry_corrections_no_delete",
        )
        connection.execute("DROP TABLE fifo_cost_late_entry_corrections")
        connection.execute("UPDATE fifo_cost_schema SET version=9 WHERE singleton=1")
    finally:
        connection.close()

    upgraded = repo.get_connection()
    try:
        assert upgraded.execute(
            "SELECT version FROM fifo_cost_schema WHERE singleton=1"
        ).fetchone()[0] == FifoCostRepository.SCHEMA_VERSION
        assert upgraded.execute(
            "SELECT value FROM legacy_marker"
        ).fetchone()[0] == "preserved"
        assert upgraded.execute("PRAGMA user_version").fetchone()[0] == 0
        assert upgraded.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' "
            "AND name='fifo_cost_late_entry_corrections'"
        ).fetchone()[0] == 1
        assert upgraded.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='trigger' "
            "AND name='trg_fifo_cost_late_entry_corrections_no_update'"
        ).fetchone()[0] == 1
        assert upgraded.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='trigger' "
            "AND name='trg_fifo_cost_late_entry_corrections_no_delete'"
        ).fetchone()[0] == 1
    finally:
        upgraded.close()


def test_fc23_v10_schema_upgrade_adds_append_only_rate_cancellations(tmp_path):
    db = tmp_path / "schema-v10.sqlite"
    repo = FifoCostRepository(db_path=db)
    connection = repo.get_connection()
    try:
        connection.execute("CREATE TABLE legacy_marker(value TEXT NOT NULL)")
        connection.execute("INSERT INTO legacy_marker VALUES ('preserved')")
        connection.execute("DROP TRIGGER trg_fifo_cost_rate_cancellations_no_update")
        connection.execute("DROP TRIGGER trg_fifo_cost_rate_cancellations_no_delete")
        connection.execute("DROP INDEX idx_fifo_cost_rate_cancellations_stream")
        connection.execute("DROP TABLE fifo_cost_rate_cancellations")
        connection.execute("UPDATE fifo_cost_schema SET version=10 WHERE singleton=1")
    finally:
        connection.close()

    upgraded = repo.get_connection()
    try:
        assert upgraded.execute(
            "SELECT version FROM fifo_cost_schema WHERE singleton=1"
        ).fetchone()[0] == FifoCostRepository.SCHEMA_VERSION
        assert upgraded.execute(
            "SELECT value FROM legacy_marker"
        ).fetchone()[0] == "preserved"
        assert upgraded.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' "
            "AND name='fifo_cost_rate_cancellations'"
        ).fetchone()[0] == 1
        assert upgraded.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='trigger' "
            "AND name='trg_fifo_cost_rate_cancellations_no_update'"
        ).fetchone()[0] == 1
        assert upgraded.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='trigger' "
            "AND name='trg_fifo_cost_rate_cancellations_no_delete'"
        ).fetchone()[0] == 1
    finally:
        upgraded.close()


def test_fc11_schema_v2_upgrade_adds_rate_history_without_changing_other_data(tmp_path):
    db = tmp_path / "schema-v2.sqlite"
    repo = FifoCostRepository(db_path=db)
    connection = repo.get_connection()
    try:
        connection.execute("UPDATE fifo_cost_schema SET version=2 WHERE singleton=1")
        connection.execute(
            "INSERT INTO fifo_cost_streams(stream_id, store_id, product_id, offer_id, sku, "
            "identity_fingerprint, policy_version, state, revision, created_at, updated_at) "
            "VALUES ('stream-v2', 'store-a', 'product-1', 'offer-1', 'sku-1', "
            "'identity-v2', 1, 'FIFO_READY', 1, 'created', 'updated')"
        )
        connection.commit()
    finally:
        connection.close()

    upgraded = FifoCostRepository(db_path=db).get_connection()
    try:
        assert upgraded.execute(
            "SELECT version FROM fifo_cost_schema WHERE singleton=1"
        ).fetchone()[0] == FifoCostRepository.SCHEMA_VERSION
        assert tuple(upgraded.execute(
            "SELECT state, revision FROM fifo_cost_streams WHERE stream_id='stream-v2'"
        ).fetchone()) == ("FIFO_READY", 1)
        assert upgraded.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' "
            "AND name='fifo_cost_rate_changes'"
        ).fetchone()[0] == 1
        assert upgraded.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='trigger' "
            "AND name='trg_fifo_cost_rate_changes_no_update'"
        ).fetchone()[0] == 1
    finally:
        upgraded.close()


def test_fc13_schema_v3_upgrade_adds_append_only_supply_evidence(tmp_path):
    db = tmp_path / "schema-v3.sqlite"
    repo = FifoCostRepository(db_path=db)
    connection = repo.get_connection()
    try:
        connection.execute("UPDATE fifo_cost_schema SET version=3 WHERE singleton=1")
        connection.execute(
            "INSERT INTO fifo_cost_streams(stream_id, store_id, product_id, offer_id, sku, "
            "identity_fingerprint, policy_version, state, revision, created_at, updated_at) "
            "VALUES ('stream-v3', 'store-a', 'product-1', 'offer-1', 'sku-1', "
            "'identity-v3', 1, 'FIFO_READY', 1, 'created', 'updated')"
        )
        connection.commit()
    finally:
        connection.close()

    upgraded = FifoCostRepository(db_path=db).get_connection()
    try:
        assert upgraded.execute(
            "SELECT version FROM fifo_cost_schema WHERE singleton=1"
        ).fetchone()[0] == FifoCostRepository.SCHEMA_VERSION
        assert tuple(upgraded.execute(
            "SELECT state, revision FROM fifo_cost_streams WHERE stream_id='stream-v3'"
        ).fetchone()) == ("FIFO_READY", 1)
        assert upgraded.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' "
            "AND name='fifo_cost_supply_evidence'"
        ).fetchone()[0] == 1
        assert upgraded.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='trigger' "
            "AND name='trg_fifo_cost_supply_evidence_no_update'"
        ).fetchone()[0] == 1
    finally:
        upgraded.close()


def test_fc14_schema_v4_upgrade_adds_append_only_rate_reconciliations(tmp_path):
    db = tmp_path / "schema-v4.sqlite"
    repo = FifoCostRepository(db_path=db)
    connection = repo.get_connection()
    try:
        connection.execute("UPDATE fifo_cost_schema SET version=4 WHERE singleton=1")
        connection.execute(
            "INSERT INTO fifo_cost_streams(stream_id, store_id, product_id, offer_id, sku, "
            "identity_fingerprint, policy_version, state, revision, created_at, updated_at) "
            "VALUES ('stream-v4', 'store-a', 'product-1', 'offer-1', 'sku-1', "
            "'identity-v4', 1, 'FIFO_READY', 1, 'created', 'updated')"
        )
        connection.commit()
    finally:
        connection.close()

    upgraded = FifoCostRepository(db_path=db).get_connection()
    try:
        assert upgraded.execute(
            "SELECT version FROM fifo_cost_schema WHERE singleton=1"
        ).fetchone()[0] == FifoCostRepository.SCHEMA_VERSION
        assert tuple(upgraded.execute(
            "SELECT state, revision FROM fifo_cost_streams WHERE stream_id='stream-v4'"
        ).fetchone()) == ("FIFO_READY", 1)
        assert upgraded.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' "
            "AND name='fifo_cost_rate_reconciliations'"
        ).fetchone()[0] == 1
        assert upgraded.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='trigger' "
            "AND name='trg_fifo_cost_rate_reconciliations_no_update'"
        ).fetchone()[0] == 1
    finally:
        upgraded.close()


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


def test_preview_is_read_only_and_commit_is_atomic_and_idempotent(tmp_path):
    db = tmp_path / "command.sqlite"
    repo = FifoCostRepository(db_path=db)
    token = set_current_tenant_user_id(_tenant())
    try:
        preview = _preview(repo)
        assert preview["error"] is False
        assert preview["code"] == "FIFO_PREVIEW_READY"
        assert preview["expected_revision"] == 0

        connection = sqlite3.connect(db)
        try:
            assert connection.execute("SELECT COUNT(*) FROM fifo_cost_streams").fetchone()[0] == 0
            assert connection.execute("SELECT COUNT(*) FROM fifo_cost_events").fetchone()[0] == 0
            assert connection.execute("SELECT COUNT(*) FROM fifo_cost_sources").fetchone()[0] == 0
        finally:
            connection.close()

        committed = _commit(repo, preview)
        assert committed["error"] is False
        assert committed["idempotent"] is False
        assert committed["revision"] == 1
        replayed = _commit(repo, preview)
        assert replayed["error"] is False
        assert replayed["idempotent"] is True
        assert replayed["event_ids"] == committed["event_ids"]
        assert replayed["command_id"] == committed["command_id"]

        connection = sqlite3.connect(db)
        try:
            assert connection.execute("SELECT revision FROM fifo_cost_streams").fetchone()[0] == 1
            assert connection.execute("SELECT COUNT(*) FROM fifo_cost_events").fetchone()[0] == 1
            assert connection.execute("SELECT COUNT(*) FROM fifo_cost_layers").fetchone()[0] == 1
            assert connection.execute("SELECT COUNT(*) FROM fifo_cost_commands").fetchone()[0] == 1
            assert connection.execute("SELECT COUNT(*) FROM fifo_cost_command_events").fetchone()[0] == 1
            assert connection.execute("SELECT COUNT(*) FROM fifo_cost_idempotency").fetchone()[0] == 1
            event_source = connection.execute(
                "SELECT provenance, source_fingerprint FROM fifo_cost_events"
            ).fetchone()
            assert event_source[0] == "OWNER_CONFIRMED"
            assert len(event_source[1]) == 64
        finally:
            connection.close()
    finally:
        reset_current_tenant_user_id(token)


def test_equivalent_preview_payload_has_stable_fingerprint(tmp_path):
    repo = FifoCostRepository(db_path=tmp_path / "stable-hash.sqlite")
    token = set_current_tenant_user_id(_tenant())
    try:
        first = _preview(repo)
        second = _preview(repo)
        assert first["preview_id"] != second["preview_id"]
        assert first["payload_fingerprint"] == second["payload_fingerprint"]
        committed = _commit(repo, second, key="stable-payload-key1")
        assert committed["error"] is False
    finally:
        reset_current_tenant_user_id(token)


def test_idempotency_key_cannot_replay_a_different_payload(tmp_path):
    repo = FifoCostRepository(db_path=tmp_path / "idempotency.sqlite")
    token = set_current_tenant_user_id(_tenant())
    try:
        first = _preview(repo)
        result = _commit(repo, first, key="same-confirm-key")
        assert result["error"] is False
        changed = _preview(repo, events=[_event(
            kind="COST_LAYER_RECEIPT", quantity=6,
        )])
        conflict = _commit(repo, changed, key="same-confirm-key")
        assert conflict == {"error": True, "code": "FIFO_IDEMPOTENCY_CONFLICT"}
        connection = sqlite3.connect(repo.db_path)
        try:
            assert connection.execute("SELECT COUNT(*) FROM fifo_cost_events").fetchone()[0] == 1
            assert connection.execute("SELECT revision FROM fifo_cost_streams").fetchone()[0] == 1
        finally:
            connection.close()
    finally:
        reset_current_tenant_user_id(token)


def test_reused_source_fingerprint_cannot_change_its_reference_set(tmp_path):
    repo = FifoCostRepository(db_path=tmp_path / "source-fingerprint.sqlite")
    token = set_current_tenant_user_id(_tenant())
    fingerprint = "a" * 64
    try:
        first = _preview(repo, source=_source(
            fingerprint=fingerprint,
            references=[{"kind": "SUPPLY", "digest": "b" * 64}],
        ))
        assert _commit(repo, first, key="source-fingerprint1")["error"] is False

        changed = _preview(repo, events=[_event(
            kind="COST_LAYER_RECEIPT", quantity=2,
        )], source=_source(
            fingerprint=fingerprint,
            references=[{"kind": "SUPPLY", "digest": "c" * 64}],
        ))
        result = _commit(repo, changed, key="source-fingerprint2")
        assert result == {"error": True, "code": "FIFO_SOURCE_FINGERPRINT_CONFLICT"}
        connection = sqlite3.connect(repo.db_path)
        try:
            assert connection.execute("SELECT COUNT(*) FROM fifo_cost_events").fetchone()[0] == 1
            assert connection.execute("SELECT revision FROM fifo_cost_streams").fetchone()[0] == 1
            refs = connection.execute(
                "SELECT reference_digest FROM fifo_cost_source_refs"
            ).fetchall()
            assert [row[0] for row in refs] == ["b" * 64]
        finally:
            connection.close()
    finally:
        reset_current_tenant_user_id(token)


def test_stale_preview_from_another_product_cannot_commit(tmp_path):
    repo = FifoCostRepository(db_path=tmp_path / "stale-preview.sqlite")
    token = set_current_tenant_user_id(_tenant())
    try:
        old = _preview(repo, sku="sku-1")
        current = _preview(repo, sku="sku-2")
        rejected = _commit(repo, old, key="stale-callback-01")
        assert rejected == {"error": True, "code": "FIFO_PREVIEW_STALE"}
        accepted = _commit(repo, current, key="current-callback1")
        assert accepted["error"] is False
        connection = sqlite3.connect(repo.db_path)
        try:
            assert connection.execute("SELECT COUNT(*) FROM fifo_cost_streams").fetchone()[0] == 1
            assert connection.execute("SELECT COUNT(*) FROM fifo_cost_events").fetchone()[0] == 1
        finally:
            connection.close()
    finally:
        reset_current_tenant_user_id(token)


def test_commit_rejects_preview_after_owner_or_store_context_changes(tmp_path):
    repo = FifoCostRepository(db_path=tmp_path / "context.sqlite")
    token = set_current_tenant_user_id(_tenant("store-a"))
    try:
        preview = _preview(repo, store_id="store-a")
    finally:
        reset_current_tenant_user_id(token)

    token = set_current_tenant_user_id(_tenant("store-b"))
    try:
        rejected = repo.commit_command(
            preview_id=preview["preview_id"],
            active_preview_id=preview["preview_id"],
            idempotency_key="wrong-store-key1",
        )
        assert rejected["error"] is True
    finally:
        reset_current_tenant_user_id(token)

    connection = sqlite3.connect(repo.db_path)
    try:
        assert connection.execute("SELECT COUNT(*) FROM fifo_cost_events").fetchone()[0] == 0
    finally:
        connection.close()


def test_concurrent_commands_with_same_expected_revision_have_one_winner(tmp_path):
    db = tmp_path / "concurrent.sqlite"
    first_repo = FifoCostRepository(db_path=db)
    second_repo = FifoCostRepository(db_path=db)
    token = set_current_tenant_user_id(_tenant())
    try:
        first_preview = _preview(first_repo)
        assert first_preview["expected_revision"] == 0
    finally:
        reset_current_tenant_user_id(token)

    def commit(repo, preview, key):
        context_token = set_current_tenant_user_id(_tenant())
        try:
            return _commit(repo, preview, key=key)
        finally:
            reset_current_tenant_user_id(context_token)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(
            lambda values: commit(*values),
            [
                (first_repo, first_preview, "concurrent-a-key"),
                (second_repo, first_preview, "concurrent-b-key"),
            ],
        ))
    assert sum(result["error"] is False for result in results) == 1
    assert sum(result["code"] == "FIFO_REVISION_CONFLICT" for result in results) == 1
    connection = sqlite3.connect(db)
    try:
        assert connection.execute("SELECT revision FROM fifo_cost_streams").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM fifo_cost_events").fetchone()[0] == 1
    finally:
        connection.close()


def test_new_store_draft_invalidates_old_store_callback_for_same_owner(tmp_path):
    repo = FifoCostRepository(db_path=tmp_path / "owner-store-draft.sqlite")
    token = set_current_tenant_user_id(_tenant("store-a"))
    try:
        old_store = _preview(repo, store_id="store-a")
    finally:
        reset_current_tenant_user_id(token)

    token = set_current_tenant_user_id(_tenant("store-b"))
    try:
        _preview(repo, store_id="store-b")
    finally:
        reset_current_tenant_user_id(token)

    token = set_current_tenant_user_id(_tenant("store-a"))
    try:
        result = _commit(repo, old_store, key="old-store-callback")
        assert result == {"error": True, "code": "FIFO_PREVIEW_STALE"}
    finally:
        reset_current_tenant_user_id(token)

    connection = sqlite3.connect(repo.db_path)
    try:
        assert connection.execute("SELECT COUNT(*) FROM fifo_cost_events").fetchone()[0] == 0
    finally:
        connection.close()


def test_invalid_batch_target_rolls_back_all_command_writes(tmp_path):
    repo = FifoCostRepository(db_path=tmp_path / "atomic-command.sqlite")
    token = set_current_tenant_user_id(_tenant())
    try:
        batch = [
            _event(kind="COST_LAYER_RECEIPT", quantity=7, unit_cost="20.00"),
            _event(
                kind="CORRECTION", quantity=7,
                supersedes_event_id="evt_" + "f" * 32,
                reason_code="QUANTITY_CORRECTION",
            ),
        ]
        preview = _preview(repo, events=batch)
        assert preview["error"] is False
        result = _commit(repo, preview, key="atomic-command01")
        assert result == {"error": True, "code": "FIFO_EVENT_TARGET_INVALID"}
        connection = sqlite3.connect(repo.db_path)
        try:
            for table in (
                "fifo_cost_streams", "fifo_cost_sources", "fifo_cost_events",
                "fifo_cost_layers", "fifo_cost_commands", "fifo_cost_idempotency",
            ):
                assert connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
        finally:
            connection.close()
    finally:
        reset_current_tenant_user_id(token)


def test_preview_validates_decimal_components_dates_and_source_reference_digests(tmp_path):
    repo = FifoCostRepository(db_path=tmp_path / "validation.sqlite")
    token = set_current_tenant_user_id(_tenant())
    try:
        bad_amount = _preview(repo, events=[_event(unit_cost=1.1)])
        assert bad_amount == {"error": True, "code": "FIFO_MONEY_INPUT_INVALID"}
        incomplete_cost = _preview(repo, events=[_event(
            unit_cost="12.00", purchase_cost_rub="10.00",
        )])
        assert incomplete_cost == {"error": True, "code": "FIFO_COST_COMPONENTS_INCOMPLETE"}
        null_component = _preview(repo, events=[_event(
            unit_cost="12.00", purchase_cost_rub="10.00",
            delivery_cost_rub=None, packaging_cost_rub="2.00",
        )])
        assert null_component == {"error": True, "code": "FIFO_MONEY_INPUT_INVALID"}
        naive_date = _preview(repo, events=[_event(
            kind="COST_LAYER_RECEIPT", effective_date=None,
            effective_at="2026-11-01T12:00:00",
        )])
        assert naive_date == {"error": True, "code": "FIFO_TIMESTAMP_INVALID"}
        utc_and_store_date = _preview(repo, events=[_event(
            kind="COST_LAYER_RECEIPT", effective_at="2026-11-01T21:30:00Z",
            effective_date="2026-11-02",
        )])
        assert utc_and_store_date["error"] is False
        raw_reference = _preview(repo, source=_source(
            references=[{"kind": "SUPPLY", "digest": "2000070135564"}],
        ))
        assert raw_reference == {"error": True, "code": "FIFO_SOURCE_REFERENCE_INVALID"}
        model = _preview(repo, source=_source(
            provenance="MODEL_ASSUMPTION", status="MODEL_ONLY",
        ))
        assert model == {"error": True, "code": "FIFO_MODEL_SOURCE_NOT_PERSISTABLE"}
    finally:
        reset_current_tenant_user_id(token)


def test_preview_expiration_uses_injected_aware_clock(tmp_path):
    now = [datetime(2026, 11, 6, 12, tzinfo=timezone.utc)]
    repo = FifoCostRepository(db_path=tmp_path / "expires.sqlite", now_provider=lambda: now[0])
    token = set_current_tenant_user_id(_tenant())
    try:
        preview = _preview(repo)
        now[0] = datetime(2026, 11, 6, 13, tzinfo=timezone.utc)
        result = _commit(repo, preview, key="expired-confirm1")
        assert result == {"error": True, "code": "FIFO_PREVIEW_STALE"}
    finally:
        reset_current_tenant_user_id(token)


@pytest.mark.parametrize(
    ("source_overrides", "event_overrides", "code"),
    [
        ({"method": "TELEGRAM_COST_ENTRY"}, {}, "FIFO_ANCHOR_OWNER_CONFIRMATION_REQUIRED"),
        ({"captured_at": None}, {}, "FIFO_ANCHOR_CAPTURE_TIME_REQUIRED"),
        ({}, {"effective_date": "2026-11-02"}, "FIFO_ANCHOR_CUTOFF_MISMATCH"),
        ({}, {"effective_at": "2026-11-01T12:00:00Z"}, "FIFO_ANCHOR_CUTOFF_MISMATCH"),
    ],
)
def test_opening_anchor_requires_exact_owner_source_and_date_only_cutoff(
    tmp_path, source_overrides, event_overrides, code,
):
    repository = FifoCostRepository(db_path=tmp_path / "strict-anchor.sqlite")
    token = set_current_tenant_user_id(make_store_tenant_scope("owner-1", "store-a"))
    try:
        event = _event(**event_overrides)
        result = repository.preview_command(
            store_id="store-a", product_id="product-1", offer_id="offer-1",
            sku="sku-1", events=[event], source=_source(**source_overrides),
        )
        assert result == {"error": True, "code": code}
        connection = repository.get_connection()
        try:
            assert connection.execute("SELECT COUNT(*) FROM fifo_cost_events").fetchone()[0] == 0
            assert connection.execute("SELECT COUNT(*) FROM fifo_cost_streams").fetchone()[0] == 0
            assert connection.execute("SELECT COUNT(*) FROM fifo_cost_commands").fetchone()[0] == 0
        finally:
            connection.close()
    finally:
        reset_current_tenant_user_id(token)
