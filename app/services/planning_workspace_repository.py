"""Tenant-scoped durable storage for local unit-economics plans.

Only explicit planning inputs and historical projections are stored here.  The
repository deliberately has no dependency on Telegram, Ozon, seller settings,
or factual finance repositories.
"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from services.ozon_account_repository import split_store_tenant_scope
from services.tenant_context import get_current_tenant_user_id
from services.tenant_storage import ensure_storage_parent, tenant_storage_path


class PlanningWorkspaceRepository:
    SCHEMA_VERSION = 2
    DATABASE_SCHEMA_VERSION = 2
    MAX_DOCUMENTS_PER_STORE = 200
    MAX_REVISIONS_PER_DOCUMENT = 20
    MAX_PAYLOAD_BYTES = 64 * 1024
    MAX_PAGE_SIZE = 10
    MAX_SALES_MIX_QUANTITY_PER_ITEM = 100_000
    MAX_SALES_MIX_TOTAL_QUANTITY = 1_000_000
    MAX_SALES_MIX_EXPENSES = 20
    MAX_SALES_MIX_EXPENSE_TOTAL = Decimal("1000000000.00")
    _TITLE_LIMIT = 80
    _IDEMPOTENCY_RE = re.compile(r"^[A-Za-z0-9_-]{8,80}$")
    _INPUT_FIELDS = frozenset({
        "price", "cost", "commission_rate", "advertising_rate",
        "discount_points_rate", "logistics_per_unit", "last_mile_per_unit",
        "acquiring_per_unit", "tax_mode", "tax_rate", "minimum_tax_rate",
        "cross_docking_per_unit",
    })
    _IDENTITY_FIELDS = frozenset({
        "product_id", "offer_id", "sku", "product_name", "store_id", "scheme",
    })
    _PROJECTION_FIELDS = frozenset({
        "status", "available", "missing_inputs", "invalid_inputs", "revenue",
        "discount_points", "taxable_revenue", "commission", "advertising",
        "fees", "profit_before_tax", "tax", "effective_tax_rate", "profit",
        "margin_percent", "cross_docking",
    })
    _SOURCE_FIELDS = frozenset({
        "periods", "as_of", "loaded_at", "completeness", "cross_docking",
    })

    def __init__(self, db_path=None, clock=None):
        self._db_path = Path(db_path) if db_path is not None else None
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    @property
    def db_path(self):
        return self._db_path or Path(tenant_storage_path("ozon_assistant.db"))

    def get_connection(self):
        ensure_storage_parent(self.db_path)
        connection = sqlite3.connect(
            self.db_path, timeout=5.0, isolation_level=None,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=5000")
        connection.execute("PRAGMA foreign_keys=ON")
        self._initialize_schema(connection)
        return connection

    def save_document(
        self, *, title, payload, owner_id=None, store_id=None,
        document_id=None, expected_revision=None, expected_state_revision=None,
        idempotency_key,
    ):
        scope = self._scope(owner_id, store_id)
        if scope.get("error"):
            return self._error(scope["code"])
        if document_id is not None and (
            type(expected_state_revision) is not int or expected_state_revision < 1
        ):
            return self._error("PLANNING_DOCUMENT_STATE_REVISION_REQUIRED")
        normalized_title = self._title(title)
        normalized_payload = self._payload(
            payload, scope, allow_legacy_sales_mix=document_id is not None,
        )
        key = self._idempotency_key(idempotency_key)
        if normalized_title is None or normalized_payload is None or key is None:
            return self._error("PLANNING_DOCUMENT_INPUT_INVALID")
        encoded = self._encode(normalized_payload)
        if encoded is None or len(encoded.encode("utf-8")) > self.MAX_PAYLOAD_BYTES:
            return self._error("PLANNING_DOCUMENT_TOO_LARGE")

        try:
            connection = self.get_connection()
        except (sqlite3.Error, OSError):
            return self._error("PLANNING_STORAGE_UNAVAILABLE")
        try:
            connection.execute("BEGIN IMMEDIATE")
            replay = self._idempotent_result(connection, scope, key)
            if replay is not None:
                connection.commit()
                return replay
            now = self._timestamp()
            if document_id is None:
                count = connection.execute(
                    "SELECT COUNT(*) FROM planning_documents WHERE owner_id=? AND store_id=?",
                    (scope["owner_id"], scope["store_id"]),
                ).fetchone()[0]
                if count >= self.MAX_DOCUMENTS_PER_STORE:
                    connection.rollback()
                    return self._error("PLANNING_DOCUMENT_QUOTA_REACHED")
                document_id = uuid4().hex
                revision = 1
                connection.execute(
                    """INSERT INTO planning_documents
                       (document_id, owner_id, store_id, title, status, revision, state_revision,
                        schema_version, calculation_version, created_at, updated_at)
                       VALUES (?, ?, ?, ?, 'ACTIVE', 1, 1, ?, ?, ?, ?)""",
                    (document_id, scope["owner_id"], scope["store_id"], normalized_title,
                     normalized_payload["schema_version"],
                     normalized_payload["calculation_version"], now, now),
                )
            else:
                if type(expected_revision) is not int or expected_revision < 1:
                    connection.rollback()
                    return self._error("PLANNING_DOCUMENT_REVISION_REQUIRED")
                row = connection.execute(
                    "SELECT revision, state_revision, status FROM planning_documents "
                    "WHERE document_id=? AND owner_id=? AND store_id=?",
                    (str(document_id), scope["owner_id"], scope["store_id"]),
                ).fetchone()
                if row is None:
                    connection.rollback()
                    return self._error("PLANNING_DOCUMENT_NOT_FOUND")
                if row["revision"] != expected_revision:
                    connection.rollback()
                    return self._error("PLANNING_DOCUMENT_REVISION_CONFLICT")
                if row["state_revision"] != expected_state_revision:
                    connection.rollback()
                    return self._error("PLANNING_DOCUMENT_STATE_CONFLICT")
                if row["status"] != "ACTIVE":
                    connection.rollback()
                    return self._error("PLANNING_DOCUMENT_NOT_ACTIVE")
                if row["revision"] >= self.MAX_REVISIONS_PER_DOCUMENT:
                    connection.rollback()
                    return self._error("PLANNING_DOCUMENT_REVISION_LIMIT")
                revision = row["revision"] + 1
                previous_row = connection.execute(
                    "SELECT payload_json FROM planning_revisions WHERE document_id=? "
                    "AND owner_id=? AND store_id=? AND revision=?",
                    (str(document_id), scope["owner_id"], scope["store_id"], row["revision"]),
                ).fetchone()
                if previous_row is None:
                    connection.rollback()
                    return self._error("PLANNING_DOCUMENT_CORRUPT")
                previous_payload = json.loads(previous_row["payload_json"])
                new_mix = normalized_payload.get("sales_mix")
                if new_mix is not None and not self._valid_sales_mix(
                    new_mix, normalized_payload["items"],
                ):
                    if (
                        self._sales_mix_identity_scope(previous_payload)
                        != self._sales_mix_identity_scope(normalized_payload)
                        or previous_payload.get("sales_mix") != new_mix
                        or not self._valid_sales_mix(
                            new_mix, normalized_payload["items"], allow_legacy=True,
                        )
                    ):
                        connection.rollback()
                        return self._error("PLANNING_DOCUMENT_INPUT_INVALID")
                params = [normalized_title, revision, normalized_payload["schema_version"],
                          normalized_payload["calculation_version"], now, str(document_id),
                          scope["owner_id"], scope["store_id"], expected_revision]
                params.append(expected_state_revision)
                changed = connection.execute(
                    "UPDATE planning_documents SET title=?, revision=?, schema_version=?, "
                    "calculation_version=?, state_revision=state_revision+1, updated_at=? "
                    "WHERE document_id=? AND owner_id=? AND store_id=? AND revision=? "
                    "AND status='ACTIVE' AND state_revision=?",
                    tuple(params),
                ).rowcount
                if changed != 1:
                    connection.rollback()
                    return self._error("PLANNING_DOCUMENT_REVISION_CONFLICT")

            connection.execute(
                """INSERT INTO planning_revisions
                   (document_id, owner_id, store_id, revision, payload_json, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (str(document_id), scope["owner_id"], scope["store_id"], revision, encoded, now),
            )
            result = {"error": False, "document_id": str(document_id), "revision": revision,
                      "state_revision": 1 if expected_revision is None else row["state_revision"] + 1}
            self._remember_idempotency(connection, scope, key, result, now)
            connection.commit()
            return result
        except sqlite3.IntegrityError:
            connection.rollback()
            return self._error("PLANNING_DOCUMENT_REVISION_CONFLICT")
        except (ValueError, TypeError, OverflowError):
            connection.rollback()
            return self._error("PLANNING_CLOCK_UNAVAILABLE")
        except (sqlite3.Error, OSError):
            connection.rollback()
            return self._error("PLANNING_STORAGE_UNAVAILABLE")
        finally:
            connection.close()

    def get_document(self, document_id, *, revision=None, owner_id=None, store_id=None):
        scope = self._scope(owner_id, store_id)
        if scope.get("error") or not isinstance(document_id, str) or not document_id:
            return self._error("PLANNING_DOCUMENT_NOT_FOUND")
        try:
            connection = self.get_connection()
        except (sqlite3.Error, OSError):
            return self._error("PLANNING_STORAGE_UNAVAILABLE")
        try:
            row = connection.execute(
                "SELECT * FROM planning_documents WHERE document_id=? AND owner_id=? AND store_id=?",
                (document_id, scope["owner_id"], scope["store_id"]),
            ).fetchone()
            if row is None:
                return self._error("PLANNING_DOCUMENT_NOT_FOUND")
            if row["schema_version"] > self.SCHEMA_VERSION:
                return self._error("PLANNING_DOCUMENT_SCHEMA_UNSUPPORTED")
            selected_revision = row["revision"] if revision is None else revision
            if type(selected_revision) is not int or selected_revision < 1:
                return self._error("PLANNING_DOCUMENT_REVISION_NOT_FOUND")
            revision_row = connection.execute(
                "SELECT payload_json, created_at FROM planning_revisions "
                "WHERE document_id=? AND owner_id=? AND store_id=? AND revision=?",
                (document_id, scope["owner_id"], scope["store_id"], selected_revision),
            ).fetchone()
            if revision_row is None:
                return self._error("PLANNING_DOCUMENT_REVISION_NOT_FOUND")
            try:
                payload = json.loads(revision_row["payload_json"])
            except (ValueError, TypeError):
                return self._error("PLANNING_DOCUMENT_CORRUPT")
            payload_schema = payload.get("schema_version") if isinstance(payload, dict) else None
            if type(payload_schema) is int and payload_schema > self.SCHEMA_VERSION:
                return self._error("PLANNING_DOCUMENT_SCHEMA_UNSUPPORTED")
            if self._payload(payload, scope, allow_legacy_sales_mix=True) is None:
                return self._error("PLANNING_DOCUMENT_CORRUPT")
            return {
                "error": False,
                "document": self._document_dict(row, selected_revision, payload, revision_row["created_at"]),
            }
        except sqlite3.Error:
            return self._error("PLANNING_STORAGE_UNAVAILABLE")
        finally:
            connection.close()

    def list_documents(self, *, owner_id=None, store_id=None, include_archived=False,
                       limit=10, offset=0):
        scope = self._scope(owner_id, store_id)
        if (scope.get("error") or type(limit) is not int or not 1 <= limit <= self.MAX_PAGE_SIZE
                or type(offset) is not int or offset < 0):
            return self._error("PLANNING_LIST_REQUEST_INVALID")
        try:
            connection = self.get_connection()
        except (sqlite3.Error, OSError):
            return self._error("PLANNING_STORAGE_UNAVAILABLE")
        try:
            status_filter = "" if include_archived else " AND status='ACTIVE'"
            rows = connection.execute(
                "SELECT document_id, title, status, revision, schema_version, calculation_version, "
                "state_revision, created_at, updated_at FROM planning_documents WHERE owner_id=? AND store_id=?"
                + status_filter + " ORDER BY updated_at DESC, document_id LIMIT ? OFFSET ?",
                (scope["owner_id"], scope["store_id"], limit + 1, offset),
            ).fetchall()
            items = [dict(row) for row in rows[:limit]]
            return {"error": False, "items": items, "has_more": len(rows) > limit,
                    "next_offset": offset + limit if len(rows) > limit else None}
        except sqlite3.Error:
            return self._error("PLANNING_STORAGE_UNAVAILABLE")
        finally:
            connection.close()

    def list_revisions(self, document_id, *, owner_id=None, store_id=None):
        scope = self._scope(owner_id, store_id)
        if scope.get("error") or not isinstance(document_id, str) or not document_id:
            return self._error("PLANNING_DOCUMENT_NOT_FOUND")
        try:
            connection = self.get_connection()
        except (sqlite3.Error, OSError):
            return self._error("PLANNING_STORAGE_UNAVAILABLE")
        try:
            exists = connection.execute(
                "SELECT 1 FROM planning_documents WHERE document_id=? AND owner_id=? AND store_id=?",
                (document_id, scope["owner_id"], scope["store_id"]),
            ).fetchone()
            if exists is None:
                return self._error("PLANNING_DOCUMENT_NOT_FOUND")
            rows = connection.execute(
                "SELECT revision, created_at FROM planning_revisions "
                "WHERE document_id=? AND owner_id=? AND store_id=? ORDER BY revision DESC",
                (document_id, scope["owner_id"], scope["store_id"]),
            ).fetchall()
            return {"error": False, "items": [dict(row) for row in rows]}
        except sqlite3.Error:
            return self._error("PLANNING_STORAGE_UNAVAILABLE")
        finally:
            connection.close()

    def rename_document(self, document_id, title, *, expected_revision,
                        expected_state_revision, idempotency_key,
                        owner_id=None, store_id=None):
        return self._mutate_document(
            document_id, owner_id, store_id, expected_revision, expected_state_revision,
            idempotency_key, "rename", self._title(title),
        )

    def set_archived(self, document_id, archived, *, expected_revision,
                     expected_state_revision, idempotency_key,
                     owner_id=None, store_id=None):
        if type(archived) is not bool:
            return self._error("PLANNING_DOCUMENT_INPUT_INVALID")
        return self._mutate_document(
            document_id, owner_id, store_id, expected_revision, expected_state_revision,
            idempotency_key, "archive" if archived else "restore", None,
        )

    def delete_document(self, document_id, *, expected_revision, expected_state_revision,
                        confirmed, idempotency_key,
                        owner_id=None, store_id=None):
        if confirmed is not True:
            return self._error("PLANNING_DOCUMENT_CONFIRMATION_REQUIRED")
        return self._mutate_document(
            document_id, owner_id, store_id, expected_revision, expected_state_revision,
            idempotency_key, "delete", None,
        )

    def _mutate_document(self, document_id, owner_id, store_id, expected_revision,
                         expected_state_revision, idempotency_key, mutation, value):
        scope = self._scope(owner_id, store_id)
        key = self._idempotency_key(idempotency_key)
        if (scope.get("error") or not isinstance(document_id, str) or not document_id
                or type(expected_revision) is not int or expected_revision < 1
                or type(expected_state_revision) is not int or expected_state_revision < 1
                or mutation not in {"rename", "archive", "restore", "delete"}
                or (mutation == "rename" and value is None) or key is None):
            return self._error("PLANNING_DOCUMENT_INPUT_INVALID")
        try:
            connection = self.get_connection()
        except (sqlite3.Error, OSError):
            return self._error("PLANNING_STORAGE_UNAVAILABLE")
        try:
            connection.execute("BEGIN IMMEDIATE")
            replay = self._idempotent_result(connection, scope, key)
            if replay is not None:
                connection.commit()
                return replay
            now = self._timestamp()
            row = connection.execute(
                "SELECT revision, state_revision FROM planning_documents "
                "WHERE document_id=? AND owner_id=? AND store_id=?",
                (document_id, scope["owner_id"], scope["store_id"]),
            ).fetchone()
            if row is None:
                connection.rollback()
                return self._error("PLANNING_DOCUMENT_NOT_FOUND")
            if (row["revision"] != expected_revision
                    or row["state_revision"] != expected_state_revision):
                connection.rollback()
                return self._error("PLANNING_DOCUMENT_STATE_CONFLICT")
            if mutation == "delete":
                connection.execute("DELETE FROM planning_revisions WHERE document_id=? AND owner_id=? AND store_id=?",
                                   (document_id, scope["owner_id"], scope["store_id"]))
                changed = connection.execute(
                    "DELETE FROM planning_documents WHERE document_id=? AND owner_id=? AND store_id=? "
                    "AND revision=? AND state_revision=?",
                    (document_id, scope["owner_id"], scope["store_id"], expected_revision,
                     expected_state_revision),
                ).rowcount
            else:
                if mutation == "rename":
                    changed = connection.execute(
                        "UPDATE planning_documents SET title=?, state_revision=state_revision+1, updated_at=? "
                        "WHERE document_id=? AND owner_id=? AND store_id=? AND revision=? AND state_revision=?",
                        (value, now, document_id, scope["owner_id"], scope["store_id"],
                         expected_revision, expected_state_revision),
                    ).rowcount
                else:
                    status = "ARCHIVED" if mutation == "archive" else "ACTIVE"
                    changed = connection.execute(
                        "UPDATE planning_documents SET status=?, state_revision=state_revision+1, updated_at=? "
                        "WHERE document_id=? AND owner_id=? AND store_id=? AND revision=? AND state_revision=?",
                        (status, now, document_id, scope["owner_id"], scope["store_id"],
                         expected_revision, expected_state_revision),
                    ).rowcount
            if changed != 1:
                exists = connection.execute(
                    "SELECT 1 FROM planning_documents WHERE document_id=? AND owner_id=? AND store_id=?",
                    (document_id, scope["owner_id"], scope["store_id"]),
                ).fetchone()
                connection.rollback()
                return self._error("PLANNING_DOCUMENT_STATE_CONFLICT" if exists else "PLANNING_DOCUMENT_NOT_FOUND")
            result = {"error": False, "document_id": document_id,
                      "deleted": mutation == "delete",
                      "state_revision": None if mutation == "delete" else expected_state_revision + 1}
            self._remember_idempotency(connection, scope, key, result, now)
            connection.commit()
            return result
        except (ValueError, TypeError, OverflowError):
            connection.rollback()
            return self._error("PLANNING_CLOCK_UNAVAILABLE")
        except sqlite3.Error:
            connection.rollback()
            return self._error("PLANNING_STORAGE_UNAVAILABLE")
        finally:
            connection.close()

    def _scope(self, owner_id, store_id):
        active = str(get_current_tenant_user_id() or "").strip()
        active_owner, active_store = split_store_tenant_scope(active)
        owner = str(owner_id if owner_id is not None else active_owner or "").strip()
        store = str(store_id if store_id is not None else active_store or "").strip()
        if not active_owner or owner != active_owner or store != str(active_store or ""):
            return {"error": True, "code": "PLANNING_TENANT_SCOPE_MISMATCH"}
        return {"error": False, "owner_id": owner, "store_id": store}

    def _payload(self, payload, scope, *, allow_legacy_sales_mix=False):
        if not isinstance(payload, dict) or set(payload) - {
            "plan_kind", "items", "sales_mix", "schema_version", "calculation_version",
            "target_margin_percent",
        }:
            return None
        kind = payload.get("plan_kind")
        items = payload.get("items")
        if kind not in {"single", "batch"} or not isinstance(items, list) or not 1 <= len(items) <= 10:
            return None
        calc = payload.get("calculation_version", 1)
        schema = payload.get("schema_version", calc)
        if (type(schema) is not int or schema not in {1, 2}
                or type(calc) is not int or calc not in {1, 2}
                or schema != calc):
            return None
        normalized_items = []
        seen = set()
        for item in items:
            if not isinstance(item, dict) or set(item) - {
                "row_id", "identity", "inputs", "provenance", "sources", "projection",
            }:
                return None
            identity = item.get("identity")
            inputs = item.get("inputs")
            provenance = item.get("provenance", {})
            sources = item.get("sources", {})
            projection = item.get("projection", {})
            if (not isinstance(identity, dict) or set(identity) - self._IDENTITY_FIELDS
                    or not isinstance(inputs, dict) or set(inputs) - self._INPUT_FIELDS
                    or not isinstance(provenance, dict) or set(provenance) - self._INPUT_FIELDS
                    or not isinstance(sources, dict) or set(sources) - self._SOURCE_FIELDS
                    or not isinstance(projection, dict) or set(projection) - self._PROJECTION_FIELDS):
                return None
            sku = self._short_text(identity.get("sku"), 64)
            product_id = self._short_text(identity.get("product_id"), 80)
            offer_id = self._short_text(identity.get("offer_id"), 120)
            if not sku or not product_id or not offer_id:
                return None
            item_key = (product_id, offer_id, sku)
            if item_key in seen:
                return None
            seen.add(item_key)
            if str(identity.get("store_id") or "") != scope["store_id"]:
                return None
            clean_inputs = {}
            for field, value in inputs.items():
                if field == "tax_mode":
                    if value is None:
                        clean_inputs[field] = None
                    elif str(value).upper() in {"NONE", "USN_INCOME", "USN_INCOME_MINUS_EXPENSES"}:
                        clean_inputs[field] = str(value).upper()
                    else:
                        return None
                else:
                    clean = self._decimal_string(value, nullable=True)
                    if clean is False:
                        return None
                    clean_inputs[field] = clean
            clean_provenance = {key: self._short_text(value, 80) for key, value in provenance.items()}
            if any(value is None for value in clean_provenance.values()):
                return None
            clean_projection = {}
            for field, value in projection.items():
                if field == "status":
                    if value not in {"READY", "INCOMPLETE_INPUTS", "SOURCE_UNAVAILABLE", "SOURCE_STALE", "UNSUPPORTED_SCHEME", "TARGET_NOT_CONFIRMED", "BUDGET_EXHAUSTED"}:
                        return None
                    clean_projection[field] = value
                elif field in {"available"}:
                    if type(value) is not bool:
                        return None
                    clean_projection[field] = value
                elif field in {"missing_inputs", "invalid_inputs"}:
                    if not isinstance(value, list) or len(value) > 20 or any(not isinstance(v, str) or len(v) > 80 for v in value):
                        return None
                    clean_projection[field] = list(value)
                else:
                    clean = self._decimal_string(value, nullable=True)
                    if clean is False:
                        return None
                    clean_projection[field] = clean
            clean_sources = self._clean_sources(sources)
            if clean_sources is None:
                return None
            if calc == 1 and (
                "cross_docking_per_unit" in clean_inputs
                or "cross_docking_per_unit" in clean_provenance
                or "cross_docking" in clean_sources
                or "cross_docking" in clean_sources.get("completeness", {})
                or "cross_docking" in clean_projection
            ):
                return None
            if calc == 2:
                cross_docking = clean_sources.get("cross_docking")
                if ("cross_docking_per_unit" not in clean_inputs
                        or "cross_docking_per_unit" not in clean_provenance
                        or not isinstance(cross_docking, dict)
                        or "cross_docking" not in clean_sources.get("completeness", {})):
                    return None
                cross_docking_completeness = clean_sources["completeness"]["cross_docking"]
                if (cross_docking_completeness.get("complete") is not cross_docking.get("evidence_complete")
                        or cross_docking_completeness.get("rate_available") is not cross_docking.get("rate_available")):
                    return None
                rate = clean_inputs.get("cross_docking_per_unit")
                if cross_docking.get("rate_available") is True:
                    if (rate is None or not self._same_decimal_value(
                            rate, cross_docking.get("amount_per_unit"))
                            or cross_docking.get("evidence_complete") is not True
                            or cross_docking.get("applicable_to_sku") is not True
                            or cross_docking.get("denominator_kind") != "DELIVERED_CROSSDOCK_UNITS"):
                        return None
                elif (rate is not None or cross_docking.get("amount_per_unit") is not None
                      or cross_docking.get("applicable_to_sku") is True):
                    return None
            row_id = self._short_text(item.get("row_id"), 64, optional=True)
            normalized_items.append({
                "row_id": row_id,
                "identity": {
                    "product_id": product_id, "offer_id": offer_id, "sku": sku,
                    "product_name": self._short_text(identity.get("product_name"), 160, optional=True),
                    "store_id": scope["store_id"],
                    "scheme": self._short_text(identity.get("scheme"), 24, optional=True),
                },
                "inputs": clean_inputs,
                "provenance": clean_provenance,
                "sources": clean_sources,
                "projection": clean_projection,
            })
        if kind == "single" and len(normalized_items) != 1:
            return None
        sales_mix = payload.get("sales_mix")
        if sales_mix is not None and not self._valid_sales_mix(
            sales_mix, normalized_items, allow_legacy=allow_legacy_sales_mix,
        ):
            return None
        target = self._decimal_string(payload.get("target_margin_percent"), nullable=True)
        if target is False:
            return None
        if target is not None:
            from decimal import Decimal
            if not Decimal("0") <= Decimal(target) <= Decimal("100"):
                return None
        return {
            "plan_kind": kind, "items": normalized_items,
            "sales_mix": sales_mix,
            "schema_version": schema, "calculation_version": calc,
            "target_margin_percent": target,
        }

    @classmethod
    def _clean_sources(cls, sources):
        if set(sources) - cls._SOURCE_FIELDS:
            return None
        cleaned = {}
        periods = sources.get("periods", {})
        if not isinstance(periods, dict) or set(periods) - {
            "seller_price_as_of", "commission_rate_as_of", "tax_policy_as_of",
            "cost_as_of", "discount_points", "cross_docking",
        }:
            return None
        period_copy = {}
        for key, value in periods.items():
            if key == "cross_docking":
                if not isinstance(value, dict) or set(value) - {"from", "to", "calendar_days", "timezone"}:
                    return None
                cleaned_period = {
                    "from": cls._short_text(value.get("from"), 32, optional=True),
                    "to": cls._short_text(value.get("to"), 32, optional=True),
                    "calendar_days": value.get("calendar_days"),
                    "timezone": cls._short_text(value.get("timezone"), 40, optional=True),
                }
                if ((cleaned_period["calendar_days"] is not None
                     and (type(cleaned_period["calendar_days"]) is not int
                          or not 1 <= cleaned_period["calendar_days"] <= 366))
                        or any(value is not None and cleaned_period[key] is None
                               for key, value in (("from", value.get("from")),
                                                  ("to", value.get("to")),
                                                  ("timezone", value.get("timezone"))))):
                    return None
                period_copy[key] = cleaned_period
            elif key == "discount_points":
                if not isinstance(value, dict) or set(value) - {"from", "to", "calendar_days"}:
                    return None
                period_copy[key] = {
                    k: (v if k == "calendar_days" and type(v) is int and 1 <= v <= 366
                        else cls._short_text(v, 32))
                    for k, v in value.items()
                }
                if any(v is None for v in period_copy[key].values()):
                    return None
            else:
                period_copy[key] = cls._short_text(value, 40, optional=True)
                if value is not None and period_copy[key] is None:
                    return None
        cleaned["periods"] = period_copy
        for key in ("as_of", "loaded_at"):
            value = sources.get(key)
            if value is not None and cls._timestamp_or_date(value) is None:
                return None
            cleaned[key] = value
        completeness = sources.get("completeness", {})
        if not isinstance(completeness, dict) or set(completeness) - {
            "catalog_identity", "seller_price", "cost", "commission_rate",
            "advertising", "discount_points", "fixed_fees", "tax_policy",
            "price", "commission", "fees", "tax", "scheme", "cross_docking",
        }:
            return None
        clean_completeness = {}
        for key, value in completeness.items():
            if key == "scheme" and isinstance(value, str):
                clean_completeness[key] = cls._short_text(value, 24)
                if clean_completeness[key] is None:
                    return None
                continue
            if not isinstance(value, dict) or set(value) - {
                "complete", "status", "reason", "days_loaded", "calendar_days",
                "positive_sale_observations", "deduplicated_by", "rate_available",
            }:
                return None
            if "complete" in value and type(value["complete"]) is not bool:
                return None
            clean_completeness[key] = {
                k: (v if type(v) is bool else
                    v if type(v) is int and 0 <= v <= 1_000_000 else
                    cls._short_text(v, 80))
                for k, v in value.items()
            }
            if any(v is None for v in clean_completeness[key].values()):
                return None
        cleaned["completeness"] = clean_completeness
        if "cross_docking" in sources:
            evidence = sources.get("cross_docking")
            allowed = {
                "evidence_complete", "rate_available", "status", "reason", "method", "amount_per_unit",
                "applicable_to_sku", "denominator_kind", "expense_total", "expense_by_sku",
                "supplied_units_sku", "supplied_units_store", "days_complete", "days_expected",
                "date_from", "date_to", "as_of", "timezone", "financial_date_basis",
                "supply_date_basis", "model_version",
            }
            if not isinstance(evidence, dict) or set(evidence) != allowed:
                return None
            if (type(evidence.get("evidence_complete")) is not bool
                    or type(evidence.get("rate_available")) is not bool
                    or type(evidence.get("applicable_to_sku")) is not bool):
                return None
            method = evidence.get("method")
            if method is not None and method not in {
                "sku_accrual_cost_per_delivered_crossdock_unit",
                "store_accrual_cost_per_delivered_crossdock_unit",
            }:
                return None
            denominator = evidence.get("denominator_kind")
            if denominator is not None and denominator != "DELIVERED_CROSSDOCK_UNITS":
                return None
            safe_evidence = {}
            for key in ("evidence_complete", "rate_available", "applicable_to_sku"):
                safe_evidence[key] = evidence[key]
            for key in ("status", "reason"):
                value = evidence.get(key)
                safe_evidence[key] = cls._short_text(value, 80, optional=True)
                if value is not None and safe_evidence[key] is None:
                    return None
            for key in ("method", "denominator_kind"):
                safe_evidence[key] = evidence.get(key)
            for key in ("amount_per_unit", "expense_total", "expense_by_sku"):
                value = cls._decimal_string(evidence.get(key), nullable=True)
                if value is False or (key == "amount_per_unit" and value is not None
                                      and Decimal(value) < 0):
                    return None
                safe_evidence[key] = value
            for key in ("supplied_units_sku", "supplied_units_store", "days_complete", "days_expected", "model_version"):
                value = evidence.get(key)
                if key == "model_version" and isinstance(value, str):
                    clean_version = cls._short_text(value, 80)
                    if clean_version is None:
                        return None
                    safe_evidence[key] = clean_version
                else:
                    if value is not None and (type(value) is not int or not 0 <= value <= 1_000_000):
                        return None
                    safe_evidence[key] = value
            for key in ("date_from", "date_to", "as_of"):
                value = evidence.get(key)
                safe_evidence[key] = cls._timestamp_or_date(value) if value is not None else None
                if value is not None and safe_evidence[key] is None:
                    return None
            for key, limit in (("timezone", 40), ("financial_date_basis", 48), ("supply_date_basis", 64)):
                value = evidence.get(key)
                safe_evidence[key] = cls._short_text(value, limit, optional=True)
                if value is not None and safe_evidence[key] is None:
                    return None
            cleaned["cross_docking"] = safe_evidence
        return cleaned

    @staticmethod
    def _valid_sales_mix(value, items, *, allow_legacy=False):
        if not isinstance(value, dict) or set(value) != {"period_label", "quantities", "expenses", "confirmed"}:
            return False
        period_label = PlanningWorkspaceRepository._short_text(value.get("period_label"), 80)
        if period_label is None or type(value.get("confirmed")) is not bool:
            return False
        quantities = value.get("quantities", {})
        item_keys = {str(item.get("row_id") or item["identity"]["sku"]) for item in items}
        if not isinstance(quantities, dict) or set(quantities) != item_keys:
            return False
        quantity_total = 0
        for quantity in quantities.values():
            if quantity is not None and (
                type(quantity) is not int or quantity < 0
                or quantity > (1_000_000 if allow_legacy else
                               PlanningWorkspaceRepository.MAX_SALES_MIX_QUANTITY_PER_ITEM)
            ):
                return False
            if quantity is not None:
                quantity_total += quantity
        if (not allow_legacy
                and quantity_total > PlanningWorkspaceRepository.MAX_SALES_MIX_TOTAL_QUANTITY):
            return False
        if (not allow_legacy
                and not PlanningWorkspaceRepository._valid_sales_mix_period(period_label)):
            return False
        expenses = value.get("expenses", [])
        if not isinstance(expenses, list) or len(expenses) > (
            50 if allow_legacy else PlanningWorkspaceRepository.MAX_SALES_MIX_EXPENSES
        ):
            return False
        expense_total = Decimal("0")
        for expense in expenses:
            if not isinstance(expense, dict) or set(expense) != {"name", "amount"}:
                return False
            if not PlanningWorkspaceRepository._short_text(expense.get("name"), 80):
                return False
            amount = PlanningWorkspaceRepository._decimal_string(expense.get("amount"))
            if (amount is False or Decimal(amount) < 0
                    or (not allow_legacy and Decimal(amount) >
                        PlanningWorkspaceRepository.MAX_SALES_MIX_EXPENSE_TOTAL)):
                return False
            expense_total += Decimal(amount)
            if (not allow_legacy and expense_total >
                    PlanningWorkspaceRepository.MAX_SALES_MIX_EXPENSE_TOTAL):
                return False
        return True

    @staticmethod
    def _sales_mix_identity_scope(payload):
        if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
            return None
        scope = []
        for item in payload["items"]:
            if not isinstance(item, dict) or not isinstance(item.get("identity"), dict):
                return None
            identity = item["identity"]
            row_id = str(item.get("row_id") or identity.get("sku") or "")
            scope.append((row_id, *(str(identity.get(key) or "") for key in (
                "product_id", "offer_id", "sku", "store_id",
            ))))
        return tuple(sorted(scope))

    @staticmethod
    def _valid_sales_mix_period(value):
        match = re.fullmatch(r"\s*(.+?)\s+(?:-|—|–)\s+(.+?)\s*", value)
        if match is None:
            return False
        parsed = []
        for part in match.groups():
            try:
                parsed.append(date.fromisoformat(part))
            except ValueError:
                try:
                    parsed.append(datetime.strptime(part, "%d.%m.%Y").date())
                except ValueError:
                    return False
        return parsed[0] <= parsed[1] and (parsed[1] - parsed[0]).days + 1 <= 366

    def _initialize_schema(self, connection):
        connection.execute("BEGIN IMMEDIATE")
        try:
            schema_exists = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='planning_schema'"
            ).fetchone() is not None
            if not schema_exists:
                connection.execute(
                    "CREATE TABLE planning_schema (singleton INTEGER PRIMARY KEY CHECK(singleton=1), "
                    "version INTEGER NOT NULL)"
                )
                connection.execute(
                    "INSERT INTO planning_schema(singleton, version) VALUES (1, ?)",
                    (self.DATABASE_SCHEMA_VERSION,),
                )
                version = self.DATABASE_SCHEMA_VERSION
            else:
                columns = {
                    row[1] for row in connection.execute("PRAGMA table_info(planning_schema)")
                }
                rows = connection.execute("SELECT rowid, version FROM planning_schema").fetchall()
                versions = {row[1] for row in rows}
                if len(versions) > 1 or (
                    versions and max(versions) > self.DATABASE_SCHEMA_VERSION
                ):
                    raise sqlite3.DatabaseError("unsupported planning schema version")
                version = next(iter(versions), 1)
                if "singleton" not in columns:
                    if len(rows) > 1:
                        connection.execute(
                            "DELETE FROM planning_schema WHERE rowid NOT IN "
                            "(SELECT MIN(rowid) FROM planning_schema)"
                        )
                    connection.execute(
                        "ALTER TABLE planning_schema ADD COLUMN singleton INTEGER NOT NULL DEFAULT 1"
                    )
                connection.execute(
                    "CREATE UNIQUE INDEX IF NOT EXISTS idx_planning_schema_singleton "
                    "ON planning_schema(singleton)"
                )
                if not rows:
                    connection.execute(
                        "INSERT INTO planning_schema(singleton, version) VALUES (1, ?)",
                        (version,),
                    )

            connection.execute("""CREATE TABLE IF NOT EXISTS planning_documents (
                document_id TEXT PRIMARY KEY,
                owner_id TEXT NOT NULL,
                store_id TEXT NOT NULL,
                title TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('ACTIVE','ARCHIVED')),
                revision INTEGER NOT NULL CHECK(revision >= 1),
                state_revision INTEGER NOT NULL DEFAULT 1 CHECK(state_revision >= 1),
                schema_version INTEGER NOT NULL,
                calculation_version INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(document_id, owner_id, store_id)
            )""")
            document_columns = {
                row[1] for row in connection.execute("PRAGMA table_info(planning_documents)")
            }
            if "state_revision" not in document_columns:
                connection.execute(
                    "ALTER TABLE planning_documents ADD COLUMN state_revision INTEGER NOT NULL DEFAULT 1"
                )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_planning_documents_scope "
                "ON planning_documents(owner_id, store_id, status, updated_at)"
            )
            connection.execute("""CREATE TABLE IF NOT EXISTS planning_revisions (
                document_id TEXT NOT NULL,
                owner_id TEXT NOT NULL,
                store_id TEXT NOT NULL,
                revision INTEGER NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY(document_id, owner_id, store_id, revision),
                FOREIGN KEY(document_id, owner_id, store_id)
                    REFERENCES planning_documents(document_id, owner_id, store_id) ON DELETE CASCADE
            )""")
            connection.execute("""CREATE TABLE IF NOT EXISTS planning_idempotency (
                owner_id TEXT NOT NULL,
                store_id TEXT NOT NULL,
                idempotency_key TEXT NOT NULL,
                result_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY(owner_id, store_id, idempotency_key)
            )""")
            if version < self.DATABASE_SCHEMA_VERSION:
                connection.execute(
                    "UPDATE planning_schema SET version=? WHERE singleton=1",
                    (self.DATABASE_SCHEMA_VERSION,),
                )
            rows = connection.execute(
                "SELECT singleton, version FROM planning_schema"
            ).fetchall()
            if (len(rows) != 1 or rows[0][0] != 1
                    or rows[0][1] != self.DATABASE_SCHEMA_VERSION):
                raise sqlite3.DatabaseError("unsupported planning schema version")
            connection.commit()
        except Exception:
            connection.rollback()
            raise

    @classmethod
    def _document_dict(cls, row, revision, payload, revision_created_at):
        return {
            "document_id": row["document_id"], "owner_id": row["owner_id"],
            "store_id": row["store_id"], "title": row["title"],
            "status": row["status"], "revision": revision,
            "state_revision": row["state_revision"],
            "current_revision": row["revision"], "schema_version": row["schema_version"],
            "calculation_version": row["calculation_version"],
            "created_at": row["created_at"], "updated_at": row["updated_at"],
            "revision_created_at": revision_created_at, "payload": payload,
        }

    @staticmethod
    def _title(value):
        if not isinstance(value, str):
            return None
        title = " ".join(value.split())
        return title if 1 <= len(title) <= PlanningWorkspaceRepository._TITLE_LIMIT else None

    @staticmethod
    def _short_text(value, limit, optional=False):
        if value is None and optional:
            return None
        if not isinstance(value, (str, int)) or isinstance(value, bool):
            return None
        text = str(value).strip()
        return text if text and len(text) <= limit else None

    @staticmethod
    def _decimal_string(value, nullable=False):
        if value is None and nullable:
            return None
        if isinstance(value, bool) or value is None:
            return False
        try:
            from decimal import Decimal, InvalidOperation
            number = Decimal(str(value))
        except (InvalidOperation, ValueError, TypeError):
            return False
        if not number.is_finite() or abs(number.adjusted()) > 12 or len(number.as_tuple().digits) > 28:
            return False
        return format(number, "f")

    @classmethod
    def _same_decimal_value(cls, left, right):
        left_value = cls._decimal_string(left)
        right_value = cls._decimal_string(right)
        return (
            left_value is not False
            and right_value is not False
            and Decimal(left_value) == Decimal(right_value)
        )

    @staticmethod
    def _utc_timestamp(value):
        if not isinstance(value, str) or len(value) > 40:
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return None
        return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

    @classmethod
    def _timestamp_or_date(cls, value):
        if not isinstance(value, str):
            return None
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            try:
                return datetime.strptime(value, "%Y-%m-%d").date().isoformat()
            except ValueError:
                return None
        return cls._utc_timestamp(value)

    @classmethod
    def _idempotency_key(cls, value):
        return value if isinstance(value, str) and cls._IDEMPOTENCY_RE.fullmatch(value) else None

    def _timestamp(self):
        value = self.clock()
        if not isinstance(value, datetime) or value.tzinfo is None:
            raise ValueError("timezone-aware clock required")
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

    @staticmethod
    def _encode(value):
        try:
            return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
        except (TypeError, ValueError):
            return None

    def _idempotent_result(self, connection, scope, key):
        row = connection.execute(
            "SELECT result_json FROM planning_idempotency WHERE owner_id=? AND store_id=? AND idempotency_key=?",
            (scope["owner_id"], scope["store_id"], key),
        ).fetchone()
        if row is None:
            return None
        try:
            return json.loads(row["result_json"])
        except (ValueError, TypeError):
            return self._error("PLANNING_IDEMPOTENCY_RECORD_CORRUPT")

    def _remember_idempotency(self, connection, scope, key, result, now):
        connection.execute(
            "INSERT INTO planning_idempotency(owner_id, store_id, idempotency_key, result_json, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (scope["owner_id"], scope["store_id"], key, self._encode(result), now),
        )
        connection.execute(
            "DELETE FROM planning_idempotency WHERE owner_id=? AND store_id=? AND idempotency_key IN ("
            "SELECT idempotency_key FROM planning_idempotency WHERE owner_id=? AND store_id=? "
            "ORDER BY created_at DESC, idempotency_key DESC LIMIT -1 OFFSET 1000)",
            (scope["owner_id"], scope["store_id"], scope["owner_id"], scope["store_id"]),
        )

    @staticmethod
    def _error(code):
        return {"error": True, "code": code}
