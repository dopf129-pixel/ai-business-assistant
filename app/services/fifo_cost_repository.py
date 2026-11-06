"""Tenant-local, additive persistence boundary for factual FIFO cost evidence.

The repository deliberately owns only its ``fifo_cost_*`` tables.  It shares
the existing seller SQLite file, but never migrates legacy cost rows or
Planning Workspace schema metadata.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import threading
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from uuid import uuid4

from services.ozon_account_repository import split_store_tenant_scope
from services.fifo_cost_allocation_service import FifoCostLayer, FifoOpenCostRate, FifoSaleEvent
from services.fifo_cost_replay_service import FifoCostReplayService, FifoDatedAllocationEvent
from services.tenant_context import get_current_tenant_user_id
from services.tenant_storage import ensure_storage_parent, tenant_storage_path


class FifoCostRepository:
    SCHEMA_VERSION = 6
    MAX_COMMAND_EVENTS = 100
    MAX_REFERENCES_PER_SOURCE = 100
    MAX_EVENT_QUANTITY = 100_000
    MAX_COMMAND_UNITS = 1_000_000
    MAX_PAYLOAD_BYTES = 64 * 1024
    PREVIEW_TTL_SECONDS = 600
    MAX_PREVIEWS = 5000
    _HEX_DIGEST = re.compile(r"^[0-9a-f]{64}$")
    _IDEMPOTENCY_KEY = re.compile(r"^[A-Za-z0-9_-]{8,80}$")
    _EVENT_KINDS = frozenset({
        "OPENING_FIFO_ANCHOR", "COST_LAYER_RECEIPT", "INVENTORY_TRANSFER",
        "PHYSICAL_SALE", "SALE_CANCELLATION", "SALEABLE_RETURN_RESTOCK",
        "NON_SALE_OUTFLOW", "CORRECTION",
    })
    _SOURCE_STATUSES = frozenset({
        "COMPLETE", "PARTIAL", "UNAVAILABLE", "STALE", "CONFLICT",
        "NOT_REQUESTED", "OWNER_CONFIRMED", "MODEL_ONLY",
    })
    _PROVENANCE = frozenset({
        "OWNER_CONFIRMED", "OZON_CONFIRMED_FIELD", "DOCUMENT_RECONCILED",
        "LEGACY_DATED_COST", "MODEL_ASSUMPTION",
    })
    _REFERENCE_KINDS = frozenset({"ORDER", "SUPPLY", "ACT", "POSTING", "DOCUMENT", "OTHER"})
    _LOCATIONS = frozenset({"HOME", "TRANSIT", "OZON", "UNKNOWN"})
    _REASON_CODES = frozenset({
        "HISTORY_GAP", "ANCHOR_UNCONFIRMED", "INVENTORY_CUTOFF_UNRECONCILED",
        "PHYSICAL_SALE_IDENTITY_UNCONFIRMED", "STOCK_SEMANTICS_UNCONFIRMED",
        "TRANSIT_OVERLAP_UNRESOLVED", "SUPPLY_COST_LINK_MISSING",
        "EVENT_ORDER_UNRESOLVED", "RECONCILIATION_CONFLICT", "STALE_PREVIEW",
        "REVISION_CONFLICT", "BUDGET_EXHAUSTED", "SOURCE_UNAVAILABLE",
        "PERIOD_PROFIT_COST_LEGACY_PROVENANCE_AMBIGUOUS",
        "OWNER_REPORTED_LATE", "COST_ENTRY_CORRECTION", "QUANTITY_CORRECTION",
        "SUPPLY_LINK_CORRECTION", "CANCELLED_FUTURE_CHANGE",
    })
    _PREVIEW_LOCK = threading.RLock()
    _ACTIVE_PREVIEWS = {}
    _ACTIVE_RATE_PREVIEWS = {}

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
        "fifo_cost_allocation_rate_lines",
        "fifo_cost_idempotency",
        "fifo_cost_commands",
        "fifo_cost_command_events",
        "fifo_cost_rate_changes",
        "fifo_cost_rate_reconciliations",
        "fifo_cost_supply_evidence",
    )

    _APPEND_ONLY_TABLES = (
        "fifo_cost_sources",
        "fifo_cost_source_refs",
        "fifo_cost_policy_revisions",
        "fifo_cost_events",
        "fifo_cost_layers",
        "fifo_cost_allocations",
        "fifo_cost_allocation_lines",
        "fifo_cost_allocation_rate_lines",
        "fifo_cost_idempotency",
        "fifo_cost_commands",
        "fifo_cost_command_events",
        "fifo_cost_rate_changes",
        "fifo_cost_rate_reconciliations",
        "fifo_cost_supply_evidence",
    )

    def __init__(self, db_path=None, *, now_provider=None):
        self._db_path = Path(db_path) if db_path is not None else None
        self._now_provider = now_provider or (lambda: datetime.now(timezone.utc))

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

    def read_cost_history_snapshot(
        self, *, store_id, product_id=None, offer_id=None, sku,
    ):
        """Read one exact tenant/store/SKU history without exposing opaque IDs."""
        scope = self._tenant_scope(store_id)
        if scope.get("error"):
            return scope
        connection = None
        try:
            identity = self._normalize_identity(
                store_id, product_id, offer_id, sku, 1,
            )
            identity_fingerprint = self._sha256(identity)
            stream_id = "fifo_" + identity_fingerprint[:40]
            connection = self.get_connection()
            stream = connection.execute(
                """SELECT state, revision FROM fifo_cost_streams
                   WHERE stream_id=? AND store_id=? AND identity_fingerprint=?""",
                (stream_id, identity["store_id"], identity_fingerprint),
            ).fetchone()
            if stream is None:
                return {
                    "error": False,
                    "code": "FIFO_HISTORY_NOT_INITIALIZED",
                    "revision": 0,
                    "stream_state": "FIFO_PENDING_ANCHOR",
                    "projection": None,
                    "layers": [],
                    "rates": [],
                    "rate_reconciliations": [],
                    "event_counts": {},
                    "movement_count": 0,
                    "latest_allocation": None,
                    "cutoff_date": None,
                }

            projection_row = connection.execute(
                """SELECT revision, state, known_quantity, known_cost_rub,
                          next_unit_cost_rub, queue_complete, cutoff_status,
                          updated_at
                   FROM fifo_cost_projections WHERE stream_id=?""",
                (stream_id,),
            ).fetchone()
            projection = None if projection_row is None else {
                "revision": projection_row["revision"],
                "state": projection_row["state"],
                "known_quantity": projection_row["known_quantity"],
                "known_cost_rub": projection_row["known_cost_rub"],
                "next_unit_cost_rub": projection_row["next_unit_cost_rub"],
                "queue_complete": bool(projection_row["queue_complete"]),
                "cutoff_status": projection_row["cutoff_status"],
                "updated_at": projection_row["updated_at"],
            }
            layer_rows = connection.execute(
                """SELECT l.layer_sequence, l.quantity, l.unit_cost_rub,
                          l.effective_date, l.provenance, e.location_to,
                          s.source_status, s.coverage_status
                   FROM fifo_cost_layers AS l
                   JOIN fifo_cost_events AS e ON e.event_id=l.event_id
                   LEFT JOIN fifo_cost_sources AS s ON s.source_id=l.source_id
                   WHERE l.stream_id=?
                   ORDER BY l.layer_sequence""",
                (stream_id,),
            ).fetchall()
            layers = [{
                "sequence": row["layer_sequence"],
                "recorded_quantity": row["quantity"],
                "unit_cost_rub": row["unit_cost_rub"],
                "effective_date": row["effective_date"],
                "provenance": row["provenance"],
                "location": row["location_to"],
                "source_status": row["source_status"],
                "coverage_status": row["coverage_status"],
            } for row in layer_rows]
            rate_rows = connection.execute(
                """SELECT r.rate_sequence, r.effective_date, r.unit_cost_rub,
                          r.purchase_cost_rub, r.delivery_cost_rub,
                          r.packaging_cost_rub, r.owner_old_home_units,
                          r.recorded_at, r.captured_at, s.provenance,
                          s.source_status, s.coverage_status
                   FROM fifo_cost_rate_changes AS r
                   LEFT JOIN fifo_cost_sources AS s ON s.source_id=r.source_id
                   WHERE r.stream_id=?
                   ORDER BY r.rate_sequence""",
                (stream_id,),
            ).fetchall()
            rates = [{
                "sequence": row["rate_sequence"],
                "effective_date": row["effective_date"],
                "unit_cost_rub": row["unit_cost_rub"],
                "purchase_cost_rub": row["purchase_cost_rub"],
                "delivery_cost_rub": row["delivery_cost_rub"],
                "packaging_cost_rub": row["packaging_cost_rub"],
                "owner_old_home_units": row["owner_old_home_units"],
                "recorded_at": row["recorded_at"],
                "captured_at": row["captured_at"],
                "provenance": row["provenance"],
                "source_status": row["source_status"],
                "coverage_status": row["coverage_status"],
            } for row in rate_rows]
            reconciliation_rows = connection.execute(
                """SELECT transition_rate_sequence, reconciled_rate_sequence,
                          reconciled_total_units, older_finite_units,
                          prior_rate_units, fbo_units, reserved_units,
                          transit_units, home_units, captured_at
                   FROM fifo_cost_rate_reconciliations
                   WHERE stream_id=? ORDER BY transition_rate_sequence""",
                (stream_id,),
            ).fetchall()
            rate_reconciliations = [{
                "transition_rate_sequence": row["transition_rate_sequence"],
                "reconciled_rate_sequence": row["reconciled_rate_sequence"],
                "reconciled_total_units": row["reconciled_total_units"],
                "older_finite_units": row["older_finite_units"],
                "prior_rate_units": row["prior_rate_units"],
                "fbo_units": row["fbo_units"],
                "reserved_units": row["reserved_units"],
                "transit_units": row["transit_units"],
                "home_units": row["home_units"],
                "captured_at": row["captured_at"],
            } for row in reconciliation_rows]
            event_rows = connection.execute(
                """SELECT event_kind, COUNT(*) AS event_count
                   FROM fifo_cost_events WHERE stream_id=?
                   GROUP BY event_kind""",
                (stream_id,),
            ).fetchall()
            event_counts = {row["event_kind"]: row["event_count"] for row in event_rows}
            movement_count = sum(
                count for kind, count in event_counts.items()
                if kind not in {"OPENING_FIFO_ANCHOR", "COST_LAYER_RECEIPT"}
            )
            allocation = connection.execute(
                """SELECT revision, stream_revision, status, cutoff_status, created_at
                   FROM fifo_cost_allocations WHERE stream_id=?
                   ORDER BY revision DESC LIMIT 1""",
                (stream_id,),
            ).fetchone()
            latest_allocation = None if allocation is None else {
                "revision": allocation["revision"],
                "stream_revision": allocation["stream_revision"],
                "status": allocation["status"],
                "cutoff_status": allocation["cutoff_status"],
                "stale": allocation["stream_revision"] != stream["revision"],
                "created_at": allocation["created_at"],
            }
            cutoff_date = connection.execute(
                """SELECT MIN(inventory_cutoff) FROM fifo_cost_events
                   WHERE stream_id=? AND event_kind='OPENING_FIFO_ANCHOR'""",
                (stream_id,),
            ).fetchone()[0]
            return {
                "error": False,
                "code": "FIFO_HISTORY_READY",
                "revision": stream["revision"],
                "stream_state": stream["state"],
                "projection": projection,
                "layers": layers,
                "rates": rates,
                "rate_reconciliations": rate_reconciliations,
                "event_counts": event_counts,
                "movement_count": movement_count,
                "latest_allocation": latest_allocation,
                "cutoff_date": cutoff_date,
            }
        except (TypeError, ValueError, InvalidOperation, OverflowError) as exc:
            code = str(exc) if str(exc).startswith("FIFO_") else "FIFO_IDENTITY_INVALID"
            return self._error(code)
        except (sqlite3.Error, OSError):
            return self._error("FIFO_STORAGE_UNAVAILABLE")
        finally:
            if connection is not None:
                connection.close()

    def read_allocation_guard(self, *, store_id, product_id=None, offer_id=None, sku):
        """Return the current replay CAS token without exposing event payloads."""
        scope = self._tenant_scope(store_id)
        if scope.get("error"):
            return scope
        connection = None
        try:
            identity = self._normalize_identity(
                store_id, product_id, offer_id, sku, 1,
            )
            fingerprint = self._sha256(identity)
            stream_id = "fifo_" + fingerprint[:40]
            connection = self.get_connection()
            stream = connection.execute(
                """SELECT revision, policy_version, state
                   FROM fifo_cost_streams
                   WHERE stream_id=? AND store_id=? AND identity_fingerprint=?""",
                (stream_id, identity["store_id"], fingerprint),
            ).fetchone()
            if stream is None:
                return self._error("FIFO_HISTORY_NOT_INITIALIZED")
            projection = connection.execute(
                """SELECT cutoff_status, queue_complete
                   FROM fifo_cost_projections WHERE stream_id=?""",
                (stream_id,),
            ).fetchone()
            if projection is None:
                return self._error("FIFO_PROJECTION_UNAVAILABLE")
            allocation_revision = connection.execute(
                """SELECT COALESCE(MAX(revision), 0)
                   FROM fifo_cost_allocations WHERE stream_id=?""",
                (stream_id,),
            ).fetchone()[0]
            event_count = connection.execute(
                "SELECT COUNT(*) FROM fifo_cost_events WHERE stream_id=?",
                (stream_id,),
            ).fetchone()[0]
            if event_count > 100_000:
                return self._error("FIFO_REPLAY_INPUT_LIMIT")
            source_fingerprint = self._allocation_source_fingerprint(
                connection, stream_id, stream["revision"],
                stream["policy_version"], projection["cutoff_status"],
            )
            untrusted_sale_count = connection.execute(
                """SELECT COUNT(*) FROM fifo_cost_events AS e
                   LEFT JOIN fifo_cost_sources AS s ON s.source_id=e.source_id
                   WHERE e.stream_id=? AND e.event_kind='PHYSICAL_SALE' AND NOT (
                       e.provenance='OZON_CONFIRMED_FIELD'
                       AND e.completeness='COMPLETE'
                       AND s.source_method='OZON_REALIZATION_REPORT'
                       AND s.source_status='COMPLETE'
                       AND s.coverage_status='COMPLETE'
                   )""",
                (stream_id,),
            ).fetchone()[0]
            anchor_meta = connection.execute(
                """SELECT COUNT(DISTINCT inventory_cutoff), MIN(inventory_cutoff)
                   FROM fifo_cost_events
                   WHERE stream_id=? AND event_kind='OPENING_FIFO_ANCHOR'""",
                (stream_id,),
            ).fetchone()
            anchor_cutoff_date = (
                anchor_meta[1] if anchor_meta[0] == 1 else None
            )
            unsupported_event_count = connection.execute(
                """SELECT COUNT(*) FROM fifo_cost_events
                   WHERE stream_id=? AND event_kind NOT IN (
                       'OPENING_FIFO_ANCHOR', 'PHYSICAL_SALE'
                   )""",
                (stream_id,),
            ).fetchone()[0]
            rate_count = connection.execute(
                "SELECT COUNT(*) FROM fifo_cost_rate_changes WHERE stream_id=?",
                (stream_id,),
            ).fetchone()[0]
            cutoff_mismatch_sale_count = connection.execute(
                """SELECT COUNT(*) FROM fifo_cost_events
                   WHERE stream_id=? AND event_kind='PHYSICAL_SALE'
                     AND (effective_date IS NULL OR inventory_cutoff IS NULL
                          OR inventory_cutoff<>? OR effective_date<=?)""",
                (stream_id, anchor_cutoff_date or "", anchor_cutoff_date or ""),
            ).fetchone()[0]
            replay = None
            if (
                stream["state"] in {"FIFO_READY", "FIFO_PARTIAL"}
                and projection["cutoff_status"] == "RECONCILED"
                and untrusted_sale_count == 0
                and anchor_cutoff_date is not None
                and unsupported_event_count == 0
                and rate_count <= 1
                and cutoff_mismatch_sale_count == 0
            ):
                replay = self._preview_allocation_from_connection(
                    connection, stream_id,
                    stream_revision=stream["revision"],
                    allocation_revision=allocation_revision,
                    source_fingerprint=source_fingerprint,
                    cutoff_status=projection["cutoff_status"],
                    anchor_cutoff_date=anchor_cutoff_date,
                )
            replay_ready = replay is not None and replay.get("complete") is True
            return {
                "error": False,
                "code": "FIFO_ALLOCATION_GUARD_READY",
                "stream_revision": stream["revision"],
                "allocation_revision": allocation_revision,
                "policy_version": stream["policy_version"],
                "stream_state": stream["state"],
                "cutoff_status": projection["cutoff_status"],
                "queue_complete": bool(projection["queue_complete"]),
                "source_set_fingerprint": source_fingerprint,
                "event_count": event_count,
                "untrusted_sale_count": untrusted_sale_count,
                "anchor_cutoff_date": anchor_cutoff_date,
                "unsupported_event_count": unsupported_event_count,
                "unsupported_rate_transition_count": max(0, rate_count - 1),
                "cutoff_mismatch_sale_count": cutoff_mismatch_sale_count,
                "replay_reason_code": (
                    None if replay_ready else
                    replay.get("reason_code") if replay is not None else
                    "FIFO_REPLAY_SOURCE_GATE_UNRESOLVED"
                ),
                "eligible_for_publication": (
                    stream["state"] in {"FIFO_READY", "FIFO_PARTIAL"}
                    and projection["cutoff_status"] == "RECONCILED"
                    and untrusted_sale_count == 0
                    and anchor_cutoff_date is not None
                    and unsupported_event_count == 0
                    and rate_count <= 1
                    and cutoff_mismatch_sale_count == 0
                    and replay_ready
                ),
            }
        except (TypeError, ValueError, InvalidOperation, OverflowError) as exc:
            code = str(exc) if str(exc).startswith("FIFO_") else "FIFO_IDENTITY_INVALID"
            return self._error(code)
        except (sqlite3.Error, OSError):
            return self._error("FIFO_STORAGE_UNAVAILABLE")
        finally:
            if connection is not None:
                connection.close()

    def read_period_allocation_summary(
        self, *, store_id, product_id=None, offer_id=None, sku,
        date_from, date_to,
    ):
        """Read one exact SKU's latest complete FIFO COGS allocation by period."""
        start = self._normalize_date(date_from)
        end = self._normalize_date(date_to)
        if start is None or end is None or start > end:
            return self._error("FIFO_PERIOD_INVALID")
        scope = self._tenant_scope(store_id)
        if scope.get("error"):
            return scope
        connection = None
        try:
            identity = self._normalize_identity(
                store_id, product_id, offer_id, sku, 1,
            )
            identity_fingerprint = self._sha256(identity)
            stream_id = "fifo_" + identity_fingerprint[:40]
            connection = self.get_connection()
            connection.execute("BEGIN")
            stream = connection.execute(
                """SELECT revision, policy_version, state
                   FROM fifo_cost_streams
                   WHERE stream_id=? AND store_id=? AND identity_fingerprint=?""",
                (stream_id, identity["store_id"], identity_fingerprint),
            ).fetchone()
            if stream is None or stream["state"] in {"LEGACY", "FIFO_PENDING_ANCHOR"}:
                connection.rollback()
                return {
                    "error": False, "code": "FIFO_COST_MODE_NOT_ACTIVE",
                    "active": False,
                }
            if stream["state"] not in {"FIFO_READY", "FIFO_PARTIAL"}:
                connection.rollback()
                return {
                    "error": False, "code": "FIFO_COST_SCOPE_INCOMPLETE",
                    "active": True, "complete": False,
                    "reason_code": "FIFO_STREAM_NOT_READY",
                }
            projection = connection.execute(
                "SELECT cutoff_status FROM fifo_cost_projections WHERE stream_id=?",
                (stream_id,),
            ).fetchone()
            if projection is None or projection["cutoff_status"] != "RECONCILED":
                connection.rollback()
                return {
                    "error": False, "code": "FIFO_COST_SCOPE_INCOMPLETE",
                    "active": True, "complete": False,
                    "reason_code": "INVENTORY_CUTOFF_UNRECONCILED",
                }
            anchor = connection.execute(
                """SELECT COUNT(DISTINCT inventory_cutoff), MIN(inventory_cutoff)
                   FROM fifo_cost_events
                   WHERE stream_id=? AND event_kind='OPENING_FIFO_ANCHOR'""",
                (stream_id,),
            ).fetchone()
            if anchor[0] != 1 or self._normalize_date(anchor[1]) is None:
                connection.rollback()
                return {
                    "error": False, "code": "FIFO_COST_SCOPE_INCOMPLETE",
                    "active": True, "complete": False,
                    "reason_code": "INVENTORY_CUTOFF_UNRECONCILED",
                }
            anchor_cutoff = anchor[1]
            source_fingerprint = self._allocation_source_fingerprint(
                connection, stream_id, stream["revision"],
                stream["policy_version"], projection["cutoff_status"],
            )
            allocation = connection.execute(
                """SELECT allocation_id, revision, stream_revision,
                          source_set_fingerprint, cutoff_status, status
                   FROM fifo_cost_allocations WHERE stream_id=?
                   ORDER BY revision DESC LIMIT 1""",
                (stream_id,),
            ).fetchone()
            sale_rows = connection.execute(
                """SELECT e.event_id, e.effective_date, e.inventory_cutoff,
                          e.quantity, e.source_identity_digest, e.provenance,
                          e.completeness, s.source_method, s.source_status,
                          s.coverage_status
                   FROM fifo_cost_events AS e
                   LEFT JOIN fifo_cost_sources AS s ON s.source_id=e.source_id
                   WHERE e.stream_id=? AND e.event_kind='PHYSICAL_SALE'
                   ORDER BY e.event_id LIMIT 100001""",
                (stream_id,),
            ).fetchall()
            if len(sale_rows) > 100_000:
                connection.rollback()
                return {
                    "error": False, "code": "FIFO_COST_SCOPE_INCOMPLETE",
                    "active": True, "complete": False,
                    "reason_code": "FIFO_REPLAY_INPUT_LIMIT",
                }
            if not sale_rows and allocation is None:
                connection.commit()
                return {
                    "error": False, "code": "FIFO_COST_PERIOD_READY",
                    "active": True, "complete": True,
                    "stream_revision": stream["revision"],
                    "allocation_revision": 0,
                    "cutoff_date": anchor_cutoff,
                    "allocations": [],
                }
            if (
                allocation is None
                or allocation["status"] != "COMPLETE"
                or allocation["cutoff_status"] != "RECONCILED"
                or allocation["stream_revision"] != stream["revision"]
                or allocation["source_set_fingerprint"] != source_fingerprint
            ):
                connection.rollback()
                return {
                    "error": False, "code": "FIFO_COST_SCOPE_INCOMPLETE",
                    "active": True, "complete": False,
                    "reason_code": "FIFO_ALLOCATION_STALE_OR_MISSING",
                }

            source_by_id = {}
            for row in sale_rows:
                effective_date = self._normalize_date(row["effective_date"])
                if (
                    effective_date is None or effective_date <= anchor_cutoff
                    or row["inventory_cutoff"] != anchor_cutoff
                    or not self._valid_digest(row["source_identity_digest"])
                    or row["provenance"] != "OZON_CONFIRMED_FIELD"
                    or row["completeness"] != "COMPLETE"
                    or row["source_method"] != "OZON_REALIZATION_REPORT"
                    or row["source_status"] != "COMPLETE"
                    or row["coverage_status"] != "COMPLETE"
                ):
                    connection.rollback()
                    return {
                        "error": False, "code": "FIFO_COST_SCOPE_INCOMPLETE",
                        "active": True, "complete": False,
                        "reason_code": "FIFO_ALLOCATION_SOURCE_INVALID",
                    }
                source_by_id[row["event_id"]] = row

            line_rows = connection.execute(
                """SELECT event_id, layer_id AS basis_id, quantity,
                          unit_cost_rub, total_cost_rub, 'LAYER' AS basis_kind
                   FROM fifo_cost_allocation_lines WHERE allocation_id=?
                   UNION ALL
                   SELECT event_id, rate_change_id AS basis_id, quantity,
                          unit_cost_rub, total_cost_rub, 'RATE' AS basis_kind
                   FROM fifo_cost_allocation_rate_lines WHERE allocation_id=?
                   ORDER BY event_id, basis_kind, basis_id""",
                (allocation["allocation_id"], allocation["allocation_id"]),
            ).fetchall()
            by_event = {}
            for line in line_rows:
                quantity = line["quantity"]
                unit_cost = self._normalize_money(line["unit_cost_rub"])
                total_cost = self._normalize_money(line["total_cost_rub"])
                if (
                    line["event_id"] not in source_by_id
                    or type(quantity) is not int or quantity <= 0
                    or unit_cost is None or total_cost is None
                    or (Decimal(unit_cost) * quantity).quantize(
                        Decimal("0.01"), rounding=ROUND_HALF_UP,
                    ) != Decimal(total_cost)
                ):
                    connection.rollback()
                    return {
                        "error": False, "code": "FIFO_COST_SCOPE_INCOMPLETE",
                        "active": True, "complete": False,
                        "reason_code": "FIFO_ALLOCATION_LINE_INVALID",
                    }
                if line["basis_kind"] == "LAYER":
                    basis = connection.execute(
                        """SELECT l.unit_cost_rub FROM fifo_cost_layers AS l
                           WHERE l.stream_id=? AND l.layer_id=?""",
                        (stream_id, line["basis_id"]),
                    ).fetchone()
                else:
                    basis = connection.execute(
                        """SELECT r.unit_cost_rub FROM fifo_cost_rate_changes AS r
                           WHERE r.stream_id=? AND r.rate_change_id=?""",
                        (stream_id, line["basis_id"]),
                    ).fetchone()
                if basis is None or self._normalize_money(basis[0]) != unit_cost:
                    connection.rollback()
                    return {
                        "error": False, "code": "FIFO_COST_SCOPE_INCOMPLETE",
                        "active": True, "complete": False,
                        "reason_code": "FIFO_ALLOCATION_BASIS_INVALID",
                    }
                group = by_event.setdefault(line["event_id"], {
                    "quantity": 0, "total": Decimal("0.00"),
                })
                group["quantity"] += quantity
                group["total"] += Decimal(total_cost)
            if set(by_event) != set(source_by_id):
                connection.rollback()
                return {
                    "error": False, "code": "FIFO_COST_SCOPE_INCOMPLETE",
                    "active": True, "complete": False,
                    "reason_code": "FIFO_ALLOCATION_COVERAGE_MISMATCH",
                }

            allocations = []
            digests = set()
            for event_id, row in source_by_id.items():
                group = by_event[event_id]
                digest = row["source_identity_digest"]
                if (
                    group["quantity"] != row["quantity"]
                    or digest in digests
                ):
                    connection.rollback()
                    return {
                        "error": False, "code": "FIFO_COST_SCOPE_INCOMPLETE",
                        "active": True, "complete": False,
                        "reason_code": "FIFO_ALLOCATION_COVERAGE_MISMATCH",
                    }
                digests.add(digest)
                total = group["total"].quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP,
                )
                if start <= row["effective_date"] <= end:
                    allocations.append({
                        "source_identity_digest": digest,
                        "effective_date": row["effective_date"],
                        "quantity": row["quantity"],
                        "total_cogs_rub": format(total, ".2f"),
                    })
            allocations.sort(key=lambda item: (
                item["effective_date"], item["source_identity_digest"],
            ))
            connection.commit()
            return {
                "error": False, "code": "FIFO_COST_PERIOD_READY",
                "active": True, "complete": True,
                "stream_revision": stream["revision"],
                "allocation_revision": allocation["revision"],
                "cutoff_date": anchor_cutoff,
                "allocations": allocations,
            }
        except (TypeError, ValueError, InvalidOperation, OverflowError) as exc:
            if connection is not None and connection.in_transaction:
                connection.rollback()
            code = str(exc) if str(exc).startswith("FIFO_") else "FIFO_IDENTITY_INVALID"
            return self._error(code)
        except (sqlite3.Error, OSError):
            if connection is not None and connection.in_transaction:
                connection.rollback()
            return self._error("FIFO_STORAGE_UNAVAILABLE")
        finally:
            if connection is not None:
                connection.close()

    def read_cost_mode_status(
        self, *, store_id, product_id=None, offer_id=None, sku,
    ):
        """Read the exact-SKU cutover state without resolving any cost value."""
        scope = self._tenant_scope(store_id)
        if scope.get("error"):
            return scope
        connection = None
        try:
            identity = self._normalize_identity(
                store_id, product_id, offer_id, sku, 1,
            )
            fingerprint = self._sha256(identity)
            stream_id = "fifo_" + fingerprint[:40]
            connection = self.get_connection()
            stream = connection.execute(
                """SELECT revision, state FROM fifo_cost_streams
                   WHERE stream_id=? AND store_id=? AND identity_fingerprint=?""",
                (stream_id, identity["store_id"], fingerprint),
            ).fetchone()
            if stream is None or stream["state"] in {"LEGACY", "FIFO_PENDING_ANCHOR"}:
                return {
                    "error": False, "code": "FIFO_COST_MODE_LEGACY",
                    "active": False,
                }
            return {
                "error": False, "code": "FIFO_COST_MODE_FIFO",
                "active": True,
                "stream_state": stream["state"],
                "stream_revision": stream["revision"],
            }
        except (TypeError, ValueError, InvalidOperation, OverflowError) as exc:
            code = str(exc) if str(exc).startswith("FIFO_") else "FIFO_IDENTITY_INVALID"
            return self._error(code)
        except (sqlite3.Error, OSError):
            return self._error("FIFO_STORAGE_UNAVAILABLE")
        finally:
            if connection is not None:
                connection.close()

    def append_allocation_revision(
        self, *, store_id, product_id=None, offer_id=None, sku,
        preview, idempotency_key,
    ):
        """Atomically publish a complete immutable projection with source CAS."""
        scope = self._tenant_scope(store_id)
        if scope.get("error"):
            return scope
        try:
            normalized = self._normalize_allocation_preview(preview, idempotency_key)
        except ValueError as exc:
            code = str(exc) if str(exc).startswith("FIFO_") else "FIFO_ALLOCATION_PREVIEW_INVALID"
            return self._error(code)
        if isinstance(normalized, str):
            return self._error(normalized)
        connection = None
        try:
            identity = self._normalize_identity(
                store_id, product_id, offer_id, sku, 1,
            )
            identity_fingerprint = self._sha256(identity)
            stream_id = "fifo_" + identity_fingerprint[:40]
            connection = self.get_connection()
            connection.execute("BEGIN IMMEDIATE")
            key = "allocation-" + idempotency_key
            prior = connection.execute(
                """SELECT payload_fingerprint, result_reference
                   FROM fifo_cost_idempotency WHERE stream_id=? AND idempotency_key=?""",
                (stream_id, key),
            ).fetchone()
            if prior is not None:
                if prior["payload_fingerprint"] != normalized["payload_fingerprint"]:
                    connection.rollback()
                    return self._error("FIFO_IDEMPOTENCY_CONFLICT")
                result = json.loads(prior["result_reference"])
                connection.rollback()
                return {"error": False, "code": "FIFO_ALLOCATION_COMMITTED",
                        "idempotent": True, **result}

            stream = connection.execute(
                """SELECT revision, policy_version, state
                   FROM fifo_cost_streams
                   WHERE stream_id=? AND store_id=? AND identity_fingerprint=?""",
                (stream_id, identity["store_id"], identity_fingerprint),
            ).fetchone()
            projection = connection.execute(
                """SELECT cutoff_status FROM fifo_cost_projections
                   WHERE stream_id=?""",
                (stream_id,),
            ).fetchone()
            if stream is None or projection is None:
                connection.rollback()
                return self._error("FIFO_HISTORY_NOT_INITIALIZED")
            if stream["revision"] != normalized["stream_revision"]:
                connection.rollback()
                return self._error("FIFO_REVISION_CONFLICT")
            if (
                stream["state"] not in {"FIFO_READY", "FIFO_PARTIAL"}
                or projection["cutoff_status"] != "RECONCILED"
            ):
                connection.rollback()
                return self._error("INVENTORY_CUTOFF_UNRECONCILED")
            current_fingerprint = self._allocation_source_fingerprint(
                connection, stream_id, stream["revision"],
                stream["policy_version"], projection["cutoff_status"],
            )
            if current_fingerprint != normalized["source_set_fingerprint"]:
                connection.rollback()
                return self._error("FIFO_SOURCE_REVISION_CONFLICT")
            current_allocation_revision = connection.execute(
                """SELECT COALESCE(MAX(revision), 0)
                   FROM fifo_cost_allocations WHERE stream_id=?""",
                (stream_id,),
            ).fetchone()[0]
            if current_allocation_revision != normalized["expected_allocation_revision"]:
                connection.rollback()
                return self._error("FIFO_REVISION_CONFLICT")

            self._validate_allocation_lines(
                connection, stream_id, normalized,
                stream_revision=stream["revision"],
                allocation_revision=current_allocation_revision,
                source_fingerprint=current_fingerprint,
                cutoff_status=projection["cutoff_status"],
            )
            allocation_revision = current_allocation_revision + 1
            allocation_id = "alloc_" + uuid4().hex
            now = self._iso(self._now())
            connection.execute(
                """INSERT INTO fifo_cost_allocations (
                    allocation_id, stream_id, revision, stream_revision,
                    policy_version, source_set_fingerprint, cutoff_status,
                    status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'RECONCILED', 'COMPLETE', ?)""",
                (
                    allocation_id, stream_id, allocation_revision,
                    stream["revision"], stream["policy_version"],
                    normalized["source_set_fingerprint"], now,
                ),
            )
            line_number = 0
            for allocation in normalized["allocations"]:
                for line in allocation["lines"]:
                    line_number += 1
                    origin_id = line["origin_sale_event_id"]
                    basis_allocation_id = None
                    basis_line_number = None
                    if origin_id is not None:
                        if line["layer_id"] is None:
                            raise ValueError("FIFO_ALLOCATION_BASIS_MISSING")
                        basis = connection.execute(
                            """SELECT l.allocation_id, l.line_number
                               FROM fifo_cost_allocation_lines AS l
                               JOIN fifo_cost_allocations AS a
                                 ON a.allocation_id=l.allocation_id
                               WHERE a.stream_id=? AND l.event_id=? AND l.layer_id=?
                               ORDER BY a.revision DESC, l.line_number LIMIT 1""",
                            (stream_id, origin_id, line["layer_id"]),
                        ).fetchone()
                        if basis is None:
                            raise ValueError("FIFO_ALLOCATION_BASIS_MISSING")
                        basis_allocation_id = basis["allocation_id"]
                        basis_line_number = basis["line_number"]
                    if line["layer_id"] is not None:
                        connection.execute(
                            """INSERT INTO fifo_cost_allocation_lines (
                                allocation_id, line_number, event_id, layer_id,
                                quantity, unit_cost_rub, total_cost_rub,
                                basis_allocation_id, basis_line_number
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                            (
                                allocation_id, line_number, allocation["event_id"],
                                line["layer_id"], line["quantity"],
                                line["unit_cost_rub"], line["total_cost_rub"],
                                basis_allocation_id, basis_line_number,
                            ),
                        )
                    else:
                        connection.execute(
                            """INSERT INTO fifo_cost_allocation_rate_lines (
                                allocation_id, line_number, event_id, rate_change_id,
                                quantity, unit_cost_rub, total_cost_rub,
                                basis_allocation_id, basis_line_number
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                            (
                                allocation_id, line_number, allocation["event_id"],
                                line["rate_change_id"], line["quantity"],
                                line["unit_cost_rub"], line["total_cost_rub"],
                                basis_allocation_id, basis_line_number,
                            ),
                        )
            result = {
                "allocation_id": allocation_id,
                "allocation_revision": allocation_revision,
                "stream_revision": stream["revision"],
                "line_count": line_number,
            }
            connection.execute(
                """INSERT INTO fifo_cost_idempotency (
                    stream_id, idempotency_key, payload_fingerprint,
                    result_reference, created_at
                ) VALUES (?, ?, ?, ?, ?)""",
                (
                    stream_id, key, normalized["payload_fingerprint"],
                    self._canonical_json(result), now,
                ),
            )
            connection.commit()
            return {"error": False, "code": "FIFO_ALLOCATION_COMMITTED",
                    "idempotent": False, **result}
        except ValueError as exc:
            if connection is not None and connection.in_transaction:
                connection.rollback()
            code = str(exc) if (
                str(exc).startswith("FIFO_") or str(exc) in self._REASON_CODES
            ) else "FIFO_ALLOCATION_INVALID"
            return self._error(code)
        except sqlite3.IntegrityError:
            if connection is not None and connection.in_transaction:
                connection.rollback()
            return self._error("FIFO_REVISION_CONFLICT")
        except (sqlite3.Error, OSError):
            if connection is not None and connection.in_transaction:
                connection.rollback()
            return self._error("FIFO_STORAGE_UNAVAILABLE")
        finally:
            if connection is not None:
                connection.close()

    def record_supply_evidence(
        self, *, store_id, product_id=None, offer_id=None, sku, snapshot,
    ):
        """Append a reconciled supply-act snapshot without creating inventory."""
        scope = self._tenant_scope(store_id)
        if scope.get("error"):
            return scope
        connection = None
        try:
            from services.fifo_cost_source_normalizer import (
                FifoCostSourceNormalizer,
                FifoSupplyActEvidence,
                FifoSupplyActSnapshot,
            )

            if not isinstance(snapshot, FifoSupplyActSnapshot):
                return self._error("FIFO_SUPPLY_SNAPSHOT_INVALID")
            identity = self._normalize_identity(store_id, product_id, offer_id, sku, 1)
            if (
                snapshot.status not in {"COMPLETE", "CONFIRMED_ZERO"}
                or snapshot.source_status != "COMPLETE"
            ):
                return self._error("FIFO_SUPPLY_SOURCE_NOT_COMPLETE")
            if (
                snapshot.store_id != identity["store_id"]
                or snapshot.effective_at is not None
                or snapshot.order_ref is None
                or not self._valid_digest(snapshot.order_ref)
                or snapshot.supply_ref is None
                or not self._valid_digest(snapshot.supply_ref)
                or snapshot.evidence_fingerprint is None
                or not self._valid_digest(snapshot.evidence_fingerprint)
                or snapshot.source_fingerprint is None
                or not self._valid_digest(snapshot.source_fingerprint)
                or self._normalize_timestamp(snapshot.captured_at) is None
            ):
                return self._error("FIFO_SUPPLY_SNAPSHOT_INVALID")
            units_by_sku = snapshot.units_by_sku
            if (
                not isinstance(units_by_sku, tuple)
                or len(units_by_sku) != 1
                or not isinstance(units_by_sku[0], tuple)
                or len(units_by_sku[0]) != 2
                or units_by_sku[0][0] != identity["sku"]
                or type(units_by_sku[0][1]) is not int
                or not 0 <= units_by_sku[0][1] <= self.MAX_COMMAND_UNITS
            ):
                return self._error("FIFO_SUPPLY_SKU_IDENTITY_MISMATCH")
            if (
                not snapshot.act_evidence
                or len(snapshot.act_evidence) > self.MAX_PAYLOAD_BYTES // 64
                or not isinstance(snapshot.act_refs, tuple)
                or len(snapshot.act_refs) != len(snapshot.act_evidence)
            ):
                return self._error("FIFO_SUPPLY_ACT_EVIDENCE_INVALID")

            normalized_acts = []
            seen_act_refs = set()
            fact_total = 0
            for item in snapshot.act_evidence:
                if (
                    not isinstance(item, FifoSupplyActEvidence)
                    or not self._valid_digest(item.act_ref)
                    or item.act_ref in seen_act_refs
                    or item.act_type != "ACCEPTANCE"
                    or item.act_state != "ACCEPTED"
                    or type(item.fact_quantity) is not int
                    or not 0 <= item.fact_quantity <= self.MAX_COMMAND_UNITS
                ):
                    return self._error("FIFO_SUPPLY_ACT_EVIDENCE_INVALID")
                seen_act_refs.add(item.act_ref)
                if item.created_date is not None:
                    self._normalize_date(item.created_date)
                quantities = {}
                for field in ("declared_quantity", "approved_quantity"):
                    value = getattr(item, field)
                    if value is not None and (
                        type(value) is not int or not 0 <= value <= self.MAX_COMMAND_UNITS
                    ):
                        return self._error("FIFO_SUPPLY_ACT_EVIDENCE_INVALID")
                    quantities[field] = value
                fact_total += item.fact_quantity
                if fact_total > self.MAX_COMMAND_UNITS:
                    return self._error("FIFO_SUPPLY_QUANTITY_LIMIT")
                normalized_acts.append({
                    "act_ref": item.act_ref,
                    "act_type": item.act_type,
                    "act_state": item.act_state,
                    "created_date": item.created_date,
                    "created_date_kind": "DOCUMENT_CREATED_DATE_ONLY",
                    "declared_quantity": quantities["declared_quantity"],
                    "approved_quantity": quantities["approved_quantity"],
                    "fact_quantity": item.fact_quantity,
                })
            if (
                seen_act_refs != set(snapshot.act_refs)
                or fact_total != units_by_sku[0][1]
                or (snapshot.status == "CONFIRMED_ZERO") != (fact_total == 0)
            ):
                return self._error("FIFO_SUPPLY_ACT_EVIDENCE_MISMATCH")

            canonical_acts = sorted(normalized_acts, key=lambda row: row["act_ref"])
            normalized_fingerprint_payload = {
                "store_id": identity["store_id"],
                "order_ref": snapshot.order_ref,
                "supply_ref": snapshot.supply_ref,
                "act_refs": sorted(snapshot.act_refs),
                "act_evidence": [
                    {key: row[key] for key in (
                        "act_ref", "act_type", "act_state", "created_date",
                        "declared_quantity", "approved_quantity", "fact_quantity",
                    )}
                    for row in canonical_acts
                ],
                "units_by_sku": [[identity["sku"], fact_total]],
                "status": snapshot.status,
            }
            expected_evidence_fingerprint = FifoCostSourceNormalizer._fingerprint(
                normalized_fingerprint_payload,
            )
            expected_source_fingerprint = FifoCostSourceNormalizer._fingerprint({
                **normalized_fingerprint_payload,
                "captured_at": snapshot.captured_at,
            })
            if (
                expected_evidence_fingerprint != snapshot.evidence_fingerprint
                or expected_source_fingerprint != snapshot.source_fingerprint
            ):
                return self._error("FIFO_SUPPLY_EVIDENCE_FINGERPRINT_CONFLICT")

            identity_fingerprint = self._sha256(identity)
            stream_id = "fifo_" + identity_fingerprint[:40]
            normalized_payload = {
                "status": snapshot.status,
                "store_id": identity["store_id"],
                "sku": identity["sku"],
                "order_ref": snapshot.order_ref,
                "supply_ref": snapshot.supply_ref,
                "act_evidence": canonical_acts,
                "fact_units": fact_total,
                "source_as_of": None,
                "physical_effective_at": None,
                "physical_effective_date": None,
            }
            payload_json = self._canonical_json(normalized_payload)
            if len(payload_json.encode("utf-8")) > self.MAX_PAYLOAD_BYTES:
                return self._error("FIFO_SUPPLY_EVIDENCE_LIMIT")
            source = self._normalize_source({
                "kind": "OZON_API",
                "method": "FIFO_SUPPLY_ACT_SNAPSHOT",
                "status": "COMPLETE",
                "completeness": "COMPLETE",
                "provenance": "OZON_CONFIRMED_FIELD",
                "coverage_status": "COMPLETE",
                "fingerprint": snapshot.source_fingerprint,
                "captured_at": snapshot.captured_at,
                "record_count": len(normalized_acts),
                "page_count": 1,
                "references": [
                    {"kind": "ORDER", "digest": snapshot.order_ref},
                    {"kind": "SUPPLY", "digest": snapshot.supply_ref},
                ],
            })
            source_id = "src_" + self._sha256({
                "store_id": identity["store_id"],
                "source_fingerprint": source["source_fingerprint"],
            })[:40]
            now = self._now()
            connection = self.get_connection()
            connection.execute("BEGIN IMMEDIATE")
            stream = connection.execute(
                """SELECT revision FROM fifo_cost_streams
                   WHERE stream_id=? AND store_id=? AND identity_fingerprint=?""",
                (stream_id, identity["store_id"], identity_fingerprint),
            ).fetchone()
            if stream is None:
                connection.rollback()
                return self._error("FIFO_HISTORY_NOT_INITIALIZED")
            existing = connection.execute(
                """SELECT evidence_id, source_id, snapshot_sequence, normalized_evidence_json
                   FROM fifo_cost_supply_evidence
                   WHERE stream_id=? AND evidence_fingerprint=?""",
                (stream_id, snapshot.evidence_fingerprint),
            ).fetchone()
            if existing is not None:
                expected_id = "supply_ev_" + self._sha256({
                    "stream_id": stream_id,
                    "evidence_fingerprint": snapshot.evidence_fingerprint,
                })[:40]
                if (
                    existing["evidence_id"] != expected_id
                    or existing["normalized_evidence_json"] != payload_json
                ):
                    connection.rollback()
                    return self._error("FIFO_SUPPLY_EVIDENCE_FINGERPRINT_CONFLICT")
                connection.rollback()
                return {
                    "error": False,
                    "code": "FIFO_SUPPLY_EVIDENCE_RECORDED",
                    "idempotent": True,
                    "evidence_sequence": existing["snapshot_sequence"],
                    "stream_revision": stream["revision"],
                    "accepted_units": fact_total,
                    "act_count": len(normalized_acts),
                }
            snapshot_sequence = connection.execute(
                "SELECT COALESCE(MAX(snapshot_sequence), 0) + 1 "
                "FROM fifo_cost_supply_evidence WHERE stream_id=?",
                (stream_id,),
            ).fetchone()[0]
            self._ensure_source(connection, {
                "identity": identity,
                "source": source,
                "source_id": source_id,
            })
            evidence_id = "supply_ev_" + self._sha256({
                "stream_id": stream_id,
                "evidence_fingerprint": snapshot.evidence_fingerprint,
            })[:40]
            connection.execute(
                """INSERT INTO fifo_cost_supply_evidence (
                    evidence_id, stream_id, snapshot_sequence, stream_revision, source_id,
                    source_fingerprint, evidence_fingerprint, order_digest,
                    supply_digest, source_status, captured_at, source_as_of,
                    physical_effective_at, physical_effective_date,
                    normalized_evidence_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'COMPLETE', ?, NULL, NULL, NULL, ?, ?)""",
                (
                    evidence_id, stream_id, snapshot_sequence, stream["revision"], source_id,
                    snapshot.source_fingerprint, snapshot.evidence_fingerprint,
                    snapshot.order_ref, snapshot.supply_ref,
                    source["captured_at"], payload_json, self._iso(now),
                ),
            )
            connection.commit()
            return {
                "error": False,
                "code": "FIFO_SUPPLY_EVIDENCE_RECORDED",
                "idempotent": False,
                "evidence_sequence": snapshot_sequence,
                "stream_revision": stream["revision"],
                "accepted_units": fact_total,
                "act_count": len(normalized_acts),
            }
        except (AttributeError, IndexError, TypeError, ValueError, InvalidOperation, OverflowError) as exc:
            code = str(exc) if str(exc).startswith("FIFO_") else "FIFO_SUPPLY_SNAPSHOT_INVALID"
            return self._error(code)
        except (sqlite3.Error, OSError):
            if connection is not None:
                try:
                    connection.rollback()
                except sqlite3.Error:
                    pass
            return self._error("FIFO_STORAGE_UNAVAILABLE")
        finally:
            if connection is not None:
                connection.close()

    def read_supply_evidence_history(
        self, *, store_id, product_id=None, offer_id=None, sku,
    ):
        """Read redacted, date-provenance-aware supply evidence for one SKU."""
        scope = self._tenant_scope(store_id)
        if scope.get("error"):
            return scope
        connection = None
        try:
            identity = self._normalize_identity(store_id, product_id, offer_id, sku, 1)
            identity_fingerprint = self._sha256(identity)
            stream_id = "fifo_" + identity_fingerprint[:40]
            connection = self.get_connection()
            rows = connection.execute(
                """SELECT e.snapshot_sequence, e.stream_revision, e.source_status, e.captured_at,
                          e.source_as_of, e.physical_effective_at,
                          e.physical_effective_date, e.normalized_evidence_json
                   FROM fifo_cost_supply_evidence AS e
                   JOIN fifo_cost_streams AS s ON s.stream_id=e.stream_id
                   WHERE e.stream_id=? AND s.store_id=? AND s.identity_fingerprint=?
                   ORDER BY e.snapshot_sequence""",
                (stream_id, identity["store_id"], identity_fingerprint),
            ).fetchall()
            snapshots = []
            for row in rows:
                evidence = json.loads(row["normalized_evidence_json"])
                snapshots.append({
                    "evidence_sequence": row["snapshot_sequence"],
                    "stream_revision": row["stream_revision"],
                    "status": evidence["status"],
                    "source_status": row["source_status"],
                    "captured_at": row["captured_at"],
                    "source_as_of": row["source_as_of"],
                    "physical_effective_at": row["physical_effective_at"],
                    "physical_effective_date": row["physical_effective_date"],
                    "accepted_units": evidence["fact_units"],
                    "order_ref": evidence["order_ref"],
                    "supply_ref": evidence["supply_ref"],
                    "acts": evidence["act_evidence"],
                })
            return {"error": False, "code": "FIFO_SUPPLY_EVIDENCE_READY", "snapshots": snapshots}
        except (TypeError, ValueError):
            return self._error("FIFO_IDENTITY_INVALID")
        except (sqlite3.Error, OSError):
            return self._error("FIFO_STORAGE_UNAVAILABLE")
        finally:
            if connection is not None:
                connection.close()

    def preview_command(
        self, *, store_id, product_id=None, offer_id=None, sku,
        policy_version=1, events, source, expected_revision=None,
    ):
        """Create a short-lived, read-only ticket bound to tenant and SKU."""
        scope = self._tenant_scope(store_id)
        if scope.get("error"):
            return scope
        try:
            identity = self._normalize_identity(
                store_id, product_id, offer_id, sku, policy_version,
            )
            normalized_source = self._normalize_source(source)
            normalized_events = self._normalize_events(events, normalized_source)
            total_units = sum(item["quantity"] for item in normalized_events)
            if total_units > self.MAX_COMMAND_UNITS:
                return self._error("FIFO_STREAM_QUANTITY_LIMIT")
            stable_events = [
                {key: value for key, value in event.items() if key != "event_id"}
                for event in normalized_events
            ]
            source_fingerprint = normalized_source.get("source_fingerprint")
            if not source_fingerprint:
                source_fingerprint = self._sha256({
                    "source": {
                        key: value for key, value in normalized_source.items()
                        if key != "source_fingerprint"
                    },
                    "events": stable_events,
                })
            normalized_source["source_fingerprint"] = source_fingerprint
            source_id = "src_" + self._sha256({
                "store_id": identity["store_id"],
                "source_fingerprint": source_fingerprint,
            })[:40]
            identity_fingerprint = self._sha256(identity)
            stream_id = "fifo_" + identity_fingerprint[:40]

            connection = self.get_connection()
            try:
                row = connection.execute(
                    "SELECT revision, state FROM fifo_cost_streams WHERE stream_id=?",
                    (stream_id,),
                ).fetchone()
                current_revision = int(row["revision"]) if row else 0
                current_state = row["state"] if row else "FIFO_PENDING_ANCHOR"
            finally:
                connection.close()

            if any(event["kind"] == "OPENING_FIFO_ANCHOR" for event in normalized_events):
                anchor_error = self._opening_anchor_error(
                    normalized_events,
                    normalized_source,
                    current_revision=current_revision,
                    current_state=current_state,
                )
                if anchor_error:
                    return self._error(anchor_error)

            if expected_revision is not None and (
                type(expected_revision) is not int
                or expected_revision < 0
                or expected_revision != current_revision
            ):
                return self._error("FIFO_REVISION_CONFLICT")

            now = self._now()
            command_id = "cmd_" + uuid4().hex
            normalized = {
                "tenant_fingerprint": scope["tenant_fingerprint"],
                "identity": identity,
                "identity_fingerprint": identity_fingerprint,
                "stream_id": stream_id,
                "source": normalized_source,
                "source_id": source_id,
                "events": normalized_events,
                "expected_revision": current_revision,
                "next_revision": current_revision + 1,
                "current_state": current_state,
                "command_id": command_id,
            }
            payload = {
                key: value for key, value in normalized.items()
                if key not in {"command_id"}
            }
            payload["events"] = stable_events
            payload_fingerprint = self._sha256(payload)
            normalized["payload_fingerprint"] = payload_fingerprint
            if len(self._canonical_json(normalized).encode("utf-8")) > self.MAX_PAYLOAD_BYTES:
                return self._error("FIFO_COMMAND_PAYLOAD_LIMIT")

            preview_id = "preview_" + uuid4().hex
            ticket = {
                "preview_id": preview_id,
                "expires_at": (now.timestamp() + self.PREVIEW_TTL_SECONDS),
                "normalized": normalized,
            }
            preview_scope = scope["owner_fingerprint"]
            with self._PREVIEW_LOCK:
                self._purge_expired_previews(now)
                if (len(self._ACTIVE_PREVIEWS) >= self.MAX_PREVIEWS
                        and preview_scope not in self._ACTIVE_PREVIEWS):
                    return self._error("FIFO_PREVIEW_CAPACITY_EXCEEDED")
                self._ACTIVE_PREVIEWS[preview_scope] = ticket

            return {
                "error": False,
                "code": "FIFO_PREVIEW_READY",
                "preview_id": preview_id,
                "expected_revision": current_revision,
                "next_revision": current_revision + 1,
                "event_count": len(normalized_events),
                "total_units": total_units,
                "source_fingerprint": source_fingerprint,
                "payload_fingerprint": payload_fingerprint,
                "expires_in_seconds": self.PREVIEW_TTL_SECONDS,
                "state": current_state,
            }
        except (TypeError, ValueError, InvalidOperation, OverflowError) as exc:
            code = str(exc) if str(exc).startswith("FIFO_") else "FIFO_COMMAND_INVALID"
            return self._error(code)
        except (sqlite3.Error, OSError):
            return self._error("FIFO_STORAGE_UNAVAILABLE")

    def commit_command(self, *, preview_id, active_preview_id, idempotency_key):
        """Atomically append a previewed command with revision and idempotency CAS."""
        key = str(idempotency_key or "")
        if not self._IDEMPOTENCY_KEY.fullmatch(key):
            return self._error("FIFO_IDEMPOTENCY_KEY_INVALID")
        try:
            now = self._now()
        except ValueError as exc:
            return self._error(str(exc))
        connection = None
        with self._PREVIEW_LOCK:
            self._purge_expired_previews(now)
            tenant_id = str(get_current_tenant_user_id() or "").strip()
            tenant_fingerprint = self._sha256_text(tenant_id) if tenant_id else ""
            owner_id, _ = split_store_tenant_scope(tenant_id)
            owner_fingerprint = self._sha256_text(owner_id) if owner_id else ""
            ticket = self._ACTIVE_PREVIEWS.get(owner_fingerprint)
            if (ticket is None or not preview_id or preview_id != active_preview_id
                    or ticket["preview_id"] != preview_id):
                return self._error("FIFO_PREVIEW_STALE")
            normalized = ticket["normalized"]
            scope = self._tenant_scope(normalized["identity"]["store_id"])
            if (scope.get("error")
                    or scope["tenant_fingerprint"] != normalized["tenant_fingerprint"]):
                return self._error("FIFO_STORE_SCOPE_MISMATCH")

            try:
                connection = self.get_connection()
                connection.execute("BEGIN IMMEDIATE")
                previous = connection.execute(
                    """SELECT payload_fingerprint, result_reference
                       FROM fifo_cost_idempotency
                       WHERE stream_id=? AND idempotency_key=?""",
                    (normalized["stream_id"], key),
                ).fetchone()
                if previous is not None:
                    if previous["payload_fingerprint"] != normalized["payload_fingerprint"]:
                        connection.rollback()
                        return self._error("FIFO_IDEMPOTENCY_CONFLICT")
                    result = json.loads(previous["result_reference"])
                    connection.rollback()
                    return {
                        "error": False,
                        "code": "FIFO_COMMAND_COMMITTED",
                        "idempotent": True,
                        **result,
                    }

                stream = connection.execute(
                    "SELECT revision, state FROM fifo_cost_streams WHERE stream_id=?",
                    (normalized["stream_id"],),
                ).fetchone()
                if stream is None:
                    if normalized["expected_revision"] != 0:
                        connection.rollback()
                        return self._error("FIFO_REVISION_CONFLICT")
                    initial_state = "FIFO_PENDING_ANCHOR"
                    identity = normalized["identity"]
                    connection.execute(
                        """INSERT INTO fifo_cost_streams (
                            stream_id, store_id, product_id, offer_id, sku,
                            identity_fingerprint, policy_version, state, revision,
                            created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)""",
                        (
                            normalized["stream_id"], identity["store_id"],
                            identity["product_id"], identity["offer_id"],
                            identity["sku"], normalized["identity_fingerprint"],
                            identity["policy_version"], initial_state,
                            self._iso(now), self._iso(now),
                        ),
                    )
                    current_revision = 0
                    current_state = initial_state
                else:
                    current_revision = int(stream["revision"])
                    current_state = stream["state"]
                if current_revision != normalized["expected_revision"]:
                    connection.rollback()
                    return self._error("FIFO_REVISION_CONFLICT")

                has_opening_anchor = any(
                    event["kind"] == "OPENING_FIFO_ANCHOR"
                    for event in normalized["events"]
                )
                if has_opening_anchor:
                    anchor_error = self._opening_anchor_error(
                        normalized["events"],
                        normalized["source"],
                        current_revision=current_revision,
                        current_state=current_state,
                    )
                    if anchor_error:
                        connection.rollback()
                        return self._error(anchor_error)

                self._ensure_source(connection, normalized)
                self._ensure_policy_revision(connection, normalized, now)
                command_id = normalized["command_id"]
                next_revision = current_revision + 1
                connection.execute(
                    """INSERT INTO fifo_cost_commands (
                        command_id, stream_id, stream_revision, payload_fingerprint,
                        source_fingerprint, event_count, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        command_id, normalized["stream_id"], next_revision,
                        normalized["payload_fingerprint"],
                        normalized["source"]["source_fingerprint"],
                        len(normalized["events"]), self._iso(now),
                    ),
                )
                event_ids = []
                for order, event in enumerate(normalized["events"], start=1):
                    target_kind = self._validate_supersedes_target(
                        connection, normalized["stream_id"], event,
                        normalized["events"][:order - 1],
                    )
                    if event["kind"] == "SALE_CANCELLATION" and target_kind != "PHYSICAL_SALE":
                        raise ValueError("FIFO_EVENT_TARGET_INVALID")
                    if (event["kind"] == "SALEABLE_RETURN_RESTOCK"
                            and target_kind != "PHYSICAL_SALE"):
                        raise ValueError("FIFO_EVENT_TARGET_INVALID")
                    if event["kind"] == "CORRECTION" and not event.get("reason_code"):
                        raise ValueError("FIFO_EVENT_REASON_REQUIRED")
                    event_id = event["event_id"]
                    event_ids.append(event_id)
                    connection.execute(
                        """INSERT INTO fifo_cost_events (
                            event_id, stream_id, event_kind, event_schema_version,
                            effective_at, effective_date, recorded_at,
                            captured_at, source_as_of, inventory_cutoff, quantity,
                            unit_cost_rub, purchase_cost_rub, delivery_cost_rub,
                            packaging_cost_rub, currency, location_from, location_to,
                            source_id, source_fingerprint, provenance, completeness,
                            source_identity_digest, supersedes_event_id, reason_code,
                            created_at
                        ) VALUES (
                            ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'RUB',
                            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                        )""",
                        (
                            event_id, normalized["stream_id"], event["kind"],
                            event["effective_at"], event["effective_date"],
                            self._iso(now), normalized["source"]["captured_at"],
                            normalized["source"]["source_as_of"], event["inventory_cutoff"],
                            event["quantity"], event["unit_cost_rub"],
                            event["purchase_cost_rub"], event["delivery_cost_rub"],
                            event["packaging_cost_rub"], event["location_from"],
                            event["location_to"], normalized["source_id"],
                            normalized["source"]["source_fingerprint"],
                            normalized["source"]["provenance"],
                            normalized["source"]["completeness"],
                            event["source_identity_digest"],
                            event["supersedes_event_id"], event["reason_code"],
                            self._iso(now),
                        ),
                    )
                    if event["kind"] in {"OPENING_FIFO_ANCHOR", "COST_LAYER_RECEIPT"}:
                        layer_sequence = connection.execute(
                            "SELECT COALESCE(MAX(layer_sequence), 0) + 1 "
                            "FROM fifo_cost_layers WHERE stream_id=?",
                            (normalized["stream_id"],),
                        ).fetchone()[0]
                        connection.execute(
                            """INSERT INTO fifo_cost_layers (
                                layer_id, stream_id, event_id, layer_sequence,
                                quantity, unit_cost_rub, currency, effective_at,
                                effective_date, provenance, source_id, created_at
                            ) VALUES (?, ?, ?, ?, ?, ?, 'RUB', ?, ?, ?, ?, ?)""",
                            (
                                "layer_" + uuid4().hex, normalized["stream_id"],
                                event_id, layer_sequence, event["quantity"],
                                event["unit_cost_rub"], event["effective_at"],
                                event["effective_date"],
                                normalized["source"]["provenance"],
                                normalized["source_id"], self._iso(now),
                            ),
                        )
                    connection.execute(
                        """INSERT INTO fifo_cost_command_events (
                            command_id, event_id, event_order
                        ) VALUES (?, ?, ?)""",
                        (command_id, event_id, order),
                    )

                new_state = current_state
                if has_opening_anchor:
                    new_state = "FIFO_READY"
                elif current_revision == 0 and not stream:
                    new_state = "FIFO_PENDING_ANCHOR"
                connection.execute(
                    """UPDATE fifo_cost_streams
                       SET revision=?, state=?, updated_at=? WHERE stream_id=?""",
                    (next_revision, new_state, self._iso(now), normalized["stream_id"]),
                )
                if has_opening_anchor:
                    known_quantity = sum(event["quantity"] for event in normalized["events"])
                    known_cost = sum(
                        Decimal(event["unit_cost_rub"]) * event["quantity"]
                        for event in normalized["events"]
                    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                    next_unit_cost = normalized["events"][0]["unit_cost_rub"]
                    connection.execute(
                        """INSERT INTO fifo_cost_projections (
                            stream_id, revision, state, known_quantity,
                            known_cost_rub, next_unit_cost_rub, queue_complete,
                            cutoff_status, source_set_fingerprint, last_event_id,
                            updated_at
                        ) VALUES (?, ?, 'FIFO_READY', ?, ?, ?, 1, ?, ?, ?, ?)
                        ON CONFLICT(stream_id) DO UPDATE SET
                            revision=excluded.revision,
                            state=excluded.state,
                            known_quantity=excluded.known_quantity,
                            known_cost_rub=excluded.known_cost_rub,
                            next_unit_cost_rub=excluded.next_unit_cost_rub,
                            queue_complete=excluded.queue_complete,
                            cutoff_status=excluded.cutoff_status,
                            source_set_fingerprint=excluded.source_set_fingerprint,
                            last_event_id=excluded.last_event_id,
                            updated_at=excluded.updated_at""",
                        (
                            normalized["stream_id"], next_revision, known_quantity,
                            format(known_cost, ".2f"), next_unit_cost,
                            "INVENTORY_CUTOFF_UNRECONCILED",
                            normalized["source"]["source_fingerprint"],
                            event_ids[-1], self._iso(now),
                        ),
                    )
                result = {
                    "command_id": command_id,
                    "stream_id": normalized["stream_id"],
                    "event_ids": event_ids,
                    "revision": next_revision,
                }
                connection.execute(
                    """INSERT INTO fifo_cost_idempotency (
                        stream_id, idempotency_key, payload_fingerprint,
                        result_reference, created_at
                    ) VALUES (?, ?, ?, ?, ?)""",
                    (
                        normalized["stream_id"], key,
                        normalized["payload_fingerprint"],
                        self._canonical_json(result), self._iso(now),
                    ),
                )
                connection.commit()
                return {
                    "error": False,
                    "code": "FIFO_COMMAND_COMMITTED",
                    "idempotent": False,
                    **result,
                }
            except ValueError as exc:
                if connection is not None and connection.in_transaction:
                    connection.rollback()
                code = str(exc) if str(exc).startswith("FIFO_") else "FIFO_COMMAND_INVALID"
                return self._error(code)
            except sqlite3.IntegrityError as exc:
                if connection is not None and connection.in_transaction:
                    connection.rollback()
                detail = str(exc).lower()
                code = (
                    "FIFO_EVENT_IDENTITY_CONFLICT"
                    if "fifo_cost_physical_sale_identity" in detail
                    else "FIFO_REVISION_CONFLICT"
                )
                return self._error(code)
            except (sqlite3.Error, OSError):
                if connection is not None and connection.in_transaction:
                    connection.rollback()
                return self._error("FIFO_STORAGE_UNAVAILABLE")
            finally:
                if connection is not None:
                    connection.close()

    def preview_cost_rate_change(
        self, *, store_id, product_id=None, offer_id=None, sku,
        effective_date, purchase_cost_rub, delivery_cost_rub,
        packaging_cost_rub, owner_old_home_units, expected_revision,
        zero_stock_evidence=None, stock_snapshot=None,
        owner_confirms_reconciliation_scope=False,
    ):
        """Preview an owner-reported open rate without adding inventory units."""
        scope = self._tenant_scope(store_id)
        if scope.get("error"):
            return scope
        connection = None
        try:
            identity = self._normalize_identity(
                store_id, product_id, offer_id, sku, 1,
            )
            if (
                not isinstance(effective_date, str)
                or len(effective_date) != 10
                or self._normalize_date(effective_date) != effective_date
            ):
                return self._error("FIFO_RATE_EFFECTIVE_DATE_INVALID")
            components = {
                "purchase_cost_rub": self._normalize_money(purchase_cost_rub),
                "delivery_cost_rub": self._normalize_money(delivery_cost_rub),
                "packaging_cost_rub": self._normalize_money(packaging_cost_rub),
            }
            if any(value is None for value in components.values()):
                return self._error("FIFO_RATE_COMPONENTS_REQUIRED")
            unit_cost = sum(
                (Decimal(value) for value in components.values()), Decimal("0.00"),
            ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            if unit_cost > Decimal("1000000000"):
                return self._error("FIFO_MONEY_INPUT_INVALID")
            if type(owner_old_home_units) is not int or not 0 <= owner_old_home_units <= self.MAX_COMMAND_UNITS:
                return self._error("FIFO_RATE_OLD_HOME_QUANTITY_INVALID")
            if type(expected_revision) is not int or expected_revision < 0:
                return self._error("FIFO_REVISION_CONFLICT")
            normalized_zero_stock = None
            if zero_stock_evidence is not None:
                normalized_zero_stock = self._normalize_zero_stock_evidence(
                    zero_stock_evidence, identity,
                )
                if isinstance(normalized_zero_stock, str):
                    return self._error(normalized_zero_stock)
                if owner_old_home_units != 0:
                    return self._error("FIFO_ZERO_ANCHOR_HOME_MUST_BE_ZERO")

            now = self._now()
            identity_fingerprint = self._sha256(identity)
            stream_id = "fifo_" + identity_fingerprint[:40]
            connection = self.get_connection()
            stream = connection.execute(
                "SELECT state, revision FROM fifo_cost_streams WHERE stream_id=?",
                (stream_id,),
            ).fetchone()
            projection = connection.execute(
                """SELECT revision, state, known_quantity, known_cost_rub,
                          next_unit_cost_rub, queue_complete, cutoff_status,
                          source_set_fingerprint
                   FROM fifo_cost_projections WHERE stream_id=?""",
                (stream_id,),
            ).fetchone()
            if stream is None:
                if normalized_zero_stock is None or expected_revision != 0:
                    return self._error("FIFO_ANCHOR_REQUIRED")
                stream_snapshot = {
                    "state": "FIFO_PENDING_ANCHOR",
                    "revision": 0,
                    "known_quantity": 0,
                    "known_cost_rub": "0.00",
                    "next_unit_cost_rub": None,
                    "queue_complete": False,
                    "cutoff_status": "INVENTORY_CUTOFF_UNRECONCILED",
                    "source_set_fingerprint": None,
                    "rate_sequence": 1,
                    "prior_rate_unit_cost_rub": None,
                    "zero_stock_anchor": True,
                }
            else:
                if normalized_zero_stock is not None:
                    return self._error("FIFO_ZERO_ANCHOR_STREAM_ALREADY_EXISTS")
                if projection is None:
                    return self._error("FIFO_PROJECTION_MISSING")
                if stream["state"] not in {"FIFO_READY", "FIFO_PARTIAL"}:
                    return self._error("FIFO_STREAM_NOT_READY")
                if type(stream["revision"]) is not int or stream["revision"] != expected_revision:
                    return self._error("FIFO_REVISION_CONFLICT")
                if projection["revision"] != stream["revision"]:
                    return self._error("FIFO_PROJECTION_STALE")
                stream_snapshot = {
                    "state": stream["state"],
                    "revision": stream["revision"],
                    "known_quantity": projection["known_quantity"],
                    "known_cost_rub": projection["known_cost_rub"],
                    "next_unit_cost_rub": projection["next_unit_cost_rub"],
                    "queue_complete": bool(projection["queue_complete"]),
                    "cutoff_status": projection["cutoff_status"],
                    "source_set_fingerprint": projection["source_set_fingerprint"],
                    "zero_stock_anchor": False,
                }
            previous = connection.execute(
                """SELECT rate_sequence, effective_date, unit_cost_rub
                   FROM fifo_cost_rate_changes WHERE stream_id=?
                   ORDER BY rate_sequence DESC LIMIT 1""",
                (stream_id,),
            ).fetchone()
            if previous is not None and effective_date < previous["effective_date"]:
                return self._error("FIFO_RATE_DATE_ORDER_UNRESOLVED")
            reconciliation = None
            if previous is not None:
                if stock_snapshot is None:
                    return self._error("FIFO_RATE_RECONCILIATION_REQUIRED")
                if owner_confirms_reconciliation_scope is not True:
                    return self._error("FIFO_RATE_RECONCILIATION_SCOPE_UNCONFIRMED")
                stock = self._normalize_rate_reconciliation_snapshot(
                    stock_snapshot, identity, effective_date,
                )
                if isinstance(stock, str):
                    return self._error(stock)
                # Until accepted sale/movement replay is available, a current
                # count cannot be used to shrink older layers or explain away
                # inventory disappearance.
                movement_count = connection.execute(
                    """SELECT COUNT(*) FROM fifo_cost_events
                       WHERE stream_id=? AND event_kind NOT IN (
                           'OPENING_FIFO_ANCHOR', 'COST_LAYER_RECEIPT'
                       )""",
                    (stream_id,),
                ).fetchone()[0]
                if movement_count:
                    return self._error("FIFO_RATE_REPLAY_REQUIRED")
                previous_rate_sequence = previous["rate_sequence"]
                prior_reconciliation_count = connection.execute(
                    """SELECT COUNT(*) FROM fifo_cost_rate_reconciliations
                       WHERE stream_id=? AND reconciled_rate_sequence < ?""",
                    (stream_id, previous_rate_sequence),
                ).fetchone()[0]
                if prior_reconciliation_count != previous_rate_sequence - 1:
                    return self._error("FIFO_RATE_HISTORY_GAP")
                already_reconciled = connection.execute(
                    """SELECT 1 FROM fifo_cost_rate_reconciliations
                       WHERE stream_id=? AND reconciled_rate_sequence=?""",
                    (stream_id, previous_rate_sequence),
                ).fetchone()
                if already_reconciled is not None:
                    return self._error("FIFO_RATE_RECONCILIATION_ALREADY_EXISTS")
                older_units = projection["known_quantity"]
                if type(older_units) is not int or older_units < 0:
                    return self._error("FIFO_PROJECTION_STALE")
                total_units = (
                    stock["fbo_units"] + stock["transit_units"]
                    + owner_old_home_units
                )
                if total_units > self.MAX_COMMAND_UNITS:
                    return self._error("FIFO_STREAM_QUANTITY_LIMIT")
                last_total = connection.execute(
                    """SELECT reconciled_total_units
                       FROM fifo_cost_rate_reconciliations WHERE stream_id=?
                       ORDER BY transition_rate_sequence DESC LIMIT 1""",
                    (stream_id,),
                ).fetchone()
                if last_total is not None and total_units < last_total["reconciled_total_units"]:
                    return self._error("FIFO_RATE_STOCK_DISCREPANCY")
                if total_units < older_units:
                    return self._error("FIFO_RATE_RECONCILIATION_CONFLICT")
                previous_rate_units = total_units - older_units
                if owner_old_home_units > previous_rate_units:
                    return self._error("FIFO_RATE_RECONCILIATION_CONFLICT")
                reconciliation = {
                    "transition_rate_sequence": previous_rate_sequence + 1,
                    "reconciled_rate_sequence": previous_rate_sequence,
                    "effective_date": effective_date,
                    "reconciled_total_units": total_units,
                    "older_finite_units": older_units,
                    "prior_rate_units": previous_rate_units,
                    "fbo_units": stock["fbo_units"],
                    "reserved_units": stock["reserved_units"],
                    "transit_units": stock["transit_units"],
                    "home_units": owner_old_home_units,
                    "source_fingerprint": stock["source_fingerprint"],
                    "captured_at": stock["captured_at"],
                    "prior_rate_unit_cost_rub": previous["unit_cost_rub"],
                    "older_finite_cost_rub": projection["known_cost_rub"],
                    "prior_total_units": (
                        last_total["reconciled_total_units"] if last_total else None
                    ),
                }
            latest_layer = connection.execute(
                """SELECT MAX(effective_date) FROM fifo_cost_layers
                   WHERE stream_id=?""",
                (stream_id,),
            ).fetchone()[0]
            latest_effective_date = max(
                date_value for date_value in (
                    previous["effective_date"] if previous is not None else None,
                    latest_layer,
                ) if date_value is not None
            ) if previous is not None or latest_layer is not None else None
            if latest_effective_date is not None and effective_date < latest_effective_date:
                return self._error("FIFO_RATE_DATE_ORDER_UNRESOLVED")
            if previous is None and normalized_zero_stock is None:
                prior_layer = connection.execute(
                    """SELECT unit_cost_rub FROM fifo_cost_layers WHERE stream_id=?
                       ORDER BY layer_sequence DESC LIMIT 1""",
                    (stream_id,),
                ).fetchone()
                stream_snapshot["prior_rate_unit_cost_rub"] = (
                    prior_layer["unit_cost_rub"] if prior_layer else projection["next_unit_cost_rub"]
                )

            normalized_identity = {
                "store_id": identity["store_id"],
                "product_id": identity["product_id"],
                "offer_id": identity["offer_id"],
                "sku": identity["sku"],
                "policy_version": identity["policy_version"],
            }
            payload = {
                "identity_fingerprint": identity_fingerprint,
                "effective_date": effective_date,
                **components,
                "unit_cost_rub": format(unit_cost, ".2f"),
                "owner_old_home_units": owner_old_home_units,
                "expected_revision": expected_revision,
                "prior_rate_sequence": previous["rate_sequence"] if previous else 0,
                "zero_stock_fingerprint": (
                    normalized_zero_stock["source_fingerprint"]
                    if normalized_zero_stock else None
                ),
                "rate_reconciliation": reconciliation,
            }
            payload_fingerprint = self._sha256(payload)
            source_fingerprint = self._sha256({
                "source_method": "OWNER_CONFIRMED_NEW_COST_RATE",
                "payload_fingerprint": payload_fingerprint,
                "captured_at": self._iso(now),
            })
            source_references = []
            if normalized_zero_stock is not None:
                source_references.append({
                    "kind": "OTHER",
                    "digest": normalized_zero_stock["source_fingerprint"],
                })
            if reconciliation is not None:
                source_references.append({
                    "kind": "OTHER",
                    "digest": reconciliation["source_fingerprint"],
                })
            source = self._normalize_source({
                "kind": "OWNER_CONFIRMATION",
                "method": "OWNER_CONFIRMED_NEW_COST_RATE",
                "status": "OWNER_CONFIRMED",
                "completeness": "OWNER_CONFIRMED",
                "provenance": "OWNER_CONFIRMED",
                "coverage_status": "OWNER_CONFIRMED",
                "fingerprint": source_fingerprint,
                "captured_at": self._iso(now),
                "references": source_references,
            })
            source_id = "src_" + self._sha256({
                "store_id": identity["store_id"],
                "source_fingerprint": source_fingerprint,
            })[:40]
            stream_snapshot["rate_sequence"] = (
                previous["rate_sequence"] + 1 if previous else 1
            )
            if previous is not None:
                stream_snapshot["prior_rate_unit_cost_rub"] = previous["unit_cost_rub"]
            normalized = {
                "tenant_fingerprint": scope["tenant_fingerprint"],
                "owner_fingerprint": scope["owner_fingerprint"],
                "identity": normalized_identity,
                "stream_id": stream_id,
                "identity_fingerprint": identity_fingerprint,
                "payload": payload,
                "payload_fingerprint": payload_fingerprint,
                "source": source,
                "source_id": source_id,
                "zero_stock_source": normalized_zero_stock,
                "stream_snapshot": stream_snapshot,
            }
            preview_id = "rate_preview_" + uuid4().hex
            ticket = {
                "preview_id": preview_id,
                "expires_at": now.timestamp() + self.PREVIEW_TTL_SECONDS,
                "normalized": normalized,
            }
            with self._PREVIEW_LOCK:
                self._purge_expired_rate_previews(now)
                if (
                    len(self._ACTIVE_RATE_PREVIEWS) >= self.MAX_PREVIEWS
                    and scope["owner_fingerprint"] not in self._ACTIVE_RATE_PREVIEWS
                ):
                    return self._error("FIFO_PREVIEW_CAPACITY_EXCEEDED")
                self._ACTIVE_RATE_PREVIEWS[scope["owner_fingerprint"]] = ticket
            return {
                "error": False,
                "code": "FIFO_RATE_PREVIEW_READY",
                "preview_id": preview_id,
                "expected_revision": stream_snapshot["revision"],
                "next_revision": stream_snapshot["revision"] + 1,
                "rate_sequence": stream_snapshot["rate_sequence"],
                "effective_date": effective_date,
                "unit_cost_rub": format(unit_cost, ".2f"),
                **components,
                "owner_old_home_units": owner_old_home_units,
                "finite_units_at_anchor": stream_snapshot["known_quantity"],
                "prior_rate_unit_cost_rub": stream_snapshot["prior_rate_unit_cost_rub"],
                "threshold_status": stream_snapshot["cutoff_status"],
                "inventory_units_added": 0,
                "new_batch_quantity": None,
                "zero_old_inventory_anchor": stream_snapshot["zero_stock_anchor"],
                "rate_reconciliation": ({
                    "reconciled_rate_sequence": reconciliation["reconciled_rate_sequence"],
                    "reconciled_total_units": reconciliation["reconciled_total_units"],
                    "older_finite_units": reconciliation["older_finite_units"],
                    "prior_rate_units": reconciliation["prior_rate_units"],
                    "prior_rate_unit_cost_rub": reconciliation["prior_rate_unit_cost_rub"],
                    "fbo_units": reconciliation["fbo_units"],
                    "reserved_units": reconciliation["reserved_units"],
                    "transit_units": reconciliation["transit_units"],
                    "home_units": reconciliation["home_units"],
                } if reconciliation else None),
                "expires_in_seconds": self.PREVIEW_TTL_SECONDS,
            }
        except (TypeError, ValueError, InvalidOperation, OverflowError) as exc:
            code = str(exc) if str(exc).startswith("FIFO_") else "FIFO_RATE_INPUT_INVALID"
            return self._error(code)
        except (sqlite3.Error, OSError):
            return self._error("FIFO_STORAGE_UNAVAILABLE")
        finally:
            if connection is not None:
                connection.close()

    def commit_cost_rate_change(self, *, preview_id, active_preview_id, idempotency_key):
        """Append a cost-rate record atomically, without creating inventory."""
        key = str(idempotency_key or "")
        if not self._IDEMPOTENCY_KEY.fullmatch(key):
            return self._error("FIFO_IDEMPOTENCY_KEY_INVALID")
        try:
            now = self._now()
        except ValueError as exc:
            return self._error(str(exc))
        connection = None
        with self._PREVIEW_LOCK:
            self._purge_expired_rate_previews(now)
            tenant_id = str(get_current_tenant_user_id() or "").strip()
            owner_id, _ = split_store_tenant_scope(tenant_id)
            owner_fingerprint = self._sha256_text(owner_id) if owner_id else ""
            ticket = self._ACTIVE_RATE_PREVIEWS.get(owner_fingerprint)
            if (
                ticket is None or not preview_id or preview_id != active_preview_id
                or ticket["preview_id"] != preview_id
            ):
                return self._error("FIFO_PREVIEW_STALE")
            normalized = ticket["normalized"]
            scope = self._tenant_scope(normalized["identity"]["store_id"])
            if (
                scope.get("error")
                or scope["tenant_fingerprint"] != normalized["tenant_fingerprint"]
            ):
                return self._error("FIFO_STORE_SCOPE_MISMATCH")
            try:
                connection = self.get_connection()
                connection.execute("BEGIN IMMEDIATE")
                previous = connection.execute(
                    """SELECT payload_fingerprint, stream_revision, rate_sequence,
                              unit_cost_rub, owner_old_home_units
                       FROM fifo_cost_rate_changes
                       WHERE stream_id=? AND idempotency_key=?""",
                    (normalized["stream_id"], key),
                ).fetchone()
                if previous is not None:
                    if previous["payload_fingerprint"] != normalized["payload_fingerprint"]:
                        connection.rollback()
                        return self._error("FIFO_IDEMPOTENCY_CONFLICT")
                    result = {
                        "revision": previous["stream_revision"],
                        "rate_sequence": previous["rate_sequence"],
                        "unit_cost_rub": previous["unit_cost_rub"],
                        "owner_old_home_units": previous["owner_old_home_units"],
                    }
                    connection.rollback()
                    return {
                        "error": False, "code": "FIFO_RATE_COMMITTED",
                        "idempotent": True, **result,
                    }

                stream = connection.execute(
                    "SELECT state, revision FROM fifo_cost_streams WHERE stream_id=?",
                    (normalized["stream_id"],),
                ).fetchone()
                projection = connection.execute(
                    "SELECT revision, state, known_quantity, known_cost_rub, "
                    "next_unit_cost_rub, source_set_fingerprint "
                    "FROM fifo_cost_projections WHERE stream_id=?",
                    (normalized["stream_id"],),
                ).fetchone()
                expected_revision = normalized["stream_snapshot"]["revision"]
                zero_anchor = normalized["stream_snapshot"]["zero_stock_anchor"]
                if zero_anchor:
                    if stream is not None or projection is not None or expected_revision != 0:
                        connection.rollback()
                        return self._error("FIFO_REVISION_CONFLICT")
                    identity = normalized["identity"]
                    connection.execute(
                        """INSERT INTO fifo_cost_streams (
                            stream_id, store_id, product_id, offer_id, sku,
                            identity_fingerprint, policy_version, state, revision,
                            created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, 'FIFO_PENDING_ANCHOR', 0, ?, ?)""",
                        (
                            normalized["stream_id"], identity["store_id"],
                            identity["product_id"], identity["offer_id"],
                            identity["sku"], normalized["identity_fingerprint"],
                            identity["policy_version"], self._iso(now), self._iso(now),
                        ),
                    )
                    self._ensure_policy_revision(connection, {
                        "identity": identity,
                        "stream_id": normalized["stream_id"],
                    }, now)
                else:
                    if stream is None or projection is None:
                        connection.rollback()
                        return self._error("FIFO_ANCHOR_REQUIRED")
                    if stream["revision"] != expected_revision:
                        connection.rollback()
                        return self._error("FIFO_REVISION_CONFLICT")
                    if projection["revision"] != expected_revision:
                        connection.rollback()
                        return self._error("FIFO_PROJECTION_STALE")
                latest = connection.execute(
                    "SELECT COALESCE(MAX(rate_sequence), 0) FROM fifo_cost_rate_changes "
                    "WHERE stream_id=?", (normalized["stream_id"],),
                ).fetchone()[0]
                if latest != normalized["stream_snapshot"]["rate_sequence"] - 1:
                    connection.rollback()
                    return self._error("FIFO_RATE_REVISION_CONFLICT")

                if zero_anchor:
                    self._ensure_source(connection, {
                        "identity": normalized["identity"],
                        "source": normalized["zero_stock_source"]["source"],
                        "source_id": normalized["zero_stock_source"]["source_id"],
                    })
                self._ensure_source(connection, {
                    "identity": normalized["identity"],
                    "source": normalized["source"],
                    "source_id": normalized["source_id"],
                })
                payload = normalized["payload"]
                next_revision = expected_revision + 1
                rate_change_id = "rate_" + uuid4().hex
                connection.execute(
                    """INSERT INTO fifo_cost_rate_changes (
                        rate_change_id, stream_id, stream_revision, rate_sequence,
                        effective_date, unit_cost_rub, purchase_cost_rub,
                        delivery_cost_rub, packaging_cost_rub,
                        owner_old_home_units, source_id, source_fingerprint,
                        payload_fingerprint, idempotency_key, recorded_at,
                        captured_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        rate_change_id, normalized["stream_id"], next_revision,
                        normalized["stream_snapshot"]["rate_sequence"],
                        payload["effective_date"], payload["unit_cost_rub"],
                        payload["purchase_cost_rub"], payload["delivery_cost_rub"],
                        payload["packaging_cost_rub"], payload["owner_old_home_units"],
                        normalized["source_id"], normalized["source"]["source_fingerprint"],
                        normalized["payload_fingerprint"], key,
                        self._iso(now), normalized["source"]["captured_at"],
                    ),
                )
                reconciliation = normalized["payload"]["rate_reconciliation"]
                if reconciliation is not None:
                    reconciliation_id = "rate_recon_" + self._sha256({
                        "stream_id": normalized["stream_id"],
                        "transition_rate_sequence": reconciliation[
                            "transition_rate_sequence"
                        ],
                        "source_fingerprint": reconciliation["source_fingerprint"],
                    })[:40]
                    connection.execute(
                        """INSERT INTO fifo_cost_rate_reconciliations (
                            reconciliation_id, stream_id, stream_revision,
                            transition_rate_sequence, reconciled_rate_sequence,
                            effective_date, reconciled_total_units,
                            older_finite_units, prior_rate_units, fbo_units,
                            reserved_units, transit_units, home_units,
                            source_fingerprint, captured_at, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            reconciliation_id, normalized["stream_id"], next_revision,
                            reconciliation["transition_rate_sequence"],
                            reconciliation["reconciled_rate_sequence"],
                            reconciliation["effective_date"],
                            reconciliation["reconciled_total_units"],
                            reconciliation["older_finite_units"],
                            reconciliation["prior_rate_units"],
                            reconciliation["fbo_units"],
                            reconciliation["reserved_units"],
                            reconciliation["transit_units"],
                            reconciliation["home_units"],
                            reconciliation["source_fingerprint"],
                            reconciliation["captured_at"], self._iso(now),
                        ),
                    )
                connection.execute(
                    "UPDATE fifo_cost_streams SET state='FIFO_PARTIAL', revision=?, updated_at=? "
                    "WHERE stream_id=?",
                    (next_revision, self._iso(now), normalized["stream_id"]),
                )
                if zero_anchor:
                    combined_source_set = self._sha256({
                        "zero_stock": normalized["zero_stock_source"]["source_fingerprint"],
                        "rate": normalized["source"]["source_fingerprint"],
                    })
                    connection.execute(
                        """INSERT INTO fifo_cost_projections (
                            stream_id, revision, state, known_quantity, known_cost_rub,
                            next_unit_cost_rub, queue_complete, cutoff_status,
                            source_set_fingerprint, last_event_id, updated_at
                        ) VALUES (?, ?, 'FIFO_PARTIAL', 0, '0.00', ?, 0, ?, ?, NULL, ?)""",
                        (
                            normalized["stream_id"], next_revision,
                            payload["unit_cost_rub"],
                            "INVENTORY_CUTOFF_UNRECONCILED", combined_source_set,
                            self._iso(now),
                        ),
                    )
                else:
                    combined_source_set = self._sha256({
                        "previous": projection["source_set_fingerprint"],
                        "rate": normalized["source"]["source_fingerprint"],
                    })
                    if reconciliation is None:
                        connection.execute(
                            """UPDATE fifo_cost_projections
                               SET revision=?, state='FIFO_PARTIAL', queue_complete=0,
                                   source_set_fingerprint=?, updated_at=?
                               WHERE stream_id=?""",
                            (
                                next_revision, combined_source_set, self._iso(now),
                                normalized["stream_id"],
                            ),
                        )
                    else:
                        prior_rate_cost = Decimal(
                            reconciliation["prior_rate_unit_cost_rub"]
                        )
                        added_cost = (
                            prior_rate_cost * reconciliation["prior_rate_units"]
                        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                        reconciled_cost = (
                            Decimal(reconciliation["older_finite_cost_rub"])
                            + added_cost
                        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                        old_next_cost = projection["next_unit_cost_rub"]
                        if projection["known_quantity"] > 0:
                            next_unit_cost = old_next_cost
                        elif reconciliation["prior_rate_units"] > 0:
                            next_unit_cost = reconciliation["prior_rate_unit_cost_rub"]
                        else:
                            next_unit_cost = payload["unit_cost_rub"]
                        connection.execute(
                            """UPDATE fifo_cost_projections
                               SET revision=?, state='FIFO_PARTIAL',
                                   known_quantity=?, known_cost_rub=?,
                                   next_unit_cost_rub=?, queue_complete=0,
                                   source_set_fingerprint=?, updated_at=?
                               WHERE stream_id=?""",
                            (
                                next_revision,
                                reconciliation["reconciled_total_units"],
                                format(reconciled_cost, ".2f"), next_unit_cost,
                                combined_source_set, self._iso(now),
                                normalized["stream_id"],
                            ),
                        )
                result = {
                    "revision": next_revision,
                    "rate_sequence": normalized["stream_snapshot"]["rate_sequence"],
                    "unit_cost_rub": payload["unit_cost_rub"],
                    "owner_old_home_units": payload["owner_old_home_units"],
                    **({"reconciled_previous_rate_units": reconciliation["prior_rate_units"]}
                       if reconciliation else {}),
                }
                connection.commit()
                return {
                    "error": False, "code": "FIFO_RATE_COMMITTED",
                    "idempotent": False, **result,
                }
            except ValueError as exc:
                if connection is not None and connection.in_transaction:
                    connection.rollback()
                code = str(exc) if str(exc).startswith("FIFO_") else "FIFO_RATE_INPUT_INVALID"
                return self._error(code)
            except sqlite3.IntegrityError:
                if connection is not None and connection.in_transaction:
                    connection.rollback()
                return self._error("FIFO_RATE_REVISION_CONFLICT")
            except (sqlite3.Error, OSError):
                if connection is not None and connection.in_transaction:
                    connection.rollback()
                return self._error("FIFO_STORAGE_UNAVAILABLE")
            finally:
                if connection is not None:
                    connection.close()

    def _purge_expired_rate_previews(self, now):
        cutoff = now.timestamp()
        expired = [
            owner for owner, ticket in self._ACTIVE_RATE_PREVIEWS.items()
            if ticket["expires_at"] <= cutoff
        ]
        for owner in expired:
            self._ACTIVE_RATE_PREVIEWS.pop(owner, None)

    def _tenant_scope(self, store_id):
        tenant_id = str(get_current_tenant_user_id() or "").strip()
        if not tenant_id:
            return self._error("FIFO_OWNER_SCOPE_REQUIRED")
        owner_id, scoped_store = split_store_tenant_scope(tenant_id)
        try:
            normalized_store = self._safe_identity_part(store_id, "store_id", 128)
        except ValueError:
            return self._error("FIFO_IDENTITY_INVALID")
        if not owner_id or not scoped_store:
            return self._error("FIFO_STORE_SCOPE_REQUIRED")
        if scoped_store != normalized_store:
            return self._error("FIFO_STORE_SCOPE_MISMATCH")
        return {
            "error": False,
            "owner_fingerprint": self._sha256_text(owner_id),
            "tenant_fingerprint": self._sha256_text(tenant_id),
        }

    @classmethod
    def _normalize_identity(cls, store_id, product_id, offer_id, sku, policy_version):
        store = cls._safe_identity_part(store_id, "store_id", 128)
        product = cls._optional_identity_part(product_id, "product_id", 128)
        offer = cls._optional_identity_part(offer_id, "offer_id", 128)
        normalized_sku = cls._safe_identity_part(sku, "sku", 64)
        if not product and not offer:
            raise ValueError("FIFO_PRODUCT_IDENTITY_REQUIRED")
        if type(policy_version) is not int or not 1 <= policy_version <= 1000:
            raise ValueError("FIFO_POLICY_VERSION_INVALID")
        return {
            "store_id": store,
            "product_id": product,
            "offer_id": offer,
            "sku": normalized_sku,
            "policy_version": policy_version,
        }

    @staticmethod
    def _safe_identity_part(value, name, max_length):
        if value is None or isinstance(value, bool):
            raise ValueError("FIFO_IDENTITY_INVALID")
        text = str(value).strip()
        if not text or len(text) > max_length or any(ord(char) < 32 for char in text):
            raise ValueError("FIFO_IDENTITY_INVALID")
        return text

    @classmethod
    def _optional_identity_part(cls, value, name, max_length):
        if value is None or str(value).strip() == "":
            return None
        return cls._safe_identity_part(value, name, max_length)

    @classmethod
    def _normalize_rate_reconciliation_snapshot(
        cls, snapshot, identity, effective_date,
    ):
        """Accept only a complete exact-SKU snapshot on the chosen date."""
        fields = (
            "status", "source_status", "store_id", "product_id", "offer_id",
            "sku", "captured_at", "pagination_complete", "fbo_units",
            "reserved_units", "transit_units", "transit_status",
            "source_fingerprint",
        )
        try:
            evidence = {field: getattr(snapshot, field) for field in fields}
        except (AttributeError, TypeError):
            return "FIFO_RATE_RECONCILIATION_SOURCE_INVALID"
        if (
            evidence["status"] != "COMPLETE"
            or evidence["source_status"] != "COMPLETE"
            or evidence["pagination_complete"] is not True
            or evidence["transit_status"] != "DISJOINT_CONFIRMED"
            or not cls._valid_digest(evidence["source_fingerprint"])
        ):
            return "FIFO_RATE_RECONCILIATION_SOURCE_INCOMPLETE"
        quantities = (
            evidence["fbo_units"], evidence["reserved_units"],
            evidence["transit_units"],
        )
        if any(
            type(value) is not int or value < 0 or value > cls.MAX_COMMAND_UNITS
            for value in quantities
        ):
            return "FIFO_RATE_RECONCILIATION_SOURCE_INVALID"
        if evidence["reserved_units"] > evidence["fbo_units"]:
            return "FIFO_RATE_RECONCILIATION_SOURCE_CONFLICT"
        try:
            store_id = cls._safe_identity_part(evidence["store_id"], "store_id", 128)
            product_id = cls._optional_identity_part(evidence["product_id"], "product_id", 128)
            offer_id = cls._optional_identity_part(evidence["offer_id"], "offer_id", 128)
            sku = cls._safe_identity_part(evidence["sku"], "sku", 64)
            captured_at = cls._normalize_timestamp(evidence["captured_at"])
        except (TypeError, ValueError):
            return "FIFO_RATE_RECONCILIATION_SOURCE_INVALID"
        if (
            store_id != identity["store_id"]
            or product_id != identity["product_id"]
            or offer_id != identity["offer_id"]
            or sku != identity["sku"]
        ):
            return "FIFO_RATE_RECONCILIATION_SCOPE_MISMATCH"
        if captured_at is None or captured_at[:10] != effective_date:
            return "FIFO_RATE_RECONCILIATION_DATE_MISMATCH"
        total = evidence["fbo_units"] + evidence["transit_units"]
        if total > cls.MAX_COMMAND_UNITS:
            return "FIFO_STREAM_QUANTITY_LIMIT"
        return {
            "fbo_units": evidence["fbo_units"],
            "reserved_units": evidence["reserved_units"],
            "transit_units": evidence["transit_units"],
            "captured_at": captured_at,
            "source_fingerprint": evidence["source_fingerprint"],
        }

    @classmethod
    def _normalize_zero_stock_evidence(cls, evidence, identity):
        required = {
            "status", "source_status", "store_id", "product_id", "offer_id",
            "sku", "captured_at", "pagination_complete", "fbo_units",
            "reserved_units", "transit_units", "transit_status",
            "source_fingerprint",
        }
        if not isinstance(evidence, dict) or set(evidence) != required:
            return "FIFO_ZERO_ANCHOR_SOURCE_INVALID"
        if (
            evidence["status"] != "CONFIRMED_ZERO"
            or evidence["source_status"] != "COMPLETE"
            or evidence["pagination_complete"] is not True
            or type(evidence["fbo_units"]) is not int or evidence["fbo_units"] != 0
            or type(evidence["reserved_units"]) is not int or evidence["reserved_units"] != 0
            or type(evidence["transit_units"]) is not int or evidence["transit_units"] != 0
            or evidence["transit_status"] != "DISJOINT_CONFIRMED"
            or not cls._valid_digest(evidence["source_fingerprint"])
        ):
            return "FIFO_ZERO_ANCHOR_SOURCE_UNCONFIRMED"
        try:
            store_id = cls._safe_identity_part(evidence["store_id"], "store_id", 128)
            product_id = cls._safe_identity_part(evidence["product_id"], "product_id", 128)
            offer_id = cls._optional_identity_part(evidence["offer_id"], "offer_id", 128)
            sku = cls._safe_identity_part(evidence["sku"], "sku", 64)
            captured_at = cls._normalize_timestamp(evidence["captured_at"])
        except (TypeError, ValueError):
            return "FIFO_ZERO_ANCHOR_SOURCE_INVALID"
        if (
            store_id != identity["store_id"]
            or product_id != identity["product_id"]
            or offer_id != identity["offer_id"]
            or sku != identity["sku"]
            or captured_at is None
        ):
            return "FIFO_ZERO_ANCHOR_SCOPE_MISMATCH"
        source = cls._normalize_source({
            "kind": "OZON_API",
            "method": "FIFO_PRODUCT_STOCKS",
            "status": "COMPLETE",
            "completeness": "COMPLETE",
            "provenance": "OZON_CONFIRMED_FIELD",
            "coverage_status": "COMPLETE",
            "fingerprint": evidence["source_fingerprint"],
            "captured_at": captured_at,
            "record_count": 1,
            "page_count": 1,
            "references": [],
        })
        source_id = "src_" + cls._sha256({
            "store_id": store_id,
            "source_fingerprint": source["source_fingerprint"],
        })[:40]
        return {
            "source": source,
            "source_id": source_id,
            "source_fingerprint": source["source_fingerprint"],
        }

    @classmethod
    def _normalize_source(cls, source):
        if not isinstance(source, dict):
            raise ValueError("FIFO_SOURCE_INVALID")
        allowed = {
            "kind", "method", "status", "completeness", "provenance",
            "coverage_status", "fingerprint", "captured_at", "source_as_of",
            "record_count", "page_count", "inventory_cutoff", "references",
        }
        if set(source) - allowed:
            raise ValueError("FIFO_SOURCE_FIELD_NOT_ALLOWED")
        kind = cls._enum_text(source.get("kind"), "FIFO_SOURCE_KIND_INVALID", 48)
        method = cls._enum_text(source.get("method"), "FIFO_SOURCE_METHOD_INVALID", 80)
        status = source.get("status")
        completeness = source.get("completeness", status)
        provenance = source.get("provenance")
        if status not in cls._SOURCE_STATUSES or completeness not in cls._SOURCE_STATUSES:
            raise ValueError("FIFO_SOURCE_STATUS_INVALID")
        if provenance not in cls._PROVENANCE:
            raise ValueError("FIFO_SOURCE_PROVENANCE_INVALID")
        if status == "MODEL_ONLY" or completeness == "MODEL_ONLY" or provenance == "MODEL_ASSUMPTION":
            raise ValueError("FIFO_MODEL_SOURCE_NOT_PERSISTABLE")
        coverage = source.get("coverage_status", "UNKNOWN")
        if coverage not in {"COMPLETE", "PARTIAL", "UNKNOWN", "OWNER_CONFIRMED", "NOT_APPLICABLE"}:
            raise ValueError("FIFO_SOURCE_COVERAGE_INVALID")
        fingerprint = source.get("fingerprint")
        if fingerprint is not None and not cls._valid_digest(fingerprint):
            raise ValueError("FIFO_SOURCE_FINGERPRINT_INVALID")
        refs = source.get("references", [])
        if not isinstance(refs, list) or len(refs) > cls.MAX_REFERENCES_PER_SOURCE:
            raise ValueError("FIFO_SOURCE_REFERENCE_LIMIT")
        normalized_refs = []
        for ref in refs:
            if not isinstance(ref, dict) or set(ref) != {"kind", "digest"}:
                raise ValueError("FIFO_SOURCE_REFERENCE_INVALID")
            ref_kind = ref["kind"]
            if ref_kind not in cls._REFERENCE_KINDS or not cls._valid_digest(ref["digest"]):
                raise ValueError("FIFO_SOURCE_REFERENCE_INVALID")
            normalized_refs.append({"kind": ref_kind, "digest": ref["digest"]})
        if len({(item["kind"], item["digest"]) for item in normalized_refs}) != len(normalized_refs):
            raise ValueError("FIFO_SOURCE_REFERENCE_DUPLICATE")
        return {
            "source_kind": kind,
            "source_method": method,
            "source_status": status,
            "completeness": completeness,
            "provenance": provenance,
            "coverage_status": coverage,
            "source_fingerprint": fingerprint,
            "captured_at": cls._normalize_timestamp(source.get("captured_at")),
            "source_as_of": cls._normalize_timestamp(source.get("source_as_of")),
            "inventory_cutoff": cls._normalize_cutoff(source.get("inventory_cutoff")),
            "record_count": cls._optional_count(source.get("record_count")),
            "page_count": cls._optional_count(source.get("page_count")),
            "references": sorted(normalized_refs, key=lambda item: (item["kind"], item["digest"])),
        }

    @classmethod
    def _normalize_events(cls, events, source):
        if not isinstance(events, list) or not 1 <= len(events) <= cls.MAX_COMMAND_EVENTS:
            raise ValueError("FIFO_COMMAND_EVENT_LIMIT")
        normalized = []
        for item in events:
            if not isinstance(item, dict):
                raise ValueError("FIFO_EVENT_INVALID")
            allowed = {
                "kind", "quantity", "effective_at", "effective_date",
                "inventory_cutoff", "unit_cost_rub", "purchase_cost_rub",
                "delivery_cost_rub", "packaging_cost_rub", "currency",
                "location_from", "location_to", "source_identity_digest",
                "supersedes_event_id", "reason_code",
            }
            if set(item) - allowed:
                raise ValueError("FIFO_EVENT_FIELD_NOT_ALLOWED")
            kind = item.get("kind")
            if kind not in cls._EVENT_KINDS:
                raise ValueError("FIFO_EVENT_KIND_INVALID")
            quantity = item.get("quantity")
            if type(quantity) is not int or not 1 <= quantity <= cls.MAX_EVENT_QUANTITY:
                raise ValueError("FIFO_EVENT_QUANTITY_INVALID")
            effective_at = cls._normalize_timestamp(item.get("effective_at"))
            effective_date = cls._normalize_date(item.get("effective_date"))
            if effective_at is None and effective_date is None:
                raise ValueError("FIFO_EVENT_EFFECTIVE_TIME_REQUIRED")
            cutoff = cls._normalize_cutoff(
                item.get("inventory_cutoff", source.get("inventory_cutoff")),
            )
            cost_fields = ("purchase_cost_rub", "delivery_cost_rub", "packaging_cost_rub")
            supplied_components = [name in item for name in cost_fields]
            components = {
                name: cls._normalize_money(item.get(name)) if name in item else None
                for name in cost_fields
            }
            if any(supplied_components) and not all(supplied_components):
                raise ValueError("FIFO_COST_COMPONENTS_INCOMPLETE")
            if all(supplied_components) and any(
                components[name] is None for name in cost_fields
            ):
                raise ValueError("FIFO_MONEY_INPUT_INVALID")
            unit_cost = cls._normalize_money(item.get("unit_cost_rub"))
            is_layer = kind in {"OPENING_FIFO_ANCHOR", "COST_LAYER_RECEIPT"}
            if is_layer and unit_cost is None:
                raise ValueError("FIFO_LAYER_COST_REQUIRED")
            if not is_layer and (unit_cost is not None or any(supplied_components)):
                raise ValueError("FIFO_EVENT_COST_NOT_ALLOWED")
            if all(supplied_components):
                component_sum = sum(
                    Decimal(components[name]) for name in cost_fields
                ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                if component_sum != Decimal(unit_cost):
                    raise ValueError("FIFO_COST_COMPONENT_TOTAL_MISMATCH")
            if item.get("currency", "RUB") != "RUB":
                raise ValueError("FIFO_CURRENCY_UNSUPPORTED")
            from_location = item.get("location_from")
            to_location = item.get("location_to")
            if kind == "OPENING_FIFO_ANCHOR":
                if from_location is not None or to_location not in {"HOME", "TRANSIT", "OZON"}:
                    raise ValueError("FIFO_ANCHOR_ZONE_REQUIRED")
                if cutoff is None:
                    raise ValueError("FIFO_ANCHOR_CUTOFF_REQUIRED")
            elif kind == "INVENTORY_TRANSFER":
                if (from_location not in cls._LOCATIONS or to_location not in cls._LOCATIONS
                        or from_location == to_location):
                    raise ValueError("FIFO_TRANSFER_LOCATION_INVALID")
            elif from_location is not None or to_location is not None:
                raise ValueError("FIFO_EVENT_LOCATION_NOT_ALLOWED")
            source_identity_digest = item.get("source_identity_digest")
            if kind == "PHYSICAL_SALE":
                if not cls._valid_digest(source_identity_digest):
                    raise ValueError("FIFO_SALE_IDENTITY_REQUIRED")
            elif source_identity_digest is not None and not cls._valid_digest(source_identity_digest):
                raise ValueError("FIFO_SOURCE_IDENTITY_INVALID")
            supersedes = item.get("supersedes_event_id")
            if kind in {"CORRECTION", "SALE_CANCELLATION", "SALEABLE_RETURN_RESTOCK"}:
                if not isinstance(supersedes, str) or not re.fullmatch(r"evt_[0-9a-f]{32}", supersedes):
                    raise ValueError("FIFO_EVENT_TARGET_REQUIRED")
            elif supersedes is not None:
                raise ValueError("FIFO_EVENT_TARGET_NOT_ALLOWED")
            reason = item.get("reason_code")
            if reason is not None and reason not in cls._REASON_CODES:
                raise ValueError("FIFO_EVENT_REASON_INVALID")
            if kind in {"CORRECTION", "SALE_CANCELLATION", "NON_SALE_OUTFLOW"} and reason is None:
                raise ValueError("FIFO_EVENT_REASON_REQUIRED")
            normalized.append({
                "event_id": "evt_" + uuid4().hex,
                "kind": kind,
                "quantity": quantity,
                "effective_at": effective_at,
                "effective_date": effective_date,
                "inventory_cutoff": cutoff,
                "unit_cost_rub": unit_cost,
                **components,
                "location_from": from_location,
                "location_to": to_location,
                "source_identity_digest": source_identity_digest,
                "supersedes_event_id": supersedes,
                "reason_code": reason,
            })
        return normalized

    @staticmethod
    def _opening_anchor_error(events, source, *, current_revision, current_state):
        if any(event["kind"] != "OPENING_FIFO_ANCHOR" for event in events):
            return "FIFO_ANCHOR_COMMAND_MUST_BE_EXCLUSIVE"
        if current_revision != 0 or current_state != "FIFO_PENDING_ANCHOR":
            return "FIFO_ANCHOR_ALREADY_EXISTS"
        if (
            source["source_status"] != "OWNER_CONFIRMED"
            or source["completeness"] != "OWNER_CONFIRMED"
            or source["provenance"] != "OWNER_CONFIRMED"
            or source["coverage_status"] != "OWNER_CONFIRMED"
            or source["source_kind"] != "OWNER_CONFIRMATION"
            or source["source_method"] != "OWNER_CONFIRMED_FIFO_CUTOFF"
        ):
            return "FIFO_ANCHOR_OWNER_CONFIRMATION_REQUIRED"
        if source["inventory_cutoff"] is None:
            return "FIFO_ANCHOR_CUTOFF_REQUIRED"
        if source["captured_at"] is None:
            return "FIFO_ANCHOR_CAPTURE_TIME_REQUIRED"
        if not events or sum(event["quantity"] for event in events) <= 0:
            return "FIFO_ANCHOR_QUANTITY_REQUIRED"
        if any(event["inventory_cutoff"] != source["inventory_cutoff"] for event in events):
            return "FIFO_ANCHOR_CUTOFF_MISMATCH"
        if any(
            event["effective_at"] is not None
            or event["effective_date"] != source["inventory_cutoff"]
            for event in events
        ):
            return "FIFO_ANCHOR_CUTOFF_MISMATCH"
        if any(event["location_to"] not in {"HOME", "TRANSIT", "OZON"} for event in events):
            return "FIFO_ANCHOR_ZONE_REQUIRED"
        return None

    def _ensure_source(self, connection, normalized):
        source = normalized["source"]
        source_id = normalized["source_id"]
        row = connection.execute(
            """SELECT source_id, source_kind, source_method, source_status,
                      provenance, captured_at, source_as_of, coverage_status,
                      record_count, page_count
               FROM fifo_cost_sources WHERE store_id=? AND source_fingerprint=?""",
            (normalized["identity"]["store_id"], source["source_fingerprint"]),
        ).fetchone()
        is_new_source = row is None
        expected = (
            source_id, source["source_kind"], source["source_method"],
            source["source_status"], source["provenance"], source["captured_at"],
            source["source_as_of"], source["coverage_status"],
            source["record_count"], source["page_count"],
        )
        if row is not None:
            if tuple(row) != expected:
                raise ValueError("FIFO_SOURCE_FINGERPRINT_CONFLICT")
            existing_refs = {
                (item["reference_kind"], item["reference_digest"])
                for item in connection.execute(
                    "SELECT reference_kind, reference_digest "
                    "FROM fifo_cost_source_refs WHERE source_id=?",
                    (source_id,),
                ).fetchall()
            }
            requested_refs = {
                (item["kind"], item["digest"]) for item in source["references"]
            }
            if existing_refs != requested_refs:
                raise ValueError("FIFO_SOURCE_FINGERPRINT_CONFLICT")
        else:
            connection.execute(
                """INSERT INTO fifo_cost_sources (
                    source_id, store_id, source_kind, source_method, source_status,
                    provenance, source_fingerprint, captured_at, source_as_of,
                    coverage_status, record_count, page_count, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    source_id, normalized["identity"]["store_id"],
                    source["source_kind"], source["source_method"],
                    source["source_status"], source["provenance"],
                    source["source_fingerprint"], source["captured_at"],
                    source["source_as_of"], source["coverage_status"],
                    source["record_count"], source["page_count"],
                    self._iso(self._now()),
                ),
            )
        for ref in (source["references"] if is_new_source else ()):
            ref_id = "ref_" + self._sha256({
                "source_id": source_id,
                "kind": ref["kind"],
                "digest": ref["digest"],
            })[:40]
            connection.execute(
                """INSERT OR IGNORE INTO fifo_cost_source_refs (
                    source_ref_id, source_id, reference_kind, reference_digest, created_at
                ) VALUES (?, ?, ?, ?, ?)""",
                (ref_id, source_id, ref["kind"], ref["digest"], self._iso(self._now())),
            )

    def _ensure_policy_revision(self, connection, normalized, now):
        identity = normalized["identity"]
        policy = {
            "version": identity["policy_version"],
            "allocation": "FIFO",
            "currency": "RUB",
            "quantity_unit": "SELLABLE_SKU_UNIT",
        }
        policy_json = self._canonical_json(policy)
        fingerprint = self._sha256_text(policy_json)
        row = connection.execute(
            """SELECT policy_json, policy_fingerprint FROM fifo_cost_policy_revisions
               WHERE stream_id=? AND policy_version=?""",
            (normalized["stream_id"], identity["policy_version"]),
        ).fetchone()
        if row is None:
            connection.execute(
                """INSERT INTO fifo_cost_policy_revisions (
                    stream_id, policy_version, policy_json, policy_fingerprint, created_at
                ) VALUES (?, ?, ?, ?, ?)""",
                (
                    normalized["stream_id"], identity["policy_version"],
                    policy_json, fingerprint, self._iso(now),
                ),
            )
        elif tuple(row) != (policy_json, fingerprint):
            raise ValueError("FIFO_POLICY_REVISION_CONFLICT")

    @staticmethod
    def _validate_supersedes_target(connection, stream_id, event, prior_events):
        target_id = event["supersedes_event_id"]
        if not target_id:
            return None
        for previous in prior_events:
            if previous["event_id"] == target_id:
                return previous["kind"]
        row = connection.execute(
            "SELECT event_kind FROM fifo_cost_events WHERE stream_id=? AND event_id=?",
            (stream_id, target_id),
        ).fetchone()
        if row is None:
            raise ValueError("FIFO_EVENT_TARGET_INVALID")
        return row["event_kind"]

    @classmethod
    def _normalize_money(cls, value):
        if value is None:
            return None
        if isinstance(value, bool) or isinstance(value, float):
            raise ValueError("FIFO_MONEY_INPUT_INVALID")
        try:
            amount = Decimal(str(value))
        except (InvalidOperation, ValueError):
            raise ValueError("FIFO_MONEY_INPUT_INVALID") from None
        if not amount.is_finite() or amount < 0 or amount > Decimal("1000000000"):
            raise ValueError("FIFO_MONEY_INPUT_INVALID")
        return format(amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), ".2f")

    @classmethod
    def _normalize_timestamp(cls, value):
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("FIFO_TIMESTAMP_INVALID")
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            raise ValueError("FIFO_TIMESTAMP_INVALID") from None
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("FIFO_TIMESTAMP_INVALID")
        return cls._iso(parsed)

    @staticmethod
    def _normalize_date(value):
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("FIFO_DATE_INVALID")
        try:
            return date.fromisoformat(value).isoformat()
        except ValueError:
            raise ValueError("FIFO_DATE_INVALID") from None

    @classmethod
    def _normalize_cutoff(cls, value):
        if value is None:
            return None
        if isinstance(value, str) and "T" not in value and " " not in value:
            return cls._normalize_date(value)
        return cls._normalize_timestamp(value)

    @staticmethod
    def _optional_count(value):
        if value is None:
            return None
        if type(value) is not int or not 0 <= value <= 10_000_000:
            raise ValueError("FIFO_SOURCE_COUNT_INVALID")
        return value

    @staticmethod
    def _enum_text(value, code, max_length):
        if not isinstance(value, str) or not re.fullmatch(r"[A-Z0-9_./-]{1," + str(max_length) + r"}", value):
            raise ValueError(code)
        return value

    @classmethod
    def _valid_digest(cls, value):
        return isinstance(value, str) and cls._HEX_DIGEST.fullmatch(value) is not None

    @staticmethod
    def _canonical_json(value):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    @classmethod
    def _sha256(cls, value):
        return cls._sha256_text(cls._canonical_json(value))

    @staticmethod
    def _sha256_text(value):
        return hashlib.sha256(str(value).encode("utf-8")).hexdigest()

    def _now(self):
        value = self._now_provider()
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("FIFO_CLOCK_INVALID")
        return value.astimezone(timezone.utc)

    @staticmethod
    def _iso(value):
        return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")

    def _purge_expired_previews(self, now):
        cutoff = now.timestamp()
        expired = [
            scope for scope, ticket in self._ACTIVE_PREVIEWS.items()
            if ticket["expires_at"] <= cutoff
        ]
        for scope in expired:
            self._ACTIVE_PREVIEWS.pop(scope, None)

    @staticmethod
    def _error(code):
        return {"error": True, "code": code}

    @classmethod
    def _migrate_schema(cls, connection, version):
        """Add allocation source revision metadata without rewriting evidence."""
        if version < 6:
            columns = {
                str(row[1]) for row in
                connection.execute("PRAGMA table_info(fifo_cost_allocations)")
            }
            if "stream_revision" not in columns:
                connection.execute(
                    """ALTER TABLE fifo_cost_allocations
                       ADD COLUMN stream_revision INTEGER NOT NULL DEFAULT 0
                       CHECK(stream_revision >= 0)"""
                )

    @classmethod
    def _normalize_allocation_preview(cls, preview, idempotency_key):
        if not isinstance(preview, dict):
            return "FIFO_ALLOCATION_PREVIEW_INVALID"
        expected_preview_keys = {
            "error", "complete", "status", "reason_code", "cutoff_status",
            "anchor_cutoff_date", "open_rate_effective_date", "stream_revision",
            "expected_allocation_revision", "source_set_fingerprint",
            "total_cogs_rub", "remaining_confirmed_units", "restored_units",
            "allocations", "preview_fingerprint",
        }
        if set(preview) != expected_preview_keys:
            return "FIFO_ALLOCATION_PREVIEW_INVALID"
        if not isinstance(idempotency_key, str) or not cls._IDEMPOTENCY_KEY.fullmatch(idempotency_key):
            return "FIFO_IDEMPOTENCY_KEY_INVALID"
        if (
            preview.get("error") is not False
            or preview.get("complete") is not True
            or preview.get("status") != "COMPLETE"
            or preview.get("reason_code") is not None
            or preview.get("cutoff_status") != "RECONCILED"
            or cls._normalize_date(preview.get("anchor_cutoff_date")) is None
            or (
                preview.get("open_rate_effective_date") is not None
                and cls._normalize_date(preview.get("open_rate_effective_date")) is None
            )
        ):
            return "FIFO_ALLOCATION_PREVIEW_INCOMPLETE"
        stream_revision = preview.get("stream_revision")
        allocation_revision = preview.get("expected_allocation_revision")
        source_fingerprint = preview.get("source_set_fingerprint")
        preview_fingerprint = preview.get("preview_fingerprint")
        if type(stream_revision) is not int or stream_revision < 1:
            return "FIFO_REVISION_CONFLICT"
        if type(allocation_revision) is not int or allocation_revision < 0:
            return "FIFO_REVISION_CONFLICT"
        if not cls._valid_digest(source_fingerprint) or not cls._valid_digest(preview_fingerprint):
            return "FIFO_ALLOCATION_PREVIEW_INVALID"
        material = {
            key: value for key, value in preview.items()
            if key not in {"preview_fingerprint", "error"}
        }
        if cls._sha256(material) != preview_fingerprint:
            return "FIFO_ALLOCATION_PREVIEW_INVALID"
        allocations = preview.get("allocations")
        if not isinstance(allocations, list) or len(allocations) > 100_000:
            return "FIFO_REPLAY_INPUT_LIMIT"
        normalized, seen_events = [], set()
        units, lines_total, total = 0, 0, Decimal("0.00")
        for row in allocations:
            if not isinstance(row, dict) or set(row) != {
                "event_id", "quantity", "total_cost_rub", "lines",
            }:
                return "FIFO_ALLOCATION_PREVIEW_INVALID"
            event_id, quantity = row.get("event_id"), row.get("quantity")
            sale_total = cls._normalize_money(row.get("total_cost_rub"))
            lines = row.get("lines")
            if (
                not isinstance(event_id, str) or not event_id or len(event_id) > 160
                or event_id in seen_events or type(quantity) is not int or quantity < 1
                or sale_total is None or not isinstance(lines, list) or not lines
            ):
                return "FIFO_ALLOCATION_PREVIEW_INVALID"
            seen_events.add(event_id)
            normalized_lines, seen_layers = [], set()
            sale_units, sale_cost = 0, Decimal("0.00")
            for line in lines:
                if not isinstance(line, dict) or set(line) != {
                    "layer_id", "rate_change_id", "quantity", "unit_cost_rub",
                    "total_cost_rub", "origin_sale_event_id",
                }:
                    return "FIFO_ALLOCATION_PREVIEW_INVALID"
                layer_id, line_quantity = line.get("layer_id"), line.get("quantity")
                rate_change_id = line.get("rate_change_id")
                unit_cost = cls._normalize_money(line.get("unit_cost_rub"))
                line_total = cls._normalize_money(line.get("total_cost_rub"))
                origin = line.get("origin_sale_event_id")
                basis_key = (
                    ("layer", layer_id) if isinstance(layer_id, str) else
                    ("rate", rate_change_id) if isinstance(rate_change_id, str) else None
                )
                if (
                    (layer_id is None) == (rate_change_id is None)
                    or (layer_id is not None and (
                        not isinstance(layer_id, str) or not layer_id or len(layer_id) > 160
                    ))
                    or (rate_change_id is not None and (
                        not isinstance(rate_change_id, str) or not rate_change_id
                        or len(rate_change_id) > 160
                    ))
                    or basis_key in seen_layers or type(line_quantity) is not int
                    or line_quantity < 1 or unit_cost is None or line_total is None
                    or (origin is not None and (
                        not isinstance(origin, str) or not origin or len(origin) > 160
                    ))
                ):
                    return "FIFO_ALLOCATION_PREVIEW_INVALID"
                seen_layers.add(basis_key)
                calculated = (Decimal(unit_cost) * line_quantity).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP,
                )
                if calculated != Decimal(line_total):
                    return "FIFO_ALLOCATION_TOTAL_MISMATCH"
                normalized_lines.append({
                    "layer_id": layer_id, "rate_change_id": rate_change_id,
                    "quantity": line_quantity,
                    "unit_cost_rub": unit_cost, "total_cost_rub": line_total,
                    "origin_sale_event_id": origin,
                })
                sale_units += line_quantity
                sale_cost += Decimal(line_total)
            if sale_units != quantity or sale_cost != Decimal(sale_total):
                return "FIFO_ALLOCATION_TOTAL_MISMATCH"
            units += quantity
            lines_total += len(normalized_lines)
            total += sale_cost
            if units > cls.MAX_COMMAND_UNITS or lines_total > 250_000:
                return "FIFO_REPLAY_WORK_LIMIT"
            normalized.append({
                "event_id": event_id, "quantity": quantity,
                "total_cost_rub": sale_total, "lines": normalized_lines,
            })
        grand_total = cls._normalize_money(preview.get("total_cogs_rub"))
        if grand_total is None or Decimal(grand_total) != total:
            return "FIFO_ALLOCATION_TOTAL_MISMATCH"
        payload = {
            "stream_revision": stream_revision,
            "expected_allocation_revision": allocation_revision,
            "source_set_fingerprint": source_fingerprint,
            "preview_fingerprint": preview_fingerprint,
            "anchor_cutoff_date": preview["anchor_cutoff_date"],
            "open_rate_effective_date": preview["open_rate_effective_date"],
            "allocations": normalized,
            "total_cogs_rub": grand_total,
        }
        return {**payload, "payload_fingerprint": cls._sha256(payload)}

    @classmethod
    def _validate_allocation_lines(
        cls, connection, stream_id, preview, *, stream_revision,
        allocation_revision, source_fingerprint, cutoff_status,
    ):
        allocations = preview["allocations"]
        anchor = connection.execute(
            """SELECT COUNT(DISTINCT inventory_cutoff), MIN(inventory_cutoff)
               FROM fifo_cost_events
               WHERE stream_id=? AND event_kind='OPENING_FIFO_ANCHOR'""",
            (stream_id,),
        ).fetchone()
        if anchor[0] != 1 or not isinstance(anchor[1], str):
            raise ValueError("INVENTORY_CUTOFF_UNRECONCILED")
        anchor_cutoff = cls._normalize_date(anchor[1])
        unsupported_events = connection.execute(
            """SELECT COUNT(*) FROM fifo_cost_events
               WHERE stream_id=? AND event_kind NOT IN (
                   'OPENING_FIFO_ANCHOR', 'PHYSICAL_SALE'
               )""",
            (stream_id,),
        ).fetchone()[0]
        if unsupported_events:
            raise ValueError("FIFO_REPLAY_UNSUPPORTED_EVENT")
        rate_count = connection.execute(
            "SELECT COUNT(*) FROM fifo_cost_rate_changes WHERE stream_id=?",
            (stream_id,),
        ).fetchone()[0]
        if rate_count > 1:
            raise ValueError("FIFO_REPLAY_RATE_TRANSITION_UNSUPPORTED")
        source_sales = connection.execute(
            """SELECT event_id, effective_date, inventory_cutoff FROM fifo_cost_events
               WHERE stream_id=? AND event_kind='PHYSICAL_SALE'
               ORDER BY event_id LIMIT 100001""",
            (stream_id,),
        ).fetchall()
        if len(source_sales) > 100_000:
            raise ValueError("FIFO_REPLAY_INPUT_LIMIT")
        if {row["event_id"] for row in source_sales} != {
            row["event_id"] for row in allocations
        }:
            raise ValueError("FIFO_ALLOCATION_COVERAGE_MISMATCH")
        source_sale_by_id = {row["event_id"]: row for row in source_sales}
        for sale in source_sale_by_id.values():
            if (
                sale["effective_date"] is None
                or sale["effective_date"] <= anchor_cutoff
                or sale["inventory_cutoff"] != anchor_cutoff
            ):
                raise ValueError("INVENTORY_CUTOFF_UNRECONCILED")
        for allocation in allocations:
            event = connection.execute(
                """SELECT e.event_kind, e.quantity, e.source_identity_digest,
                          e.provenance, e.completeness, s.source_method,
                          s.source_status, s.coverage_status
                   FROM fifo_cost_events AS e
                   LEFT JOIN fifo_cost_sources AS s ON s.source_id=e.source_id
                   WHERE e.stream_id=? AND e.event_id=?""",
                (stream_id, allocation["event_id"]),
            ).fetchone()
            sale_row = source_sale_by_id[allocation["event_id"]]
            if (
                event is None or event["event_kind"] != "PHYSICAL_SALE"
                or event["source_identity_digest"] is None
                or event["quantity"] != allocation["quantity"]
                or event["provenance"] != "OZON_CONFIRMED_FIELD"
                or event["completeness"] != "COMPLETE"
                or event["source_method"] != "OZON_REALIZATION_REPORT"
                or event["source_status"] != "COMPLETE"
                or event["coverage_status"] != "COMPLETE"
            ):
                raise ValueError("FIFO_ALLOCATION_EVENT_INVALID")
            for line in allocation["lines"]:
                if line["layer_id"] is not None:
                    layer = connection.execute(
                        """SELECT l.unit_cost_rub, l.effective_date,
                                  e.event_kind, e.inventory_cutoff
                           FROM fifo_cost_layers AS l
                           JOIN fifo_cost_events AS e ON e.event_id=l.event_id
                           WHERE l.stream_id=? AND l.layer_id=?""",
                        (stream_id, line["layer_id"]),
                    ).fetchone()
                    if layer is None:
                        raise ValueError("FIFO_ALLOCATION_LAYER_INVALID")
                    if (
                        layer["event_kind"] != "OPENING_FIFO_ANCHOR"
                        or layer["effective_date"] != anchor_cutoff
                        or layer["inventory_cutoff"] != anchor_cutoff
                    ):
                        raise ValueError("FIFO_REPLAY_UNSUPPORTED_EVENT")
                    if cls._normalize_money(layer["unit_cost_rub"]) != line["unit_cost_rub"]:
                        raise ValueError("FIFO_ALLOCATION_RATE_MISMATCH")
                else:
                    rate = connection.execute(
                        """SELECT unit_cost_rub, effective_date FROM fifo_cost_rate_changes
                           WHERE stream_id=? AND rate_change_id=?""",
                        (stream_id, line["rate_change_id"]),
                    ).fetchone()
                    if rate is None:
                        raise ValueError("FIFO_ALLOCATION_RATE_INVALID")
                    if cls._normalize_money(rate["unit_cost_rub"]) != line["unit_cost_rub"]:
                        raise ValueError("FIFO_ALLOCATION_RATE_MISMATCH")
                    if rate["effective_date"] >= sale_row["effective_date"]:
                        raise ValueError("FIFO_ALLOCATION_RATE_DATE_CONFLICT")
                if line["origin_sale_event_id"] is not None:
                    basis = connection.execute(
                        """SELECT 1 FROM fifo_cost_events
                           WHERE stream_id=? AND event_id=?
                             AND event_kind='PHYSICAL_SALE' LIMIT 1""",
                        (stream_id, line["origin_sale_event_id"]),
                    ).fetchone()
                    if basis is None:
                        raise ValueError("FIFO_ALLOCATION_BASIS_MISSING")

        expected = cls._preview_allocation_from_connection(
            connection, stream_id,
            stream_revision=stream_revision,
            allocation_revision=allocation_revision,
            source_fingerprint=source_fingerprint,
            cutoff_status=cutoff_status,
            anchor_cutoff_date=anchor_cutoff,
        )
        if expected is None or expected.get("complete") is not True:
            reason = (
                expected.get("reason_code") if expected is not None else None
            ) or "FIFO_ALLOCATION_REPLAY_UNAVAILABLE"
            raise ValueError(reason)
        if (
            preview["anchor_cutoff_date"] != anchor_cutoff
            or preview["open_rate_effective_date"] != expected["open_rate_effective_date"]
            or preview["allocations"] != expected["allocations"]
            or preview["total_cogs_rub"] != expected["total_cogs_rub"]
        ):
            raise ValueError("FIFO_ALLOCATION_REPLAY_MISMATCH")

    @classmethod
    def _preview_allocation_from_connection(
        cls, connection, stream_id, *, stream_revision,
        allocation_revision, source_fingerprint, cutoff_status,
        anchor_cutoff_date,
    ):
        """Rebuild expected FIFO output from immutable source rows before write."""
        anchor_row = connection.execute(
            """SELECT event_id, provenance, completeness, location_to
               FROM fifo_cost_events
               WHERE stream_id=? AND event_kind='OPENING_FIFO_ANCHOR'
               ORDER BY event_id LIMIT 100001""",
            (stream_id,),
        ).fetchall()
        if not anchor_row or len(anchor_row) > 100_000:
            return None
        anchor_status = (
            "CONFIRMED"
            if all(
                event["provenance"] == "OWNER_CONFIRMED"
                and event["completeness"] == "OWNER_CONFIRMED"
                and event["location_to"] in {"OZON", "TRANSIT", "HOME"}
                for event in anchor_row
            )
            else "UNKNOWN"
        )
        layer_rows = connection.execute(
            """SELECT layer_id, unit_cost_rub, quantity
               FROM fifo_cost_layers WHERE stream_id=?
               ORDER BY layer_sequence LIMIT 100001""",
            (stream_id,),
        ).fetchall()
        if len(layer_rows) > 100_000:
            return {"complete": False, "reason_code": "FIFO_REPLAY_INPUT_LIMIT"}
        layers = [
            FifoCostLayer(row["layer_id"], row["unit_cost_rub"], row["quantity"])
            for row in layer_rows
        ]
        sale_rows = connection.execute(
            """SELECT event_id, effective_at, effective_date, quantity,
                      source_identity_digest
               FROM fifo_cost_events
               WHERE stream_id=? AND event_kind='PHYSICAL_SALE'
               ORDER BY event_id LIMIT 100001""",
            (stream_id,),
        ).fetchall()
        if len(sale_rows) > 100_000:
            return {"complete": False, "reason_code": "FIFO_REPLAY_INPUT_LIMIT"}
        sales = []
        for row in sale_rows:
            sales.append(FifoDatedAllocationEvent(
                event=FifoSaleEvent(row["event_id"], row["quantity"]),
                effective_at=row["effective_at"],
                effective_date=row["effective_date"],
                source_identity_digest=row["source_identity_digest"],
                physical_time_confirmed=True,
                cutoff_bridge_confirmed=(cutoff_status == "RECONCILED"),
            ))
        rate_rows = connection.execute(
            """SELECT rate_change_id, effective_date, unit_cost_rub
               FROM fifo_cost_rate_changes
               WHERE stream_id=? ORDER BY rate_sequence LIMIT 2""",
            (stream_id,),
        ).fetchall()
        if len(rate_rows) > 1:
            return {
                "complete": False,
                "reason_code": "FIFO_REPLAY_RATE_TRANSITION_UNSUPPORTED",
            }
        open_rate = None
        open_rate_date = None
        if rate_rows:
            rate = rate_rows[0]
            open_rate = FifoOpenCostRate(
                rate["rate_change_id"], rate["unit_cost_rub"],
            )
            open_rate_date = rate["effective_date"]
        return FifoCostReplayService().preview(
            layers=layers,
            events=sales,
            stream_revision=stream_revision,
            expected_allocation_revision=allocation_revision,
            source_set_fingerprint=source_fingerprint,
            anchor_cutoff_date=anchor_cutoff_date,
            anchor_status=anchor_status,
            cutoff_status=cutoff_status,
            source_completeness="COMPLETE",
            open_rate=open_rate,
            open_rate_effective_date=open_rate_date,
        )

    @classmethod
    def _allocation_source_fingerprint(
        cls, connection, stream_id, stream_revision, policy_version, cutoff_status,
    ):
        queries = {
            "events": "SELECT event_id, event_kind, effective_at, effective_date, quantity, "
                "unit_cost_rub, source_fingerprint, provenance, completeness, "
                "source_identity_digest, supersedes_event_id, reason_code "
                "FROM fifo_cost_events WHERE stream_id=? ORDER BY event_id",
            "layers": "SELECT layer_id, event_id, layer_sequence, quantity, unit_cost_rub, "
                "effective_at, effective_date, provenance, source_id "
                "FROM fifo_cost_layers WHERE stream_id=? ORDER BY layer_sequence",
            "rates": "SELECT rate_change_id, rate_sequence, effective_date, unit_cost_rub, purchase_cost_rub, "
                "delivery_cost_rub, packaging_cost_rub, payload_fingerprint "
                "FROM fifo_cost_rate_changes WHERE stream_id=? ORDER BY rate_sequence",
            "reconciliations": "SELECT transition_rate_sequence, reconciled_rate_sequence, "
                "effective_date, reconciled_total_units, older_finite_units, "
                "prior_rate_units, source_fingerprint FROM fifo_cost_rate_reconciliations "
                "WHERE stream_id=? ORDER BY transition_rate_sequence",
            "supplies": "SELECT snapshot_sequence, source_fingerprint, evidence_fingerprint, "
                "source_status, physical_effective_date FROM fifo_cost_supply_evidence "
                "WHERE stream_id=? ORDER BY snapshot_sequence",
        }
        material = {}
        for name, query in queries.items():
            rows = connection.execute(query + " LIMIT 100001", (stream_id,)).fetchall()
            if len(rows) > 100_000:
                raise ValueError("FIFO_REPLAY_INPUT_LIMIT")
            material[name] = [dict(row) for row in rows]
        material.update({
            "stream_revision": stream_revision,
            "policy_version": policy_version,
            "cutoff_status": cutoff_status,
        })
        return cls._sha256(material)


    def _initialize_schema(self, connection):
        """Create the additive FIFO schema atomically and reject unknown versions."""
        connection.execute("BEGIN IMMEDIATE")
        try:
            version = self._read_schema_version(connection)
            if version > self.SCHEMA_VERSION:
                raise sqlite3.DatabaseError("unsupported FIFO cost schema version")
            if version not in range(0, self.SCHEMA_VERSION + 1):
                raise sqlite3.DatabaseError("unsupported FIFO cost schema version")

            self._create_tables(connection)
            self._migrate_schema(connection, version)
            self._create_indexes(connection)
            self._create_append_only_guards(connection)

            if version == 0:
                connection.execute(
                    "INSERT INTO fifo_cost_schema(singleton, version) VALUES (1, ?)",
                    (self.SCHEMA_VERSION,),
                )
            elif version < self.SCHEMA_VERSION:
                connection.execute(
                    "UPDATE fifo_cost_schema SET version=? WHERE singleton=1",
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
                UNIQUE(stream_id, layer_sequence)
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

            CREATE TABLE IF NOT EXISTS fifo_cost_rate_changes (
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
            );

            CREATE TABLE IF NOT EXISTS fifo_cost_rate_reconciliations (
                reconciliation_id TEXT PRIMARY KEY,
                stream_id TEXT NOT NULL REFERENCES fifo_cost_streams(stream_id),
                stream_revision INTEGER NOT NULL CHECK(stream_revision >= 2),
                transition_rate_sequence INTEGER NOT NULL CHECK(
                    transition_rate_sequence >= 2
                ),
                reconciled_rate_sequence INTEGER NOT NULL CHECK(
                    reconciled_rate_sequence >= 1
                ),
                effective_date TEXT NOT NULL,
                reconciled_total_units INTEGER NOT NULL CHECK(
                    reconciled_total_units >= 0 AND reconciled_total_units <= 1000000
                ),
                older_finite_units INTEGER NOT NULL CHECK(
                    older_finite_units >= 0 AND older_finite_units <= 1000000
                ),
                prior_rate_units INTEGER NOT NULL CHECK(
                    prior_rate_units >= 0 AND prior_rate_units <= 1000000
                ),
                fbo_units INTEGER NOT NULL CHECK(fbo_units >= 0 AND fbo_units <= 1000000),
                reserved_units INTEGER NOT NULL CHECK(
                    reserved_units >= 0 AND reserved_units <= fbo_units
                ),
                transit_units INTEGER NOT NULL CHECK(
                    transit_units >= 0 AND transit_units <= 1000000
                ),
                home_units INTEGER NOT NULL CHECK(home_units >= 0 AND home_units <= 1000000),
                source_fingerprint TEXT NOT NULL CHECK(length(source_fingerprint) = 64),
                captured_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                CHECK(transition_rate_sequence = reconciled_rate_sequence + 1),
                CHECK(reconciled_total_units = fbo_units + transit_units + home_units),
                CHECK(reconciled_total_units = older_finite_units + prior_rate_units),
                UNIQUE(stream_id, transition_rate_sequence),
                UNIQUE(stream_id, reconciled_rate_sequence)
            );

            CREATE TABLE IF NOT EXISTS fifo_cost_supply_evidence (
                evidence_id TEXT PRIMARY KEY,
                stream_id TEXT NOT NULL REFERENCES fifo_cost_streams(stream_id),
                snapshot_sequence INTEGER NOT NULL CHECK(snapshot_sequence >= 1),
                stream_revision INTEGER NOT NULL CHECK(stream_revision >= 0),
                source_id TEXT NOT NULL REFERENCES fifo_cost_sources(source_id),
                source_fingerprint TEXT NOT NULL CHECK(length(source_fingerprint) = 64),
                evidence_fingerprint TEXT NOT NULL CHECK(length(evidence_fingerprint) = 64),
                order_digest TEXT NOT NULL CHECK(length(order_digest) = 64),
                supply_digest TEXT NOT NULL CHECK(length(supply_digest) = 64),
                source_status TEXT NOT NULL CHECK(source_status = 'COMPLETE'),
                captured_at TEXT NOT NULL,
                source_as_of TEXT CHECK(source_as_of IS NULL),
                physical_effective_at TEXT CHECK(physical_effective_at IS NULL),
                physical_effective_date TEXT CHECK(physical_effective_date IS NULL),
                normalized_evidence_json TEXT NOT NULL CHECK(
                    length(normalized_evidence_json) <= 65536
                ),
                created_at TEXT NOT NULL,
                UNIQUE(stream_id, evidence_fingerprint),
                UNIQUE(stream_id, snapshot_sequence)
            );

            CREATE TABLE IF NOT EXISTS fifo_cost_allocations (
                allocation_id TEXT PRIMARY KEY,
                stream_id TEXT NOT NULL REFERENCES fifo_cost_streams(stream_id),
                revision INTEGER NOT NULL CHECK(revision >= 1),
                stream_revision INTEGER NOT NULL DEFAULT 0 CHECK(stream_revision >= 0),
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

            CREATE TABLE IF NOT EXISTS fifo_cost_allocation_rate_lines (
                allocation_id TEXT NOT NULL REFERENCES fifo_cost_allocations(allocation_id),
                line_number INTEGER NOT NULL CHECK(line_number >= 1),
                event_id TEXT NOT NULL REFERENCES fifo_cost_events(event_id),
                rate_change_id TEXT NOT NULL REFERENCES fifo_cost_rate_changes(rate_change_id),
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

            CREATE TABLE IF NOT EXISTS fifo_cost_commands (
                command_id TEXT PRIMARY KEY,
                stream_id TEXT NOT NULL REFERENCES fifo_cost_streams(stream_id),
                stream_revision INTEGER NOT NULL CHECK(stream_revision >= 1),
                payload_fingerprint TEXT NOT NULL,
                source_fingerprint TEXT NOT NULL,
                event_count INTEGER NOT NULL CHECK(event_count > 0 AND event_count <= 100),
                created_at TEXT NOT NULL,
                UNIQUE(stream_id, stream_revision)
            );

            CREATE TABLE IF NOT EXISTS fifo_cost_command_events (
                command_id TEXT NOT NULL REFERENCES fifo_cost_commands(command_id),
                event_id TEXT NOT NULL REFERENCES fifo_cost_events(event_id),
                event_order INTEGER NOT NULL CHECK(event_order >= 1),
                PRIMARY KEY(command_id, event_order),
                UNIQUE(command_id, event_id)
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
            CREATE INDEX IF NOT EXISTS idx_fifo_cost_commands_stream_revision
                ON fifo_cost_commands(stream_id, stream_revision);
            CREATE INDEX IF NOT EXISTS idx_fifo_cost_source_refs_digest
                ON fifo_cost_source_refs(reference_kind, reference_digest);
            CREATE INDEX IF NOT EXISTS idx_fifo_cost_rate_changes_order
                ON fifo_cost_rate_changes(stream_id, effective_date, rate_sequence);
            CREATE INDEX IF NOT EXISTS idx_fifo_cost_rate_reconciliations_order
                ON fifo_cost_rate_reconciliations(stream_id, transition_rate_sequence);
            CREATE INDEX IF NOT EXISTS idx_fifo_cost_supply_evidence_order
                ON fifo_cost_supply_evidence(stream_id, snapshot_sequence);
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
        allocation_columns = {
            str(item[1])
            for item in connection.execute("PRAGMA table_info(fifo_cost_allocations)")
        }
        rate_line_columns = {
            str(item[1])
            for item in connection.execute(
                "PRAGMA table_info(fifo_cost_allocation_rate_lines)"
            )
        }
        if "stream_revision" not in allocation_columns or not {
            "allocation_id", "line_number", "event_id", "rate_change_id",
            "quantity", "unit_cost_rub", "total_cost_rub",
        } <= rate_line_columns:
            raise sqlite3.DatabaseError("invalid FIFO allocation schema")

