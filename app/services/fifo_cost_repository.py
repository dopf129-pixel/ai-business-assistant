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
from services.tenant_context import get_current_tenant_user_id
from services.tenant_storage import ensure_storage_parent, tenant_storage_path


class FifoCostRepository:
    SCHEMA_VERSION = 2
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
    _REFERENCE_KINDS = frozenset({"SUPPLY", "ACT", "POSTING", "DOCUMENT", "OTHER"})
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
        "fifo_cost_commands",
        "fifo_cost_command_events",
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
        "fifo_cost_commands",
        "fifo_cost_command_events",
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


    def _initialize_schema(self, connection):
        """Create the additive FIFO schema atomically and reject unknown versions."""
        connection.execute("BEGIN IMMEDIATE")
        try:
            version = self._read_schema_version(connection)
            if version > self.SCHEMA_VERSION:
                raise sqlite3.DatabaseError("unsupported FIFO cost schema version")
            if version not in (0, 1, self.SCHEMA_VERSION):
                raise sqlite3.DatabaseError("unsupported FIFO cost schema version")

            self._create_tables(connection)
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

