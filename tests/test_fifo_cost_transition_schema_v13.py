import hashlib
import json
import sqlite3

import pytest
from cryptography.fernet import Fernet

from services.fifo_cost_repository import FifoCostRepository
from services.tenant_cipher_provider import (
    decrypt_tenant_value,
    encrypt_tenant_value,
    get_tenant_fernet,
)


_MASTER_KEY = Fernet.generate_key().decode("ascii")
_WRONG_KEY = Fernet.generate_key().decode("ascii")


def _seed_rate(connection):
    connection.execute(
        """INSERT INTO fifo_cost_sources (
            source_id, store_id, source_kind, source_method, source_status,
            provenance, source_fingerprint, coverage_status, created_at
        ) VALUES ('source-1', 'store-1', 'OWNER', 'TEST', 'OWNER_CONFIRMED',
                  'OWNER_CONFIRMED', ?, 'OWNER_CONFIRMED', '2026-11-07T10:00:00Z')""",
        ("a" * 64,),
    )
    connection.execute(
        """INSERT INTO fifo_cost_streams (
            stream_id, store_id, product_id, offer_id, sku, identity_fingerprint,
            policy_version, state, revision, created_at, updated_at
        ) VALUES ('stream-1', 'store-1', 'product-1', 'offer-1', 'sku-1',
                  'identity-1', 1, 'LEGACY', 0, 'now', 'now')"""
    )
    connection.execute(
        """INSERT INTO fifo_cost_rate_changes (
            rate_change_id, stream_id, stream_revision, rate_sequence,
            effective_date, unit_cost_rub, cost_input_mode, purchase_cost_rub,
            delivery_cost_rub, packaging_cost_rub, owner_old_home_units,
            source_id, source_fingerprint, payload_fingerprint, idempotency_key,
            recorded_at, captured_at
        ) VALUES ('rate-1', 'stream-1', 1, 1, '2026-11-07', '21.00',
                  'COMPONENTS', '18.00', '2.00', '1.00', 0, 'source-1', ?, ?,
                  'rate-key-0001', '2026-11-07T10:00:00Z', '2026-11-07T10:00:00Z')""",
        ("a" * 64, "b" * 64),
    )


def _downgrade_rate_table_to_v12(database):
    connection = sqlite3.connect(database, isolation_level=None)
    try:
        connection.execute("PRAGMA foreign_keys=OFF")
        connection.execute("BEGIN IMMEDIATE")
        for table in (
            "fifo_cost_transition_commits", "fifo_cost_transition_previews",
            "fifo_cost_report_evidence", "fifo_cost_supply_observations",
            "fifo_cost_supply_declarations", "fifo_cost_transition_case_revisions",
            "fifo_cost_transition_cases",
        ):
            connection.execute(f"DROP TABLE {table}")
        connection.execute(
            """CREATE TABLE fifo_cost_rate_changes_v12 (
                rate_change_id TEXT PRIMARY KEY,
                stream_id TEXT NOT NULL REFERENCES fifo_cost_streams(stream_id),
                stream_revision INTEGER NOT NULL CHECK(stream_revision >= 1),
                rate_sequence INTEGER NOT NULL CHECK(rate_sequence >= 1),
                effective_date TEXT NOT NULL,
                unit_cost_rub TEXT NOT NULL,
                purchase_cost_rub TEXT NOT NULL,
                delivery_cost_rub TEXT NOT NULL,
                packaging_cost_rub TEXT NOT NULL,
                owner_old_home_units INTEGER NOT NULL CHECK(
                    owner_old_home_units >= 0 AND owner_old_home_units <= 1000000
                ),
                source_id TEXT NOT NULL REFERENCES fifo_cost_sources(source_id),
                source_fingerprint TEXT NOT NULL,
                payload_fingerprint TEXT NOT NULL,
                idempotency_key TEXT NOT NULL,
                recorded_at TEXT NOT NULL,
                captured_at TEXT NOT NULL,
                UNIQUE(stream_id, rate_sequence),
                UNIQUE(stream_id, idempotency_key)
            )"""
        )
        connection.execute(
            """INSERT INTO fifo_cost_rate_changes_v12 (
                rate_change_id, stream_id, stream_revision, rate_sequence,
                effective_date, unit_cost_rub, purchase_cost_rub,
                delivery_cost_rub, packaging_cost_rub, owner_old_home_units,
                source_id, source_fingerprint, payload_fingerprint, idempotency_key,
                recorded_at, captured_at
            ) SELECT rate_change_id, stream_id, stream_revision, rate_sequence,
                     effective_date, unit_cost_rub, purchase_cost_rub,
                     delivery_cost_rub, packaging_cost_rub, owner_old_home_units,
                     source_id, source_fingerprint, payload_fingerprint,
                     idempotency_key, recorded_at, captured_at
              FROM fifo_cost_rate_changes"""
        )
        connection.execute("DROP TABLE fifo_cost_rate_changes")
        connection.execute(
            "ALTER TABLE fifo_cost_rate_changes_v12 RENAME TO fifo_cost_rate_changes"
        )
        connection.execute(
            "UPDATE fifo_cost_schema SET version=12 WHERE singleton=1"
        )
        connection.execute(
            "CREATE INDEX idx_fifo_cost_rate_changes_order "
            "ON fifo_cost_rate_changes(stream_id, effective_date, rate_sequence)"
        )
        for operation in ("UPDATE", "DELETE"):
            connection.execute(
                f"CREATE TRIGGER trg_fifo_cost_rate_changes_no_{operation.lower()} "
                f"BEFORE {operation} ON fifo_cost_rate_changes "
                "BEGIN SELECT RAISE(ABORT, 'FIFO evidence is append-only'); END"
            )
        connection.execute(
            "CREATE INDEX custom_rate_migration_index "
            "ON fifo_cost_rate_changes(stream_id, payload_fingerprint)"
        )
        connection.execute(
            """CREATE TRIGGER custom_rate_migration_trigger
               BEFORE UPDATE ON fifo_cost_rate_changes
               BEGIN SELECT RAISE(ABORT, 'custom rate trigger'); END"""
        )
        connection.commit()
    finally:
        connection.close()


def _rate_row_digest(connection):
    columns = [
        row[1] for row in connection.execute(
            "PRAGMA table_info(fifo_cost_rate_changes)"
        ) if row[1] != "cost_input_mode"
    ]
    row = connection.execute(
        f"SELECT {', '.join(columns)} FROM fifo_cost_rate_changes WHERE rate_change_id='rate-1'"
    ).fetchone()
    return hashlib.sha256(
        json.dumps(tuple(row), separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _rate_sql_objects(connection):
    return tuple(tuple(row) for row in connection.execute(
        """SELECT type, name, sql FROM sqlite_master
           WHERE tbl_name='fifo_cost_rate_changes'
             AND type IN ('index', 'trigger') AND sql IS NOT NULL
           ORDER BY type, name"""
    ).fetchall())


def _schema_objects(connection):
    return tuple(tuple(row) for row in connection.execute(
        "SELECT type, name, sql FROM sqlite_master ORDER BY type, name"
    ).fetchall())


def test_fresh_schema_v13_accepts_only_consistent_cost_input_modes(tmp_path):
    repository = FifoCostRepository(db_path=tmp_path / "fresh-v13.sqlite")
    connection = repository.get_connection()
    try:
        _seed_rate(connection)
        connection.execute(
            """INSERT INTO fifo_cost_rate_changes (
                rate_change_id, stream_id, stream_revision, rate_sequence,
                effective_date, unit_cost_rub, cost_input_mode, purchase_cost_rub,
                delivery_cost_rub, packaging_cost_rub, owner_old_home_units,
                source_id, source_fingerprint, payload_fingerprint, idempotency_key,
                recorded_at, captured_at
            ) VALUES ('rate-total', 'stream-1', 2, 2, '2026-11-08', '14.65',
                      'TOTAL_LANDED', NULL, NULL, NULL, 0, 'source-1', ?, ?,
                      'rate-key-0002', 'now', 'now')""",
            ("c" * 64, "d" * 64),
        )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """INSERT INTO fifo_cost_rate_changes (
                    rate_change_id, stream_id, stream_revision, rate_sequence,
                    effective_date, unit_cost_rub, cost_input_mode,
                    purchase_cost_rub, delivery_cost_rub, packaging_cost_rub,
                    owner_old_home_units, source_id, source_fingerprint,
                    payload_fingerprint, idempotency_key, recorded_at, captured_at
                ) VALUES ('rate-invalid', 'stream-1', 3, 3, '2026-11-09', '14.65',
                          'TOTAL_LANDED', '14.65', NULL, NULL, 0, 'source-1', ?, ?,
                          'rate-key-0003', 'now', 'now')""",
                ("e" * 64, "f" * 64),
            )
        assert connection.execute(
            "SELECT version FROM fifo_cost_schema WHERE singleton=1"
        ).fetchone()[0] == FifoCostRepository.SCHEMA_VERSION == 15
        assert tuple(connection.execute(
            "SELECT cost_input_mode, purchase_cost_rub, delivery_cost_rub, packaging_cost_rub "
            "FROM fifo_cost_rate_changes WHERE rate_change_id='rate-total'"
        ).fetchone()) == ("TOTAL_LANDED", None, None, None)
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        connection.close()


def test_v12_migration_preserves_rate_values_custom_objects_and_child_foreign_keys(tmp_path):
    database = tmp_path / "v12-upgrade.sqlite"
    repository = FifoCostRepository(db_path=database)
    connection = repository.get_connection()
    try:
        _seed_rate(connection)
    finally:
        connection.close()
    _downgrade_rate_table_to_v12(database)

    before = sqlite3.connect(database)
    try:
        before_digest = _rate_row_digest(before)
        before_objects = _rate_sql_objects(before)
    finally:
        before.close()

    migrated = FifoCostRepository(db_path=database).get_connection()
    try:
        assert migrated.execute(
            "SELECT version FROM fifo_cost_schema WHERE singleton=1"
        ).fetchone()[0] == FifoCostRepository.SCHEMA_VERSION == 15
        assert _rate_row_digest(migrated) == before_digest
        assert migrated.execute(
            "SELECT cost_input_mode FROM fifo_cost_rate_changes WHERE rate_change_id='rate-1'"
        ).fetchone()[0] == "COMPONENTS"
        assert _rate_sql_objects(migrated) == before_objects
        foreign_key_children = set()
        for (table,) in migrated.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ):
            foreign_key_children.update(
                table for row in migrated.execute(f"PRAGMA foreign_key_list({table})")
                if row[2] == "fifo_cost_rate_changes"
            )
        assert {
            "fifo_cost_allocation_rate_lines", "fifo_cost_return_basis",
            "fifo_cost_late_entry_corrections", "fifo_cost_rate_cancellations",
        } <= foreign_key_children
        assert migrated.execute("PRAGMA foreign_key_check").fetchall() == []
        assert {
            row[0] for row in migrated.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        } >= {
            "fifo_cost_transition_cases", "fifo_cost_transition_case_revisions",
            "fifo_cost_supply_declarations", "fifo_cost_supply_observations",
            "fifo_cost_report_evidence", "fifo_cost_transition_previews",
            "fifo_cost_transition_commits",
        }
        with pytest.raises(sqlite3.IntegrityError):
            migrated.execute(
                "UPDATE fifo_cost_rate_changes SET effective_date='2026-11-08' "
                "WHERE rate_change_id='rate-1'"
            )
    finally:
        migrated.close()


def test_v12_partial_ddl_failure_rolls_back_rate_rebuild_and_restores_foreign_keys(
    tmp_path, monkeypatch,
):
    database = tmp_path / "v12-rollback.sqlite"
    repository = FifoCostRepository(db_path=database)
    connection = repository.get_connection()
    try:
        _seed_rate(connection)
    finally:
        connection.close()
    _downgrade_rate_table_to_v12(database)

    connection = sqlite3.connect(database, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    before = _rate_row_digest(connection)
    before_objects = _rate_sql_objects(connection)
    before_schema = _schema_objects(connection)

    def fail_after_table_rebuild(_connection):
        raise sqlite3.OperationalError("injected index creation failure")

    monkeypatch.setattr(
        FifoCostRepository, "_create_indexes", staticmethod(fail_after_table_rebuild),
    )
    try:
        with pytest.raises(sqlite3.OperationalError, match="injected index"):
            repository._initialize_schema(connection)
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert connection.execute(
            "SELECT version FROM fifo_cost_schema WHERE singleton=1"
        ).fetchone()[0] == 12
        columns = {
            row[1] for row in connection.execute(
                "PRAGMA table_info(fifo_cost_rate_changes)"
            )
        }
        assert "cost_input_mode" not in columns
        assert _rate_row_digest(connection) == before
        assert _rate_sql_objects(connection) == before_objects
        assert _schema_objects(connection) == before_schema
        assert connection.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' "
            "AND name LIKE 'fifo_cost_transition_%' "
            "OR type='table' AND name IN ('fifo_cost_supply_declarations', "
            "'fifo_cost_supply_observations', 'fifo_cost_report_evidence')"
        ).fetchone()[0] == 0
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        connection.close()


def test_future_schema_is_refused_without_mutation(tmp_path):
    database = tmp_path / "future.sqlite"
    repository = FifoCostRepository(db_path=database)
    connection = repository.get_connection()
    connection.execute(
        "UPDATE fifo_cost_schema SET version=? WHERE singleton=1",
        (FifoCostRepository.SCHEMA_VERSION + 1,),
    )
    connection.commit()
    before_objects = tuple(tuple(row) for row in connection.execute(
        "SELECT type, name, sql FROM sqlite_master ORDER BY type, name"
    ).fetchall())
    connection.close()

    with pytest.raises(sqlite3.DatabaseError, match="unsupported FIFO cost schema version"):
        FifoCostRepository(db_path=database).get_connection()

    unchanged = sqlite3.connect(database)
    try:
        assert unchanged.execute(
            "SELECT version FROM fifo_cost_schema WHERE singleton=1"
        ).fetchone()[0] == FifoCostRepository.SCHEMA_VERSION + 1
        assert tuple(tuple(row) for row in unchanged.execute(
            "SELECT type, name, sql FROM sqlite_master ORDER BY type, name"
        ).fetchall()) == before_objects
    finally:
        unchanged.close()


def test_fl28_v13_schema_upgrade_adds_append_only_cutoff_sale_mappings(tmp_path):
    database = tmp_path / "v13-cutoff-mapping.sqlite"
    repository = FifoCostRepository(db_path=database)
    connection = repository.get_connection()
    try:
        connection.execute("DROP TABLE fifo_cost_cutoff_sale_mappings")
        connection.execute("DROP TABLE fifo_cost_cutoff_sale_mapping_sets")
        connection.execute(
            "UPDATE fifo_cost_schema SET version=13 WHERE singleton=1"
        )
        connection.commit()
    finally:
        connection.close()

    migrated = FifoCostRepository(db_path=database).get_connection()
    try:
        assert migrated.execute(
            "SELECT version FROM fifo_cost_schema WHERE singleton=1"
        ).fetchone()[0] == FifoCostRepository.SCHEMA_VERSION == 15
        tables = {
            row[0] for row in migrated.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert {
            "fifo_cost_cutoff_sale_mapping_sets",
            "fifo_cost_cutoff_sale_mappings",
        } <= tables
        triggers = {
            row[0] for row in migrated.execute(
                "SELECT name FROM sqlite_master WHERE type='trigger'"
            )
        }
        assert {
            "trg_fifo_cost_cutoff_sale_mapping_sets_no_update",
            "trg_fifo_cost_cutoff_sale_mapping_sets_no_delete",
            "trg_fifo_cost_cutoff_sale_mappings_no_update",
            "trg_fifo_cost_cutoff_sale_mappings_no_delete",
        } <= triggers
        assert migrated.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        migrated.close()


def test_v14_upgrade_adds_append_only_report_period_confirmations(tmp_path):
    database = tmp_path / "v14-upgrade.sqlite"
    repository = FifoCostRepository(db_path=database)
    connection = repository.get_connection()
    try:
        connection.execute("DROP TABLE fifo_cost_report_period_confirmations")
        connection.execute(
            "UPDATE fifo_cost_schema SET version=14 WHERE singleton=1"
        )
        connection.commit()
    finally:
        connection.close()

    migrated = FifoCostRepository(db_path=database).get_connection()
    try:
        assert migrated.execute(
            "SELECT version FROM fifo_cost_schema WHERE singleton=1"
        ).fetchone()[0] == 15
        assert migrated.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name='fifo_cost_report_period_confirmations'"
        ).fetchone() is not None
        assert migrated.execute("PRAGMA foreign_key_check").fetchall() == []
        triggers = {
            row[0] for row in migrated.execute(
                "SELECT name FROM sqlite_master WHERE type='trigger'"
            )
        }
        assert {
            "trg_fifo_cost_report_period_confirmations_no_update",
            "trg_fifo_cost_report_period_confirmations_no_delete",
        } <= triggers
    finally:
        migrated.close()


def test_transition_case_rows_are_scoped_by_owner_tenant_store_and_sku(tmp_path):
    repository = FifoCostRepository(db_path=tmp_path / "tenant-scope.sqlite")
    connection = repository.get_connection()
    try:
        base_columns = (
            "case_id, schema_version, owner_fingerprint, tenant_fingerprint, store_id, "
            "product_id, offer_id, sku, current_revision, current_state, created_at, updated_at"
        )
        values = "?, 1, ?, ?, 'same-store', 'product', 'offer', 'same-sku', 1, 'DRAFT', 'now', 'now'"
        connection.execute(
            f"INSERT INTO fifo_cost_transition_cases ({base_columns}) VALUES ({values})",
            ("case-a", "a" * 64, "b" * 64),
        )
        connection.execute(
            f"INSERT INTO fifo_cost_transition_cases ({base_columns}) VALUES ({values})",
            ("case-b", "c" * 64, "d" * 64),
        )
        first_tenant = connection.execute(
            """SELECT case_id FROM fifo_cost_transition_cases
               WHERE owner_fingerprint=? AND tenant_fingerprint=?
                 AND store_id='same-store' AND sku='same-sku'""",
            ("a" * 64, "b" * 64),
        ).fetchall()
        second_tenant = connection.execute(
            """SELECT case_id FROM fifo_cost_transition_cases
               WHERE owner_fingerprint=? AND tenant_fingerprint=?
                 AND store_id='same-store' AND sku='same-sku'""",
            ("c" * 64, "d" * 64),
        ).fetchall()
        assert [row[0] for row in first_tenant] == ["case-a"]
        assert [row[0] for row in second_tenant] == ["case-b"]
        columns = {
            row[1] for row in connection.execute(
                "PRAGMA table_info(fifo_cost_transition_cases)"
            )
        }
        assert "owner_id" not in columns
        assert "telegram_user_id" not in columns
    finally:
        connection.close()


def test_tenant_cipher_reuses_existing_key_and_fails_closed(monkeypatch):
    monkeypatch.delenv("OZON_CREDENTIAL_MASTER_KEY", raising=False)
    assert get_tenant_fernet() is None
    assert encrypt_tenant_value("supply-reference") is None
    assert encrypt_tenant_value(None, master_key=_MASTER_KEY) is None
    assert encrypt_tenant_value(True, master_key=_MASTER_KEY) is None

    encrypted = encrypt_tenant_value("supply-reference-2000070135564", master_key=_MASTER_KEY)
    assert encrypted is not None
    assert "2000070135564" not in encrypted
    assert decrypt_tenant_value(encrypted, master_key=_MASTER_KEY) == "supply-reference-2000070135564"
    assert decrypt_tenant_value(encrypted, master_key=_WRONG_KEY) is None
    assert decrypt_tenant_value("not-a-fernet-token", master_key=_MASTER_KEY) is None

    monkeypatch.setenv("OZON_CREDENTIAL_MASTER_KEY", _MASTER_KEY)
    assert get_tenant_fernet().decrypt(encrypted.encode("ascii")).decode("utf-8") == (
        "supply-reference-2000070135564"
    )
