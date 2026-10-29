"""Tenant-scoped durable storage for local unit-economics plans.

Only explicit planning inputs and historical projections are stored here.  The
repository deliberately has no dependency on Telegram, Ozon, seller settings,
or factual finance repositories.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from copy import deepcopy
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from services.ozon_account_repository import split_store_tenant_scope
from services.tenant_context import get_current_tenant_user_id
from services.tenant_storage import ensure_storage_parent, tenant_storage_path
from services.unit_price_tariff_resolver import UnitPriceTariffResolver


class PlanningWorkspaceRepository:
    SCHEMA_VERSION = 3
    DATABASE_SCHEMA_VERSION = 5
    MAX_TARIFF_PROFILES_PER_STORE = 200
    MAX_TARIFF_REVISIONS_PER_PROFILE = 20
    MAX_TARIFF_PROFILE_PAYLOAD_BYTES = 64 * 1024
    MAX_TARIFF_PAGE_SIZE = 10
    MAX_DOCUMENTS_PER_STORE = 200
    MAX_UNIT_PRICE_OBSERVATIONS_PER_STORE = 100
    MAX_UNIT_PRICE_OBSERVATION_RESULTS = 20
    MAX_UNIT_PRICE_OBSERVATION_PAYLOAD_BYTES = 64 * 1024
    MAX_UNIT_PRICE_COMPARISONS_PER_STORE = 200
    MAX_UNIT_PRICE_COMPARISON_REVISIONS = 100
    MAX_UNIT_PRICE_COMPARISON_PAYLOAD_BYTES = 64 * 1024
    MAX_UNIT_PRICE_OBSERVATION_NOTE_LENGTH = 500
    MAX_REVISIONS_PER_DOCUMENT = 20
    MAX_PAYLOAD_BYTES = 64 * 1024
    MAX_PAGE_SIZE = 10
    MAX_SALES_MIX_QUANTITY_PER_ITEM = 100_000
    MAX_SALES_MIX_TOTAL_QUANTITY = 1_000_000
    MAX_SALES_MIX_EXPENSES = 20
    MAX_SALES_MIX_EXPENSE_TOTAL = Decimal("1000000000.00")
    _TITLE_LIMIT = 80
    _IDEMPOTENCY_RE = re.compile(r"^[A-Za-z0-9_-]{8,80}$")
    _OBSERVATION_STATUSES = frozenset({"ACTIVE", "FINISHED", "ARCHIVED"})
    _OBSERVATION_RESULT_STATUSES = frozenset({
        "AVAILABLE", "INSUFFICIENT_DATA", "SOURCE_UNAVAILABLE", "STALE",
        "INCOMPARABLE", "CONFLICT", "UNSUPPORTED_SCHEME",
    })
    _OBSERVATION_EVIDENCE_BASES = frozenset({
        "SCENARIO_ASSUMPTIONS", "MODELLED_FROM_OBSERVED_INPUTS",
        "CANONICAL_FACT_COMPARABLE",
    })
    _OBSERVATION_SOURCE_NAMES = frozenset({
        "FINANCE", "ANALYTICS", "PERFORMANCE", "RETURNS", "TARIFF",
        "COST", "TAX", "OWNER_DECLARED_PRICE", "SELLER_PRICE",
    })
    _OBSERVATION_SOURCE_STATUSES = frozenset({
        "COMPLETE", "PARTIAL", "SOURCE_UNAVAILABLE", "NOT_REQUESTED",
        "STALE", "CONFLICT", "RATE_LIMITED",
    })
    _OBSERVATION_METRIC_KEYS = frozenset({
        "ordered_units", "delivered_units", "cancelled_units", "returned_units",
        "successful_sale_units", "buyout_rate_percent", "buyout_sample_size",
        "gross_seller_revenue", "net_seller_revenue", "attributed_revenue",
        "discount_points", "other_fees",
        "seller_revenue_drr_percent", "attributed_revenue_drr_percent",
        "cpc_spend", "other_ad_spend", "finance_net", "acquiring", "commission",
        "logistics", "last_mile", "cross_docking", "paid_storage", "unit_cost",
        "tax_per_unit", "profit_per_unit", "scenario_profit_per_unit",
        "observed_profit_per_unit", "price_change_count", "source_row_count",
        "duplicate_row_count", "correction_count", "sample_days",
        "successful_unit_denominator", "weighted_ad_spend_numerator",
        "revenue_basis", "date_basis", "window_start", "window_end",
        "price_evidence_status", "tariff_status", "tax_status", "unit_cost_status",
        "advertising_status",
    })
    _OBSERVATION_METRIC_FIELDS = frozenset({
        "value", "amount", "numerator", "denominator", "unit", "currency",
        "revenue_basis", "date_basis", "quantity_basis", "source", "status",
        "complete", "reason", "correction_count", "sample_count",
    })
    _OBSERVATION_COMPLETENESS_KEYS = frozenset({
        "price_history", "successful_units", "finance", "advertising", "tariff",
        "tax", "unit_cost", "returns", "analytics", "window", "deduplication",
    })
    _OBSERVATION_COMPLETENESS_STATUSES = frozenset({
        "CONFIRMED", "MANUAL_ASSUMPTION", "UNKNOWN", "STALE", "NOT_APPLICABLE",
        "PARTIAL", "SOURCE_UNAVAILABLE", "PRICE_HISTORY_UNCONFIRMED", "MIXED_PRICES",
        "CONFLICT", "INCOMPARABLE",
    })
    _OBSERVATION_FORBIDDEN_KEYS = frozenset({
        "apikey", "clientid", "authorization", "token", "password",
        "secret", "headers", "rawjson", "rawresponse",
    })
    _INPUT_FIELDS = frozenset({
        "price", "cost", "commission_rate", "advertising_rate",
        "advertising_mode", "advertising_cost_per_unit",
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
        "tariff_resolution", "advertising_basis",
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

    def create_tariff_profile(self, payload, *, idempotency_key,
                              owner_id=None, store_id=None):
        scope = self._scope(owner_id, store_id)
        key = self._idempotency_key(idempotency_key)
        normalized = self._normalize_tariff_profile_payload(payload, scope)
        if scope.get("error") or key is None or normalized is None:
            return self._error("PLANNING_TARIFF_PROFILE_INPUT_INVALID")
        try:
            connection = self.get_connection()
        except (sqlite3.Error, OSError):
            return self._error("PLANNING_STORAGE_UNAVAILABLE")
        try:
            connection.execute("BEGIN IMMEDIATE")
            replay = self._tariff_idempotent_result(connection, scope, key)
            if replay is not None:
                connection.commit()
                return replay
            count = connection.execute(
                "SELECT COUNT(*) FROM planning_tariff_profiles WHERE owner_id=? AND store_id=?",
                (scope["owner_id"], scope["store_id"]),
            ).fetchone()[0]
            if count >= self.MAX_TARIFF_PROFILES_PER_STORE:
                connection.rollback()
                return self._error("PLANNING_TARIFF_PROFILE_QUOTA_REACHED")
            now = self._timestamp()
            profile_id = uuid4().hex
            profile = {
                **normalized,
                "profile_id": profile_id,
                "owner_id": scope["owner_id"],
                "store_id": scope["store_id"],
                "revision": 1,
                "state_revision": 1,
                "origin": "MANUAL_SELLER_ASSUMPTION",
                "confirmed_by_owner": True,
                "recorded_at": now,
            }
            encoded = self._encode(profile)
            if encoded is None or len(encoded.encode("utf-8")) > self.MAX_TARIFF_PROFILE_PAYLOAD_BYTES:
                connection.rollback()
                return self._error("PLANNING_TARIFF_PROFILE_TOO_LARGE")
            connection.execute(
                """INSERT INTO planning_tariff_profiles
                   (profile_id, owner_id, store_id, product_id, offer_id, sku,
                    sale_schema, status, revision, state_revision, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, 'FBO', 'ACTIVE', 1, 1, ?, ?)""",
                (profile_id, scope["owner_id"], scope["store_id"],
                 profile["identity"]["product_id"], profile["identity"]["offer_id"],
                 profile["identity"]["sku"], now, now),
            )
            connection.execute(
                """INSERT INTO planning_tariff_profile_revisions
                   (profile_id, owner_id, store_id, revision, state_revision, payload_json, created_at)
                   VALUES (?, ?, ?, 1, 1, ?, ?)""",
                (profile_id, scope["owner_id"], scope["store_id"], encoded, now),
            )
            result = {
                "error": False, "profile_id": profile_id, "revision": 1,
                "state_revision": 1, "status": "ACTIVE", "profile": profile,
            }
            self._remember_tariff_idempotency(connection, scope, key, result, now)
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

    def update_tariff_profile(self, profile_id, payload, *, expected_revision,
                              expected_state_revision, idempotency_key,
                              owner_id=None, store_id=None):
        scope = self._scope(owner_id, store_id)
        key = self._idempotency_key(idempotency_key)
        normalized = self._normalize_tariff_profile_payload(payload, scope)
        if (scope.get("error") or not self._valid_tariff_profile_id(profile_id)
                or type(expected_revision) is not int or expected_revision < 1
                or type(expected_state_revision) is not int or expected_state_revision < 1
                or key is None or normalized is None):
            return self._error("PLANNING_TARIFF_PROFILE_INPUT_INVALID")
        try:
            connection = self.get_connection()
        except (sqlite3.Error, OSError):
            return self._error("PLANNING_STORAGE_UNAVAILABLE")
        try:
            connection.execute("BEGIN IMMEDIATE")
            replay = self._tariff_idempotent_result(connection, scope, key)
            if replay is not None:
                connection.commit()
                return replay
            row = connection.execute(
                """SELECT product_id, offer_id, sku, status, revision, state_revision
                   FROM planning_tariff_profiles
                   WHERE profile_id=? AND owner_id=? AND store_id=?""",
                (profile_id, scope["owner_id"], scope["store_id"]),
            ).fetchone()
            if row is None:
                connection.rollback()
                return self._error("PLANNING_TARIFF_PROFILE_NOT_FOUND")
            if row["status"] != "ACTIVE":
                connection.rollback()
                return self._error("PLANNING_TARIFF_PROFILE_ARCHIVED")
            if (row["revision"] != expected_revision
                    or row["state_revision"] != expected_state_revision):
                connection.rollback()
                return self._error("PLANNING_TARIFF_PROFILE_STATE_CONFLICT")
            identity = normalized["identity"]
            if (identity["product_id"] != row["product_id"]
                    or identity["offer_id"] != row["offer_id"]
                    or identity["sku"] != row["sku"]):
                connection.rollback()
                return self._error("PLANNING_TARIFF_PROFILE_IDENTITY_IMMUTABLE")
            count = connection.execute(
                """SELECT COUNT(*) FROM planning_tariff_profile_revisions
                   WHERE profile_id=? AND owner_id=? AND store_id=?""",
                (profile_id, scope["owner_id"], scope["store_id"]),
            ).fetchone()[0]
            if count >= self.MAX_TARIFF_REVISIONS_PER_PROFILE:
                connection.rollback()
                return self._error("PLANNING_TARIFF_PROFILE_REVISION_QUOTA_REACHED")
            now = self._timestamp()
            revision = expected_revision + 1
            state_revision = expected_state_revision + 1
            profile = {
                **normalized,
                "profile_id": profile_id,
                "owner_id": scope["owner_id"],
                "store_id": scope["store_id"],
                "revision": revision,
                "state_revision": state_revision,
                "origin": "MANUAL_SELLER_ASSUMPTION",
                "confirmed_by_owner": True,
                "recorded_at": now,
            }
            encoded = self._encode(profile)
            if encoded is None or len(encoded.encode("utf-8")) > self.MAX_TARIFF_PROFILE_PAYLOAD_BYTES:
                connection.rollback()
                return self._error("PLANNING_TARIFF_PROFILE_TOO_LARGE")
            changed = connection.execute(
                """UPDATE planning_tariff_profiles
                   SET revision=?, state_revision=?, updated_at=?
                   WHERE profile_id=? AND owner_id=? AND store_id=?
                     AND revision=? AND state_revision=? AND status='ACTIVE'""",
                (revision, state_revision, now, profile_id, scope["owner_id"],
                 scope["store_id"], expected_revision, expected_state_revision),
            ).rowcount
            if changed != 1:
                connection.rollback()
                return self._error("PLANNING_TARIFF_PROFILE_STATE_CONFLICT")
            connection.execute(
                """INSERT INTO planning_tariff_profile_revisions
                   (profile_id, owner_id, store_id, revision, state_revision, payload_json, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (profile_id, scope["owner_id"], scope["store_id"], revision,
                 state_revision, encoded, now),
            )
            result = {
                "error": False, "profile_id": profile_id, "revision": revision,
                "state_revision": state_revision, "status": "ACTIVE", "profile": profile,
            }
            self._remember_tariff_idempotency(connection, scope, key, result, now)
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

    def archive_tariff_profile(self, profile_id, *, expected_revision,
                               expected_state_revision, idempotency_key,
                               owner_id=None, store_id=None):
        scope = self._scope(owner_id, store_id)
        key = self._idempotency_key(idempotency_key)
        if (scope.get("error") or not self._valid_tariff_profile_id(profile_id)
                or type(expected_revision) is not int or expected_revision < 1
                or type(expected_state_revision) is not int or expected_state_revision < 1
                or key is None):
            return self._error("PLANNING_TARIFF_PROFILE_INPUT_INVALID")
        try:
            connection = self.get_connection()
        except (sqlite3.Error, OSError):
            return self._error("PLANNING_STORAGE_UNAVAILABLE")
        try:
            connection.execute("BEGIN IMMEDIATE")
            replay = self._tariff_idempotent_result(connection, scope, key)
            if replay is not None:
                connection.commit()
                return replay
            row = connection.execute(
                "SELECT status, revision, state_revision FROM planning_tariff_profiles "
                "WHERE profile_id=? AND owner_id=? AND store_id=?",
                (profile_id, scope["owner_id"], scope["store_id"]),
            ).fetchone()
            if row is None:
                connection.rollback()
                return self._error("PLANNING_TARIFF_PROFILE_NOT_FOUND")
            if (row["revision"] != expected_revision
                    or row["state_revision"] != expected_state_revision):
                connection.rollback()
                return self._error("PLANNING_TARIFF_PROFILE_STATE_CONFLICT")
            if row["status"] == "ARCHIVED":
                connection.rollback()
                return self._error("PLANNING_TARIFF_PROFILE_ARCHIVED")
            now = self._timestamp()
            next_state = expected_state_revision + 1
            changed = connection.execute(
                """UPDATE planning_tariff_profiles SET status='ARCHIVED', state_revision=?, updated_at=?
                   WHERE profile_id=? AND owner_id=? AND store_id=? AND revision=?
                     AND state_revision=? AND status='ACTIVE'""",
                (next_state, now, profile_id, scope["owner_id"], scope["store_id"],
                 expected_revision, expected_state_revision),
            ).rowcount
            if changed != 1:
                connection.rollback()
                return self._error("PLANNING_TARIFF_PROFILE_STATE_CONFLICT")
            result = {
                "error": False, "profile_id": profile_id,
                "revision": expected_revision, "state_revision": next_state,
                "status": "ARCHIVED",
            }
            self._remember_tariff_idempotency(connection, scope, key, result, now)
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

    def get_tariff_profile(self, profile_id, *, revision=None,
                           owner_id=None, store_id=None):
        scope = self._scope(owner_id, store_id)
        if (scope.get("error") or not self._valid_tariff_profile_id(profile_id)
                or (revision is not None and (type(revision) is not int or revision < 1))):
            return self._error("PLANNING_TARIFF_PROFILE_NOT_FOUND")
        try:
            connection = self.get_connection()
        except (sqlite3.Error, OSError):
            return self._error("PLANNING_STORAGE_UNAVAILABLE")
        try:
            row = connection.execute(
                """SELECT status, revision, state_revision, product_id, offer_id, sku
                   FROM planning_tariff_profiles
                   WHERE profile_id=? AND owner_id=? AND store_id=?""",
                (profile_id, scope["owner_id"], scope["store_id"]),
            ).fetchone()
            if row is None:
                return self._error("PLANNING_TARIFF_PROFILE_NOT_FOUND")
            selected_revision = row["revision"] if revision is None else revision
            revision_row = connection.execute(
                """SELECT state_revision, payload_json, created_at
                   FROM planning_tariff_profile_revisions
                   WHERE profile_id=? AND owner_id=? AND store_id=? AND revision=?""",
                (profile_id, scope["owner_id"], scope["store_id"], selected_revision),
            ).fetchone()
            if revision_row is None:
                return self._error("PLANNING_TARIFF_PROFILE_REVISION_NOT_FOUND")
            try:
                profile = json.loads(revision_row["payload_json"])
            except (ValueError, TypeError):
                return self._error("PLANNING_TARIFF_PROFILE_CORRUPT")
            if not self._stored_tariff_profile_valid(profile, scope, profile_id, selected_revision):
                return self._error("PLANNING_TARIFF_PROFILE_CORRUPT")
            selected_state_revision = (
                row["state_revision"] if revision is None else revision_row["state_revision"]
            )
            profile["state_revision"] = selected_state_revision
            return {
                "error": False, "status": row["status"], "revision": selected_revision,
                "state_revision": selected_state_revision,
                "profile": profile, "revision_created_at": revision_row["created_at"],
            }
        except sqlite3.Error:
            return self._error("PLANNING_STORAGE_UNAVAILABLE")
        finally:
            connection.close()

    def list_tariff_profiles(self, *, identity=None, include_archived=False,
                             limit=10, offset=0, owner_id=None, store_id=None):
        scope = self._scope(owner_id, store_id)
        if (scope.get("error") or type(include_archived) is not bool
                or type(limit) is not int or not 1 <= limit <= self.MAX_TARIFF_PAGE_SIZE
                or type(offset) is not int or offset < 0):
            return self._error("PLANNING_TARIFF_PROFILE_LIST_INVALID")
        filters = []
        params = [scope["owner_id"], scope["store_id"]]
        if not include_archived:
            filters.append("status='ACTIVE'")
        if identity is not None:
            if not isinstance(identity, dict) or set(identity) != {"product_id", "offer_id", "sku"}:
                return self._error("PLANNING_TARIFF_PROFILE_LIST_INVALID")
            normalized_identity = {
                key: self._short_text(value, max_len)
                for key, value, max_len in (
                    ("product_id", identity.get("product_id"), 80),
                    ("offer_id", identity.get("offer_id"), 120),
                    ("sku", identity.get("sku"), 64),
                )
            }
            if any(value is None for value in normalized_identity.values()):
                return self._error("PLANNING_TARIFF_PROFILE_LIST_INVALID")
            filters.append("product_id=? AND offer_id=? AND sku=?")
            params.extend(normalized_identity[key] for key in ("product_id", "offer_id", "sku"))
        where = " AND ".join(filters)
        if where:
            where = " AND " + where
        try:
            connection = self.get_connection()
        except (sqlite3.Error, OSError):
            return self._error("PLANNING_STORAGE_UNAVAILABLE")
        try:
            rows = connection.execute(
                """SELECT profile_id, product_id, offer_id, sku, status, revision,
                          state_revision, created_at, updated_at
                   FROM planning_tariff_profiles WHERE owner_id=? AND store_id=?"""
                + where + " ORDER BY updated_at DESC, profile_id LIMIT ? OFFSET ?",
                (*params, limit + 1, offset),
            ).fetchall()
            return {
                "error": False,
                "items": [dict(item) for item in rows[:limit]],
                "has_more": len(rows) > limit,
                "next_offset": offset + limit if len(rows) > limit else None,
            }
        except sqlite3.Error:
            return self._error("PLANNING_STORAGE_UNAVAILABLE")
        finally:
            connection.close()

    def start_unit_price_observation(
        self, *, identity, seller_price_cents, source_document_id,
        source_document_revision, effective_from, window_timezone,
        owner_confirmed, idempotency_key, note="", owner_id=None, store_id=None,
    ):
        """Start a tenant-scoped observation without copying its saved plan."""
        scope = self._scope(owner_id, store_id)
        key = self._idempotency_key(idempotency_key)
        normalized_identity = self._normalize_observation_identity(identity)
        effective = self._timestamp_preserving_offset(effective_from)
        timezone_name = self._observation_timezone(window_timezone)
        normalized_note = self._observation_note(note)
        normalized_document_id = self._short_text(source_document_id, 80)
        if (
            scope.get("error") or key is None or normalized_identity is None
            or type(seller_price_cents) is not int or seller_price_cents < 1
            or seller_price_cents > UnitPriceTariffResolver.MAX_PRICE_CENTS
            or normalized_document_id is None
            or type(source_document_revision) is not int or source_document_revision < 1
            or effective is None or owner_confirmed is not True
            or timezone_name is None or normalized_note is None
        ):
            return self._error("PLANNING_OBSERVATION_INPUT_INVALID")
        request_hash = self._observation_request_hash({
            "operation": "start", "identity": normalized_identity,
            "seller_price_cents": seller_price_cents,
            "source_document_id": normalized_document_id,
            "source_document_revision": source_document_revision,
            "effective_from": effective, "window_timezone": timezone_name,
            "owner_confirmed": owner_confirmed, "note": normalized_note,
        })
        if request_hash is None:
            return self._error("PLANNING_OBSERVATION_INPUT_INVALID")

        try:
            connection = self.get_connection()
        except (sqlite3.Error, OSError):
            return self._error("PLANNING_STORAGE_UNAVAILABLE")
        try:
            connection.execute("BEGIN IMMEDIATE")
            replay = self._observation_idempotent_result(
                connection, scope, key, request_hash,
            )
            if replay is not None:
                connection.commit()
                return replay
            now = self._timestamp()
            if datetime.fromisoformat(effective.replace("Z", "+00:00")) > datetime.fromisoformat(
                now.replace("Z", "+00:00")
            ):
                connection.rollback()
                return self._error("PLANNING_OBSERVATION_EFFECTIVE_TIME_FUTURE")
            plan = connection.execute(
                """SELECT d.status, r.payload_json FROM planning_documents d
                   JOIN planning_revisions r ON r.document_id=d.document_id
                     AND r.owner_id=d.owner_id AND r.store_id=d.store_id
                   WHERE d.document_id=? AND d.owner_id=? AND d.store_id=? AND r.revision=?""",
                (normalized_document_id, scope["owner_id"], scope["store_id"],
                 source_document_revision),
            ).fetchone()
            if plan is None:
                connection.rollback()
                return self._error("PLANNING_OBSERVATION_SOURCE_PLAN_NOT_FOUND")
            if not self._saved_plan_contains_observation_identity(
                plan["payload_json"], normalized_identity, scope["store_id"],
            ):
                connection.rollback()
                return self._error("PLANNING_OBSERVATION_SOURCE_PLAN_SCOPE_MISMATCH")
            count = connection.execute(
                "SELECT COUNT(*) FROM planning_unit_price_observations WHERE owner_id=? AND store_id=?",
                (scope["owner_id"], scope["store_id"]),
            ).fetchone()[0]
            if count >= self.MAX_UNIT_PRICE_OBSERVATIONS_PER_STORE:
                connection.rollback()
                return self._error("PLANNING_OBSERVATION_QUOTA_REACHED")
            observation_id = uuid4().hex
            connection.execute(
                """INSERT INTO planning_unit_price_observations
                   (observation_id, owner_id, store_id, product_id, offer_id, sku,
                    sale_schema, source_document_id, source_document_revision,
                    seller_price_cents, price_evidence_kind, effective_from,
                    window_timezone, status, state_revision, result_revision, note,
                    started_at, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, 'FBO', ?, ?, ?,
                           'OWNER_DECLARED_PRICE_CHANGE', ?, ?, 'ACTIVE', 1, 0, ?, ?, ?, ?)""",
                (observation_id, scope["owner_id"], scope["store_id"],
                 normalized_identity["product_id"], normalized_identity["offer_id"],
                 normalized_identity["sku"], normalized_document_id,
                 source_document_revision, seller_price_cents, effective,
                 timezone_name, normalized_note, now, now, now),
            )
            result = {
                "error": False, "observation_id": observation_id,
                "status": "ACTIVE", "state_revision": 1, "result_revision": 0,
            }
            self._remember_observation_idempotency(
                connection, scope, key, request_hash, result, now,
            )
            connection.commit()
            return result
        except sqlite3.IntegrityError:
            connection.rollback()
            return self._error("PLANNING_OBSERVATION_ALREADY_ACTIVE")
        except (ValueError, TypeError, OverflowError):
            connection.rollback()
            return self._error("PLANNING_CLOCK_UNAVAILABLE")
        except sqlite3.Error:
            connection.rollback()
            return self._error("PLANNING_STORAGE_UNAVAILABLE")
        finally:
            connection.close()

    def get_unit_price_observation(
        self, observation_id, *, result_revision=None, owner_id=None, store_id=None,
    ):
        scope = self._scope(owner_id, store_id)
        if (scope.get("error") or not isinstance(observation_id, str)
                or not observation_id.strip()
                or (result_revision is not None and (
                    type(result_revision) is not int or result_revision < 1
                ))):
            return self._error("PLANNING_OBSERVATION_NOT_FOUND")
        try:
            connection = self.get_connection()
        except (sqlite3.Error, OSError):
            return self._error("PLANNING_STORAGE_UNAVAILABLE")
        try:
            row = connection.execute(
                "SELECT * FROM planning_unit_price_observations WHERE observation_id=? "
                "AND owner_id=? AND store_id=?",
                (observation_id, scope["owner_id"], scope["store_id"]),
            ).fetchone()
            if row is None:
                return self._error("PLANNING_OBSERVATION_NOT_FOUND")
            selected_revision = (
                result_revision if result_revision is not None else row["result_revision"]
            )
            result = None
            if selected_revision:
                result_row = connection.execute(
                    "SELECT payload_json, created_at FROM planning_unit_price_observation_results "
                    "WHERE observation_id=? AND owner_id=? AND store_id=? AND result_revision=?",
                    (observation_id, scope["owner_id"], scope["store_id"], selected_revision),
                ).fetchone()
                if result_row is None:
                    return self._error("PLANNING_OBSERVATION_RESULT_NOT_FOUND")
                decoded = self._decode_observation_result(result_row["payload_json"])
                if decoded.get("error"):
                    return decoded
                if not self._observation_result_matches(
                    decoded["payload"], row, scope["store_id"],
                ):
                    return self._error("PLANNING_OBSERVATION_RESULT_IDENTITY_MISMATCH")
                result = {
                    "revision": selected_revision,
                    "created_at": result_row["created_at"],
                    "payload": decoded["payload"],
                }
            return {
                "error": False,
                "observation": self._observation_dict(row),
                "result": result,
            }
        except sqlite3.Error:
            return self._error("PLANNING_STORAGE_UNAVAILABLE")
        finally:
            connection.close()

    def list_unit_price_observations(
        self, *, include_archived=False, limit=10, offset=0,
        owner_id=None, store_id=None,
    ):
        scope = self._scope(owner_id, store_id)
        if (scope.get("error") or type(include_archived) is not bool
                or type(limit) is not int or not 1 <= limit <= self.MAX_PAGE_SIZE
                or type(offset) is not int or offset < 0):
            return self._error("PLANNING_OBSERVATION_LIST_INVALID")
        try:
            connection = self.get_connection()
        except (sqlite3.Error, OSError):
            return self._error("PLANNING_STORAGE_UNAVAILABLE")
        try:
            filter_sql = "" if include_archived else " AND status!='ARCHIVED'"
            rows = connection.execute(
                "SELECT * FROM planning_unit_price_observations WHERE owner_id=? AND store_id=?"
                + filter_sql + " ORDER BY updated_at DESC, observation_id LIMIT ? OFFSET ?",
                (scope["owner_id"], scope["store_id"], limit + 1, offset),
            ).fetchall()
            return {
                "error": False,
                "items": [self._observation_dict(row) for row in rows[:limit]],
                "has_more": len(rows) > limit,
                "next_offset": offset + limit if len(rows) > limit else None,
            }
        except sqlite3.Error:
            return self._error("PLANNING_STORAGE_UNAVAILABLE")
        finally:
            connection.close()

    def list_unit_price_observation_results(
        self, observation_id, *, limit=10, offset=0, owner_id=None, store_id=None,
    ):
        scope = self._scope(owner_id, store_id)
        if (scope.get("error") or not isinstance(observation_id, str)
                or not observation_id.strip() or type(limit) is not int
                or not 1 <= limit <= self.MAX_PAGE_SIZE or type(offset) is not int or offset < 0):
            return self._error("PLANNING_OBSERVATION_LIST_INVALID")
        try:
            connection = self.get_connection()
        except (sqlite3.Error, OSError):
            return self._error("PLANNING_STORAGE_UNAVAILABLE")
        try:
            observation = connection.execute(
                "SELECT * FROM planning_unit_price_observations WHERE observation_id=? "
                "AND owner_id=? AND store_id=?",
                (observation_id, scope["owner_id"], scope["store_id"]),
            ).fetchone()
            if observation is None:
                return self._error("PLANNING_OBSERVATION_NOT_FOUND")
            rows = connection.execute(
                "SELECT result_revision, payload_json, created_at FROM planning_unit_price_observation_results "
                "WHERE observation_id=? AND owner_id=? AND store_id=? "
                "ORDER BY result_revision DESC LIMIT ? OFFSET ?",
                (observation_id, scope["owner_id"], scope["store_id"], limit + 1, offset),
            ).fetchall()
            items = []
            for row in rows[:limit]:
                decoded = self._decode_observation_result(row["payload_json"])
                if decoded.get("error"):
                    return decoded
                if not self._observation_result_matches(
                    decoded["payload"], observation, scope["store_id"],
                ):
                    return self._error("PLANNING_OBSERVATION_RESULT_IDENTITY_MISMATCH")
                items.append({
                    "revision": row["result_revision"],
                    "created_at": row["created_at"],
                    "payload": decoded["payload"],
                })
            return {
                "error": False, "items": items, "has_more": len(rows) > limit,
                "next_offset": offset + limit if len(rows) > limit else None,
            }
        except sqlite3.Error:
            return self._error("PLANNING_STORAGE_UNAVAILABLE")
        finally:
            connection.close()

    def create_unit_price_comparison(
        self, payload, *, idempotency_key, owner_id=None, store_id=None,
    ):
        """Persist the first immutable revision of an owner-scoped comparison."""
        scope = self._scope(owner_id, store_id)
        key = self._idempotency_key(idempotency_key)
        normalized = self._normalize_unit_price_comparison(payload, scope)
        if scope.get("error") or key is None or normalized is None:
            return self._error("PLANNING_COMPARISON_INPUT_INVALID")
        fingerprint = self._observation_request_hash(normalized)
        request_hash = self._observation_request_hash({
            "operation": "create_comparison", "payload": normalized,
        })
        if fingerprint is None or request_hash is None:
            return self._error("PLANNING_COMPARISON_INPUT_INVALID")
        try:
            connection = self.get_connection()
        except (sqlite3.Error, OSError):
            return self._error("PLANNING_STORAGE_UNAVAILABLE")
        try:
            connection.execute("BEGIN IMMEDIATE")
            replay = self._comparison_idempotent_result(connection, scope, key, request_hash)
            if replay is not None:
                connection.commit()
                return replay
            count = connection.execute(
                "SELECT COUNT(DISTINCT comparison_id) FROM planning_unit_price_comparisons "
                "WHERE owner_id=? AND store_id=?",
                (scope["owner_id"], scope["store_id"]),
            ).fetchone()[0]
            if count >= self.MAX_UNIT_PRICE_COMPARISONS_PER_STORE:
                connection.rollback()
                return self._error("PLANNING_COMPARISON_QUOTA_REACHED")
            if not self._unit_price_comparison_references_exist(
                connection, scope, normalized,
            ):
                connection.rollback()
                return self._error("PLANNING_COMPARISON_SOURCE_REFERENCE_INVALID")
            comparison_id = uuid4().hex
            now = self._timestamp()
            connection.execute(
                "INSERT INTO planning_unit_price_comparisons "
                "(comparison_id, owner_id, store_id, revision, payload_json, evidence_hash, created_at) "
                "VALUES (?, ?, ?, 1, ?, ?, ?)",
                (comparison_id, scope["owner_id"], scope["store_id"],
                 self._encode(normalized), fingerprint, now),
            )
            result = {"error": False, "comparison_id": comparison_id, "revision": 1}
            self._remember_comparison_idempotency(connection, scope, key, request_hash, result, now)
            connection.commit()
            return result
        except sqlite3.IntegrityError:
            connection.rollback()
            return self._error("PLANNING_COMPARISON_CONFLICT")
        except (ValueError, TypeError, OverflowError):
            connection.rollback()
            return self._error("PLANNING_CLOCK_UNAVAILABLE")
        except sqlite3.Error:
            connection.rollback()
            return self._error("PLANNING_STORAGE_UNAVAILABLE")
        finally:
            connection.close()

    def append_unit_price_comparison_revision(
        self, comparison_id, payload, *, expected_revision, idempotency_key,
        owner_id=None, store_id=None,
    ):
        """Append refreshed comparison evidence with CAS; prior revisions remain immutable."""
        scope = self._scope(owner_id, store_id)
        key = self._idempotency_key(idempotency_key)
        normalized_id = self._short_text(comparison_id, 80)
        normalized = self._normalize_unit_price_comparison(payload, scope)
        if (scope.get("error") or key is None or normalized_id is None
                or type(expected_revision) is not int or expected_revision < 1
                or normalized is None):
            return self._error("PLANNING_COMPARISON_INPUT_INVALID")
        request_hash = self._observation_request_hash({
            "operation": "append_comparison", "comparison_id": normalized_id,
            "expected_revision": expected_revision, "payload": normalized,
        })
        fingerprint = self._observation_request_hash(normalized)
        if request_hash is None or fingerprint is None:
            return self._error("PLANNING_COMPARISON_INPUT_INVALID")
        try:
            connection = self.get_connection()
        except (sqlite3.Error, OSError):
            return self._error("PLANNING_STORAGE_UNAVAILABLE")
        try:
            connection.execute("BEGIN IMMEDIATE")
            replay = self._comparison_idempotent_result(connection, scope, key, request_hash)
            if replay is not None:
                connection.commit()
                return replay
            latest = connection.execute(
                "SELECT revision, payload_json FROM planning_unit_price_comparisons "
                "WHERE comparison_id=? AND owner_id=? AND store_id=? "
                "ORDER BY revision DESC LIMIT 1",
                (normalized_id, scope["owner_id"], scope["store_id"]),
            ).fetchone()
            if latest is None:
                connection.rollback()
                return self._error("PLANNING_COMPARISON_NOT_FOUND")
            if latest["revision"] != expected_revision:
                connection.rollback()
                return self._error("PLANNING_COMPARISON_REVISION_CONFLICT")
            try:
                previous_payload = json.loads(latest["payload_json"])
            except (TypeError, ValueError):
                connection.rollback()
                return self._error("PLANNING_COMPARISON_CORRUPT")
            previous = self._normalize_unit_price_comparison(previous_payload, scope)
            if previous is None or previous["identity"] != normalized["identity"]:
                connection.rollback()
                return self._error("PLANNING_COMPARISON_IDENTITY_CONFLICT")
            if not self._unit_price_comparison_references_exist(
                connection, scope, normalized,
            ):
                connection.rollback()
                return self._error("PLANNING_COMPARISON_SOURCE_REFERENCE_INVALID")
            if expected_revision >= self.MAX_UNIT_PRICE_COMPARISON_REVISIONS:
                connection.rollback()
                return self._error("PLANNING_COMPARISON_REVISION_QUOTA_REACHED")
            now = self._timestamp()
            revision = expected_revision + 1
            connection.execute(
                "INSERT INTO planning_unit_price_comparisons "
                "(comparison_id, owner_id, store_id, revision, payload_json, evidence_hash, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (normalized_id, scope["owner_id"], scope["store_id"], revision,
                 self._encode(normalized), fingerprint, now),
            )
            result = {"error": False, "comparison_id": normalized_id, "revision": revision}
            self._remember_comparison_idempotency(connection, scope, key, request_hash, result, now)
            connection.commit()
            return result
        except sqlite3.IntegrityError:
            connection.rollback()
            return self._error("PLANNING_COMPARISON_CONFLICT")
        except (ValueError, TypeError, OverflowError):
            connection.rollback()
            return self._error("PLANNING_CLOCK_UNAVAILABLE")
        except sqlite3.Error:
            connection.rollback()
            return self._error("PLANNING_STORAGE_UNAVAILABLE")
        finally:
            connection.close()

    def get_unit_price_comparison(
        self, comparison_id, *, revision=None, owner_id=None, store_id=None,
    ):
        scope = self._scope(owner_id, store_id)
        normalized_id = self._short_text(comparison_id, 80)
        if (scope.get("error") or normalized_id is None
                or (revision is not None and (type(revision) is not int or revision < 1))):
            return self._error("PLANNING_COMPARISON_NOT_FOUND")
        try:
            connection = self.get_connection()
        except (sqlite3.Error, OSError):
            return self._error("PLANNING_STORAGE_UNAVAILABLE")
        try:
            latest = connection.execute(
                "SELECT MAX(revision) FROM planning_unit_price_comparisons "
                "WHERE comparison_id=? AND owner_id=? AND store_id=?",
                (normalized_id, scope["owner_id"], scope["store_id"]),
            ).fetchone()[0]
            if latest is None:
                return self._error("PLANNING_COMPARISON_NOT_FOUND")
            selected = revision if revision is not None else latest
            row = connection.execute(
                "SELECT payload_json, evidence_hash, created_at FROM planning_unit_price_comparisons "
                "WHERE comparison_id=? AND owner_id=? AND store_id=? AND revision=?",
                (normalized_id, scope["owner_id"], scope["store_id"], selected),
            ).fetchone()
            if row is None:
                return self._error("PLANNING_COMPARISON_REVISION_NOT_FOUND")
            try:
                decoded = self._normalize_unit_price_comparison(
                    json.loads(row["payload_json"]), scope,
                )
            except (TypeError, ValueError):
                decoded = None
            if decoded is None or self._observation_request_hash(decoded) != row["evidence_hash"]:
                return self._error("PLANNING_COMPARISON_CORRUPT")
            return {
                "error": False, "comparison_id": normalized_id,
                "revision": selected, "latest_revision": latest,
                "superseded": selected < latest, "created_at": row["created_at"],
                "payload": decoded,
            }
        except sqlite3.Error:
            return self._error("PLANNING_STORAGE_UNAVAILABLE")
        finally:
            connection.close()

    def list_unit_price_comparisons(
        self, *, limit=10, offset=0, owner_id=None, store_id=None,
    ):
        scope = self._scope(owner_id, store_id)
        if (scope.get("error") or type(limit) is not int or not 1 <= limit <= self.MAX_PAGE_SIZE
                or type(offset) is not int or offset < 0):
            return self._error("PLANNING_COMPARISON_LIST_INVALID")
        try:
            connection = self.get_connection()
        except (sqlite3.Error, OSError):
            return self._error("PLANNING_STORAGE_UNAVAILABLE")
        try:
            rows = connection.execute(
                "SELECT c.comparison_id, c.revision, c.payload_json, c.evidence_hash, c.created_at "
                "FROM planning_unit_price_comparisons c JOIN ("
                "SELECT comparison_id, MAX(revision) AS latest_revision "
                "FROM planning_unit_price_comparisons WHERE owner_id=? AND store_id=? "
                "GROUP BY comparison_id) latest ON latest.comparison_id=c.comparison_id "
                "AND latest.latest_revision=c.revision WHERE c.owner_id=? AND c.store_id=? "
                "ORDER BY c.created_at DESC, c.comparison_id LIMIT ? OFFSET ?",
                (scope["owner_id"], scope["store_id"], scope["owner_id"],
                 scope["store_id"], limit + 1, offset),
            ).fetchall()
            items = []
            for row in rows[:limit]:
                try:
                    payload = self._normalize_unit_price_comparison(
                        json.loads(row["payload_json"]), scope,
                    )
                except (TypeError, ValueError):
                    payload = None
                if payload is None or self._observation_request_hash(payload) != row["evidence_hash"]:
                    return self._error("PLANNING_COMPARISON_CORRUPT")
                items.append({
                    "comparison_id": row["comparison_id"], "revision": row["revision"],
                    "created_at": row["created_at"], "payload": payload,
                })
            return {
                "error": False, "items": items, "has_more": len(rows) > limit,
                "next_offset": offset + limit if len(rows) > limit else None,
            }
        except sqlite3.Error:
            return self._error("PLANNING_STORAGE_UNAVAILABLE")
        finally:
            connection.close()

    def set_unit_price_observation_note(
        self, observation_id, note, *, expected_state_revision,
        idempotency_key, owner_id=None, store_id=None,
    ):
        normalized_note = self._observation_note(note)
        if normalized_note is None:
            return self._error("PLANNING_OBSERVATION_INPUT_INVALID")
        return self._mutate_unit_price_observation(
            observation_id, owner_id, store_id, expected_state_revision,
            idempotency_key, "note", normalized_note,
        )

    def finish_unit_price_observation(
        self, observation_id, *, expected_state_revision,
        idempotency_key, owner_id=None, store_id=None,
    ):
        return self._mutate_unit_price_observation(
            observation_id, owner_id, store_id, expected_state_revision,
            idempotency_key, "finish", None,
        )

    def archive_unit_price_observation(
        self, observation_id, *, expected_state_revision,
        idempotency_key, owner_id=None, store_id=None,
    ):
        return self._mutate_unit_price_observation(
            observation_id, owner_id, store_id, expected_state_revision,
            idempotency_key, "archive", None,
        )

    def _mutate_unit_price_observation(
        self, observation_id, owner_id, store_id, expected_state_revision,
        idempotency_key, mutation, value,
    ):
        scope = self._scope(owner_id, store_id)
        key = self._idempotency_key(idempotency_key)
        if (scope.get("error") or not isinstance(observation_id, str)
                or not observation_id.strip()
                or type(expected_state_revision) is not int or expected_state_revision < 1
                or mutation not in {"note", "finish", "archive"} or key is None):
            return self._error("PLANNING_OBSERVATION_INPUT_INVALID")
        request_hash = self._observation_request_hash({
            "operation": mutation, "observation_id": observation_id,
            "expected_state_revision": expected_state_revision, "value": value,
        })
        if request_hash is None:
            return self._error("PLANNING_OBSERVATION_INPUT_INVALID")
        try:
            connection = self.get_connection()
        except (sqlite3.Error, OSError):
            return self._error("PLANNING_STORAGE_UNAVAILABLE")
        try:
            connection.execute("BEGIN IMMEDIATE")
            replay = self._observation_idempotent_result(
                connection, scope, key, request_hash,
            )
            if replay is not None:
                connection.commit()
                return replay
            row = connection.execute(
                "SELECT status, state_revision FROM planning_unit_price_observations "
                "WHERE observation_id=? AND owner_id=? AND store_id=?",
                (observation_id, scope["owner_id"], scope["store_id"]),
            ).fetchone()
            if row is None:
                connection.rollback()
                return self._error("PLANNING_OBSERVATION_NOT_FOUND")
            if row["state_revision"] != expected_state_revision:
                connection.rollback()
                return self._error("PLANNING_OBSERVATION_STATE_CONFLICT")
            if row["status"] == "ARCHIVED":
                connection.rollback()
                return self._error("PLANNING_OBSERVATION_ARCHIVED")
            if mutation == "finish" and row["status"] != "ACTIVE":
                connection.rollback()
                return self._error("PLANNING_OBSERVATION_NOT_ACTIVE")
            now = self._timestamp()
            next_state = expected_state_revision + 1
            if mutation == "note":
                changed = connection.execute(
                    "UPDATE planning_unit_price_observations SET note=?, state_revision=?, updated_at=? "
                    "WHERE observation_id=? AND owner_id=? AND store_id=? AND state_revision=? "
                    "AND status IN ('ACTIVE','FINISHED')",
                    (value, next_state, now, observation_id, scope["owner_id"],
                     scope["store_id"], expected_state_revision),
                ).rowcount
                status = row["status"]
            elif mutation == "finish":
                changed = connection.execute(
                    "UPDATE planning_unit_price_observations SET status='FINISHED', finished_at=?, "
                    "state_revision=?, updated_at=? WHERE observation_id=? AND owner_id=? AND store_id=? "
                    "AND state_revision=? AND status='ACTIVE'",
                    (now, next_state, now, observation_id, scope["owner_id"],
                     scope["store_id"], expected_state_revision),
                ).rowcount
                status = "FINISHED"
            else:
                changed = connection.execute(
                    "UPDATE planning_unit_price_observations SET status='ARCHIVED', archived_at=?, "
                    "state_revision=?, updated_at=? WHERE observation_id=? AND owner_id=? AND store_id=? "
                    "AND state_revision=? AND status IN ('ACTIVE','FINISHED')",
                    (now, next_state, now, observation_id, scope["owner_id"],
                     scope["store_id"], expected_state_revision),
                ).rowcount
                status = "ARCHIVED"
            if changed != 1:
                connection.rollback()
                return self._error("PLANNING_OBSERVATION_STATE_CONFLICT")
            result = {
                "error": False, "observation_id": observation_id,
                "status": status, "state_revision": next_state,
            }
            self._remember_observation_idempotency(
                connection, scope, key, request_hash, result, now,
            )
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

    def append_unit_price_observation_result(
        self, observation_id, payload, *, expected_state_revision,
        expected_result_revision, idempotency_key, owner_id=None, store_id=None,
    ):
        scope = self._scope(owner_id, store_id)
        key = self._idempotency_key(idempotency_key)
        normalized = self._normalize_unit_price_observation_result(payload)
        encoded = self._encode(normalized) if normalized is not None else None
        if (scope.get("error") or not isinstance(observation_id, str)
                or not observation_id.strip() or key is None
                or type(expected_state_revision) is not int or expected_state_revision < 1
                or type(expected_result_revision) is not int or expected_result_revision < 0
                or encoded is None
                or len(encoded.encode("utf-8")) > self.MAX_UNIT_PRICE_OBSERVATION_PAYLOAD_BYTES):
            return self._error("PLANNING_OBSERVATION_RESULT_INVALID")
        request_hash = self._observation_request_hash({
            "operation": "append_result", "observation_id": observation_id,
            "expected_state_revision": expected_state_revision,
            "expected_result_revision": expected_result_revision,
            "payload": normalized,
        })
        if request_hash is None:
            return self._error("PLANNING_OBSERVATION_RESULT_INVALID")
        try:
            connection = self.get_connection()
        except (sqlite3.Error, OSError):
            return self._error("PLANNING_STORAGE_UNAVAILABLE")
        try:
            connection.execute("BEGIN IMMEDIATE")
            replay = self._observation_idempotent_result(
                connection, scope, key, request_hash,
            )
            if replay is not None:
                connection.commit()
                return replay
            row = connection.execute(
                "SELECT status, state_revision, result_revision, product_id, offer_id, sku, "
                "sale_schema, seller_price_cents FROM planning_unit_price_observations "
                "WHERE observation_id=? AND owner_id=? AND store_id=?",
                (observation_id, scope["owner_id"], scope["store_id"]),
            ).fetchone()
            if row is None:
                connection.rollback()
                return self._error("PLANNING_OBSERVATION_NOT_FOUND")
            if row["status"] == "ARCHIVED":
                connection.rollback()
                return self._error("PLANNING_OBSERVATION_ARCHIVED")
            if not self._observation_result_matches(payload, row, scope["store_id"]):
                connection.rollback()
                return self._error("PLANNING_OBSERVATION_RESULT_IDENTITY_MISMATCH")
            if (row["state_revision"] != expected_state_revision
                    or row["result_revision"] != expected_result_revision):
                connection.rollback()
                return self._error("PLANNING_OBSERVATION_RESULT_CONFLICT")
            if row["result_revision"] >= self.MAX_UNIT_PRICE_OBSERVATION_RESULTS:
                connection.rollback()
                return self._error("PLANNING_OBSERVATION_RESULT_QUOTA_REACHED")
            now = self._timestamp()
            revision = expected_result_revision + 1
            connection.execute(
                """INSERT INTO planning_unit_price_observation_results
                   (observation_id, owner_id, store_id, result_revision, payload_json, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (observation_id, scope["owner_id"], scope["store_id"], revision, encoded, now),
            )
            changed = connection.execute(
                "UPDATE planning_unit_price_observations SET result_revision=?, updated_at=? "
                "WHERE observation_id=? AND owner_id=? AND store_id=? AND state_revision=? "
                "AND result_revision=? AND status!='ARCHIVED'",
                (revision, now, observation_id, scope["owner_id"], scope["store_id"],
                 expected_state_revision, expected_result_revision),
            ).rowcount
            if changed != 1:
                connection.rollback()
                return self._error("PLANNING_OBSERVATION_RESULT_CONFLICT")
            result = {
                "error": False, "observation_id": observation_id,
                "result_revision": revision,
                "state_revision": expected_state_revision,
            }
            self._remember_observation_idempotency(
                connection, scope, key, request_hash, result, now,
            )
            connection.commit()
            return result
        except (ValueError, TypeError, OverflowError):
            connection.rollback()
            return self._error("PLANNING_CLOCK_UNAVAILABLE")
        except sqlite3.IntegrityError:
            connection.rollback()
            return self._error("PLANNING_STORAGE_UNAVAILABLE")
        except sqlite3.Error:
            connection.rollback()
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

    @classmethod
    def _normalize_unit_price_comparison(cls, payload, scope):
        if (scope.get("error") or not isinstance(payload, dict)
                or set(payload) != {
                    "schema_version", "identity", "ranking", "source_references",
                    "known_source_references",
                }
                or type(payload.get("schema_version")) is not int
                or payload["schema_version"] != 1
                or not isinstance(payload.get("identity"), dict)
                or not isinstance(payload.get("ranking"), dict)
                or not isinstance(payload.get("source_references"), list)
                or not 1 <= len(payload["source_references"]) <= 10
                or not isinstance(payload.get("known_source_references"), list)
                or not 1 <= len(payload["known_source_references"]) <= cls.MAX_UNIT_PRICE_OBSERVATIONS_PER_STORE):
            return None
        identity = payload["identity"]
        if (set(identity) != {"store_id", "product_id", "offer_id", "sku", "sale_schema"}
                or identity.get("store_id") != scope["store_id"]
                or identity.get("sale_schema") != "FBO"
                or any(not cls._short_text(identity.get(key), limit) for key, limit in (
                    ("store_id", 80), ("product_id", 80), ("offer_id", 120), ("sku", 64),
                ))):
            return None
        ranking = payload["ranking"]
        ranking_fields = {
            "error", "kind", "status", "evidence_basis", "verified", "baseline_index",
            "checked_candidate_count", "quality_assessment", "ranking", "best_indices",
            "best_profit_per_unit", "read_only", "executed", "recommendation_scope",
            "display_basis", "omitted_candidate_count", "omitted_repeated_price_count",
        }
        if (set(ranking) - ranking_fields or ranking.get("error") is not False
                or ranking.get("kind") != "UNIT_PRICE_OBSERVATION_RANKING"
                or ranking.get("status") not in {"RANKED", "NOT_READY", "INCOMPARABLE"}
                or (ranking.get("evidence_basis") is not None
                    and ranking.get("evidence_basis") not in cls._OBSERVATION_EVIDENCE_BASES)
                or type(ranking.get("verified")) is not bool
                or ranking.get("read_only") is not True or ranking.get("executed") is not False
                or type(ranking.get("checked_candidate_count")) is not int
                or not 1 <= ranking["checked_candidate_count"] <= 10
                or type(ranking.get("baseline_index")) is not int
                or ranking["baseline_index"] < 0
                or not isinstance(ranking.get("quality_assessment"), dict)
                or not isinstance(ranking.get("ranking"), list)
                or not isinstance(ranking.get("best_indices"), list)
                or any(type(index) is not int or index < 0 for index in ranking["best_indices"])
                or len(set(ranking["best_indices"])) != len(ranking["best_indices"])):
            return None
        quality = ranking["quality_assessment"]
        quality_fields = {
            "error", "status", "evidence_basis", "verified", "candidate_count",
            "candidates", "reasons", "warnings", "thresholds", "read_only", "executed",
        }
        if (set(quality) != quality_fields or quality.get("error") is not False
                or quality.get("status") not in {"COMPARABLE", "NOT_READY", "INCOMPARABLE"}
                or (quality.get("evidence_basis") is not None
                    and quality.get("evidence_basis") not in cls._OBSERVATION_EVIDENCE_BASES)
                or type(quality.get("verified")) is not bool
                or type(quality.get("candidate_count")) is not int
                or not isinstance(quality.get("candidates"), list)
                or not isinstance(quality.get("reasons"), list)
                or not isinstance(quality.get("warnings"), list)
                or not isinstance(quality.get("thresholds"), dict)
                or quality.get("read_only") is not True or quality.get("executed") is not False
                or len(quality["candidates"]) != ranking["checked_candidate_count"]
                or quality["candidate_count"] != len(quality["candidates"])
                or quality["status"] != ("COMPARABLE" if ranking["status"] == "RANKED"
                                          else ranking["status"])):
            return None
        if (set(quality["thresholds"]) != {
                "recommended_window_days", "small_sample_units", "max_evidence_age_days",
        } or any(type(value) is not int or value < 0 for value in quality["thresholds"].values())):
            return None
        candidate_fields = {
            "index", "result_revision", "status", "window_days", "successful_units",
            "price_cents", "evidence_age_days", "reasons", "warnings",
        }
        for item in quality["candidates"]:
            if (not isinstance(item, dict) or set(item) != candidate_fields
                    or type(item.get("index")) is not int or item["index"] < 0
                    or type(item.get("result_revision")) is not int or item["result_revision"] < 1
                    or item.get("status") not in {"READY", "INCOMPARABLE"}
                    or any(item.get(key) is not None and (
                        type(item[key]) is not int or item[key] < 0
                    ) for key in ("window_days", "successful_units", "price_cents", "evidence_age_days"))
                    or not isinstance(item.get("reasons"), list)
                    or not isinstance(item.get("warnings"), list)
                    or any(not isinstance(text, str) or len(text) > 300
                           for text in item["reasons"] + item["warnings"])):
                return None
        candidate_by_index = {item["index"]: item for item in quality["candidates"]}
        if (len(candidate_by_index) != len(quality["candidates"])
                or ranking["baseline_index"] not in candidate_by_index):
            return None
        ranking_row_fields = {
            "index", "result_revision", "seller_price_cents", "profit_per_unit",
            "delta_vs_baseline", "delta_percent_vs_baseline", "delta_percent_reason", "is_best",
        }
        if len(ranking["ranking"]) > 10:
            return None
        ranked_indices = set()
        for item in ranking["ranking"]:
            if (not isinstance(item, dict) or set(item) != ranking_row_fields
                    or type(item.get("index")) is not int
                    or type(item.get("result_revision")) is not int
                    or type(item.get("seller_price_cents")) is not int
                    or type(item.get("is_best")) is not bool
                    or item["index"] not in candidate_by_index
                    or item["result_revision"] != candidate_by_index[item["index"]]["result_revision"]
                    or item["seller_price_cents"] < 1
                    or cls._decimal_string(item.get("profit_per_unit")) is False
                    or cls._decimal_string(item.get("delta_vs_baseline")) is False
                    or (item.get("delta_percent_vs_baseline") is not None and
                        cls._decimal_string(item.get("delta_percent_vs_baseline")) is False)
                    or (item.get("delta_percent_reason") is not None and
                        not isinstance(item.get("delta_percent_reason"), str))):
                return None
            ranked_indices.add(item["index"])
        if ranking["status"] == "RANKED":
            if (len(ranked_indices) != ranking["checked_candidate_count"]
                    or not isinstance(ranking.get("best_profit_per_unit"), str)
                    or cls._decimal_string(ranking["best_profit_per_unit"]) is False
                    or set(ranking["best_indices"]) != {
                        item["index"] for item in ranking["ranking"] if item["is_best"]
                    }):
                return None
        elif ranking["ranking"] or ranking["best_indices"] or ranking.get("best_profit_per_unit") is not None:
            return None
        if len(quality["reasons"]) > 64 or len(quality["warnings"]) > 64:
            return None
        reference_fields = {
            "index", "observation_id", "result_revision", "source_document_id",
            "source_document_revision",
        }
        references = []
        seen_indices = set()
        for item in payload["source_references"]:
            if (not isinstance(item, dict) or set(item) != reference_fields
                    or type(item.get("index")) is not int or item["index"] < 0
                    or item["index"] in seen_indices
                    or not cls._short_text(item.get("observation_id"), 80)
                    or type(item.get("result_revision")) is not int or item["result_revision"] < 1
                    or not cls._short_text(item.get("source_document_id"), 80)
                    or type(item.get("source_document_revision")) is not int
                    or item["source_document_revision"] < 1):
                return None
            seen_indices.add(item["index"])
            references.append(dict(item))
        if len(references) != ranking["checked_candidate_count"]:
            return None
        if seen_indices != set(candidate_by_index):
            return None
        known_fields = {
            "observation_id", "result_revision", "source_document_id",
            "source_document_revision",
        }
        known_references = []
        known_ids = set()
        for item in payload["known_source_references"]:
            if (not isinstance(item, dict) or set(item) != known_fields
                    or not cls._short_text(item.get("observation_id"), 80)
                    or item["observation_id"] in known_ids
                    or type(item.get("result_revision")) is not int or item["result_revision"] < 1
                    or not cls._short_text(item.get("source_document_id"), 80)
                    or type(item.get("source_document_revision")) is not int
                    or item["source_document_revision"] < 1):
                return None
            known_ids.add(item["observation_id"])
            known_references.append(dict(item))
        known_by_id = {item["observation_id"]: item for item in known_references}
        if any(
            known_by_id.get(item["observation_id"], {}).get("result_revision")
                != item["result_revision"]
            or known_by_id.get(item["observation_id"], {}).get("source_document_id")
                != item["source_document_id"]
            or known_by_id.get(item["observation_id"], {}).get("source_document_revision")
                != item["source_document_revision"]
            for item in references
        ):
            return None
        if quality.get("candidate_count") != len(references):
            return None
        normalized = {
            "schema_version": 1, "identity": dict(identity),
            "ranking": cls._json_roundtrip_safe(ranking),
            "source_references": sorted(references, key=lambda item: item["index"]),
            "known_source_references": sorted(
                known_references, key=lambda item: item["observation_id"],
            ),
        }
        if normalized["ranking"] is None:
            return None
        encoded = cls._encode(normalized)
        if encoded is None or len(encoded.encode("utf-8")) > cls.MAX_UNIT_PRICE_COMPARISON_PAYLOAD_BYTES:
            return None
        return normalized

    @classmethod
    def _unit_price_comparison_references_exist(cls, connection, scope, payload):
        identity = payload.get("identity") or {}
        known = payload.get("known_source_references") or []
        for reference in known:
            observation = connection.execute(
                "SELECT * FROM planning_unit_price_observations "
                "WHERE observation_id=? AND owner_id=? AND store_id=?",
                (reference["observation_id"], scope["owner_id"], scope["store_id"]),
            ).fetchone()
            if (observation is None
                    or observation["result_revision"] < reference["result_revision"]
                    or observation["product_id"] != identity.get("product_id")
                    or observation["offer_id"] != identity.get("offer_id")
                    or observation["sku"] != identity.get("sku")
                    or observation["sale_schema"] != identity.get("sale_schema")
                    or observation["source_document_id"] != reference["source_document_id"]
                    or observation["source_document_revision"] != reference["source_document_revision"]):
                return False
            result_row = connection.execute(
                "SELECT payload_json FROM planning_unit_price_observation_results "
                "WHERE observation_id=? AND owner_id=? AND store_id=? AND result_revision=?",
                (reference["observation_id"], scope["owner_id"], scope["store_id"],
                 reference["result_revision"]),
            ).fetchone()
            if result_row is None:
                return False
            decoded = cls._decode_observation_result(result_row["payload_json"])
            if (decoded.get("error") is True or not cls._observation_result_matches(
                    decoded["payload"], observation, scope["store_id"],
            )):
                return False
            plan = connection.execute(
                "SELECT r.payload_json FROM planning_revisions r "
                "JOIN planning_documents d ON d.document_id=r.document_id "
                "AND d.owner_id=r.owner_id AND d.store_id=r.store_id "
                "WHERE r.document_id=? AND r.owner_id=? AND r.store_id=? AND r.revision=?",
                (reference["source_document_id"], scope["owner_id"], scope["store_id"],
                 reference["source_document_revision"]),
            ).fetchone()
            if (plan is None or not cls._saved_plan_contains_observation_identity(
                plan["payload_json"], {
                    "product_id": observation["product_id"],
                    "offer_id": observation["offer_id"],
                    "sku": observation["sku"],
                    "sale_schema": observation["sale_schema"],
                }, scope["store_id"],
            )):
                return False
        return True

    @classmethod
    def _json_roundtrip_safe(cls, value):
        nodes = [0]

        def visit(node, depth):
            nodes[0] += 1
            if nodes[0] > 1200 or depth > 12:
                raise ValueError("comparison payload limit")
            if node is None or type(node) in (bool, int):
                return node
            if isinstance(node, str):
                if len(node) > 1000:
                    raise ValueError("comparison text limit")
                return node
            if isinstance(node, list):
                if len(node) > 100:
                    raise ValueError("comparison list limit")
                return [visit(item, depth + 1) for item in node]
            if isinstance(node, dict):
                if len(node) > 100 or any(not isinstance(key, str) or len(key) > 100 for key in node):
                    raise ValueError("comparison object limit")
                return {key: visit(item, depth + 1) for key, item in node.items()}
            # Decimal-like metrics are serialized as strings by the ranking service;
            # binary floats are intentionally rejected.
            raise ValueError("comparison value type")

        try:
            return visit(value, 0)
        except ValueError:
            return None

    @classmethod
    def _normalize_tariff_profile_payload(cls, payload, scope):
        allowed = {
            "identity", "sale_schema", "price_basis", "currency", "origin",
            "confirmed_by_owner", "effective_from", "effective_to", "bands",
            "profile_schema_version",
        }
        required = {"identity", "sale_schema", "effective_from", "bands", "confirmed_by_owner"}
        if (scope.get("error") or not isinstance(payload, dict)
                or set(payload) - allowed or not required <= set(payload)
                or payload.get("confirmed_by_owner") is not True
                or payload.get("sale_schema") != "FBO"
                or payload.get("price_basis", "SELLER_PRICE_RUB") != "SELLER_PRICE_RUB"
                or payload.get("currency", "RUB") != "RUB"
                or payload.get("origin", "MANUAL_SELLER_ASSUMPTION") != "MANUAL_SELLER_ASSUMPTION"
                or type(payload.get("profile_schema_version", 1)) is not int
                or payload.get("profile_schema_version", 1) != 1):
            return None
        raw_identity = payload.get("identity")
        if not isinstance(raw_identity, dict) or set(raw_identity) != {"product_id", "offer_id", "sku"}:
            return None
        identity = {
            "product_id": cls._short_text(raw_identity.get("product_id"), 80),
            "offer_id": cls._short_text(raw_identity.get("offer_id"), 120),
            "sku": cls._short_text(raw_identity.get("sku"), 64),
        }
        if any(value is None for value in identity.values()):
            return None
        start = cls._date_only(payload.get("effective_from"))
        end = cls._date_only(payload.get("effective_to"), optional=True)
        if start is None or (payload.get("effective_to") is not None and end is None):
            return None
        if end is not None and end < start:
            return None
        raw_bands = payload.get("bands")
        if not isinstance(raw_bands, (list, tuple)) or not 1 <= len(raw_bands) <= UnitPriceTariffResolver.MAX_BANDS_PER_PROFILE:
            return None
        bands = []
        for band in raw_bands:
            if not isinstance(band, dict) or set(band) != {
                "price_from_cents", "price_to_cents", "commission_rate",
            }:
                return None
            lower = band.get("price_from_cents")
            upper = band.get("price_to_cents")
            rate_value = band.get("commission_rate")
            if (type(lower) is not int or type(upper) is not int
                    or not 1 <= lower <= upper <= UnitPriceTariffResolver.MAX_PRICE_CENTS
                    or isinstance(rate_value, bool)
                    or not isinstance(rate_value, (str, int, Decimal))):
                return None
            rate_text = cls._decimal_string(rate_value)
            if rate_text is False:
                return None
            rate = Decimal(rate_text)
            if (rate < 0 or rate > 100
                    or len(rate.as_tuple().digits) > UnitPriceTariffResolver.MAX_RATE_DIGITS
                    or (not rate.is_zero()
                        and rate.adjusted() < UnitPriceTariffResolver.MIN_RATE_ADJUSTED_EXPONENT)):
                return None
            bands.append({
                "price_from_cents": lower,
                "price_to_cents": upper,
                "commission_rate": "0" if rate.is_zero() else format(rate.normalize(), "f"),
            })
        bands.sort(key=lambda item: (item["price_from_cents"], item["price_to_cents"]))
        if any(previous["price_to_cents"] >= current["price_from_cents"]
               for previous, current in zip(bands, bands[1:])):
            return None
        return {
            "profile_schema_version": 1,
            "identity": identity,
            "sale_schema": "FBO",
            "price_basis": "SELLER_PRICE_RUB",
            "currency": "RUB",
            "origin": "MANUAL_SELLER_ASSUMPTION",
            "confirmed_by_owner": True,
            "effective_from": start,
            "effective_to": end,
            "bands": bands,
        }

    @staticmethod
    def _date_only(value, optional=False):
        if value is None and optional:
            return None
        if not isinstance(value, str) or len(value) != 10:
            return None
        try:
            parsed = date.fromisoformat(value)
        except ValueError:
            return None
        return parsed.isoformat() if parsed.isoformat() == value else None

    @staticmethod
    def _valid_tariff_profile_id(value):
        return isinstance(value, str) and re.fullmatch(r"[a-f0-9]{32}", value) is not None

    @classmethod
    def _stored_tariff_profile_valid(cls, profile, scope, profile_id, revision):
        if not isinstance(profile, dict):
            return False
        payload_fields = {
            "profile_schema_version", "identity", "sale_schema", "price_basis",
            "currency", "origin", "confirmed_by_owner", "effective_from",
            "effective_to", "bands",
        }
        expected_fields = payload_fields | {
            "profile_id", "owner_id", "store_id", "revision", "state_revision", "recorded_at",
        }
        if (set(profile) != expected_fields or profile.get("owner_id") != scope.get("owner_id")
                or profile.get("store_id") != scope.get("store_id")
                or profile.get("profile_id") != profile_id
                or not cls._valid_tariff_profile_id(profile_id)
                or type(profile.get("revision")) is not int or profile["revision"] != revision
                or type(profile.get("state_revision")) is not int or profile["state_revision"] < 1
                or cls._utc_timestamp(profile.get("recorded_at")) != profile.get("recorded_at")):
            return False
        payload = {key: profile[key] for key in payload_fields}
        normalized = cls._normalize_tariff_profile_payload(payload, scope)
        return (normalized is not None
                and all(profile.get(key) == value for key, value in normalized.items()))

    def _tariff_idempotent_result(self, connection, scope, key):
        row = connection.execute(
            "SELECT result_json FROM planning_tariff_profile_idempotency "
            "WHERE owner_id=? AND store_id=? AND idempotency_key=?",
            (scope["owner_id"], scope["store_id"], key),
        ).fetchone()
        if row is None:
            return None
        try:
            result = json.loads(row["result_json"])
        except (ValueError, TypeError):
            return self._error("PLANNING_TARIFF_PROFILE_IDEMPOTENCY_CORRUPT")
        return result if isinstance(result, dict) else self._error("PLANNING_TARIFF_PROFILE_IDEMPOTENCY_CORRUPT")

    def _remember_tariff_idempotency(self, connection, scope, key, result, now):
        encoded = self._encode(result)
        if encoded is None:
            raise sqlite3.IntegrityError("tariff idempotency result is not serializable")
        connection.execute(
            """INSERT INTO planning_tariff_profile_idempotency
               (owner_id, store_id, idempotency_key, result_json, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (scope["owner_id"], scope["store_id"], key, encoded, now),
        )
        connection.execute(
            """DELETE FROM planning_tariff_profile_idempotency
               WHERE owner_id=? AND store_id=? AND idempotency_key IN (
                   SELECT idempotency_key FROM planning_tariff_profile_idempotency
                   WHERE owner_id=? AND store_id=? ORDER BY created_at DESC, idempotency_key DESC
                   LIMIT -1 OFFSET 1000)""",
            (scope["owner_id"], scope["store_id"], scope["owner_id"], scope["store_id"]),
        )

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
        supported_versions = {1: 1, 2: 2, 3: 2}
        if (type(schema) is not int or schema not in supported_versions
                or type(calc) is not int or supported_versions[schema] != calc):
            return None
        if schema == 3 and kind != "single":
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
                if field in {"tax_mode", "advertising_mode"}:
                    if value is None:
                        clean_inputs[field] = None
                    elif field == "tax_mode" and str(value).upper() in {
                        "NONE", "USN_INCOME", "USN_INCOME_MINUS_EXPENSES",
                    }:
                        clean_inputs[field] = str(value).upper()
                    elif field == "advertising_mode" and str(value).upper() == "ABSOLUTE_PER_SUCCESSFUL_UNIT":
                        clean_inputs[field] = "ABSOLUTE_PER_SUCCESSFUL_UNIT"
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
            advertising_mode = clean_inputs.get("advertising_mode")
            if advertising_mode == "ABSOLUTE_PER_SUCCESSFUL_UNIT":
                if (clean_inputs.get("advertising_cost_per_unit") is None
                        or "advertising_rate" in clean_inputs
                        or clean_provenance.get("advertising_mode") is None
                        or clean_provenance.get("advertising_cost_per_unit") is None):
                    return None
            elif (advertising_mode is not None
                    or "advertising_cost_per_unit" in clean_inputs):
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
            if schema == 3:
                from services.unit_price_tariff_snapshot_adapter import UnitPriceTariffSnapshotAdapter
                tariff_resolution = clean_sources.get("tariff_resolution")
                frozen_identity = {
                    "owner_id": scope["owner_id"],
                    "store_id": scope["store_id"],
                    "product_id": product_id,
                    "offer_id": offer_id,
                    "sku": sku,
                }
                normalized_tariff = UnitPriceTariffSnapshotAdapter.validate(
                    tariff_resolution, frozen_identity, clean_inputs,
                )
                if normalized_tariff is None:
                    return None
                clean_sources["tariff_resolution"] = normalized_tariff
                advertising_basis = clean_sources.get("advertising_basis")
                if not isinstance(advertising_basis, dict):
                    return None
                if advertising_basis.get("mode") == "SAME_DRR":
                    if (set(advertising_basis) != {"mode", "revenue_basis", "rate", "origin"}
                            or advertising_basis.get("revenue_basis") != "SELLER_REVENUE"
                            or advertising_basis.get("rate") != clean_inputs.get("advertising_rate")
                            or advertising_basis.get("origin") != clean_provenance.get("advertising_rate")
                            or "advertising_mode" in clean_inputs
                            or "advertising_cost_per_unit" in clean_inputs):
                        return None
                elif advertising_basis.get("mode") == "ABSOLUTE_PER_SUCCESSFUL_UNIT":
                    if (set(advertising_basis) != {
                            "mode", "denominator", "amount_per_unit", "origin",
                        }
                            or advertising_basis.get("denominator") != "SUCCESSFUL_UNITS"
                            or advertising_basis.get("amount_per_unit")
                            != clean_inputs.get("advertising_cost_per_unit")
                            or advertising_basis.get("origin")
                            != clean_provenance.get("advertising_cost_per_unit")
                            or clean_inputs.get("advertising_mode")
                            != "ABSOLUTE_PER_SUCCESSFUL_UNIT"
                            or "advertising_rate" in clean_inputs):
                        return None
                else:
                    return None
                if (clean_sources.get("tariff_resolution", {}).get("status")
                        in UnitPriceTariffSnapshotAdapter.AVAILABLE_STATUSES
                        and clean_provenance.get("commission_rate") not in {
                            "current_price_point", "manual_seller_assumption",
                            "confirmed_official_source",
                        }):
                    return None
            elif "tariff_resolution" in clean_sources or "advertising_basis" in clean_sources:
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
        for key in ("tariff_resolution", "advertising_basis"):
            if key in sources:
                value = sources.get(key)
                if not isinstance(value, dict):
                    return None
                cleaned[key] = deepcopy(value)
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
                "financial_status", "financial_complete", "financial_days_complete",
                "financial_days_expected", "supply_status", "supply_complete",
                "supply_orders_scanned", "crossdock_supplies_seen",
                "signed_accrual_total", "signed_accrual_by_sku",
            }
            optional = {
                "financial_status", "financial_complete", "financial_days_complete",
                "financial_days_expected", "supply_status", "supply_complete",
                "supply_orders_scanned", "crossdock_supplies_seen",
                "signed_accrual_total", "signed_accrual_by_sku",
            }
            required = allowed - optional
            if (not isinstance(evidence, dict) or set(evidence) - allowed
                    or required - set(evidence)):
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
            for key in ("signed_accrual_total", "signed_accrual_by_sku"):
                if key not in evidence:
                    continue
                value = cls._decimal_string(evidence.get(key), nullable=True)
                if value is False:
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
            for key in ("financial_status", "supply_status"):
                if key not in evidence:
                    continue
                value = cls._short_text(evidence.get(key), 80, optional=True)
                if evidence.get(key) is not None and value is None:
                    return None
                safe_evidence[key] = value
            for key in ("financial_complete", "supply_complete"):
                if key not in evidence:
                    continue
                value = evidence.get(key)
                if type(value) is not bool:
                    return None
                safe_evidence[key] = value
            for key in (
                "financial_days_complete", "financial_days_expected",
                "supply_orders_scanned", "crossdock_supplies_seen",
            ):
                if key not in evidence:
                    continue
                value = evidence.get(key)
                if value is not None and (
                    type(value) is not int or not 0 <= value <= 1_000_000
                ):
                    return None
                safe_evidence[key] = value
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
            connection.execute("""CREATE TABLE IF NOT EXISTS planning_tariff_profiles (
                profile_id TEXT NOT NULL,
                owner_id TEXT NOT NULL,
                store_id TEXT NOT NULL,
                product_id TEXT NOT NULL,
                offer_id TEXT NOT NULL,
                sku TEXT NOT NULL,
                sale_schema TEXT NOT NULL CHECK(sale_schema='FBO'),
                status TEXT NOT NULL CHECK(status IN ('ACTIVE','ARCHIVED')),
                revision INTEGER NOT NULL CHECK(revision >= 1),
                state_revision INTEGER NOT NULL CHECK(state_revision >= 1),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY(profile_id, owner_id, store_id)
            )""")
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_planning_tariff_profiles_scope "
                "ON planning_tariff_profiles(owner_id, store_id, status, product_id, offer_id, sku, updated_at)"
            )
            connection.execute("""CREATE TABLE IF NOT EXISTS planning_tariff_profile_revisions (
                profile_id TEXT NOT NULL,
                owner_id TEXT NOT NULL,
                store_id TEXT NOT NULL,
                revision INTEGER NOT NULL CHECK(revision >= 1),
                state_revision INTEGER NOT NULL CHECK(state_revision >= 1),
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY(profile_id, owner_id, store_id, revision),
                FOREIGN KEY(profile_id, owner_id, store_id)
                    REFERENCES planning_tariff_profiles(profile_id, owner_id, store_id) ON DELETE CASCADE
            )""")
            connection.execute("""CREATE TABLE IF NOT EXISTS planning_tariff_profile_idempotency (
                owner_id TEXT NOT NULL,
                store_id TEXT NOT NULL,
                idempotency_key TEXT NOT NULL,
                result_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY(owner_id, store_id, idempotency_key)
            )""")
            connection.execute("""CREATE TABLE IF NOT EXISTS planning_unit_price_observations (
                observation_id TEXT NOT NULL,
                owner_id TEXT NOT NULL,
                store_id TEXT NOT NULL,
                product_id TEXT NOT NULL,
                offer_id TEXT NOT NULL,
                sku TEXT NOT NULL,
                sale_schema TEXT NOT NULL CHECK(sale_schema='FBO'),
                source_document_id TEXT NOT NULL,
                source_document_revision INTEGER NOT NULL CHECK(source_document_revision >= 1),
                seller_price_cents INTEGER NOT NULL CHECK(seller_price_cents > 0),
                price_evidence_kind TEXT NOT NULL CHECK(price_evidence_kind='OWNER_DECLARED_PRICE_CHANGE'),
                effective_from TEXT NOT NULL,
                window_timezone TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('ACTIVE','FINISHED','ARCHIVED')),
                state_revision INTEGER NOT NULL CHECK(state_revision >= 1),
                result_revision INTEGER NOT NULL DEFAULT 0 CHECK(result_revision >= 0),
                note TEXT NOT NULL DEFAULT '',
                started_at TEXT NOT NULL,
                finished_at TEXT,
                archived_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY(observation_id, owner_id, store_id)
            )""")
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_unit_price_observations_scope "
                "ON planning_unit_price_observations(owner_id, store_id, status, updated_at)"
            )
            connection.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_unit_price_observations_one_active_sku "
                "ON planning_unit_price_observations(owner_id, store_id, product_id, offer_id, sku, sale_schema) "
                "WHERE status='ACTIVE'"
            )
            connection.execute("""CREATE TABLE IF NOT EXISTS planning_unit_price_observation_results (
                observation_id TEXT NOT NULL,
                owner_id TEXT NOT NULL,
                store_id TEXT NOT NULL,
                result_revision INTEGER NOT NULL CHECK(result_revision >= 1),
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY(observation_id, owner_id, store_id, result_revision),
                FOREIGN KEY(observation_id, owner_id, store_id)
                    REFERENCES planning_unit_price_observations(observation_id, owner_id, store_id) ON DELETE CASCADE
            )""")
            connection.execute("""CREATE TABLE IF NOT EXISTS planning_unit_price_observation_idempotency (
                owner_id TEXT NOT NULL,
                store_id TEXT NOT NULL,
                idempotency_key TEXT NOT NULL,
                request_hash TEXT NOT NULL,
                result_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY(owner_id, store_id, idempotency_key)
            )""")
            connection.execute("""CREATE TABLE IF NOT EXISTS planning_unit_price_comparisons (
                comparison_id TEXT NOT NULL,
                owner_id TEXT NOT NULL,
                store_id TEXT NOT NULL,
                revision INTEGER NOT NULL CHECK(revision >= 1),
                payload_json TEXT NOT NULL,
                evidence_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY(comparison_id, owner_id, store_id, revision)
            )""")
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_unit_price_comparisons_scope "
                "ON planning_unit_price_comparisons(owner_id, store_id, created_at DESC)"
            )
            connection.execute("""CREATE TABLE IF NOT EXISTS planning_unit_price_comparison_idempotency (
                owner_id TEXT NOT NULL,
                store_id TEXT NOT NULL,
                idempotency_key TEXT NOT NULL,
                request_hash TEXT NOT NULL,
                result_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY(owner_id, store_id, idempotency_key)
            )""")
            connection.execute("""CREATE TRIGGER IF NOT EXISTS trg_unit_price_observation_results_no_update
                BEFORE UPDATE ON planning_unit_price_observation_results
                BEGIN SELECT RAISE(ABORT, 'immutable observation result'); END""")
            connection.execute("""CREATE TRIGGER IF NOT EXISTS trg_unit_price_observation_results_no_delete
                BEFORE DELETE ON planning_unit_price_observation_results
                BEGIN SELECT RAISE(ABORT, 'immutable observation result'); END""")
            connection.execute("""CREATE TRIGGER IF NOT EXISTS trg_unit_price_comparisons_no_update
                BEFORE UPDATE ON planning_unit_price_comparisons
                BEGIN SELECT RAISE(ABORT, 'immutable price comparison'); END""")
            connection.execute("""CREATE TRIGGER IF NOT EXISTS trg_unit_price_comparisons_no_delete
                BEFORE DELETE ON planning_unit_price_comparisons
                BEGIN SELECT RAISE(ABORT, 'immutable price comparison'); END""")
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

    @classmethod
    def _normalize_observation_identity(cls, identity):
        if not isinstance(identity, dict) or set(identity) != {
            "product_id", "offer_id", "sku", "sale_schema",
        } or identity.get("sale_schema") != "FBO":
            return None
        result = {
            "product_id": cls._short_text(identity.get("product_id"), 80),
            "offer_id": cls._short_text(identity.get("offer_id"), 120),
            "sku": cls._short_text(identity.get("sku"), 64),
            "sale_schema": "FBO",
        }
        return result if all(result.get(key) for key in result) else None

    @staticmethod
    def _observation_timezone(value):
        if not isinstance(value, str) or not value or len(value) > 64:
            return None
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError, TypeError):
            return None
        return value

    @classmethod
    def _observation_note(cls, value):
        if not isinstance(value, str) or "\x00" in value:
            return None
        normalized = " ".join(value.split())
        return normalized if len(normalized) <= cls.MAX_UNIT_PRICE_OBSERVATION_NOTE_LENGTH else None

    @staticmethod
    def _saved_plan_contains_observation_identity(
        payload_json, identity, store_id,
    ):
        try:
            payload = json.loads(payload_json)
        except (ValueError, TypeError):
            return False
        items = payload.get("items") if isinstance(payload, dict) else None
        if not isinstance(items, list):
            return False
        for item in items:
            if not isinstance(item, dict):
                continue
            item_identity = item.get("identity")
            product = item.get("product")
            if not isinstance(item_identity, dict):
                continue
            item_scheme = item_identity.get("scheme")
            if item_scheme is None and isinstance(product, dict):
                item_scheme = product.get("scheme")
            if (
                str(item_identity.get("product_id") or "") == identity["product_id"]
                and str(item_identity.get("offer_id") or "") == identity["offer_id"]
                and str(item_identity.get("sku") or "") == identity["sku"]
                and str(item_identity.get("store_id") or "") == store_id
                and str(item_scheme or "").upper() == identity["sale_schema"]
            ):
                return True
        return False

    @classmethod
    def _normalize_unit_price_observation_result(cls, payload):
        allowed = {
            "schema_version", "identity", "seller_price_cents", "status",
            "evidence_basis", "window",
            "sources", "metrics", "completeness", "reasons", "warnings",
        }
        if (not isinstance(payload, dict) or set(payload) != allowed
                or type(payload.get("schema_version")) is not int
                or payload.get("schema_version") != 1
                or not isinstance(payload.get("identity"), dict)
                or type(payload.get("seller_price_cents")) is not int
                or payload.get("seller_price_cents") < 1
                or payload.get("seller_price_cents") > UnitPriceTariffResolver.MAX_PRICE_CENTS
                or not isinstance(payload.get("status"), str)
                or payload.get("status") not in cls._OBSERVATION_RESULT_STATUSES
                or not isinstance(payload.get("evidence_basis"), str)
                or payload.get("evidence_basis") not in cls._OBSERVATION_EVIDENCE_BASES
                or not isinstance(payload.get("window"), dict)
                or not isinstance(payload.get("sources"), list)
                or len(payload["sources"]) > 20
                or not isinstance(payload.get("metrics"), dict)
                or not isinstance(payload.get("completeness"), dict)
                or not isinstance(payload.get("reasons"), list)
                or not isinstance(payload.get("warnings"), list)
                or len(payload["reasons"]) > 32 or len(payload["warnings"]) > 32):
            return None
        identity = payload["identity"]
        if (set(identity) != {"store_id", "product_id", "offer_id", "sku", "sale_schema"}
                or any(not cls._short_text(identity.get(key), limit) for key, limit in (
                    ("store_id", 80), ("product_id", 80), ("offer_id", 120),
                    ("sku", 64),
                ))
                or identity.get("sale_schema") != "FBO"):
            return None
        if any(not cls._valid_observation_source(item) for item in payload["sources"]):
            return None
        if any(
            key not in cls._OBSERVATION_METRIC_KEYS
            or not cls._valid_observation_metric_value(value)
            for key, value in payload["metrics"].items()
        ):
            return None
        if any(
            key not in cls._OBSERVATION_COMPLETENESS_KEYS
            or not cls._valid_observation_completeness(value)
            for key, value in payload["completeness"].items()
        ):
            return None
        window = payload["window"]
        if set(window) != {"from", "to", "timezone", "date_basis"}:
            return None
        if (not isinstance(window.get("from"), str)
                or not isinstance(window.get("to"), str)
                or not isinstance(window.get("date_basis"), str)):
            return None
        try:
            start = date.fromisoformat(window["from"])
            end = date.fromisoformat(window["to"])
        except (TypeError, ValueError):
            return None
        if (end < start or (end - start).days >= 56
                or cls._observation_timezone(window["timezone"]) is None
                or window["date_basis"] not in {
                    "LOCAL_CALENDAR_DATE", "SOURCE_CALENDAR_DATE", "UTC_DATE",
                }):
            return None
        for message_list in (payload["reasons"], payload["warnings"]):
            if any(not isinstance(item, str) or len(item) > 300 for item in message_list):
                return None
        nodes = [0]
        if not cls._observation_result_json_safe(payload, 0, nodes):
            return None
        # Return a JSON-round-tripped copy so caller-owned nested values cannot be
        # mutated after validation or affect the immutable stored revision.
        encoded = cls._encode(payload)
        if encoded is None or len(encoded.encode("utf-8")) > cls.MAX_UNIT_PRICE_OBSERVATION_PAYLOAD_BYTES:
            return None
        try:
            return json.loads(encoded)
        except (TypeError, ValueError):
            return None

    @classmethod
    def _valid_observation_source(cls, source):
        allowed = {
            "name", "status", "complete", "row_count", "requested_at", "received_at",
            "as_of", "source_date_basis", "source_window_start", "source_window_end",
            "timezone", "correction_revision", "reason", "unknown_field_count",
            "unknown_fields", "unsupported_types",
        }
        if (not isinstance(source, dict) or not set(source).issubset(allowed)
                or not {"name", "status", "complete"}.issubset(source)
                or not isinstance(source.get("name"), str)
                or source["name"].upper() not in cls._OBSERVATION_SOURCE_NAMES
                or not isinstance(source.get("status"), str)
                or source["status"] not in cls._OBSERVATION_SOURCE_STATUSES
                or type(source.get("complete")) is not bool):
            return False
        for key in ("row_count", "correction_revision", "unknown_field_count"):
            if key in source and (type(source[key]) is not int or source[key] < 0
                                  or source[key] > 10**9):
                return False
        for key in ("requested_at", "received_at", "as_of"):
            if key in source and source[key] is not None and (
                not isinstance(source[key], str) or cls._timestamp_or_date(source[key]) is None
            ):
                return False
        for key in ("source_date_basis", "source_window_start", "source_window_end"):
            if key in source and source[key] is not None and not isinstance(source[key], str):
                return False
        if ("timezone" in source and source["timezone"] is not None
                and cls._observation_timezone(source["timezone"]) is None):
            return False
        if "reason" in source and (
            not isinstance(source["reason"], str) or len(source["reason"]) > 300
        ):
            return False
        if "unsupported_types" in source and (
            not isinstance(source["unsupported_types"], list)
            or len(source["unsupported_types"]) > 50
            or any(not isinstance(item, str) or len(item) > 80
                   for item in source["unsupported_types"])
        ):
            return False
        if "unknown_fields" in source and (
            not isinstance(source["unknown_fields"], list)
            or len(source["unknown_fields"]) > 50
            or any(
                not isinstance(item, dict)
                or set(item) != {"name", "type"}
                or not isinstance(item.get("name"), str)
                or not item["name"]
                or len(item["name"]) > 80
                or not isinstance(item.get("type"), str)
                or item["type"] not in {
                    "null", "bool", "int", "decimal", "float", "string",
                    "object", "array", "unknown",
                }
                for item in source["unknown_fields"]
            )
        ):
            return False
        return True

    @classmethod
    def _valid_observation_completeness(cls, value):
        if isinstance(value, str):
            return value in cls._OBSERVATION_COMPLETENESS_STATUSES
        if not isinstance(value, dict) or not set(value).issubset({"status", "origin", "reason"}):
            return False
        return (
            isinstance(value.get("status"), str)
            and value["status"] in cls._OBSERVATION_COMPLETENESS_STATUSES
            and ("origin" not in value or isinstance(value["origin"], str))
            and ("reason" not in value or (
                isinstance(value["reason"], str) and len(value["reason"]) <= 300
            ))
        )

    @classmethod
    def _valid_observation_metric_value(cls, value):
        if value is None or type(value) in (bool, int) or isinstance(value, str):
            return True
        if not isinstance(value, dict) or not set(value).issubset(cls._OBSERVATION_METRIC_FIELDS):
            return False
        return all(
            item is None or type(item) in (bool, int) or isinstance(item, str)
            for item in value.values()
        )

    @classmethod
    def _observation_result_matches(cls, payload, observation_row, store_id):
        identity = payload.get("identity") if isinstance(payload, dict) else None
        if not isinstance(identity, dict):
            return False
        return (
            identity.get("store_id") == store_id
            and identity.get("product_id") == observation_row["product_id"]
            and identity.get("offer_id") == observation_row["offer_id"]
            and identity.get("sku") == observation_row["sku"]
            and identity.get("sale_schema") == observation_row["sale_schema"]
            and payload.get("seller_price_cents") == observation_row["seller_price_cents"]
        )

    @classmethod
    def _observation_result_json_safe(cls, value, depth, nodes):
        nodes[0] += 1
        if depth > 8 or nodes[0] > 2000:
            return False
        if value is None or type(value) in (bool, int):
            return not (type(value) is int and abs(value) > 10**15)
        if isinstance(value, str):
            return len(value) <= 4096 and "\x00" not in value
        if isinstance(value, list):
            return len(value) <= 200 and all(
                cls._observation_result_json_safe(item, depth + 1, nodes)
                for item in value
            )
        if isinstance(value, dict):
            if len(value) > 100:
                return False
            for key, item in value.items():
                if not isinstance(key, str) or not key or len(key) > 80:
                    return False
                normalized_key = re.sub(r"[^a-z0-9]", "", key.casefold())
                if normalized_key in cls._OBSERVATION_FORBIDDEN_KEYS:
                    return False
                if not cls._observation_result_json_safe(item, depth + 1, nodes):
                    return False
            return True
        # Money and rates are serialized as decimal strings; floats are forbidden.
        return False

    @classmethod
    def _decode_observation_result(cls, payload_json):
        try:
            payload = json.loads(payload_json)
        except (TypeError, ValueError):
            return cls._error("PLANNING_OBSERVATION_RESULT_CORRUPT")
        if isinstance(payload, dict) and type(payload.get("schema_version")) is int:
            if payload["schema_version"] > 1:
                return cls._error("PLANNING_OBSERVATION_RESULT_VERSION_UNSUPPORTED")
        normalized = cls._normalize_unit_price_observation_result(payload)
        if normalized is None:
            return cls._error("PLANNING_OBSERVATION_RESULT_CORRUPT")
        return {"error": False, "payload": normalized}

    @staticmethod
    def _observation_dict(row):
        return {
            "observation_id": row["observation_id"],
            "store_id": row["store_id"],
            "identity": {
                "product_id": row["product_id"], "offer_id": row["offer_id"],
                "sku": row["sku"], "sale_schema": row["sale_schema"],
            },
            "source_plan": {
                "document_id": row["source_document_id"],
                "revision": row["source_document_revision"],
            },
            "seller_price_cents": row["seller_price_cents"],
            "price_evidence_kind": row["price_evidence_kind"],
            "effective_from": row["effective_from"],
            "window_timezone": row["window_timezone"],
            "recorded_at": row["started_at"],
            "price_evidence_source": "USER",
            "status": row["status"],
            "state_revision": row["state_revision"],
            "result_revision": row["result_revision"],
            "note": row["note"],
            "started_at": row["started_at"],
            "finished_at": row["finished_at"],
            "archived_at": row["archived_at"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    @staticmethod
    def _observation_request_hash(request):
        encoded = PlanningWorkspaceRepository._encode(request)
        if encoded is None:
            return None
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    @staticmethod
    def _observation_idempotent_result(connection, scope, key, request_hash):
        row = connection.execute(
            "SELECT request_hash, result_json FROM planning_unit_price_observation_idempotency "
            "WHERE owner_id=? AND store_id=? AND idempotency_key=?",
            (scope["owner_id"], scope["store_id"], key),
        ).fetchone()
        if row is None:
            return None
        if row["request_hash"] != request_hash:
            return PlanningWorkspaceRepository._error(
                "PLANNING_OBSERVATION_IDEMPOTENCY_CONFLICT"
            )
        try:
            result = json.loads(row["result_json"])
        except (TypeError, ValueError):
            return PlanningWorkspaceRepository._error(
                "PLANNING_OBSERVATION_IDEMPOTENCY_RECORD_CORRUPT"
            )
        if not isinstance(result, dict) or type(result.get("error")) is not bool:
            return PlanningWorkspaceRepository._error(
                "PLANNING_OBSERVATION_IDEMPOTENCY_RECORD_CORRUPT"
            )
        return result

    @staticmethod
    def _remember_observation_idempotency(connection, scope, key, request_hash, result, now):
        connection.execute(
            "INSERT INTO planning_unit_price_observation_idempotency "
            "(owner_id, store_id, idempotency_key, request_hash, result_json, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (scope["owner_id"], scope["store_id"], key, request_hash,
             PlanningWorkspaceRepository._encode(result), now),
        )
        connection.execute(
            """DELETE FROM planning_unit_price_observation_idempotency
               WHERE owner_id=? AND store_id=? AND idempotency_key IN (
                 SELECT idempotency_key FROM planning_unit_price_observation_idempotency
                 WHERE owner_id=? AND store_id=? ORDER BY created_at DESC, idempotency_key DESC
                 LIMIT -1 OFFSET 1000)""",
            (scope["owner_id"], scope["store_id"], scope["owner_id"], scope["store_id"]),
        )

    @staticmethod
    def _comparison_idempotent_result(connection, scope, key, request_hash):
        row = connection.execute(
            "SELECT request_hash, result_json FROM planning_unit_price_comparison_idempotency "
            "WHERE owner_id=? AND store_id=? AND idempotency_key=?",
            (scope["owner_id"], scope["store_id"], key),
        ).fetchone()
        if row is None:
            return None
        if row["request_hash"] != request_hash:
            return PlanningWorkspaceRepository._error(
                "PLANNING_COMPARISON_IDEMPOTENCY_CONFLICT"
            )
        try:
            result = json.loads(row["result_json"])
        except (TypeError, ValueError):
            return PlanningWorkspaceRepository._error(
                "PLANNING_COMPARISON_IDEMPOTENCY_RECORD_CORRUPT"
            )
        if not isinstance(result, dict) or type(result.get("error")) is not bool:
            return PlanningWorkspaceRepository._error(
                "PLANNING_COMPARISON_IDEMPOTENCY_RECORD_CORRUPT"
            )
        return result

    @staticmethod
    def _remember_comparison_idempotency(connection, scope, key, request_hash, result, now):
        connection.execute(
            "INSERT INTO planning_unit_price_comparison_idempotency "
            "(owner_id, store_id, idempotency_key, request_hash, result_json, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (scope["owner_id"], scope["store_id"], key, request_hash,
             PlanningWorkspaceRepository._encode(result), now),
        )
        connection.execute(
            """DELETE FROM planning_unit_price_comparison_idempotency
               WHERE owner_id=? AND store_id=? AND idempotency_key IN (
                 SELECT idempotency_key FROM planning_unit_price_comparison_idempotency
                 WHERE owner_id=? AND store_id=? ORDER BY created_at DESC, idempotency_key DESC
                 LIMIT -1 OFFSET 1000)""",
            (scope["owner_id"], scope["store_id"], scope["owner_id"], scope["store_id"]),
        )

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

    @staticmethod
    def _timestamp_preserving_offset(value):
        if not isinstance(value, str) or len(value) > 40:
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return None
        return parsed.isoformat()

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
