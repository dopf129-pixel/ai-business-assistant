import sqlite3

import pytest

from services.fifo_cost_repository import FifoCostRepository
from services.tenant_cipher_provider import encrypt_tenant_value


_OWNER = "a" * 64
_TENANT = "b" * 64
_IDENTITY = "c" * 64
_SOURCE = "d" * 64
_PAYLOAD = "e" * 64
_SCOPE = "f" * 64


def _seed_case_and_period_confirmation(connection):
    connection.execute(
        """INSERT INTO fifo_cost_transition_cases (
            case_id, schema_version, owner_fingerprint, tenant_fingerprint,
            store_id, product_id, offer_id, sku, current_revision, current_state,
            created_at, updated_at
        ) VALUES ('case-1', 1, ?, ?, 'store-1', 'product-1', 'offer-1',
                  'sku-1', 1, 'DRAFT', 'now', 'now')""",
        (_OWNER, _TENANT),
    )
    connection.execute(
        """INSERT INTO fifo_cost_report_evidence (
            report_evidence_id, case_id, report_type, period_from, period_to,
            period_provenance, captured_at, file_sha256, parser_version,
            source_kind, completeness, source_fingerprint,
            cell_references_json, normalized_fields_json
        ) VALUES ('report-1', 'case-1', 'TURNOVER', '2026-11-01',
                  '2026-11-30', 'OWNER_CONFIRMED', '2026-12-01T00:00:00Z',
                  ?, 'v1', 'OWNER_IMPORTED', 'COMPLETE', ?, '[]', '{}')""",
        ("1" * 64, _SOURCE),
    )
    connection.execute(
        """INSERT INTO fifo_cost_report_period_confirmations (
            period_confirmation_id, report_evidence_id, case_id,
            confirmation_revision, period_from, period_to, period_provenance,
            source_fingerprint, confirmed_at
        ) VALUES ('period-confirm-1', 'report-1', 'case-1', 1,
                  '2026-11-01', '2026-11-30', 'OWNER_CONFIRMED', ?,
                  '2026-12-01T00:01:00Z')""",
        ("2" * 64,),
    )


def _evidence_values(*, evidence_id="evidence-1", revision=1,
                     evidence_kind="PERIOD_SUMMARY_SNAPSHOT",
                     payload_json="{}", encrypted_payload=b"ciphertext",
                     row_count=None, tenant_fingerprint=_TENANT,
                     store_id="store-1", owner_fingerprint=_OWNER):
    return (
        evidence_id, "case-1", owner_fingerprint, tenant_fingerprint,
        _SCOPE, _IDENTITY,
        store_id, evidence_kind, 1,
        "OZON_REPORT", _SOURCE, revision, "2026-11-01", "2026-11-30", None,
        "2026-12-01T00:00:00Z", "2026-11-30", "COMPLETE", row_count, payload_json,
        encrypted_payload, _PAYLOAD, f"{evidence_id}-key",
        "2026-12-01T00:02:00Z",
    )


def _insert_evidence(connection, values=None, **kwargs):
    row = values or _evidence_values(**kwargs)
    connection.execute(
        """INSERT INTO fifo_cost_transition_bridge_evidence (
            evidence_id, case_id, owner_fingerprint, tenant_fingerprint,
            scope_fingerprint, identity_fingerprint, store_id, evidence_kind,
            schema_version, source_kind,
            source_fingerprint, evidence_revision, period_from, period_to,
            as_of, captured_at, complete_through, completeness, row_count, payload_json,
            encrypted_payload, payload_fingerprint, idempotency_key, recorded_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        row,
    )


def test_fresh_fifo_schema_v17_has_scoped_append_only_tables_and_leaves_user_version(tmp_path):
    repository = FifoCostRepository(db_path=tmp_path / "fresh-v17.sqlite")
    connection = repository.get_connection()
    try:
        assert connection.execute(
            "SELECT version FROM fifo_cost_schema WHERE singleton=1"
        ).fetchone()[0] == FifoCostRepository.SCHEMA_VERSION == 17
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 0
        tables = {
            row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert {
            "fifo_cost_transition_bridge_evidence",
            "fifo_cost_transition_evidence_confirmations",
            "fifo_cost_allocation_rate_balances",
            "fifo_cost_batch_rule_revisions",
            "fifo_cost_batch_supply_observations",
            "fifo_cost_batch_membership_decisions",
            "fifo_cost_batch_membership_decision_observations",
            "fifo_cost_batch_supply_scans",
            "fifo_cost_batch_total_controls",
        } <= tables
        for table, expected in {
            "fifo_cost_transition_bridge_evidence": {
                "evidence_id", "case_id", "owner_fingerprint",
                "tenant_fingerprint", "scope_fingerprint", "identity_fingerprint",
                "evidence_kind",
                "schema_version", "source_fingerprint", "evidence_revision",
                "encrypted_payload", "payload_fingerprint", "idempotency_key",
            },
            "fifo_cost_transition_evidence_confirmations": {
                "confirmation_id", "evidence_id", "case_id", "evidence_fingerprint",
                "confirmation_kind", "confirmed_fields_json", "scope_fingerprint",
                "expected_case_revision", "idempotency_key", "confirmed_at",
            },
            "fifo_cost_allocation_rate_balances": {
                "allocation_id", "ordinal", "rate_change_id", "remaining_units",
                "unit_cost_rub", "reconciliation_fingerprint", "original_basis_kind",
                "original_basis_reference", "origin_sale_event_id",
            },
            "fifo_cost_batch_rule_revisions": {
                "rule_event_id", "rule_id", "rule_revision", "case_id",
                "owner_fingerprint", "tenant_fingerprint", "store_id", "sku",
                "scope_fingerprint", "policy_version", "start_local_date",
                "start_day_policy", "new_unit_cost_rub", "old_home_confirmed_zero",
                "old_transit_confirmed_zero", "idempotency_key", "payload_fingerprint",
            },
            "fifo_cost_batch_supply_observations": {
                "observation_id", "case_id", "record_key", "observation_revision",
                "encrypted_lookup_payload", "source_fingerprint", "normalized_status",
                "planned_declared_quantity", "shipped_composition_quantity",
                "accepted_quantity", "quantity_coverage", "membership",
            },
            "fifo_cost_batch_membership_decisions": {
                "decision_id", "case_id", "rule_id", "rule_revision",
                "candidate_set_fingerprint", "membership_binding_fingerprint",
                "idempotency_key",
            },
            "fifo_cost_batch_supply_scans": {
                "scan_id", "case_id", "revision", "list_pagination_complete",
                "details_complete", "sku_composition_complete",
                "historical_window_proven", "membership_complete", "quantity_complete",
                "physical_receipt_timing_complete", "encrypted_resumable_token",
            },
            "fifo_cost_batch_total_controls": {
                "control_id", "case_id", "total_units", "window_from",
                "window_through", "control_kind", "control_status",
                "owner_confirmation_fingerprint",
            },
        }.items():
            columns = {
                row[1] for row in connection.execute(f"PRAGMA table_info({table})")
            }
            assert expected <= columns
        foreign_keys = {
            table: {
                (row[2], row[3], row[4])
                for row in connection.execute(f"PRAGMA foreign_key_list({table})")
            }
            for table in (
                "fifo_cost_transition_bridge_evidence",
                "fifo_cost_transition_evidence_confirmations",
                "fifo_cost_allocation_rate_balances",
                "fifo_cost_batch_rule_revisions",
                "fifo_cost_batch_supply_observations",
                "fifo_cost_batch_membership_decisions",
                "fifo_cost_batch_membership_decision_observations",
                "fifo_cost_batch_supply_scans",
                "fifo_cost_batch_total_controls",
            )
        }
        assert any(row[0] == "fifo_cost_transition_cases" for row in foreign_keys[
            "fifo_cost_transition_bridge_evidence"
        ])
        assert any(row[0] == "fifo_cost_transition_bridge_evidence" for row in foreign_keys[
            "fifo_cost_transition_evidence_confirmations"
        ])
        assert any(row[0] == "fifo_cost_allocations" for row in foreign_keys[
            "fifo_cost_allocation_rate_balances"
        ])
        assert any(row[0] == "fifo_cost_transition_cases" for row in foreign_keys[
            "fifo_cost_batch_rule_revisions"
        ])
        assert any(row[0] == "fifo_cost_batch_rule_revisions" for row in foreign_keys[
            "fifo_cost_batch_membership_decisions"
        ])
        assert any(row[0] == "fifo_cost_batch_supply_observations" for row in foreign_keys[
            "fifo_cost_batch_membership_decision_observations"
        ])
        triggers = {
            row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='trigger'"
            )
        }
        for table in (
            "fifo_cost_transition_bridge_evidence",
            "fifo_cost_transition_evidence_confirmations",
            "fifo_cost_allocation_rate_balances",
            "fifo_cost_batch_rule_revisions",
            "fifo_cost_batch_supply_observations",
            "fifo_cost_batch_membership_decisions",
            "fifo_cost_batch_membership_decision_observations",
            "fifo_cost_batch_total_controls",
        ):
            assert f"trg_{table}_no_update" in triggers
            assert f"trg_{table}_no_delete" in triggers
        indexes = {
            row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            )
        }
        assert "idx_fifo_cost_transition_evidence_case_kind" in indexes
        assert "idx_fifo_cost_transition_confirmations_evidence" in indexes
        assert "idx_fifo_cost_transition_cases_owner_scope" in indexes
        assert "idx_fifo_cost_allocation_rate_balances_current" in indexes
        assert "idx_fifo_cost_transition_cases_batch_scope" in indexes
        assert "idx_fifo_cost_batch_rules_case_date" in indexes
        assert "idx_fifo_cost_batch_observations_record" in indexes
        assert "idx_fifo_cost_batch_decisions_rule" in indexes
        assert "idx_fifo_cost_batch_scans_updated" in indexes
        assert "idx_fifo_cost_batch_controls_window" in indexes
        assert "trg_fifo_cost_batch_rule_case_quota" in triggers
        assert "trg_fifo_cost_batch_observation_case_quota" in triggers
        assert "trg_fifo_cost_batch_supply_scans_no_update" not in triggers
        assert "trg_fifo_cost_batch_supply_scans_no_delete" not in triggers
        case_columns = {
            row[1]: row for row in connection.execute(
                "PRAGMA table_info(fifo_cost_transition_cases)"
            )
        }
        assert case_columns["supply_total_mode"][4] == "'LEGACY_OWNER_TOTAL'"
        rate_balance_columns = {
            row[1]: row for row in connection.execute(
                "PRAGMA table_info(fifo_cost_allocation_rate_balances)"
            )
        }
        assert rate_balance_columns["remaining_units"][3] == 0
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        connection.close()


@pytest.mark.parametrize("legacy_version", [12, 13, 14, 15, 16])
def test_v12_through_v16_upgrade_adds_v17_without_mutating_period_confirmations(
    tmp_path, legacy_version,
):
    database = tmp_path / f"v{legacy_version}-to-v17.sqlite"
    repository = FifoCostRepository(db_path=database)
    connection = repository.get_connection()
    try:
        _seed_case_and_period_confirmation(connection)
        for table in (
            "fifo_cost_batch_membership_decision_observations",
            "fifo_cost_batch_membership_decisions",
            "fifo_cost_batch_supply_observations",
            "fifo_cost_batch_supply_scans",
            "fifo_cost_batch_total_controls",
            "fifo_cost_batch_rule_revisions",
            "fifo_cost_allocation_rate_balances",
            "fifo_cost_transition_evidence_confirmations",
            "fifo_cost_transition_bridge_evidence",
        ):
            connection.execute(f"DROP TABLE IF EXISTS {table}")
        connection.execute(
            "ALTER TABLE fifo_cost_transition_cases DROP COLUMN supply_total_mode"
        )
        connection.execute(
            "UPDATE fifo_cost_schema SET version=? WHERE singleton=1",
            (legacy_version,),
        )
        connection.commit()
        before = tuple(connection.execute(
            "SELECT * FROM fifo_cost_report_period_confirmations"
        ).fetchone())
        user_version = connection.execute("PRAGMA user_version").fetchone()[0]
    finally:
        connection.close()

    migrated = repository.get_connection()
    try:
        assert migrated.execute(
            "SELECT version FROM fifo_cost_schema WHERE singleton=1"
        ).fetchone()[0] == 17
        assert tuple(migrated.execute(
            "SELECT * FROM fifo_cost_report_period_confirmations"
        ).fetchone()) == before
        assert migrated.execute("PRAGMA user_version").fetchone()[0] == user_version
        assert migrated.execute(
            "SELECT supply_total_mode FROM fifo_cost_transition_cases WHERE case_id='case-1'"
        ).fetchone()[0] == "LEGACY_OWNER_TOTAL"
        assert migrated.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        migrated.close()


def test_v16_migration_rolls_back_new_tables_and_restores_existing_confirmation(tmp_path, monkeypatch):
    database = tmp_path / "v16-rollback.sqlite"
    repository = FifoCostRepository(db_path=database)
    connection = repository.get_connection()
    try:
        _seed_case_and_period_confirmation(connection)
        connection.row_factory = sqlite3.Row
        for table in (
            "fifo_cost_batch_membership_decision_observations",
            "fifo_cost_batch_membership_decisions",
            "fifo_cost_batch_supply_observations",
            "fifo_cost_batch_supply_scans",
            "fifo_cost_batch_total_controls",
            "fifo_cost_batch_rule_revisions",
            "fifo_cost_allocation_rate_balances",
            "fifo_cost_transition_evidence_confirmations",
            "fifo_cost_transition_bridge_evidence",
        ):
            connection.execute(f"DROP TABLE IF EXISTS {table}")
        connection.execute(
            "ALTER TABLE fifo_cost_transition_cases DROP COLUMN supply_total_mode"
        )
        connection.execute(
            "UPDATE fifo_cost_schema SET version=16 WHERE singleton=1"
        )
        connection.commit()
    finally:
        connection.close()

    raw = sqlite3.connect(database, isolation_level=None)
    raw.row_factory = sqlite3.Row
    raw.execute("PRAGMA foreign_keys=ON")
    before_objects = tuple(tuple(row) for row in raw.execute(
        "SELECT type, name, sql FROM sqlite_master ORDER BY type, name"
    ).fetchall())
    before_period = tuple(raw.execute(
        "SELECT * FROM fifo_cost_report_period_confirmations"
    ).fetchone())

    def fail_after_new_ddl(_connection):
        raise sqlite3.OperationalError("injected v17 index failure")

    monkeypatch.setattr(FifoCostRepository, "_create_indexes", staticmethod(fail_after_new_ddl))
    try:
        with pytest.raises(sqlite3.OperationalError, match="injected v17 index failure"):
            repository._initialize_schema(raw)
        assert raw.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert raw.execute(
            "SELECT version FROM fifo_cost_schema WHERE singleton=1"
        ).fetchone()[0] == 16
        assert tuple(raw.execute(
            "SELECT * FROM fifo_cost_report_period_confirmations"
        ).fetchone()) == before_period
        assert tuple(tuple(row) for row in raw.execute(
            "SELECT type, name, sql FROM sqlite_master ORDER BY type, name"
        ).fetchall()) == before_objects
    finally:
        raw.close()


def test_future_fifo_schema_version_fails_closed_without_schema_mutation(tmp_path):
    database = tmp_path / "future-schema.sqlite"
    repository = FifoCostRepository(db_path=database)
    connection = repository.get_connection()
    connection.execute("UPDATE fifo_cost_schema SET version=18 WHERE singleton=1")
    connection.commit()
    before = tuple(tuple(row) for row in connection.execute(
        "SELECT type, name, sql FROM sqlite_master ORDER BY type, name"
    ).fetchall())
    connection.close()

    with pytest.raises(sqlite3.DatabaseError, match="unsupported FIFO cost schema version"):
        repository.get_connection()
    raw = sqlite3.connect(database)
    try:
        assert raw.execute(
            "SELECT version FROM fifo_cost_schema WHERE singleton=1"
        ).fetchone()[0] == 18
        assert tuple(tuple(row) for row in raw.execute(
            "SELECT type, name, sql FROM sqlite_master ORDER BY type, name"
        ).fetchall()) == before
    finally:
        raw.close()


def test_transition_evidence_requires_ciphertext_exact_scope_and_is_append_only(tmp_path):
    repository = FifoCostRepository(db_path=tmp_path / "evidence-schema.sqlite")
    connection = repository.get_connection()
    try:
        _seed_case_and_period_confirmation(connection)
        ciphertext = encrypt_tenant_value("synthetic-source-reference", master_key="invalid")
        assert ciphertext is None
        with pytest.raises(sqlite3.IntegrityError):
            _insert_evidence(connection, encrypted_payload=None)
        _insert_evidence(connection)
        connection.execute(
            """INSERT INTO fifo_cost_transition_evidence_confirmations (
                confirmation_id, evidence_id, case_id, evidence_fingerprint,
                owner_fingerprint, scope_fingerprint, confirmation_kind,
                confirmed_fields_json, payload_fingerprint,
                expected_case_revision, idempotency_key, confirmed_at
            ) VALUES ('confirm-1', 'evidence-1', 'case-1', ?, ?, ?, 'PERIOD', '{}',
                      ?, 1, 'confirm-key-001', '2026-12-01T00:03:00Z')""",
            (_PAYLOAD, _OWNER, _SCOPE, _PAYLOAD),
        )
        with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
            connection.execute(
                """INSERT INTO fifo_cost_transition_evidence_confirmations (
                    confirmation_id, evidence_id, case_id, evidence_fingerprint,
                    owner_fingerprint, scope_fingerprint, confirmation_kind,
                    confirmed_fields_json, payload_fingerprint,
                    expected_case_revision, idempotency_key, confirmed_at
                ) VALUES ('confirm-wrong-scope', 'evidence-1', 'case-1', ?, ?, ?,
                          'PERIOD', '{}', ?, 1, 'confirm-key-wrong',
                          '2026-12-01T00:03:00Z')""",
                (_PAYLOAD, "9" * 64, _SCOPE, "8" * 64),
            )
        for statement in (
            "UPDATE fifo_cost_transition_bridge_evidence SET payload_json='{}' WHERE evidence_id='evidence-1'",
            "DELETE FROM fifo_cost_transition_bridge_evidence WHERE evidence_id='evidence-1'",
            "UPDATE fifo_cost_transition_evidence_confirmations SET confirmed_fields_json='{}' WHERE confirmation_id='confirm-1'",
        ):
            with pytest.raises(sqlite3.IntegrityError, match="append-only"):
                connection.execute(statement)
    finally:
        connection.close()


def test_transition_evidence_row_and_case_quotas_are_enforced_without_truncation(tmp_path):
    repository = FifoCostRepository(db_path=tmp_path / "evidence-quota.sqlite")
    connection = repository.get_connection()
    try:
        _seed_case_and_period_confirmation(connection)
        with pytest.raises(sqlite3.IntegrityError):
            _insert_evidence(connection, payload_json="x" * 262145)
        with pytest.raises(sqlite3.IntegrityError):
            _insert_evidence(connection, evidence_kind="PHYSICAL_SALES_DOCUMENT",
                             encrypted_payload=sqlite3.Binary(bytes(16 * 1024 * 1024 + 1)))
        for index in range(100):
            _insert_evidence(
                connection,
                _evidence_values(
                    evidence_id=f"evidence-{index:03}", revision=index + 1,
                    evidence_kind="PERIOD_SUMMARY_SNAPSHOT" if index % 2 == 0
                    else "TAX_POLICY_SNAPSHOT",
                ),
            )
        with pytest.raises(sqlite3.IntegrityError, match="quota"):
            _insert_evidence(
                connection,
                _evidence_values(
                    evidence_id="evidence-101", revision=51,
                    evidence_kind="PERIOD_SUMMARY_SNAPSHOT",
                ),
            )
        assert connection.execute(
            "SELECT COUNT(*) FROM fifo_cost_transition_bridge_evidence"
        ).fetchone()[0] == 100
    finally:
        connection.close()


def test_transition_evidence_scope_and_physical_document_bounds_are_database_enforced(tmp_path):
    repository = FifoCostRepository(db_path=tmp_path / "evidence-scope.sqlite")
    connection = repository.get_connection()
    try:
        _seed_case_and_period_confirmation(connection)
        with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
            _insert_evidence(connection, _evidence_values(tenant_fingerprint="9" * 64))
        with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
            _insert_evidence(connection, _evidence_values(
                evidence_id="wrong-owner", owner_fingerprint="9" * 64,
            ))
        with pytest.raises(sqlite3.IntegrityError):
            _insert_evidence(connection, evidence_kind="PHYSICAL_SALES_DOCUMENT")
        with pytest.raises(sqlite3.IntegrityError):
            _insert_evidence(
                connection, evidence_kind="PHYSICAL_SALES_DOCUMENT", row_count=50001,
            )
        _insert_evidence(
            connection, evidence_kind="PHYSICAL_SALES_DOCUMENT", row_count=50000,
        )
        with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
            connection.execute(
                """INSERT INTO fifo_cost_allocation_rate_balances (
                    allocation_id, ordinal, rate_change_id, remaining_units,
                    unit_cost_rub, reconciliation_reference,
                    reconciliation_fingerprint, original_basis_kind,
                    original_basis_reference, origin_sale_event_id
                ) VALUES ('missing-allocation', 1, 'missing-rate', NULL, '14.65',
                          'ref', ?, 'RATE_BOUNDARY', 'boundary', NULL)""",
                ("a" * 64,),
            )
    finally:
        connection.close()


def test_transition_evidence_aggregate_ciphertext_quota_rejects_without_truncation(tmp_path):
    repository = FifoCostRepository(db_path=tmp_path / "evidence-aggregate-quota.sqlite")
    connection = repository.get_connection()
    document_ciphertext = bytes(16 * 1024 * 1024)
    try:
        _seed_case_and_period_confirmation(connection)
        for revision in range(1, 5):
            _insert_evidence(
                connection,
                evidence_id=f"physical-{revision}",
                revision=revision,
                evidence_kind="PHYSICAL_SALES_DOCUMENT",
                row_count=1,
                encrypted_payload=document_ciphertext,
            )
        with pytest.raises(sqlite3.IntegrityError, match="quota"):
            _insert_evidence(
                connection,
                evidence_id="physical-over-limit",
                revision=5,
                evidence_kind="PHYSICAL_SALES_DOCUMENT",
                row_count=1,
                encrypted_payload=b"x",
            )
        assert connection.execute(
            "SELECT COUNT(*) FROM fifo_cost_transition_bridge_evidence"
        ).fetchone()[0] == 4
        assert connection.execute(
            "SELECT SUM(length(encrypted_payload)) "
            "FROM fifo_cost_transition_bridge_evidence"
        ).fetchone()[0] == 64 * 1024 * 1024
    finally:
        connection.close()
