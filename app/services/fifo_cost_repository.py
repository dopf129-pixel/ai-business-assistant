"""Tenant-local, additive persistence boundary for factual FIFO cost evidence.

The repository deliberately owns only its ``fifo_cost_*`` tables.  It shares
the existing seller SQLite file, but never migrates legacy cost rows or
Planning Workspace schema metadata.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from services.tenant_storage import ensure_storage_parent, tenant_storage_path


class FifoCostRepository:
    SCHEMA_VERSION = 1

    _TABLES = (
        "fifo_cost_schema",
        "fifo_cost_streams",
        "fifo_cost_sources",
        "fifo_cost_source_refs",
        "fifo_cost_policy_revisions",
        "fifo_cost_events",
        "fifo_cost_layers",
        "fifo_cost_projections",
        "fifo_cost_allocations",
        "fifo_cost_allocation_lines",
        "fifo_cost_idempotency",
    )

    _APPEND_ONLY_TABLES = (
        "fifo_cost_sources",
        "fifo_cost_source_refs",
        "fifo_cost_policy_revisions",
        "fifo_cost_events",
        "fifo_cost_layers",
        "fifo_cost_allocations",
        "fifo_cost_allocation_lines",
        "fifo_cost_idempotency",
    )

    def __init__(self, db_path=None):
        self._db_path = Path(db_path) if db_path is not None else None

    @property
    def db_path(self):
        return self._db_path or Path(tenant_storage_path("ozon_assistant.db"))

    def get_connection(self):
        """Open a tenant-local connection and apply only FIFO-owned migrations."""
        ensure_storage_parent(self.db_path)
        connection = sqlite3.connect(
            self.db_path, timeout=5.0, isolation_level=None,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=5000")
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            self._initialize_schema(connection)
        except Exception:
            connection.close()
            raise
        return connection

    def _initialize_schema(self, connection):
        """Create the additive FIFO schema atomically and reject unknown versions."""
        connection.execute("BEGIN IMMEDIATE")
        try:
            version = self._read_schema_version(connection)
            if version > self.SCHEMA_VERSION:
                raise sqlite3.DatabaseError("unsupported FIFO cost schema version")
            if version not in (0, self.SCHEMA_VERSION):
                raise sqlite3.DatabaseError("unsupported FIFO cost schema version")

            self._create_tables(connection)
            self._create_indexes(connection)
            self._create_append_only_guards(connection)

            if version == 0:
                connection.execute(
                    "INSERT INTO fifo_cost_schema(singleton, version) VALUES (1, ?)",
                    (self.SCHEMA_VERSION,),
                )
            self._validate_schema_metadata(connection)
            connection.commit()
        except Exception:
            connection.rollback()
            raise

    @staticmethod
    def _read_schema_version(connection):
        exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='fifo_cost_schema'"
        ).fetchone() is not None
        if not exists:
            return 0

        columns = {
            str(row[1])
            for row in connection.execute("PRAGMA table_info(fifo_cost_schema)")
        }
        if not {"singleton", "version"} <= columns:
            raise sqlite3.DatabaseError("invalid FIFO cost schema metadata")
        rows = connection.execute(
            "SELECT singleton, version FROM fifo_cost_schema"
        ).fetchall()
        if len(rows) != 1 or rows[0]["singleton"] != 1:
            raise sqlite3.DatabaseError("invalid FIFO cost schema metadata")
        value = rows[0]["version"]
        if type(value) is not int or value < 1:
            raise sqlite3.DatabaseError("invalid FIFO cost schema metadata")
        return value

    @staticmethod
    def _create_tables(connection):
        statements = """
            CREATE TABLE IF NOT EXISTS fifo_cost_schema (
                singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
                version INTEGER NOT NULL CHECK(version >= 1)
            );

            CREATE TABLE IF NOT EXISTS fifo_cost_streams (
                stream_id TEXT PRIMARY KEY,
                store_id TEXT NOT NULL,
                product_id TEXT,
                offer_id TEXT,
                sku TEXT NOT NULL,
                identity_fingerprint TEXT NOT NULL,
                policy_version INTEGER NOT NULL CHECK(policy_version >= 1),
                state TEXT NOT NULL CHECK(state IN (
                    'LEGACY', 'FIFO_PENDING_ANCHOR', 'FIFO_READY',
                    'FIFO_PARTIAL', 'FIFO_CONFLICT', 'FIFO_SOURCE_BLOCKED'
                )),
                revision INTEGER NOT NULL DEFAULT 0 CHECK(revision >= 0),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                CHECK(length(trim(store_id)) > 0),
                CHECK(length(trim(sku)) > 0),
                CHECK(product_id IS NOT NULL OR offer_id IS NOT NULL),
                UNIQUE(store_id, identity_fingerprint, policy_version)
            );

            CREATE TABLE IF NOT EXISTS fifo_cost_sources (
                source_id TEXT PRIMARY KEY,
                store_id TEXT NOT NULL,
                source_kind TEXT NOT NULL,
                source_method TEXT NOT NULL,
                source_status TEXT NOT NULL CHECK(source_status IN (
                    'COMPLETE', 'PARTIAL', 'UNAVAILABLE', 'STALE', 'CONFLICT',
                    'NOT_REQUESTED', 'OWNER_CONFIRMED', 'MODEL_ONLY'
                )),
                provenance TEXT NOT NULL CHECK(provenance IN (
                    'OWNER_CONFIRMED', 'OZON_CONFIRMED_FIELD',
                    'DOCUMENT_RECONCILED', 'LEGACY_DATED_COST', 'MODEL_ASSUMPTION'
                )),
                source_fingerprint TEXT NOT NULL,
                captured_at TEXT,
                source_as_of TEXT,
                coverage_status TEXT NOT NULL,
                record_count INTEGER CHECK(record_count IS NULL OR record_count >= 0),
                page_count INTEGER CHECK(page_count IS NULL OR page_count >= 0),
                created_at TEXT NOT NULL,
                UNIQUE(store_id, source_fingerprint)
            );

            CREATE TABLE IF NOT EXISTS fifo_cost_source_refs (
                source_ref_id TEXT PRIMARY KEY,
                source_id TEXT NOT NULL REFERENCES fifo_cost_sources(source_id),
                reference_kind TEXT NOT NULL,
                reference_digest TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(source_id, reference_kind, reference_digest)
            );

            CREATE TABLE IF NOT EXISTS fifo_cost_policy_revisions (
                stream_id TEXT NOT NULL REFERENCES fifo_cost_streams(stream_id),
                policy_version INTEGER NOT NULL CHECK(policy_version >= 1),
                policy_json TEXT NOT NULL,
                policy_fingerprint TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY(stream_id, policy_version)
            );

            CREATE TABLE IF NOT EXISTS fifo_cost_events (
                event_id TEXT PRIMARY KEY,
                stream_id TEXT NOT NULL REFERENCES fifo_cost_streams(stream_id),
                event_kind TEXT NOT NULL CHECK(event_kind IN (
                    'OPENING_FIFO_ANCHOR', 'COST_LAYER_RECEIPT',
                    'INVENTORY_TRANSFER', 'PHYSICAL_SALE', 'SALE_CANCELLATION',
                    'SALEABLE_RETURN_RESTOCK', 'NON_SALE_OUTFLOW', 'CORRECTION'
                )),
                event_schema_version INTEGER NOT NULL CHECK(event_schema_version >= 1),
                effective_at TEXT,
                effective_date TEXT,
                recorded_at TEXT NOT NULL,
                captured_at TEXT,
                source_as_of TEXT,
                inventory_cutoff TEXT,
                quantity INTEGER NOT NULL CHECK(quantity > 0 AND quantity <= 100000),
                unit_cost_rub TEXT,
                purchase_cost_rub TEXT,
                delivery_cost_rub TEXT,
                packaging_cost_rub TEXT,
                currency TEXT NOT NULL DEFAULT 'RUB' CHECK(currency = 'RUB'),
                location_from TEXT,
                location_to TEXT,
                source_id TEXT REFERENCES fifo_cost_sources(source_id),
                source_fingerprint TEXT,
                provenance TEXT NOT NULL CHECK(provenance IN (
                    'OWNER_CONFIRMED', 'OZON_CONFIRMED_FIELD',
                    'DOCUMENT_RECONCILED', 'LEGACY_DATED_COST', 'MODEL_ASSUMPTION'
                )),
                completeness TEXT NOT NULL CHECK(completeness IN (
                    'COMPLETE', 'PARTIAL', 'UNAVAILABLE', 'STALE', 'CONFLICT',
                    'NOT_REQUESTED', 'OWNER_CONFIRMED', 'MODEL_ONLY'
                )),
                source_identity_digest TEXT,
                supersedes_event_id TEXT REFERENCES fifo_cost_events(event_id),
                reason_code TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS fifo_cost_layers (
                layer_id TEXT PRIMARY KEY,
                stream_id TEXT NOT NULL REFERENCES fifo_cost_streams(stream_id),
                event_id TEXT NOT NULL REFERENCES fifo_cost_events(event_id),
                layer_sequence INTEGER NOT NULL CHECK(layer_sequence >= 1),
                quantity INTEGER NOT NULL CHECK(quantity > 0 AND quantity <= 100000),
                unit_cost_rub TEXT NOT NULL,
                currency TEXT NOT NULL DEFAULT 'RUB' CHECK(currency = 'RUB'),
                effective_at TEXT,
                effective_date TEXT,
                provenance TEXT NOT NULL CHECK(provenance IN (
                    'OWNER_CONFIRMED', 'OZON_CONFIRMED_FIELD',
                    'DOCUMENT_RECONCILED', 'LEGACY_DATED_COST', 'MODEL_ASSUMPTION'
                )),
                source_id TEXT REFERENCES fifo_cost_sources(source_id),
                created_at TEXT NOT NULL,
                UNIQUE(stream_id, event_id, layer_sequence)
            );

            CREATE TABLE IF NOT EXISTS fifo_cost_projections (
                stream_id TEXT PRIMARY KEY REFERENCES fifo_cost_streams(stream_id),
                revision INTEGER NOT NULL CHECK(revision >= 0),
                state TEXT NOT NULL CHECK(state IN (
                    'LEGACY', 'FIFO_PENDING_ANCHOR', 'FIFO_READY',
                    'FIFO_PARTIAL', 'FIFO_CONFLICT', 'FIFO_SOURCE_BLOCKED'
                )),
                known_quantity INTEGER CHECK(known_quantity IS NULL OR
                    (known_quantity >= 0 AND known_quantity <= 1000000)),
                known_cost_rub TEXT,
                next_unit_cost_rub TEXT,
                queue_complete INTEGER NOT NULL CHECK(queue_complete IN (0, 1)),
                cutoff_status TEXT NOT NULL,
                source_set_fingerprint TEXT,
                last_event_id TEXT REFERENCES fifo_cost_events(event_id),
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS fifo_cost_allocations (
                allocation_id TEXT PRIMARY KEY,
                stream_id TEXT NOT NULL REFERENCES fifo_cost_streams(stream_id),
                revision INTEGER NOT NULL CHECK(revision >= 1),
                policy_version INTEGER NOT NULL CHECK(policy_version >= 1),
                source_set_fingerprint TEXT NOT NULL,
                cutoff_status TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN (
                    'COMPLETE', 'PARTIAL', 'CONFLICT', 'SOURCE_BLOCKED'
                )),
                created_at TEXT NOT NULL,
                UNIQUE(stream_id, revision)
            );

            CREATE TABLE IF NOT EXISTS fifo_cost_allocation_lines (
                allocation_id TEXT NOT NULL REFERENCES fifo_cost_allocations(allocation_id),
                line_number INTEGER NOT NULL CHECK(line_number >= 1),
                event_id TEXT NOT NULL REFERENCES fifo_cost_events(event_id),
                layer_id TEXT NOT NULL REFERENCES fifo_cost_layers(layer_id),
                quantity INTEGER NOT NULL CHECK(quantity > 0),
                unit_cost_rub TEXT NOT NULL,
                total_cost_rub TEXT NOT NULL,
                basis_allocation_id TEXT,
                basis_line_number INTEGER,
                PRIMARY KEY(allocation_id, line_number),
                CHECK((basis_allocation_id IS NULL) = (basis_line_number IS NULL))
            );

            CREATE TABLE IF NOT EXISTS fifo_cost_idempotency (
                stream_id TEXT NOT NULL REFERENCES fifo_cost_streams(stream_id),
                idempotency_key TEXT NOT NULL,
                payload_fingerprint TEXT NOT NULL,
                result_reference TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY(stream_id, idempotency_key)
            );
            """
        for statement in statements.split(";"):
            if statement.strip():
                connection.execute(statement)

    @staticmethod
    def _create_indexes(connection):
        statements = """
            CREATE INDEX IF NOT EXISTS idx_fifo_cost_events_stream_order
                ON fifo_cost_events(stream_id, effective_date, recorded_at, event_id);
            CREATE INDEX IF NOT EXISTS idx_fifo_cost_layers_fifo_order
                ON fifo_cost_layers(stream_id, effective_date, layer_sequence, layer_id);
            CREATE INDEX IF NOT EXISTS idx_fifo_cost_allocations_stream_revision
                ON fifo_cost_allocations(stream_id, revision);
            CREATE INDEX IF NOT EXISTS idx_fifo_cost_source_refs_digest
                ON fifo_cost_source_refs(reference_kind, reference_digest);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_fifo_cost_physical_sale_identity
                ON fifo_cost_events(stream_id, source_identity_digest)
                WHERE event_kind='PHYSICAL_SALE' AND source_identity_digest IS NOT NULL;
            """
        for statement in statements.split(";"):
            if statement.strip():
                connection.execute(statement)

    @classmethod
    def _create_append_only_guards(cls, connection):
        for table in cls._APPEND_ONLY_TABLES:
            for operation in ("UPDATE", "DELETE"):
                trigger_name = f"trg_{table}_no_{operation.lower()}"
                connection.execute(
                    f"CREATE TRIGGER IF NOT EXISTS {trigger_name} "
                    f"BEFORE {operation} ON {table} "
                    "BEGIN SELECT RAISE(ABORT, 'FIFO evidence is append-only'); END"
                )

    def _validate_schema_metadata(self, connection):
        row = connection.execute(
            "SELECT singleton, version FROM fifo_cost_schema"
        ).fetchone()
        if (row is None or row["singleton"] != 1
                or row["version"] != self.SCHEMA_VERSION):
            raise sqlite3.DatabaseError("invalid FIFO cost schema metadata")

