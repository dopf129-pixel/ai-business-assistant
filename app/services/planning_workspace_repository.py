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
from decimal import Decimal, InvalidOperation
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from services.ozon_account_repository import split_store_tenant_scope
from services.tenant_context import get_current_tenant_user_id
from services.tenant_storage import ensure_storage_parent, tenant_storage_path
from services.unit_price_tariff_resolver import UnitPriceTariffResolver
from services.planning_unit_economics_experiment_adapter import (
    PlanningUnitEconomicsExperimentAdapter,
)
from services.unit_economics_experiment_state_machine import (
    UnitEconomicsExperimentStateMachine,
)
from services.unit_economics_experiment_plan_service import (
    UnitEconomicsExperimentPlanService,
)
from services.unit_economics_experiment_phase_confirmation_service import (
    UnitEconomicsExperimentPhaseConfirmationService,
)
from services.unit_economics_experiment_control_service import (
    UnitEconomicsExperimentControlService,
)


class PlanningWorkspaceRepository:
    SCHEMA_VERSION = 4
    DATABASE_SCHEMA_VERSION = 12
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
    MAX_UNIT_ECONOMICS_SNAPSHOTS_PER_STORE = 1000
    MAX_PRICE_EXPERIMENTS_PER_STORE = 100
    MAX_PRICE_EXPERIMENT_PHASES = 10
    MAX_PRICE_EXPERIMENT_RESULTS_PER_PHASE = 20
    MAX_PRICE_EXPERIMENT_DECISIONS = 100
    MAX_PRICE_EXPERIMENT_COLLECTIONS_PER_PHASE = 20
    MAX_PRICE_EXPERIMENT_PAYLOAD_BYTES = 64 * 1024
    MAX_PRICE_EXPERIMENT_IDEMPOTENCY_PER_STORE = 1000
    MAX_PRICE_EXPERIMENT_EVENTS = 100
    MAX_PRICE_EXPERIMENT_EVENT_PAYLOAD_BYTES = 64 * 1024
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
        "extended_cost_mode", "extended_cost_origin", "extended_cost_signature",
        "extended_cost_per_unit",
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
        "margin_percent", "cross_docking", "additional_unit_expenses",
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
            if not self._claim_active_sku_guard(
                connection, scope, normalized_identity, "OBSERVATION", observation_id, now,
            ):
                guard = connection.execute(
                    "SELECT operation_kind FROM planning_active_sku_guards "
                    "WHERE owner_id=? AND store_id=? AND product_id=? AND offer_id=? "
                    "AND sku=? AND sale_schema=?",
                    self._active_guard_identity(scope, normalized_identity),
                ).fetchone()
                connection.rollback()
                if guard is not None and guard["operation_kind"] == "EXPERIMENT":
                    return self._error("PLANNING_PRICE_EXPERIMENT_ALREADY_ACTIVE")
                if guard is not None and guard["operation_kind"] == "CONFLICT":
                    return self._error("PLANNING_ACTIVE_SKU_GUARD_CONFLICT")
                return self._error("PLANNING_OBSERVATION_ALREADY_ACTIVE")
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
                "SELECT status, state_revision, product_id, offer_id, sku, sale_schema "
                "FROM planning_unit_price_observations "
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
            if mutation in {"finish", "archive"}:
                self._sync_active_sku_guard(connection, scope, {
                    key: row[key] for key in ("product_id", "offer_id", "sku", "sale_schema")
                })
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

    def create_unit_economics_expense_snapshot(
        self, payload, *, owner_id=None, store_id=None,
    ):
        """Persist an immutable normalized expense projection by content hash."""
        scope = self._scope(owner_id, store_id)
        normalized = PlanningUnitEconomicsExperimentAdapter.normalize_expense_snapshot(
            payload, scope,
        )
        if scope.get("error") or normalized is None:
            return self._error("PLANNING_EXPENSE_SNAPSHOT_INVALID")
        encoded = self._encode(normalized)
        if (encoded is None or len(encoded.encode("utf-8"))
                > self.MAX_PRICE_EXPERIMENT_PAYLOAD_BYTES):
            return self._error("PLANNING_EXPENSE_SNAPSHOT_TOO_LARGE")
        snapshot_id = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
        identity = normalized["identity"]
        try:
            connection = self.get_connection()
        except (sqlite3.Error, OSError):
            return self._error("PLANNING_STORAGE_UNAVAILABLE")
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT payload_json FROM planning_unit_economics_snapshots "
                "WHERE snapshot_id=? AND owner_id=? AND store_id=?",
                (snapshot_id, scope["owner_id"], scope["store_id"]),
            ).fetchone()
            if existing is not None:
                if existing["payload_json"] != encoded:
                    connection.rollback()
                    return self._error("PLANNING_EXPENSE_SNAPSHOT_HASH_CONFLICT")
                connection.commit()
                return {
                    "error": False, "snapshot_id": snapshot_id,
                    "schema_version": normalized["schema_version"], "created": False,
                }
            count = connection.execute(
                "SELECT COUNT(*) FROM planning_unit_economics_snapshots "
                "WHERE owner_id=? AND store_id=?",
                (scope["owner_id"], scope["store_id"]),
            ).fetchone()[0]
            if count >= self.MAX_UNIT_ECONOMICS_SNAPSHOTS_PER_STORE:
                connection.rollback()
                return self._error("PLANNING_EXPENSE_SNAPSHOT_QUOTA_REACHED")
            now = self._timestamp()
            connection.execute(
                """INSERT INTO planning_unit_economics_snapshots
                   (snapshot_id, owner_id, store_id, product_id, offer_id, sku,
                    sale_schema, schema_version, payload_json, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (snapshot_id, scope["owner_id"], scope["store_id"],
                 identity["product_id"], identity["offer_id"], identity["sku"],
                 identity["sale_schema"], normalized["schema_version"], encoded, now),
            )
            connection.commit()
            return {
                "error": False, "snapshot_id": snapshot_id,
                "schema_version": normalized["schema_version"], "created": True,
            }
        except (ValueError, TypeError, OverflowError):
            connection.rollback()
            return self._error("PLANNING_CLOCK_UNAVAILABLE")
        except sqlite3.Error:
            connection.rollback()
            return self._error("PLANNING_STORAGE_UNAVAILABLE")
        finally:
            connection.close()

    def get_unit_economics_expense_snapshot(
        self, snapshot_id, *, owner_id=None, store_id=None,
    ):
        scope = self._scope(owner_id, store_id)
        if (scope.get("error") or not isinstance(snapshot_id, str)
                or PlanningUnitEconomicsExperimentAdapter._HEX_256.fullmatch(snapshot_id) is None):
            return self._error("PLANNING_EXPENSE_SNAPSHOT_NOT_FOUND")
        try:
            connection = self.get_connection()
        except (sqlite3.Error, OSError):
            return self._error("PLANNING_STORAGE_UNAVAILABLE")
        try:
            row = connection.execute(
                "SELECT payload_json, schema_version, created_at "
                "FROM planning_unit_economics_snapshots "
                "WHERE snapshot_id=? AND owner_id=? AND store_id=?",
                (snapshot_id, scope["owner_id"], scope["store_id"]),
            ).fetchone()
            if row is None:
                return self._error("PLANNING_EXPENSE_SNAPSHOT_NOT_FOUND")
            try:
                payload = json.loads(row["payload_json"])
            except (ValueError, TypeError):
                return self._error("PLANNING_EXPENSE_SNAPSHOT_CORRUPT")
            normalized = PlanningUnitEconomicsExperimentAdapter.normalize_expense_snapshot(
                payload, scope,
            )
            digest = hashlib.sha256(row["payload_json"].encode("utf-8")).hexdigest()
            if (normalized is None or digest != snapshot_id
                    or row["schema_version"] != normalized["schema_version"]):
                return self._error("PLANNING_EXPENSE_SNAPSHOT_CORRUPT")
            return {
                "error": False, "snapshot_id": snapshot_id,
                "schema_version": row["schema_version"],
                "created_at": row["created_at"], "payload": normalized,
            }
        except sqlite3.Error:
            return self._error("PLANNING_STORAGE_UNAVAILABLE")
        finally:
            connection.close()

    def list_unit_economics_expense_snapshots(
        self, *, identity=None, limit=10, offset=0, owner_id=None, store_id=None,
    ):
        scope = self._scope(owner_id, store_id)
        normalized_identity = None
        if identity is not None:
            normalized_identity = PlanningUnitEconomicsExperimentAdapter.normalize_identity(
                identity, scope,
            )
        if (scope.get("error") or type(limit) is not int
                or not 1 <= limit <= self.MAX_PAGE_SIZE
                or type(offset) is not int or offset < 0
                or identity is not None and normalized_identity is None):
            return self._error("PLANNING_EXPENSE_SNAPSHOT_INPUT_INVALID")
        clauses = ["owner_id=?", "store_id=?"]
        params = [scope["owner_id"], scope["store_id"]]
        if normalized_identity is not None:
            clauses.extend(["product_id=?", "offer_id=?", "sku=?", "sale_schema=?"])
            params.extend(normalized_identity[key] for key in (
                "product_id", "offer_id", "sku", "sale_schema",
            ))
        try:
            connection = self.get_connection()
        except (sqlite3.Error, OSError):
            return self._error("PLANNING_STORAGE_UNAVAILABLE")
        try:
            rows = connection.execute(
                "SELECT snapshot_id, schema_version, product_id, offer_id, sku, "
                "sale_schema, payload_json, created_at FROM planning_unit_economics_snapshots WHERE "
                + " AND ".join(clauses)
                + " ORDER BY created_at DESC, snapshot_id LIMIT ? OFFSET ?",
                (*params, limit + 1, offset),
            ).fetchall()
            items = []
            for row in rows[:limit]:
                digest = hashlib.sha256(row["payload_json"].encode("utf-8")).hexdigest()
                try:
                    payload = json.loads(row["payload_json"])
                except (TypeError, ValueError):
                    return self._error("PLANNING_EXPENSE_SNAPSHOT_CORRUPT")
                normalized = PlanningUnitEconomicsExperimentAdapter.normalize_expense_snapshot(
                    payload, scope,
                )
                if (normalized is None or digest != row["snapshot_id"]
                        or row["schema_version"] != normalized["schema_version"]
                        or any(normalized["identity"][key] != row[key] for key in (
                            "product_id", "offer_id", "sku", "sale_schema",
                        ))):
                    return self._error("PLANNING_EXPENSE_SNAPSHOT_CORRUPT")
                items.append({
                    "snapshot_id": row["snapshot_id"], "schema_version": row["schema_version"],
                    "product_id": row["product_id"], "offer_id": row["offer_id"],
                    "sku": row["sku"], "sale_schema": row["sale_schema"],
                    "created_at": row["created_at"],
                })
            return {
                "error": False, "items": items,
                "has_more": len(rows) > limit,
                "next_offset": offset + limit if len(rows) > limit else None,
            }
        except sqlite3.Error:
            return self._error("PLANNING_STORAGE_UNAVAILABLE")
        finally:
            connection.close()

    def create_price_experiment(
        self, payload, *, idempotency_key, owner_id=None, store_id=None,
    ):
        scope = self._scope(owner_id, store_id)
        key = self._idempotency_key(idempotency_key)
        normalized = PlanningUnitEconomicsExperimentAdapter.normalize_experiment(
            payload, scope, allow_incomplete=True,
        )
        encoded = self._encode(normalized) if normalized is not None else None
        if (scope.get("error") or key is None or encoded is None
                or len(encoded.encode("utf-8")) > self.MAX_PRICE_EXPERIMENT_PAYLOAD_BYTES):
            return self._error("PLANNING_PRICE_EXPERIMENT_INPUT_INVALID")
        request_hash = self._price_experiment_request_hash({
            "operation": "create", "payload": normalized,
        })
        if request_hash is None:
            return self._error("PLANNING_PRICE_EXPERIMENT_INPUT_INVALID")
        try:
            connection = self.get_connection()
        except (sqlite3.Error, OSError):
            return self._error("PLANNING_STORAGE_UNAVAILABLE")
        try:
            connection.execute("BEGIN IMMEDIATE")
            replay = self._price_experiment_idempotent_result(
                connection, scope, key, request_hash,
            )
            if replay is not None:
                connection.commit()
                return replay
            reference_error = self._validate_price_experiment_references(
                connection, normalized, scope,
            )
            if reference_error:
                connection.rollback()
                return self._error(reference_error)
            count = connection.execute(
                "SELECT COUNT(*) FROM planning_price_experiments WHERE owner_id=? AND store_id=?",
                (scope["owner_id"], scope["store_id"]),
            ).fetchone()[0]
            if count >= self.MAX_PRICE_EXPERIMENTS_PER_STORE:
                connection.rollback()
                return self._error("PLANNING_PRICE_EXPERIMENT_QUOTA_REACHED")
            now = self._timestamp()
            experiment_id = uuid4().hex
            identity = normalized["identity"]
            references = normalized["source_references"]
            tariff = references["tariff"]
            observation = references["observation"]
            connection.execute(
                """INSERT INTO planning_price_experiments
                   (experiment_id, owner_id, store_id, product_id, offer_id, sku,
                    sale_schema, status, state_revision, result_revision, schema_version,
                    calculation_mode, plan_document_id, plan_revision, expense_snapshot_id,
                    tariff_profile_id, tariff_revision, observation_id,
                    observation_result_revision, config_json, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 'DRAFT', 1, 0, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (experiment_id, scope["owner_id"], scope["store_id"],
                 identity["product_id"], identity["offer_id"], identity["sku"],
                 identity["sale_schema"], normalized["schema_version"],
                 normalized["calculation_mode"], references["plan"]["document_id"],
                 references["plan"]["revision"], references["expense_snapshot_id"],
                 tariff["profile_id"] if tariff else None,
                 tariff["revision"] if tariff else None,
                 observation["observation_id"] if observation else None,
                 observation["result_revision"] if observation else None,
                 encoded, now, now),
            )
            self._insert_price_experiment_revision(
                connection, experiment_id, scope, 1, 1, "DRAFT", normalized, now,
            )
            result = {
                "error": False, "experiment_id": experiment_id,
                "status": "DRAFT", "state_revision": 1, "result_revision": 0,
            }
            self._remember_price_experiment_idempotency(
                connection, scope, key, request_hash, result, now,
            )
            connection.commit()
            return result
        except sqlite3.IntegrityError:
            connection.rollback()
            return self._error("PLANNING_STORAGE_UNAVAILABLE")
        except (ValueError, TypeError, OverflowError):
            connection.rollback()
            return self._error("PLANNING_CLOCK_UNAVAILABLE")
        except sqlite3.Error:
            connection.rollback()
            return self._error("PLANNING_STORAGE_UNAVAILABLE")
        finally:
            connection.close()

    def update_price_experiment_draft(
        self, experiment_id, payload, *, expected_state_revision,
        idempotency_key, owner_id=None, store_id=None,
    ):
        """Append a config revision while an experiment is still a DRAFT."""
        scope = self._scope(owner_id, store_id)
        key = self._idempotency_key(idempotency_key)
        if (scope.get("error") or not self._valid_uuid_hex(experiment_id)
                or key is None or type(expected_state_revision) is not int
                or expected_state_revision < 1):
            return self._error("PLANNING_PRICE_EXPERIMENT_DRAFT_INPUT_INVALID")
        normalized = PlanningUnitEconomicsExperimentAdapter.normalize_experiment(
            payload, scope, allow_incomplete=True,
        )
        if normalized is None or "plan_schema_version" not in normalized:
            return self._error("PLANNING_PRICE_EXPERIMENT_DRAFT_INPUT_INVALID")
        request_hash = self._price_experiment_request_hash({
            "operation": "update_draft", "experiment_id": experiment_id,
            "expected_state_revision": expected_state_revision,
            "payload": normalized,
        })
        encoded = self._encode(normalized)
        if (request_hash is None or encoded is None
                or len(encoded.encode("utf-8")) > self.MAX_PRICE_EXPERIMENT_PAYLOAD_BYTES):
            return self._error("PLANNING_PRICE_EXPERIMENT_DRAFT_INPUT_INVALID")
        try:
            connection = self.get_connection()
        except (sqlite3.Error, OSError):
            return self._error("PLANNING_STORAGE_UNAVAILABLE")
        try:
            connection.execute("BEGIN IMMEDIATE")
            replay = self._price_experiment_idempotent_result(
                connection, scope, key, request_hash,
            )
            if replay is not None:
                connection.commit()
                return replay
            row = connection.execute(
                "SELECT * FROM planning_price_experiments WHERE experiment_id=? "
                "AND owner_id=? AND store_id=?",
                (experiment_id, scope["owner_id"], scope["store_id"]),
            ).fetchone()
            if row is None:
                connection.rollback()
                return self._error("PLANNING_PRICE_EXPERIMENT_NOT_FOUND")
            if row["status"] != "DRAFT":
                connection.rollback()
                return self._error("PLANNING_PRICE_EXPERIMENT_DRAFT_FROZEN")
            if row["state_revision"] != expected_state_revision:
                connection.rollback()
                return self._error("PLANNING_PRICE_EXPERIMENT_STATE_CONFLICT")
            current = self._decode_price_experiment(row, scope)
            if current.get("error"):
                connection.rollback()
                return current
            current_config = current["experiment"]["config"]
            if any(normalized[key_name] != current_config[key_name] for key_name in (
                "identity", "calculation_mode", "source_references",
            )):
                connection.rollback()
                return self._error("PLANNING_PRICE_EXPERIMENT_SCOPE_IMMUTABLE")
            reference_error = self._validate_price_experiment_references(
                connection, normalized, scope,
            )
            if reference_error:
                connection.rollback()
                return self._error(reference_error)
            next_state = expected_state_revision + 1
            now = self._timestamp()
            changed = connection.execute(
                "UPDATE planning_price_experiments SET config_json=?, state_revision=?, "
                "updated_at=? WHERE experiment_id=? AND owner_id=? AND store_id=? "
                "AND status='DRAFT' AND state_revision=?",
                (encoded, next_state, now, experiment_id, scope["owner_id"],
                 scope["store_id"], expected_state_revision),
            ).rowcount
            if changed != 1:
                connection.rollback()
                return self._error("PLANNING_PRICE_EXPERIMENT_STATE_CONFLICT")
            self._insert_price_experiment_revision(
                connection, experiment_id, scope, next_state, next_state,
                "DRAFT", normalized, now,
            )
            readiness = UnitEconomicsExperimentPlanService.evaluate(normalized)
            result = {
                "error": False, "experiment_id": experiment_id,
                "status": "DRAFT", "state_revision": next_state,
                "result_revision": row["result_revision"],
                "plan_status": readiness["status"],
                "reason_codes": readiness["reason_codes"],
            }
            self._remember_price_experiment_idempotency(
                connection, scope, key, request_hash, result, now,
            )
            connection.commit()
            return result
        except sqlite3.IntegrityError:
            connection.rollback()
            return self._error("PLANNING_PRICE_EXPERIMENT_STATE_CONFLICT")
        except (ValueError, TypeError, OverflowError):
            connection.rollback()
            return self._error("PLANNING_CLOCK_UNAVAILABLE")
        except sqlite3.Error:
            connection.rollback()
            return self._error("PLANNING_STORAGE_UNAVAILABLE")
        finally:
            connection.close()

    def _validate_price_experiment_references(self, connection, payload, scope):
        identity = payload["identity"]
        references = payload["source_references"]
        plan = references["plan"]
        plan_row = connection.execute(
            """SELECT d.status, d.schema_version, r.payload_json FROM planning_documents d
               JOIN planning_revisions r ON r.document_id=d.document_id
                 AND r.owner_id=d.owner_id AND r.store_id=d.store_id
               WHERE d.document_id=? AND d.owner_id=? AND d.store_id=? AND r.revision=?""",
            (plan["document_id"], scope["owner_id"], scope["store_id"], plan["revision"]),
        ).fetchone()
        if plan_row is None:
            return "PLANNING_PRICE_EXPERIMENT_SOURCE_PLAN_NOT_FOUND"
        try:
            plan_payload = json.loads(plan_row["payload_json"])
        except (TypeError, ValueError):
            return "PLANNING_PRICE_EXPERIMENT_SOURCE_PLAN_CORRUPT"
        if (not isinstance(plan_payload, dict)
                or type(plan_payload.get("schema_version")) is not int
                or plan_payload["schema_version"] not in {1, 2, 3, 4}
                or plan_payload["schema_version"] != plan_row["schema_version"]
                or self._payload(plan_payload, scope, allow_legacy_sales_mix=True) is None):
            return "PLANNING_PRICE_EXPERIMENT_SOURCE_PLAN_UNSUPPORTED"
        if not self._saved_plan_contains_observation_identity(
            self._encode(plan_payload), identity, scope["store_id"],
        ):
            return "PLANNING_PRICE_EXPERIMENT_SOURCE_PLAN_SCOPE_MISMATCH"
        snapshot = connection.execute(
            """SELECT 1 FROM planning_unit_economics_snapshots
               WHERE snapshot_id=? AND owner_id=? AND store_id=?
                 AND product_id=? AND offer_id=? AND sku=? AND sale_schema=?""",
            (references["expense_snapshot_id"], scope["owner_id"], scope["store_id"],
             identity["product_id"], identity["offer_id"], identity["sku"],
             identity["sale_schema"]),
        ).fetchone()
        if snapshot is None:
            return "PLANNING_PRICE_EXPERIMENT_SNAPSHOT_SCOPE_MISMATCH"
        tariff = references["tariff"]
        if tariff:
            tariff_row = connection.execute(
                """SELECT p.product_id, p.offer_id, p.sku, p.sale_schema, p.status,
                          r.payload_json, r.state_revision, r.created_at FROM planning_tariff_profiles p
                   JOIN planning_tariff_profile_revisions r ON r.profile_id=p.profile_id
                     AND r.owner_id=p.owner_id AND r.store_id=p.store_id
                   WHERE p.profile_id=? AND p.owner_id=? AND p.store_id=? AND r.revision=?""",
                (tariff["profile_id"], scope["owner_id"], scope["store_id"],
                 tariff["revision"]),
            ).fetchone()
            if tariff_row is None:
                return "PLANNING_PRICE_EXPERIMENT_TARIFF_REVISION_NOT_FOUND"
            if any(tariff_row[key] != identity[key] for key in (
                "product_id", "offer_id", "sku", "sale_schema",
            )):
                return "PLANNING_PRICE_EXPERIMENT_TARIFF_SCOPE_MISMATCH"
            try:
                tariff_payload = json.loads(tariff_row["payload_json"])
            except (TypeError, ValueError):
                return "PLANNING_PRICE_EXPERIMENT_TARIFF_REVISION_CORRUPT"
            if not self._stored_tariff_profile_valid(
                tariff_payload, scope, tariff["profile_id"], tariff["revision"],
            ) or tariff_payload.get("state_revision") != tariff_row["state_revision"]:
                return "PLANNING_PRICE_EXPERIMENT_TARIFF_REVISION_CORRUPT"
        observation = references["observation"]
        if observation:
            observation_row = connection.execute(
                """SELECT o.product_id, o.offer_id, o.sku, o.sale_schema,
                          o.seller_price_cents,
                          r.payload_json FROM planning_unit_price_observations o
                   JOIN planning_unit_price_observation_results r
                     ON r.observation_id=o.observation_id AND r.owner_id=o.owner_id
                    AND r.store_id=o.store_id
                   WHERE o.observation_id=? AND o.owner_id=? AND o.store_id=?
                     AND r.result_revision=?""",
                (observation["observation_id"], scope["owner_id"], scope["store_id"],
                 observation["result_revision"]),
            ).fetchone()
            if observation_row is None:
                return "PLANNING_PRICE_EXPERIMENT_OBSERVATION_REVISION_NOT_FOUND"
            if any(observation_row[key] != identity[key] for key in (
                "product_id", "offer_id", "sku", "sale_schema",
            )):
                return "PLANNING_PRICE_EXPERIMENT_OBSERVATION_SCOPE_MISMATCH"
            try:
                result_payload = json.loads(observation_row["payload_json"])
            except (ValueError, TypeError):
                return "PLANNING_PRICE_EXPERIMENT_OBSERVATION_RESULT_CORRUPT"
            observation_identity = {
                "store_id": scope["store_id"],
                "product_id": identity["product_id"], "offer_id": identity["offer_id"],
                "sku": identity["sku"], "sale_schema": identity["sale_schema"],
            }
            if not self._observation_result_matches(
                result_payload, observation_row, scope["store_id"],
            ) or result_payload.get("identity") != observation_identity:
                return "PLANNING_PRICE_EXPERIMENT_OBSERVATION_SCOPE_MISMATCH"
            if self._normalize_unit_price_observation_result(result_payload) is None:
                return "PLANNING_PRICE_EXPERIMENT_OBSERVATION_RESULT_CORRUPT"
        return None

    def _insert_price_experiment_revision(
        self, connection, experiment_id, scope, revision, state_revision,
        status, config, now, resume_target=None,
    ):
        payload = {
            "schema_version": PlanningUnitEconomicsExperimentAdapter.EXPERIMENT_SCHEMA_VERSION,
            "experiment_id": experiment_id, "state": status,
            "state_revision": state_revision, "config": config,
            "resume_target": resume_target,
        }
        encoded = self._encode(payload)
        if encoded is None or len(encoded.encode("utf-8")) > self.MAX_PRICE_EXPERIMENT_PAYLOAD_BYTES:
            raise ValueError("experiment revision exceeds storage bound")
        connection.execute(
            """INSERT INTO planning_price_experiment_revisions
               (experiment_id, owner_id, store_id, revision, state_revision,
                payload_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (experiment_id, scope["owner_id"], scope["store_id"], revision,
             state_revision, encoded, now),
        )

    def create_price_experiment_phase(
        self, experiment_id, payload, *, expected_state_revision,
        idempotency_key, owner_id=None, store_id=None,
    ):
        scope = self._scope(owner_id, store_id)
        key = self._idempotency_key(idempotency_key)
        if (scope.get("error") or key is None or not self._valid_uuid_hex(experiment_id)
                or type(expected_state_revision) is not int or expected_state_revision < 1):
            return self._error("PLANNING_PRICE_EXPERIMENT_PHASE_INPUT_INVALID")
        request_hash = self._price_experiment_request_hash({
            "operation": "create_phase", "experiment_id": experiment_id,
            "expected_state_revision": expected_state_revision, "payload": payload,
        })
        if request_hash is None:
            return self._error("PLANNING_PRICE_EXPERIMENT_PHASE_INPUT_INVALID")
        try:
            connection = self.get_connection()
        except (sqlite3.Error, OSError):
            return self._error("PLANNING_STORAGE_UNAVAILABLE")
        try:
            connection.execute("BEGIN IMMEDIATE")
            replay = self._price_experiment_idempotent_result(
                connection, scope, key, request_hash,
            )
            if replay is not None:
                connection.commit()
                return replay
            experiment = connection.execute(
                "SELECT * FROM planning_price_experiments WHERE experiment_id=? "
                "AND owner_id=? AND store_id=?",
                (experiment_id, scope["owner_id"], scope["store_id"]),
            ).fetchone()
            if experiment is None:
                connection.rollback()
                return self._error("PLANNING_PRICE_EXPERIMENT_NOT_FOUND")
            decoded_experiment = self._decode_price_experiment(experiment, scope)
            if decoded_experiment.get("error"):
                connection.rollback()
                return decoded_experiment
            if experiment["state_revision"] != expected_state_revision:
                connection.rollback()
                return self._error("PLANNING_PRICE_EXPERIMENT_STATE_CONFLICT")
            if experiment["status"] != "DRAFT":
                connection.rollback()
                return self._error("PLANNING_PRICE_EXPERIMENT_STATE_INVALID")
            identity = {key: experiment[key] for key in (
                "owner_id", "store_id", "product_id", "offer_id", "sku", "sale_schema",
            )}
            normalized = PlanningUnitEconomicsExperimentAdapter.normalize_phase(
                payload, identity,
            )
            encoded = self._encode(normalized) if normalized is not None else None
            if (encoded is None or len(encoded.encode("utf-8"))
                    > self.MAX_PRICE_EXPERIMENT_PAYLOAD_BYTES):
                connection.rollback()
                return self._error("PLANNING_PRICE_EXPERIMENT_PHASE_INVALID")
            if normalized["expense_snapshot_id"] != experiment["expense_snapshot_id"]:
                snapshot = connection.execute(
                    """SELECT 1 FROM planning_unit_economics_snapshots WHERE snapshot_id=?
                       AND owner_id=? AND store_id=? AND product_id=? AND offer_id=? AND sku=?
                       AND sale_schema=?""",
                    (normalized["expense_snapshot_id"], scope["owner_id"],
                     scope["store_id"], experiment["product_id"], experiment["offer_id"],
                     experiment["sku"], experiment["sale_schema"]),
                ).fetchone()
                if snapshot is None:
                    connection.rollback()
                    return self._error("PLANNING_PRICE_EXPERIMENT_PHASE_SNAPSHOT_SCOPE_MISMATCH")
            if (normalized["kind"] == "CANDIDATE"
                    and normalized["planned_price_cents"]
                    not in decoded_experiment["experiment"]["config"]["candidate_prices_cents"]):
                connection.rollback()
                return self._error("PLANNING_PRICE_EXPERIMENT_CANDIDATE_NOT_SELECTED")
            phase_count = connection.execute(
                "SELECT COUNT(*) FROM planning_price_experiment_phases "
                "WHERE experiment_id=? AND owner_id=? AND store_id=?",
                (experiment_id, scope["owner_id"], scope["store_id"]),
            ).fetchone()[0]
            if phase_count >= self.MAX_PRICE_EXPERIMENT_PHASES:
                connection.rollback()
                return self._error("PLANNING_PRICE_EXPERIMENT_PHASE_QUOTA_REACHED")
            if normalized["segment_number"] != phase_count + 1:
                connection.rollback()
                return self._error("PLANNING_PRICE_EXPERIMENT_SEGMENT_SEQUENCE_INVALID")
            phase_days = (
                date.fromisoformat(normalized["planned_to_date"])
                - date.fromisoformat(normalized["planned_from_date"])
            ).days + 1
            if phase_days > decoded_experiment["experiment"]["config"]["planned_duration_days"]:
                connection.rollback()
                return self._error("PLANNING_PRICE_EXPERIMENT_PHASE_DURATION_INVALID")
            if phase_count == 0 and normalized["kind"] != "BASELINE":
                connection.rollback()
                return self._error("PLANNING_PRICE_EXPERIMENT_BASELINE_REQUIRED")
            if normalized["kind"] == "BASELINE" and phase_count != 0:
                connection.rollback()
                return self._error("PLANNING_PRICE_EXPERIMENT_BASELINE_ALREADY_EXISTS")
            now = self._timestamp()
            phase_id = uuid4().hex
            connection.execute(
                """INSERT INTO planning_price_experiment_phases
                   (phase_id, experiment_id, owner_id, store_id, product_id, offer_id,
                    sku, sale_schema, segment_number, kind, status, state_revision,
                    result_revision, expense_snapshot_id, payload_json, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PLANNED', 1, 0, ?, ?, ?, ?)""",
                (phase_id, experiment_id, scope["owner_id"], scope["store_id"],
                 experiment["product_id"], experiment["offer_id"], experiment["sku"],
                 experiment["sale_schema"], normalized["segment_number"],
                 normalized["kind"], normalized["expense_snapshot_id"], encoded, now, now),
            )
            phase_revision_payload = {
                "schema_version": normalized["schema_version"], "phase_id": phase_id,
                "experiment_id": experiment_id, "state": "PLANNED",
                "state_revision": 1, "result_revision": 0, "phase": normalized,
            }
            phase_revision_json = self._encode(phase_revision_payload)
            connection.execute(
                """INSERT INTO planning_price_experiment_phase_revisions
                   (phase_id, experiment_id, owner_id, store_id, revision, state_revision,
                    result_revision, payload_json, created_at)
                   VALUES (?, ?, ?, ?, 1, 1, 0, ?, ?)""",
                (phase_id, experiment_id, scope["owner_id"], scope["store_id"],
                 phase_revision_json, now),
            )
            next_state = expected_state_revision + 1
            changed = connection.execute(
                "UPDATE planning_price_experiments SET state_revision=?, updated_at=? "
                "WHERE experiment_id=? AND owner_id=? AND store_id=? AND state_revision=? "
                "AND status='DRAFT'",
                (next_state, now, experiment_id, scope["owner_id"], scope["store_id"],
                 expected_state_revision),
            ).rowcount
            if changed != 1:
                connection.rollback()
                return self._error("PLANNING_PRICE_EXPERIMENT_STATE_CONFLICT")
            config = decoded_experiment["experiment"]["config"]
            self._insert_price_experiment_revision(
                connection, experiment_id, scope, next_state, next_state,
                experiment["status"], config, now,
            )
            result = {
                "error": False, "experiment_id": experiment_id,
                "phase_id": phase_id, "status": "PLANNED",
                "phase_state_revision": 1, "experiment_state_revision": next_state,
                "result_revision": 0,
            }
            self._remember_price_experiment_idempotency(
                connection, scope, key, request_hash, result, now,
            )
            connection.commit()
            return result
        except sqlite3.IntegrityError:
            connection.rollback()
            return self._error("PLANNING_PRICE_EXPERIMENT_PHASE_CONFLICT")
        except (ValueError, TypeError, OverflowError):
            connection.rollback()
            return self._error("PLANNING_CLOCK_UNAVAILABLE")
        except sqlite3.Error:
            connection.rollback()
            return self._error("PLANNING_STORAGE_UNAVAILABLE")
        finally:
            connection.close()

    def preview_price_experiment_phase_confirmation(
        self, experiment_id, phase_id, *, seller_price_cents, effective_from,
        owner_confirmed=False, owner_id=None, store_id=None,
    ):
        """Preview an owner-declared phase start without changing local state."""
        experiment_result = self.get_price_experiment(
            experiment_id, owner_id=owner_id, store_id=store_id,
        )
        if experiment_result.get("error"):
            return experiment_result
        phases_result = self.list_price_experiment_phases(
            experiment_id, owner_id=owner_id, store_id=store_id,
        )
        if phases_result.get("error"):
            return phases_result
        phase = next((item for item in phases_result.get("items", [])
                      if item.get("phase_id") == phase_id), None)
        if phase is None:
            return self._error("PLANNING_PRICE_EXPERIMENT_PHASE_NOT_FOUND")
        try:
            now = self._timestamp()
        except (ValueError, TypeError, OverflowError):
            return self._error("PLANNING_CLOCK_UNAVAILABLE")
        preview = UnitEconomicsExperimentPhaseConfirmationService.preview(
            phase["config"], experiment_result["experiment"]["status"],
            phase["status"], seller_price_cents, effective_from, now,
            owner_confirmed=owner_confirmed,
            candidate_prices_cents=experiment_result["experiment"]["config"].get(
                "candidate_prices_cents",
            ),
            resume_target=experiment_result["experiment"].get("resume_target"),
        )
        if preview.get("error"):
            return preview
        return {
            **preview,
            "experiment_id": experiment_id, "phase_id": phase_id,
            "experiment_state_revision": experiment_result["experiment"][
                "state_revision"
            ],
            "phase_state_revision": phase["state_revision"],
        }

    def confirm_price_experiment_phase(
        self, experiment_id, phase_id, *, seller_price_cents, effective_from,
        owner_confirmed, expected_state_revision, expected_phase_state_revision,
        idempotency_key, owner_id=None, store_id=None,
    ):
        """Atomically attach a new observation and activate its confirmed phase."""
        scope = self._scope(owner_id, store_id)
        key = self._idempotency_key(idempotency_key)
        effective = self._timestamp_preserving_offset(effective_from)
        if (scope.get("error") or key is None
                or not self._valid_uuid_hex(experiment_id)
                or not self._valid_uuid_hex(phase_id)
                or type(seller_price_cents) is not int or seller_price_cents < 1
                or seller_price_cents > UnitPriceTariffResolver.MAX_PRICE_CENTS
                or owner_confirmed is not True
                or type(expected_state_revision) is not int or expected_state_revision < 1
                or type(expected_phase_state_revision) is not int
                or expected_phase_state_revision < 1 or effective is None):
            return self._error("PLANNING_PRICE_EXPERIMENT_CONFIRMATION_INPUT_INVALID")
        request_hash = self._price_experiment_request_hash({
            "operation": "confirm_phase", "experiment_id": experiment_id,
            "phase_id": phase_id, "seller_price_cents": seller_price_cents,
            "effective_from": effective, "owner_confirmed": owner_confirmed,
            "expected_state_revision": expected_state_revision,
            "expected_phase_state_revision": expected_phase_state_revision,
        })
        if request_hash is None:
            return self._error("PLANNING_PRICE_EXPERIMENT_CONFIRMATION_INPUT_INVALID")
        try:
            connection = self.get_connection()
        except (sqlite3.Error, OSError):
            return self._error("PLANNING_STORAGE_UNAVAILABLE")
        try:
            connection.execute("BEGIN IMMEDIATE")
            replay = self._price_experiment_idempotent_result(
                connection, scope, key, request_hash,
            )
            if replay is not None:
                connection.commit()
                return replay
            experiment_row = connection.execute(
                "SELECT * FROM planning_price_experiments WHERE experiment_id=? "
                "AND owner_id=? AND store_id=?",
                (experiment_id, scope["owner_id"], scope["store_id"]),
            ).fetchone()
            phase_row = connection.execute(
                "SELECT * FROM planning_price_experiment_phases WHERE phase_id=? "
                "AND experiment_id=? AND owner_id=? AND store_id=?",
                (phase_id, experiment_id, scope["owner_id"], scope["store_id"]),
            ).fetchone()
            if experiment_row is None or phase_row is None:
                connection.rollback()
                return self._error("PLANNING_PRICE_EXPERIMENT_PHASE_NOT_FOUND")
            if experiment_row["state_revision"] != expected_state_revision:
                connection.rollback()
                return self._error("PLANNING_PRICE_EXPERIMENT_STATE_CONFLICT")
            if phase_row["state_revision"] != expected_phase_state_revision:
                connection.rollback()
                return self._error("PLANNING_PRICE_EXPERIMENT_PHASE_STATE_CONFLICT")
            experiment = self._decode_price_experiment(experiment_row, scope)
            phase = self._decode_price_experiment_phase(phase_row)
            if experiment.get("error") or phase.get("error"):
                connection.rollback()
                return self._error("PLANNING_PRICE_EXPERIMENT_RECORD_CORRUPT")
            config = experiment["experiment"]["config"]
            phase_value = phase["phase"]
            if phase_value.get("observation_id") is not None:
                connection.rollback()
                return self._error("PLANNING_PRICE_EXPERIMENT_PHASE_ALREADY_CONFIRMED")
            reference_error = self._validate_price_experiment_references(
                connection, config, scope,
            )
            if reference_error:
                connection.rollback()
                return self._error(reference_error)
            try:
                now = self._timestamp()
            except (ValueError, TypeError, OverflowError):
                connection.rollback()
                return self._error("PLANNING_CLOCK_UNAVAILABLE")
            preview = UnitEconomicsExperimentPhaseConfirmationService.preview(
                phase_value["config"], experiment_row["status"], phase_row["status"],
                seller_price_cents, effective, now, owner_confirmed=True,
                candidate_prices_cents=config.get("candidate_prices_cents"),
                resume_target=experiment_row["resume_target"],
            )
            if preview.get("error"):
                connection.rollback()
                return preview
            confirmation = UnitEconomicsExperimentPhaseConfirmationService.normalize_confirmation(
                preview.get("confirmation"), phase_value["config"],
            )
            if confirmation is None:
                connection.rollback()
                return self._error("PLANNING_PRICE_EXPERIMENT_CONFIRMATION_INVALID")
            if experiment_row["status"] == "PAUSED":
                action = "resume"
                decision = UnitEconomicsExperimentStateMachine.transition(
                    experiment_row["status"], action,
                    resume_target=experiment_row["resume_target"],
                    fresh_confirmation=True, active_guard_available=True,
                )
                expected_resume_target = (
                    "READY" if phase_value["kind"] == "BASELINE"
                    else "CANDIDATE_READY"
                )
                if experiment_row["resume_target"] != expected_resume_target:
                    connection.rollback()
                    return self._error(
                        "PLANNING_PRICE_EXPERIMENT_RESUME_TARGET_MISMATCH"
                    )
            else:
                action = (
                    "activate_baseline" if phase_value["kind"] == "BASELINE"
                    else "activate_candidate"
                )
                decision = UnitEconomicsExperimentStateMachine.transition(
                    experiment_row["status"], action,
                    phase_confirmed=True, active_guard_available=True,
                )
            if decision.get("error"):
                connection.rollback()
                return self._error("PLANNING_PRICE_EXPERIMENT_TRANSITION_NOT_ALLOWED")
            observation_count = connection.execute(
                "SELECT COUNT(*) FROM planning_unit_price_observations "
                "WHERE owner_id=? AND store_id=?",
                (scope["owner_id"], scope["store_id"]),
            ).fetchone()[0]
            if observation_count >= self.MAX_UNIT_PRICE_OBSERVATIONS_PER_STORE:
                connection.rollback()
                return self._error("PLANNING_OBSERVATION_QUOTA_REACHED")
            identity = {key_name: experiment_row[key_name] for key_name in (
                "owner_id", "store_id", "product_id", "offer_id", "sku", "sale_schema",
            )}
            if not self._claim_active_sku_guard(
                connection, scope, identity, "EXPERIMENT", experiment_id, now,
            ):
                connection.rollback()
                return self._error("PLANNING_PRICE_EXPERIMENT_ACTIVE_SKU_GUARD_UNAVAILABLE")

            source_plan = config["source_references"]["plan"]
            observation_identity = {
                key_name: identity[key_name] for key_name in (
                    "product_id", "offer_id", "sku", "sale_schema",
                )
            }
            observation_id = uuid4().hex
            observation_key = f"exp_{experiment_id}_{phase_id}"
            observation_request = {
                "operation": "start", "identity": observation_identity,
                "seller_price_cents": seller_price_cents,
                "source_document_id": source_plan["document_id"],
                "source_document_revision": source_plan["revision"],
                "effective_from": effective,
                "window_timezone": phase_value["config"]["timezone"],
                "owner_confirmed": True, "note": "",
            }
            observation_hash = self._observation_request_hash(observation_request)
            if observation_hash is None:
                connection.rollback()
                return self._error("PLANNING_PRICE_EXPERIMENT_CONFIRMATION_INVALID")
            connection.execute(
                """INSERT INTO planning_unit_price_observations
                   (observation_id, owner_id, store_id, product_id, offer_id, sku,
                    sale_schema, source_document_id, source_document_revision,
                    seller_price_cents, price_evidence_kind, effective_from,
                    window_timezone, status, state_revision, result_revision, note,
                    started_at, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, 'FBO', ?, ?, ?,
                           'OWNER_DECLARED_PRICE_CHANGE', ?, ?, 'ACTIVE', 1, 0, '', ?, ?, ?)""",
                (observation_id, scope["owner_id"], scope["store_id"],
                 observation_identity["product_id"], observation_identity["offer_id"],
                 observation_identity["sku"], source_plan["document_id"],
                 source_plan["revision"], seller_price_cents, effective,
                 phase_value["config"]["timezone"], now, now, now),
            )
            observation_result = {
                "error": False, "observation_id": observation_id,
                "status": "ACTIVE", "state_revision": 1, "result_revision": 0,
            }
            self._remember_observation_idempotency(
                connection, scope, observation_key, observation_hash,
                observation_result, now,
            )

            next_phase_revision = expected_phase_state_revision + 1
            confirmation_json = self._encode(confirmation)
            phase_updated = connection.execute(
                "UPDATE planning_price_experiment_phases SET status='ACTIVE', "
                "state_revision=?, observation_id=?, confirmation_json=?, updated_at=? "
                "WHERE phase_id=? AND experiment_id=? AND owner_id=? AND store_id=? "
                "AND status='PLANNED' AND state_revision=? AND observation_id IS NULL",
                (next_phase_revision, observation_id, confirmation_json, now,
                 phase_id, experiment_id, scope["owner_id"], scope["store_id"],
                 expected_phase_state_revision),
            ).rowcount
            if phase_updated != 1:
                connection.rollback()
                return self._error("PLANNING_PRICE_EXPERIMENT_PHASE_STATE_CONFLICT")
            phase_revision = next_phase_revision + phase_row["result_revision"]
            phase_revision_payload = {
                "schema_version": PlanningUnitEconomicsExperimentAdapter.PHASE_SCHEMA_VERSION,
                "phase_id": phase_id, "experiment_id": experiment_id,
                "state": "ACTIVE", "state_revision": next_phase_revision,
                "result_revision": phase_row["result_revision"],
                "phase": phase_value["config"],
                "observation_id": observation_id, "confirmation": confirmation,
            }
            phase_revision_encoded = self._encode(phase_revision_payload)
            if (phase_revision_encoded is None or len(phase_revision_encoded.encode("utf-8"))
                    > self.MAX_PRICE_EXPERIMENT_PAYLOAD_BYTES):
                connection.rollback()
                return self._error("PLANNING_PRICE_EXPERIMENT_CONFIRMATION_INVALID")
            connection.execute(
                """INSERT INTO planning_price_experiment_phase_revisions
                   (phase_id, experiment_id, owner_id, store_id, revision, state_revision,
                    result_revision, payload_json, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (phase_id, experiment_id, scope["owner_id"], scope["store_id"],
                 phase_revision, next_phase_revision, phase_row["result_revision"],
                 phase_revision_encoded, now),
            )
            next_experiment_revision = expected_state_revision + 1
            experiment_updated = connection.execute(
                "UPDATE planning_price_experiments SET status=?, resume_target=NULL, "
                "state_revision=?, updated_at=? "
                "WHERE experiment_id=? AND owner_id=? AND store_id=? AND state_revision=? "
                "AND status=?",
                (decision["to_state"], next_experiment_revision, now,
                 experiment_id, scope["owner_id"], scope["store_id"],
                 expected_state_revision, experiment_row["status"]),
            ).rowcount
            if experiment_updated != 1:
                connection.rollback()
                return self._error("PLANNING_PRICE_EXPERIMENT_STATE_CONFLICT")
            self._insert_price_experiment_revision(
                connection, experiment_id, scope, next_experiment_revision,
                next_experiment_revision, decision["to_state"], config, now,
            )
            result = {
                "error": False, "experiment_id": experiment_id,
                "phase_id": phase_id, "observation_id": observation_id,
                "status": decision["to_state"],
                "phase_status": "ACTIVE",
                "state_revision": next_experiment_revision,
                "phase_state_revision": next_phase_revision,
                "result_revision": experiment_row["result_revision"],
                "first_full_local_day": confirmation["first_full_local_day"],
                "price_evidence_kind": confirmation["price_evidence_kind"],
                "price_history_verified": False,
            }
            self._remember_price_experiment_idempotency(
                connection, scope, key, request_hash, result, now,
            )
            connection.commit()
            return result
        except sqlite3.IntegrityError:
            connection.rollback()
            return self._error("PLANNING_PRICE_EXPERIMENT_CONFIRMATION_CONFLICT")
        except (ValueError, TypeError, OverflowError):
            connection.rollback()
            return self._error("PLANNING_CLOCK_UNAVAILABLE")
        except sqlite3.Error:
            connection.rollback()
            return self._error("PLANNING_STORAGE_UNAVAILABLE")
        finally:
            connection.close()

    def record_price_experiment_control_update(
        self, experiment_id, phase_id, control_flags, *, expected_state_revision,
        idempotency_key, owner_id=None, store_id=None,
    ):
        """Append owner-reported conditions without rewriting phase configuration."""
        scope = self._scope(owner_id, store_id)
        key = self._idempotency_key(idempotency_key)
        base_payload = {
            "schema_version": 1, "event_kind": "CONTROL_UPDATE",
            "phase_id": phase_id, "control_flags": control_flags,
            "source": "OWNER_REPORTED",
        }
        normalized = UnitEconomicsExperimentControlService.normalize_event(
            base_payload, expected_phase_id=phase_id,
        )
        if (scope.get("error") or key is None
                or not self._valid_uuid_hex(experiment_id)
                or not self._valid_uuid_hex(phase_id)
                or normalized is None
                or type(expected_state_revision) is not int
                or expected_state_revision < 1):
            return self._error("PLANNING_PRICE_EXPERIMENT_CONTROL_INPUT_INVALID")
        request_hash = self._price_experiment_request_hash({
            "operation": "control_update", "experiment_id": experiment_id,
            "phase_id": phase_id, "payload": base_payload,
            "expected_state_revision": expected_state_revision,
        })
        if request_hash is None:
            return self._error("PLANNING_PRICE_EXPERIMENT_CONTROL_INPUT_INVALID")
        try:
            connection = self.get_connection()
        except (sqlite3.Error, OSError):
            return self._error("PLANNING_STORAGE_UNAVAILABLE")
        try:
            connection.execute("BEGIN IMMEDIATE")
            replay = self._price_experiment_idempotent_result(
                connection, scope, key, request_hash,
            )
            if replay is not None:
                connection.commit()
                return replay
            experiment_row = connection.execute(
                "SELECT * FROM planning_price_experiments WHERE experiment_id=? "
                "AND owner_id=? AND store_id=?",
                (experiment_id, scope["owner_id"], scope["store_id"]),
            ).fetchone()
            phase_row = connection.execute(
                "SELECT * FROM planning_price_experiment_phases WHERE phase_id=? "
                "AND experiment_id=? AND owner_id=? AND store_id=?",
                (phase_id, experiment_id, scope["owner_id"], scope["store_id"]),
            ).fetchone()
            if experiment_row is None or phase_row is None:
                connection.rollback()
                return self._error("PLANNING_PRICE_EXPERIMENT_PHASE_NOT_FOUND")
            if experiment_row["state_revision"] != expected_state_revision:
                connection.rollback()
                return self._error("PLANNING_PRICE_EXPERIMENT_STATE_CONFLICT")
            experiment = self._decode_price_experiment(experiment_row, scope)
            phase = self._decode_price_experiment_phase(phase_row)
            if experiment.get("error") or phase.get("error"):
                connection.rollback()
                return self._error("PLANNING_PRICE_EXPERIMENT_RECORD_CORRUPT")
            allowed_pairs = {
                "BASELINE_ACTIVE": ("BASELINE", "ACTIVE"),
                "BASELINE_REVIEW": ("BASELINE", "FINISHED"),
                "CANDIDATE_ACTIVE": ("CANDIDATE", "ACTIVE"),
                "CANDIDATE_REVIEW": ("CANDIDATE", "FINISHED"),
                "PAUSED": (phase["phase"]["kind"], "PAUSED"),
            }
            if allowed_pairs.get(experiment_row["status"]) != (
                phase["phase"]["kind"], phase_row["status"],
            ):
                connection.rollback()
                return self._error("PLANNING_PRICE_EXPERIMENT_CONTROL_STATE_INVALID")
            prior_flags = [phase["phase"]["config"]["control_flags"]]
            prior_events = connection.execute(
                "SELECT payload_json, payload_hash FROM planning_price_experiment_events "
                "WHERE experiment_id=? AND owner_id=? AND store_id=? AND phase_id=? "
                "AND event_kind='CONTROL_UPDATE' ORDER BY event_revision",
                (experiment_id, scope["owner_id"], scope["store_id"], phase_id),
            ).fetchall()
            for event_row in prior_events:
                try:
                    prior_payload = json.loads(event_row["payload_json"])
                except (TypeError, ValueError):
                    connection.rollback()
                    return self._error("PLANNING_PRICE_EXPERIMENT_EVENT_CORRUPT")
                prior_event = UnitEconomicsExperimentControlService.normalize_event(
                    prior_payload, expected_phase_id=phase_id,
                )
                digest = hashlib.sha256(
                    event_row["payload_json"].encode("utf-8"),
                ).hexdigest()
                if prior_event is None or digest != event_row["payload_hash"]:
                    connection.rollback()
                    return self._error("PLANNING_PRICE_EXPERIMENT_EVENT_CORRUPT")
                prior_flags.append(prior_event["control_flags"])
            compatibility = UnitEconomicsExperimentControlService.compatibility(
                *prior_flags, normalized["control_flags"],
            )
            now = self._timestamp()
            event = self._insert_price_experiment_event(
                connection, scope, experiment_id, phase_id, base_payload, now,
            )
            if event.get("error"):
                connection.rollback()
                return event
            next_state = expected_state_revision + 1
            changed = connection.execute(
                "UPDATE planning_price_experiments SET state_revision=?, updated_at=? "
                "WHERE experiment_id=? AND owner_id=? AND store_id=? "
                "AND state_revision=? AND status=?",
                (next_state, now, experiment_id, scope["owner_id"], scope["store_id"],
                 expected_state_revision, experiment_row["status"]),
            ).rowcount
            if changed != 1:
                connection.rollback()
                return self._error("PLANNING_PRICE_EXPERIMENT_STATE_CONFLICT")
            self._insert_price_experiment_revision(
                connection, experiment_id, scope, next_state, next_state,
                experiment_row["status"], experiment["experiment"]["config"], now,
                experiment_row["resume_target"],
            )
            result = {
                "error": False, "experiment_id": experiment_id,
                "phase_id": phase_id, "event_id": event["event_id"],
                "event_revision": event["event_revision"],
                "status": experiment_row["status"], "state_revision": next_state,
                "result_revision": experiment_row["result_revision"],
                "compatibility": compatibility,
                "evidence_rewritten": False,
            }
            self._remember_price_experiment_idempotency(
                connection, scope, key, request_hash, result, now,
            )
            connection.commit()
            return result
        except sqlite3.IntegrityError:
            connection.rollback()
            return self._error("PLANNING_PRICE_EXPERIMENT_CONTROL_CONFLICT")
        except (ValueError, TypeError, OverflowError):
            connection.rollback()
            return self._error("PLANNING_CLOCK_UNAVAILABLE")
        except sqlite3.Error:
            connection.rollback()
            return self._error("PLANNING_STORAGE_UNAVAILABLE")
        finally:
            connection.close()

    def pause_price_experiment_phase(
        self, experiment_id, phase_id, *, expected_state_revision,
        expected_phase_state_revision, idempotency_key, owner_id=None, store_id=None,
    ):
        """Close one active segment and atomically release the shared SKU guard."""
        scope = self._scope(owner_id, store_id)
        key = self._idempotency_key(idempotency_key)
        if (scope.get("error") or key is None
                or not self._valid_uuid_hex(experiment_id)
                or not self._valid_uuid_hex(phase_id)
                or type(expected_state_revision) is not int or expected_state_revision < 1
                or type(expected_phase_state_revision) is not int
                or expected_phase_state_revision < 1):
            return self._error("PLANNING_PRICE_EXPERIMENT_PAUSE_INPUT_INVALID")
        request_hash = self._price_experiment_request_hash({
            "operation": "pause_phase", "experiment_id": experiment_id,
            "phase_id": phase_id,
            "expected_state_revision": expected_state_revision,
            "expected_phase_state_revision": expected_phase_state_revision,
        })
        if request_hash is None:
            return self._error("PLANNING_PRICE_EXPERIMENT_PAUSE_INPUT_INVALID")
        try:
            connection = self.get_connection()
        except (sqlite3.Error, OSError):
            return self._error("PLANNING_STORAGE_UNAVAILABLE")
        try:
            connection.execute("BEGIN IMMEDIATE")
            replay = self._price_experiment_idempotent_result(
                connection, scope, key, request_hash,
            )
            if replay is not None:
                connection.commit()
                return replay
            experiment_row = connection.execute(
                "SELECT * FROM planning_price_experiments WHERE experiment_id=? "
                "AND owner_id=? AND store_id=?",
                (experiment_id, scope["owner_id"], scope["store_id"]),
            ).fetchone()
            phase_row = connection.execute(
                "SELECT * FROM planning_price_experiment_phases WHERE phase_id=? "
                "AND experiment_id=? AND owner_id=? AND store_id=?",
                (phase_id, experiment_id, scope["owner_id"], scope["store_id"]),
            ).fetchone()
            if experiment_row is None or phase_row is None:
                connection.rollback()
                return self._error("PLANNING_PRICE_EXPERIMENT_PHASE_NOT_FOUND")
            if experiment_row["state_revision"] != expected_state_revision:
                connection.rollback()
                return self._error("PLANNING_PRICE_EXPERIMENT_STATE_CONFLICT")
            if phase_row["state_revision"] != expected_phase_state_revision:
                connection.rollback()
                return self._error("PLANNING_PRICE_EXPERIMENT_PHASE_STATE_CONFLICT")
            experiment = self._decode_price_experiment(experiment_row, scope)
            phase = self._decode_price_experiment_phase(phase_row)
            if experiment.get("error") or phase.get("error"):
                connection.rollback()
                return self._error("PLANNING_PRICE_EXPERIMENT_RECORD_CORRUPT")
            decision = UnitEconomicsExperimentStateMachine.transition(
                experiment_row["status"], "pause",
            )
            if decision.get("error") or phase_row["status"] != "ACTIVE":
                connection.rollback()
                return self._error("PLANNING_PRICE_EXPERIMENT_PAUSE_STATE_INVALID")
            observation_id = phase_row["observation_id"]
            observation_row = connection.execute(
                "SELECT * FROM planning_unit_price_observations WHERE observation_id=? "
                "AND owner_id=? AND store_id=?",
                (observation_id, scope["owner_id"], scope["store_id"]),
            ).fetchone()
            if (observation_row is None or observation_row["status"] != "ACTIVE"
                    or observation_row["product_id"] != experiment_row["product_id"]
                    or observation_row["offer_id"] != experiment_row["offer_id"]
                    or observation_row["sku"] != experiment_row["sku"]
                    or observation_row["sale_schema"] != experiment_row["sale_schema"]):
                connection.rollback()
                return self._error("PLANNING_PRICE_EXPERIMENT_OBSERVATION_LINK_INVALID")
            now = self._timestamp()
            pause_payload = UnitEconomicsExperimentControlService.normalize_pause_event({
                "schema_version": 1, "event_kind": "PAUSE",
                "phase_id": phase_id, "observation_id": observation_id,
                "resume_target": decision["resume_target"], "source": "OWNER_ACTION",
            }, expected_phase_id=phase_id)
            if pause_payload is None:
                connection.rollback()
                return self._error("PLANNING_PRICE_EXPERIMENT_PAUSE_INPUT_INVALID")
            event = self._insert_price_experiment_event(
                connection, scope, experiment_id, phase_id, pause_payload, now,
            )
            if event.get("error"):
                connection.rollback()
                return event
            observation_updated = connection.execute(
                "UPDATE planning_unit_price_observations SET status='FINISHED', "
                "state_revision=state_revision+1, finished_at=?, updated_at=? "
                "WHERE observation_id=? AND owner_id=? AND store_id=? "
                "AND status='ACTIVE' AND state_revision=?",
                (now, now, observation_id, scope["owner_id"], scope["store_id"],
                 observation_row["state_revision"]),
            ).rowcount
            if observation_updated != 1:
                connection.rollback()
                return self._error("PLANNING_PRICE_EXPERIMENT_OBSERVATION_STATE_CONFLICT")
            next_phase_state = expected_phase_state_revision + 1
            phase_updated = connection.execute(
                "UPDATE planning_price_experiment_phases SET status='PAUSED', "
                "state_revision=?, updated_at=? WHERE phase_id=? AND experiment_id=? "
                "AND owner_id=? AND store_id=? AND status='ACTIVE' AND state_revision=?",
                (next_phase_state, now, phase_id, experiment_id, scope["owner_id"],
                 scope["store_id"], expected_phase_state_revision),
            ).rowcount
            if phase_updated != 1:
                connection.rollback()
                return self._error("PLANNING_PRICE_EXPERIMENT_PHASE_STATE_CONFLICT")
            phase_revision = next_phase_state + phase_row["result_revision"]
            phase_revision_payload = {
                "schema_version": PlanningUnitEconomicsExperimentAdapter.PHASE_SCHEMA_VERSION,
                "phase_id": phase_id, "experiment_id": experiment_id,
                "state": "PAUSED", "state_revision": next_phase_state,
                "result_revision": phase_row["result_revision"],
                "phase": phase["phase"]["config"],
                "observation_id": observation_id,
                "confirmation": phase["phase"]["confirmation"],
            }
            encoded_phase_revision = self._encode(phase_revision_payload)
            if (encoded_phase_revision is None or len(encoded_phase_revision.encode("utf-8"))
                    > self.MAX_PRICE_EXPERIMENT_PAYLOAD_BYTES):
                connection.rollback()
                return self._error("PLANNING_PRICE_EXPERIMENT_PAUSE_INVALID")
            connection.execute(
                "INSERT INTO planning_price_experiment_phase_revisions "
                "(phase_id, experiment_id, owner_id, store_id, revision, state_revision, "
                "result_revision, payload_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (phase_id, experiment_id, scope["owner_id"], scope["store_id"],
                 phase_revision, next_phase_state, phase_row["result_revision"],
                 encoded_phase_revision, now),
            )
            next_state = expected_state_revision + 1
            experiment_updated = connection.execute(
                "UPDATE planning_price_experiments SET status='PAUSED', resume_target=?, "
                "state_revision=?, updated_at=? WHERE experiment_id=? AND owner_id=? "
                "AND store_id=? AND state_revision=? AND status=?",
                (decision["resume_target"], next_state, now, experiment_id,
                 scope["owner_id"], scope["store_id"], expected_state_revision,
                 experiment_row["status"]),
            ).rowcount
            if experiment_updated != 1:
                connection.rollback()
                return self._error("PLANNING_PRICE_EXPERIMENT_STATE_CONFLICT")
            self._insert_price_experiment_revision(
                connection, experiment_id, scope, next_state, next_state, "PAUSED",
                experiment["experiment"]["config"], now, decision["resume_target"],
            )
            identity = {name: experiment_row[name] for name in (
                "owner_id", "store_id", "product_id", "offer_id", "sku", "sale_schema",
            )}
            self._sync_active_sku_guard(connection, scope, identity)
            result = {
                "error": False, "experiment_id": experiment_id,
                "phase_id": phase_id, "observation_id": observation_id,
                "event_id": event["event_id"],
                "event_revision": event["event_revision"],
                "status": "PAUSED", "phase_status": "PAUSED",
                "resume_target": decision["resume_target"],
                "state_revision": next_state,
                "phase_state_revision": next_phase_state,
                "result_revision": experiment_row["result_revision"],
            }
            self._remember_price_experiment_idempotency(
                connection, scope, key, request_hash, result, now,
            )
            connection.commit()
            return result
        except sqlite3.IntegrityError:
            connection.rollback()
            return self._error("PLANNING_PRICE_EXPERIMENT_PAUSE_CONFLICT")
        except (ValueError, TypeError, OverflowError):
            connection.rollback()
            return self._error("PLANNING_CLOCK_UNAVAILABLE")
        except sqlite3.Error:
            connection.rollback()
            return self._error("PLANNING_STORAGE_UNAVAILABLE")
        finally:
            connection.close()

    def prepare_price_experiment_resume(
        self, experiment_id, payload, *, expected_state_revision,
        idempotency_key, owner_id=None, store_id=None,
    ):
        """Create a fresh planned segment while keeping the experiment paused."""
        scope = self._scope(owner_id, store_id)
        key = self._idempotency_key(idempotency_key)
        if (scope.get("error") or key is None
                or not self._valid_uuid_hex(experiment_id)
                or type(expected_state_revision) is not int
                or expected_state_revision < 1):
            return self._error("PLANNING_PRICE_EXPERIMENT_RESUME_INPUT_INVALID")
        request_hash = self._price_experiment_request_hash({
            "operation": "prepare_resume", "experiment_id": experiment_id,
            "expected_state_revision": expected_state_revision, "payload": payload,
        })
        if request_hash is None:
            return self._error("PLANNING_PRICE_EXPERIMENT_RESUME_INPUT_INVALID")
        try:
            connection = self.get_connection()
        except (sqlite3.Error, OSError):
            return self._error("PLANNING_STORAGE_UNAVAILABLE")
        try:
            connection.execute("BEGIN IMMEDIATE")
            replay = self._price_experiment_idempotent_result(
                connection, scope, key, request_hash,
            )
            if replay is not None:
                connection.commit()
                return replay
            experiment_row = connection.execute(
                "SELECT * FROM planning_price_experiments WHERE experiment_id=? "
                "AND owner_id=? AND store_id=?",
                (experiment_id, scope["owner_id"], scope["store_id"]),
            ).fetchone()
            if experiment_row is None:
                connection.rollback()
                return self._error("PLANNING_PRICE_EXPERIMENT_NOT_FOUND")
            if experiment_row["state_revision"] != expected_state_revision:
                connection.rollback()
                return self._error("PLANNING_PRICE_EXPERIMENT_STATE_CONFLICT")
            experiment = self._decode_price_experiment(experiment_row, scope)
            if experiment.get("error"):
                connection.rollback()
                return experiment
            resume_target = experiment_row["resume_target"]
            if experiment_row["status"] != "PAUSED" or resume_target not in {
                "READY", "CANDIDATE_READY",
            }:
                connection.rollback()
                return self._error("PLANNING_PRICE_EXPERIMENT_RESUME_STATE_INVALID")
            paused_row = connection.execute(
                "SELECT * FROM planning_price_experiment_phases WHERE experiment_id=? "
                "AND owner_id=? AND store_id=? AND status='PAUSED' "
                "ORDER BY segment_number DESC LIMIT 1",
                (experiment_id, scope["owner_id"], scope["store_id"]),
            ).fetchone()
            if paused_row is None:
                connection.rollback()
                return self._error("PLANNING_PRICE_EXPERIMENT_RESUME_PHASE_NOT_FOUND")
            paused = self._decode_price_experiment_phase(paused_row)
            if paused.get("error"):
                connection.rollback()
                return paused
            expected_kind = "BASELINE" if resume_target == "READY" else "CANDIDATE"
            identity = {name: experiment_row[name] for name in (
                "owner_id", "store_id", "product_id", "offer_id", "sku", "sale_schema",
            )}
            normalized = PlanningUnitEconomicsExperimentAdapter.normalize_phase(
                payload, identity,
            )
            if normalized is None:
                connection.rollback()
                return self._error("PLANNING_PRICE_EXPERIMENT_RESUME_PHASE_INVALID")
            if (paused["phase"]["kind"] != expected_kind
                    or normalized["kind"] != expected_kind
                    or normalized["planned_price_cents"]
                    != paused["phase"]["config"]["planned_price_cents"]
                    or normalized["expense_snapshot_id"]
                    != paused["phase"]["config"]["expense_snapshot_id"]):
                connection.rollback()
                return self._error("PLANNING_PRICE_EXPERIMENT_RESUME_SEGMENT_MISMATCH")
            if (normalized["kind"] == "CANDIDATE"
                    and normalized["planned_price_cents"]
                    not in experiment["experiment"]["config"]["candidate_prices_cents"]):
                connection.rollback()
                return self._error("PLANNING_PRICE_EXPERIMENT_CANDIDATE_NOT_SELECTED")
            phase_rows = connection.execute(
                "SELECT COUNT(*) FROM planning_price_experiment_phases WHERE "
                "experiment_id=? AND owner_id=? AND store_id=?",
                (experiment_id, scope["owner_id"], scope["store_id"]),
            ).fetchone()[0]
            pending_rows = connection.execute(
                "SELECT COUNT(*) FROM planning_price_experiment_phases WHERE "
                "experiment_id=? AND owner_id=? AND store_id=? AND status='PLANNED'",
                (experiment_id, scope["owner_id"], scope["store_id"]),
            ).fetchone()[0]
            if pending_rows:
                connection.rollback()
                return self._error("PLANNING_PRICE_EXPERIMENT_RESUME_SEGMENT_ALREADY_PREPARED")
            if phase_rows >= self.MAX_PRICE_EXPERIMENT_PHASES:
                connection.rollback()
                return self._error("PLANNING_PRICE_EXPERIMENT_PHASE_QUOTA_REACHED")
            if normalized["segment_number"] != phase_rows + 1:
                connection.rollback()
                return self._error("PLANNING_PRICE_EXPERIMENT_SEGMENT_SEQUENCE_INVALID")
            duration = (
                date.fromisoformat(normalized["planned_to_date"])
                - date.fromisoformat(normalized["planned_from_date"])
            ).days + 1
            if duration > experiment["experiment"]["config"]["planned_duration_days"]:
                connection.rollback()
                return self._error("PLANNING_PRICE_EXPERIMENT_PHASE_DURATION_INVALID")
            reference_error = self._validate_price_experiment_references(
                connection, experiment["experiment"]["config"], scope,
            )
            if reference_error:
                connection.rollback()
                return self._error(reference_error)
            now = self._timestamp()
            phase_id = uuid4().hex
            encoded_phase = self._encode(normalized)
            connection.execute(
                "INSERT INTO planning_price_experiment_phases "
                "(phase_id, experiment_id, owner_id, store_id, product_id, offer_id, "
                "sku, sale_schema, segment_number, kind, status, state_revision, "
                "result_revision, expense_snapshot_id, payload_json, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PLANNED', 1, 0, ?, ?, ?, ?)",
                (phase_id, experiment_id, scope["owner_id"], scope["store_id"],
                 experiment_row["product_id"], experiment_row["offer_id"],
                 experiment_row["sku"], experiment_row["sale_schema"],
                 normalized["segment_number"], normalized["kind"],
                 normalized["expense_snapshot_id"], encoded_phase, now, now),
            )
            phase_revision_payload = {
                "schema_version": normalized["schema_version"],
                "phase_id": phase_id, "experiment_id": experiment_id,
                "state": "PLANNED", "state_revision": 1, "result_revision": 0,
                "phase": normalized,
            }
            encoded_revision = self._encode(phase_revision_payload)
            connection.execute(
                "INSERT INTO planning_price_experiment_phase_revisions "
                "(phase_id, experiment_id, owner_id, store_id, revision, state_revision, "
                "result_revision, payload_json, created_at) VALUES (?, ?, ?, ?, 1, 1, 0, ?, ?)",
                (phase_id, experiment_id, scope["owner_id"], scope["store_id"],
                 encoded_revision, now),
            )
            resume_payload = UnitEconomicsExperimentControlService.normalize_resume_event({
                "schema_version": 1, "event_kind": "RESUME_SEGMENT_PREPARED",
                "previous_phase_id": paused_row["phase_id"], "phase_id": phase_id,
                "resume_target": resume_target, "source": "OWNER_ACTION",
            }, expected_resume_target=resume_target)
            if resume_payload is None:
                connection.rollback()
                return self._error("PLANNING_PRICE_EXPERIMENT_RESUME_INPUT_INVALID")
            event = self._insert_price_experiment_event(
                connection, scope, experiment_id, phase_id, resume_payload, now,
            )
            if event.get("error"):
                connection.rollback()
                return event
            next_state = expected_state_revision + 1
            changed = connection.execute(
                "UPDATE planning_price_experiments SET state_revision=?, updated_at=? "
                "WHERE experiment_id=? AND owner_id=? AND store_id=? "
                "AND state_revision=? AND status='PAUSED' AND resume_target=?",
                (next_state, now, experiment_id, scope["owner_id"], scope["store_id"],
                 expected_state_revision, resume_target),
            ).rowcount
            if changed != 1:
                connection.rollback()
                return self._error("PLANNING_PRICE_EXPERIMENT_STATE_CONFLICT")
            self._insert_price_experiment_revision(
                connection, experiment_id, scope, next_state, next_state, "PAUSED",
                experiment["experiment"]["config"], now, resume_target,
            )
            result = {
                "error": False, "experiment_id": experiment_id,
                "previous_phase_id": paused_row["phase_id"], "phase_id": phase_id,
                "event_id": event["event_id"], "event_revision": event["event_revision"],
                "status": "PAUSED", "phase_status": "PLANNED",
                "resume_target": resume_target, "state_revision": next_state,
                "phase_state_revision": 1,
                "result_revision": experiment_row["result_revision"],
                "requires_fresh_confirmation": True,
            }
            self._remember_price_experiment_idempotency(
                connection, scope, key, request_hash, result, now,
            )
            connection.commit()
            return result
        except sqlite3.IntegrityError:
            connection.rollback()
            return self._error("PLANNING_PRICE_EXPERIMENT_RESUME_CONFLICT")
        except (ValueError, TypeError, OverflowError):
            connection.rollback()
            return self._error("PLANNING_CLOCK_UNAVAILABLE")
        except sqlite3.Error:
            connection.rollback()
            return self._error("PLANNING_STORAGE_UNAVAILABLE")
        finally:
            connection.close()

    def get_price_experiment_phase_collection_replay(
        self, experiment_id, phase_id, *, expected_state_revision,
        expected_phase_state_revision, expected_result_revision, idempotency_key,
        owner_id=None, store_id=None,
    ):
        """Resolve a completed collection callback before issuing source reads."""
        scope = self._scope(owner_id, store_id)
        key = self._idempotency_key(idempotency_key)
        if (scope.get("error") or key is None
                or not self._valid_uuid_hex(experiment_id)
                or not self._valid_uuid_hex(phase_id)
                or type(expected_state_revision) is not int or expected_state_revision < 1
                or type(expected_phase_state_revision) is not int or expected_phase_state_revision < 1
                or type(expected_result_revision) is not int or expected_result_revision < 0):
            return self._error("PLANNING_PRICE_EXPERIMENT_COLLECTION_INPUT_INVALID")
        request_hash = self._price_experiment_request_hash({
            "operation": "phase_collection", "experiment_id": experiment_id,
            "phase_id": phase_id, "expected_state_revision": expected_state_revision,
            "expected_phase_state_revision": expected_phase_state_revision,
            "expected_result_revision": expected_result_revision,
        })
        if request_hash is None:
            return self._error("PLANNING_PRICE_EXPERIMENT_COLLECTION_INPUT_INVALID")
        try:
            connection = self.get_connection()
        except (sqlite3.Error, OSError):
            return self._error("PLANNING_STORAGE_UNAVAILABLE")
        try:
            row = connection.execute(
                "SELECT request_hash,result_json FROM planning_price_experiment_idempotency "
                "WHERE owner_id=? AND store_id=? AND idempotency_key=?",
                (scope["owner_id"], scope["store_id"], key),
            ).fetchone()
            if row is None:
                return {"error": False, "found": False, "read_only": True}
            if row["request_hash"] != request_hash:
                return self._error("PLANNING_PRICE_EXPERIMENT_IDEMPOTENCY_CONFLICT")
            try:
                saved = json.loads(row["result_json"])
            except (TypeError, ValueError):
                return self._error("PLANNING_PRICE_EXPERIMENT_IDEMPOTENCY_RECORD_CORRUPT")
            if (not isinstance(saved, dict) or saved.get("error") is not False
                    or not self._valid_uuid_hex(saved.get("experiment_id"))
                    or not self._valid_uuid_hex(saved.get("phase_id"))
                    or not isinstance(saved.get("collection_id"), str)
                    or PlanningUnitEconomicsExperimentAdapter._HEX_256.fullmatch(
                        saved["collection_id"],
                    ) is None):
                return self._error("PLANNING_PRICE_EXPERIMENT_IDEMPOTENCY_RECORD_CORRUPT")
            return {"error": False, "found": True, "result": saved, "read_only": True}
        except sqlite3.Error:
            return self._error("PLANNING_STORAGE_UNAVAILABLE")
        finally:
            connection.close()

    def append_price_experiment_phase_collection_result(
        self, experiment_id, phase_id, collection_payload, result_payload, *,
        expected_state_revision, expected_phase_state_revision,
        expected_result_revision, idempotency_key, owner_id=None, store_id=None,
    ):
        """Atomically append one bounded phase collection and its pending result."""
        scope = self._scope(owner_id, store_id)
        key = self._idempotency_key(idempotency_key)
        collection = PlanningUnitEconomicsExperimentAdapter.normalize_phase_collection(
            collection_payload, scope,
        )
        collection_encoded = self._encode(collection) if collection is not None else None
        result = PlanningUnitEconomicsExperimentAdapter.normalize_result(result_payload)
        result_encoded = self._encode(result) if result is not None else None
        if (scope.get("error") or key is None or not self._valid_uuid_hex(experiment_id)
                or not self._valid_uuid_hex(phase_id)
                or type(expected_state_revision) is not int or expected_state_revision < 1
                or type(expected_phase_state_revision) is not int
                or expected_phase_state_revision < 1
                or type(expected_result_revision) is not int or expected_result_revision < 0
                or collection is None or result is None
                or collection["experiment_id"] != experiment_id
                or collection["phase_id"] != phase_id
                or len(collection_encoded.encode("utf-8")) > self.MAX_PRICE_EXPERIMENT_PAYLOAD_BYTES
                or len(result_encoded.encode("utf-8")) > self.MAX_PRICE_EXPERIMENT_PAYLOAD_BYTES):
            return self._error("PLANNING_PRICE_EXPERIMENT_COLLECTION_INVALID")
        collection_id = hashlib.sha256(collection_encoded.encode("utf-8")).hexdigest()
        if collection_id not in result["snapshot_refs"]:
            return self._error("PLANNING_PRICE_EXPERIMENT_COLLECTION_RESULT_MISMATCH")
        request_hash = self._price_experiment_request_hash({
            "operation": "phase_collection",
            "experiment_id": experiment_id, "phase_id": phase_id,
            "expected_state_revision": expected_state_revision,
            "expected_phase_state_revision": expected_phase_state_revision,
            "expected_result_revision": expected_result_revision,
        })
        if request_hash is None:
            return self._error("PLANNING_PRICE_EXPERIMENT_COLLECTION_INVALID")
        try:
            connection = self.get_connection()
        except (sqlite3.Error, OSError):
            return self._error("PLANNING_STORAGE_UNAVAILABLE")
        try:
            connection.execute("BEGIN IMMEDIATE")
            replay = self._price_experiment_idempotent_result(connection, scope, key, request_hash)
            if replay is not None:
                connection.commit()
                return replay
            experiment = connection.execute(
                "SELECT * FROM planning_price_experiments WHERE experiment_id=? "
                "AND owner_id=? AND store_id=?",
                (experiment_id, scope["owner_id"], scope["store_id"]),
            ).fetchone()
            phase = connection.execute(
                "SELECT * FROM planning_price_experiment_phases WHERE phase_id=? "
                "AND experiment_id=? AND owner_id=? AND store_id=?",
                (phase_id, experiment_id, scope["owner_id"], scope["store_id"]),
            ).fetchone()
            if experiment is None or phase is None:
                connection.rollback()
                return self._error("PLANNING_PRICE_EXPERIMENT_PHASE_NOT_FOUND")
            if experiment["state_revision"] != expected_state_revision:
                connection.rollback()
                return self._error("PLANNING_PRICE_EXPERIMENT_STATE_CONFLICT")
            if (phase["state_revision"] != expected_phase_state_revision
                    or phase["result_revision"] != expected_result_revision):
                connection.rollback()
                return self._error("PLANNING_PRICE_EXPERIMENT_RESULT_CONFLICT")
            expected_phase_status = {
                "BASELINE": "BASELINE_ACTIVE", "CANDIDATE": "CANDIDATE_ACTIVE",
            }.get(phase["kind"])
            if (phase["status"] != "ACTIVE" or experiment["status"] != expected_phase_status
                    or collection["observation_id"] != phase["observation_id"]
                    or any(collection["identity"].get(field) != experiment[field] for field in (
                        "owner_id", "store_id", "product_id", "offer_id", "sku", "sale_schema",
                    ))):
                connection.rollback()
                return self._error("PLANNING_PRICE_EXPERIMENT_COLLECTION_STATE_CONFLICT")
            try:
                phase_config = json.loads(phase["payload_json"])
            except (TypeError, ValueError):
                connection.rollback()
                return self._error("PLANNING_PRICE_EXPERIMENT_PHASE_CORRUPT")
            if collection["seller_price_cents"] != phase_config.get("planned_price_cents"):
                connection.rollback()
                return self._error("PLANNING_PRICE_EXPERIMENT_COLLECTION_PRICE_MISMATCH")
            required_refs = {experiment["expense_snapshot_id"], phase["expense_snapshot_id"]}
            if not required_refs.issubset(set(result["snapshot_refs"])):
                connection.rollback()
                return self._error("PLANNING_PRICE_EXPERIMENT_RESULT_SNAPSHOT_MISMATCH")
            for snapshot_ref in result["snapshot_refs"]:
                if snapshot_ref == collection_id:
                    continue
                if not self._price_experiment_snapshot_ref_exists(
                    connection, snapshot_ref, scope, experiment,
                ):
                    connection.rollback()
                    return self._error("PLANNING_PRICE_EXPERIMENT_RESULT_SNAPSHOT_MISMATCH")
            if phase["result_revision"] >= self.MAX_PRICE_EXPERIMENT_RESULTS_PER_PHASE:
                connection.rollback()
                return self._error("PLANNING_PRICE_EXPERIMENT_RESULT_QUOTA_REACHED")
            existing_collection = connection.execute(
                "SELECT collection_revision,payload_json,content_hash FROM "
                "planning_price_experiment_phase_collections WHERE collection_id=? "
                "AND experiment_id=? AND owner_id=? AND store_id=?",
                (collection_id, experiment_id, scope["owner_id"], scope["store_id"]),
            ).fetchone()
            if existing_collection is not None:
                if (existing_collection["payload_json"] != collection_encoded
                        or existing_collection["content_hash"] != collection_id):
                    connection.rollback()
                    return self._error("PLANNING_PRICE_EXPERIMENT_COLLECTION_HASH_CONFLICT")
                collection_revision = existing_collection["collection_revision"]
            else:
                collection_revision = connection.execute(
                    "SELECT COALESCE(MAX(collection_revision),0)+1 FROM "
                    "planning_price_experiment_phase_collections WHERE phase_id=? "
                    "AND owner_id=? AND store_id=?",
                    (phase_id, scope["owner_id"], scope["store_id"]),
                ).fetchone()[0]
                if collection_revision > self.MAX_PRICE_EXPERIMENT_COLLECTIONS_PER_PHASE:
                    connection.rollback()
                    return self._error("PLANNING_PRICE_EXPERIMENT_COLLECTION_QUOTA_REACHED")
                now = self._timestamp()
                connection.execute(
                    """INSERT INTO planning_price_experiment_phase_collections
                       (experiment_id,phase_id,owner_id,store_id,collection_revision,
                        collection_id,payload_json,content_hash,created_at)
                       VALUES (?,?,?,?,?,?,?,?,?)""",
                    (experiment_id, phase_id, scope["owner_id"], scope["store_id"],
                     collection_revision, collection_id, collection_encoded,
                     collection_id, now),
                )
            phase_result_revision = expected_result_revision + 1
            experiment_result_revision = experiment["result_revision"] + 1
            now = self._timestamp()
            result_digest = hashlib.sha256(result_encoded.encode("utf-8")).hexdigest()
            connection.execute(
                """INSERT INTO planning_price_experiment_results
                   (experiment_id,phase_id,owner_id,store_id,result_revision,
                    payload_json,content_hash,created_at) VALUES (?,?,?,?,?,?,?,?)""",
                (experiment_id, phase_id, scope["owner_id"], scope["store_id"],
                 phase_result_revision, result_encoded, result_digest, now),
            )
            changed = connection.execute(
                "UPDATE planning_price_experiment_phases SET result_revision=?,updated_at=? "
                "WHERE phase_id=? AND experiment_id=? AND owner_id=? AND store_id=? "
                "AND status='ACTIVE' AND state_revision=? AND result_revision=?",
                (phase_result_revision, now, phase_id, experiment_id, scope["owner_id"],
                 scope["store_id"], expected_phase_state_revision, expected_result_revision),
            ).rowcount
            if changed != 1:
                connection.rollback()
                return self._error("PLANNING_PRICE_EXPERIMENT_RESULT_CONFLICT")
            changed = connection.execute(
                "UPDATE planning_price_experiments SET result_revision=?,updated_at=? "
                "WHERE experiment_id=? AND owner_id=? AND store_id=? AND state_revision=? "
                "AND status=?",
                (experiment_result_revision, now, experiment_id, scope["owner_id"],
                 scope["store_id"], expected_state_revision, expected_phase_status),
            ).rowcount
            if changed != 1:
                connection.rollback()
                return self._error("PLANNING_PRICE_EXPERIMENT_STATE_CONFLICT")
            revision_payload = {
                "schema_version": PlanningUnitEconomicsExperimentAdapter.PHASE_SCHEMA_VERSION,
                "phase_id": phase_id, "experiment_id": experiment_id,
                "state": phase["status"], "state_revision": phase["state_revision"],
                "result_revision": phase_result_revision,
                "phase": phase_config,
            }
            phase_revision = phase["state_revision"] + phase_result_revision
            connection.execute(
                """INSERT INTO planning_price_experiment_phase_revisions
                   (phase_id,experiment_id,owner_id,store_id,revision,state_revision,
                    result_revision,payload_json,created_at) VALUES (?,?,?,?,?,?,?,?,?)""",
                (phase_id, experiment_id, scope["owner_id"], scope["store_id"],
                 phase_revision, phase["state_revision"], phase_result_revision,
                 self._encode(revision_payload), now),
            )
            saved = {
                "error": False, "experiment_id": experiment_id, "phase_id": phase_id,
                "collection_id": collection_id, "collection_revision": collection_revision,
                "result_revision": phase_result_revision,
                "experiment_result_revision": experiment_result_revision,
                "state_revision": expected_state_revision,
                "phase_state_revision": expected_phase_state_revision,
            }
            self._remember_price_experiment_idempotency(
                connection, scope, key, request_hash, saved, now,
            )
            connection.commit()
            return saved
        except sqlite3.IntegrityError:
            connection.rollback()
            return self._error("PLANNING_PRICE_EXPERIMENT_COLLECTION_CONFLICT")
        except (ValueError, TypeError, OverflowError):
            connection.rollback()
            return self._error("PLANNING_CLOCK_UNAVAILABLE")
        except sqlite3.Error:
            connection.rollback()
            return self._error("PLANNING_STORAGE_UNAVAILABLE")
        finally:
            connection.close()

    def _price_experiment_snapshot_ref_exists(self, connection, snapshot_id, scope, experiment):
        snapshot = connection.execute(
            """SELECT 1 FROM planning_unit_economics_snapshots
               WHERE snapshot_id=? AND owner_id=? AND store_id=? AND product_id=?
                 AND offer_id=? AND sku=? AND sale_schema=?""",
            (snapshot_id, scope["owner_id"], scope["store_id"], experiment["product_id"],
             experiment["offer_id"], experiment["sku"], experiment["sale_schema"]),
        ).fetchone()
        if snapshot is not None:
            return True
        collection = connection.execute(
            """SELECT 1 FROM planning_price_experiment_phase_collections
               WHERE collection_id=? AND experiment_id=? AND owner_id=? AND store_id=?""",
            (snapshot_id, experiment["experiment_id"], scope["owner_id"], scope["store_id"]),
        ).fetchone()
        return collection is not None

    def list_price_experiment_phase_collections(
        self, experiment_id, phase_id, *, limit=10, offset=0,
        owner_id=None, store_id=None,
    ):
        scope = self._scope(owner_id, store_id)
        if (scope.get("error") or not self._valid_uuid_hex(experiment_id)
                or not self._valid_uuid_hex(phase_id) or type(limit) is not int
                or not 1 <= limit <= self.MAX_PAGE_SIZE
                or type(offset) is not int or offset < 0):
            return self._error("PLANNING_PRICE_EXPERIMENT_COLLECTION_INPUT_INVALID")
        try:
            connection = self.get_connection()
        except (sqlite3.Error, OSError):
            return self._error("PLANNING_STORAGE_UNAVAILABLE")
        try:
            phase = connection.execute(
                "SELECT product_id,offer_id,sku,sale_schema FROM planning_price_experiment_phases "
                "WHERE experiment_id=? AND phase_id=? AND owner_id=? AND store_id=?",
                (experiment_id, phase_id, scope["owner_id"], scope["store_id"]),
            ).fetchone()
            if phase is None:
                return self._error("PLANNING_PRICE_EXPERIMENT_PHASE_NOT_FOUND")
            rows = connection.execute(
                "SELECT collection_revision,collection_id,payload_json,content_hash,created_at "
                "FROM planning_price_experiment_phase_collections WHERE experiment_id=? "
                "AND phase_id=? AND owner_id=? AND store_id=? "
                "ORDER BY collection_revision DESC LIMIT ? OFFSET ?",
                (experiment_id, phase_id, scope["owner_id"], scope["store_id"], limit + 1, offset),
            ).fetchall()
            items = []
            for row in rows[:limit]:
                try:
                    payload = json.loads(row["payload_json"])
                except (TypeError, ValueError):
                    return self._error("PLANNING_PRICE_EXPERIMENT_COLLECTION_CORRUPT")
                normalized = PlanningUnitEconomicsExperimentAdapter.normalize_phase_collection(
                    payload, scope,
                )
                digest = hashlib.sha256(row["payload_json"].encode("utf-8")).hexdigest()
                if (normalized is None or digest != row["collection_id"]
                        or digest != row["content_hash"]
                        or normalized["experiment_id"] != experiment_id
                        or normalized["phase_id"] != phase_id
                        or any(normalized["identity"].get(key) != phase[key] for key in (
                            "product_id", "offer_id", "sku", "sale_schema",
                        ))):
                    return self._error("PLANNING_PRICE_EXPERIMENT_COLLECTION_CORRUPT")
                items.append({
                    "collection_revision": row["collection_revision"],
                    "collection_id": row["collection_id"], "created_at": row["created_at"],
                    "payload": normalized,
                })
            return {
                "error": False, "items": items,
                "has_more": len(rows) > limit,
                "next_offset": offset + limit if len(rows) > limit else None,
            }
        except sqlite3.Error:
            return self._error("PLANNING_STORAGE_UNAVAILABLE")
        finally:
            connection.close()

    def append_price_experiment_result(
        self, experiment_id, phase_id, payload, *, expected_state_revision,
        expected_phase_state_revision, expected_result_revision, idempotency_key,
        owner_id=None, store_id=None, comparison_guard=None,
    ):
        scope = self._scope(owner_id, store_id)
        key = self._idempotency_key(idempotency_key)
        normalized = PlanningUnitEconomicsExperimentAdapter.normalize_result(payload)
        encoded = self._encode(normalized) if normalized is not None else None
        guard = self._normalize_price_experiment_comparison_guard(comparison_guard)
        if comparison_guard is not None and guard is None:
            return self._error("PLANNING_PRICE_EXPERIMENT_RESULT_INVALID")
        if (scope.get("error") or key is None or not self._valid_uuid_hex(experiment_id)
                or not self._valid_uuid_hex(phase_id)
                or type(expected_state_revision) is not int or expected_state_revision < 1
                or type(expected_phase_state_revision) is not int
                or expected_phase_state_revision < 1
                or type(expected_result_revision) is not int or expected_result_revision < 0
                or encoded is None or len(encoded.encode("utf-8"))
                > self.MAX_PRICE_EXPERIMENT_PAYLOAD_BYTES):
            return self._error("PLANNING_PRICE_EXPERIMENT_RESULT_INVALID")
        request_payload = {
            "operation": "append_result", "experiment_id": experiment_id,
            "phase_id": phase_id, "expected_state_revision": expected_state_revision,
            "expected_phase_state_revision": expected_phase_state_revision,
            "expected_result_revision": expected_result_revision, "payload": normalized,
        }
        if guard is not None:
            request_payload["comparison_guard"] = guard
        request_hash = self._price_experiment_request_hash(request_payload)
        if request_hash is None:
            return self._error("PLANNING_PRICE_EXPERIMENT_RESULT_INVALID")
        try:
            connection = self.get_connection()
        except (sqlite3.Error, OSError):
            return self._error("PLANNING_STORAGE_UNAVAILABLE")
        try:
            connection.execute("BEGIN IMMEDIATE")
            replay = self._price_experiment_idempotent_result(
                connection, scope, key, request_hash,
            )
            if replay is not None:
                connection.commit()
                return replay
            experiment = connection.execute(
                "SELECT * FROM planning_price_experiments WHERE experiment_id=? "
                "AND owner_id=? AND store_id=?",
                (experiment_id, scope["owner_id"], scope["store_id"]),
            ).fetchone()
            phase = connection.execute(
                "SELECT * FROM planning_price_experiment_phases WHERE phase_id=? "
                "AND experiment_id=? AND owner_id=? AND store_id=?",
                (phase_id, experiment_id, scope["owner_id"], scope["store_id"]),
            ).fetchone()
            if experiment is None or phase is None:
                connection.rollback()
                return self._error("PLANNING_PRICE_EXPERIMENT_PHASE_NOT_FOUND")
            decoded_experiment = self._decode_price_experiment(experiment, scope)
            if decoded_experiment.get("error"):
                connection.rollback()
                return decoded_experiment
            if experiment["state_revision"] != expected_state_revision:
                connection.rollback()
                return self._error("PLANNING_PRICE_EXPERIMENT_STATE_CONFLICT")
            if experiment["status"] in {"CANCELLED", "COMPLETED", "ARCHIVED"}:
                connection.rollback()
                return self._error("PLANNING_PRICE_EXPERIMENT_TERMINAL")
            if (phase["state_revision"] != expected_phase_state_revision
                    or phase["result_revision"] != expected_result_revision):
                connection.rollback()
                return self._error("PLANNING_PRICE_EXPERIMENT_RESULT_CONFLICT")
            if phase["status"] == "ARCHIVED":
                connection.rollback()
                return self._error("PLANNING_PRICE_EXPERIMENT_PHASE_ARCHIVED")
            if guard is not None:
                baseline = connection.execute(
                    "SELECT state_revision,result_revision,status,kind FROM planning_price_experiment_phases "
                    "WHERE phase_id=? AND experiment_id=? AND owner_id=? AND store_id=?",
                    (guard["baseline_phase_id"], experiment_id,
                     scope["owner_id"], scope["store_id"]),
                ).fetchone()
                if (baseline is None or baseline["status"] == "ARCHIVED"
                        or baseline["kind"] != "BASELINE" or phase["kind"] != "CANDIDATE"
                        or guard["baseline_phase_id"] == phase_id
                        or baseline["state_revision"] != guard["baseline_state_revision"]
                        or baseline["result_revision"] != guard["baseline_result_revision"]):
                    connection.rollback()
                    return self._error("PLANNING_PRICE_EXPERIMENT_COMPARISON_CONFLICT")
                for guarded_phase_id, expected_collection_id, expected_event_revision in (
                    (guard["baseline_phase_id"], guard["baseline_collection_id"],
                     guard["baseline_control_event_revision"]),
                    (phase_id, guard["candidate_collection_id"],
                     guard["candidate_control_event_revision"]),
                ):
                    latest_collection = connection.execute(
                        "SELECT collection_id FROM planning_price_experiment_phase_collections "
                        "WHERE phase_id=? AND experiment_id=? AND owner_id=? AND store_id=? "
                        "ORDER BY collection_revision DESC LIMIT 1",
                        (guarded_phase_id, experiment_id, scope["owner_id"], scope["store_id"]),
                    ).fetchone()
                    latest_event = connection.execute(
                        "SELECT COALESCE(MAX(event_revision),0) AS revision "
                        "FROM planning_price_experiment_events WHERE phase_id=? AND experiment_id=? "
                        "AND owner_id=? AND store_id=?",
                        (guarded_phase_id, experiment_id, scope["owner_id"], scope["store_id"]),
                    ).fetchone()
                    if (latest_collection is None
                            or latest_collection["collection_id"] != expected_collection_id
                            or latest_event["revision"] != expected_event_revision):
                        connection.rollback()
                        return self._error("PLANNING_PRICE_EXPERIMENT_COMPARISON_CONFLICT")
            expected_refs = {experiment["expense_snapshot_id"], phase["expense_snapshot_id"]}
            if not expected_refs.issubset(set(normalized["snapshot_refs"])):
                connection.rollback()
                return self._error("PLANNING_PRICE_EXPERIMENT_RESULT_SNAPSHOT_MISMATCH")
            for snapshot_id in normalized["snapshot_refs"]:
                if not self._price_experiment_snapshot_ref_exists(
                    connection, snapshot_id, scope, experiment,
                ):
                    connection.rollback()
                    return self._error("PLANNING_PRICE_EXPERIMENT_RESULT_SNAPSHOT_MISMATCH")
            if phase["result_revision"] >= self.MAX_PRICE_EXPERIMENT_RESULTS_PER_PHASE:
                connection.rollback()
                return self._error("PLANNING_PRICE_EXPERIMENT_RESULT_QUOTA_REACHED")
            phase_result_revision = expected_result_revision + 1
            experiment_result_revision = experiment["result_revision"] + 1
            now = self._timestamp()
            digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
            connection.execute(
                """INSERT INTO planning_price_experiment_results
                   (experiment_id, phase_id, owner_id, store_id, result_revision,
                    payload_json, content_hash, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (experiment_id, phase_id, scope["owner_id"], scope["store_id"],
                 phase_result_revision, encoded, digest, now),
            )
            changed = connection.execute(
                "UPDATE planning_price_experiment_phases SET result_revision=?, updated_at=? "
                "WHERE phase_id=? AND experiment_id=? AND owner_id=? AND store_id=? "
                "AND state_revision=? AND result_revision=? AND status!='ARCHIVED'",
                (phase_result_revision, now, phase_id, experiment_id, scope["owner_id"],
                 scope["store_id"], expected_phase_state_revision, expected_result_revision),
            ).rowcount
            if changed != 1:
                connection.rollback()
                return self._error("PLANNING_PRICE_EXPERIMENT_RESULT_CONFLICT")
            connection.execute(
                "UPDATE planning_price_experiments SET result_revision=?, updated_at=? "
                "WHERE experiment_id=? AND owner_id=? AND store_id=? AND state_revision=?",
                (experiment_result_revision, now, experiment_id, scope["owner_id"],
                 scope["store_id"], expected_state_revision),
            )
            phase_revision = phase["state_revision"] + phase["result_revision"] + 1
            phase_revision_payload = {
                "schema_version": PlanningUnitEconomicsExperimentAdapter.PHASE_SCHEMA_VERSION,
                "phase_id": phase_id, "experiment_id": experiment_id,
                "state": phase["status"], "state_revision": phase["state_revision"],
                "result_revision": phase_result_revision,
                "phase": json.loads(phase["payload_json"]),
            }
            connection.execute(
                """INSERT INTO planning_price_experiment_phase_revisions
                   (phase_id, experiment_id, owner_id, store_id, revision, state_revision,
                    result_revision, payload_json, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (phase_id, experiment_id, scope["owner_id"], scope["store_id"],
                 phase_revision, phase["state_revision"], phase_result_revision,
                 self._encode(phase_revision_payload), now),
            )
            result = {
                "error": False, "experiment_id": experiment_id, "phase_id": phase_id,
                "result_revision": phase_result_revision,
                "experiment_result_revision": experiment_result_revision,
                "state_revision": expected_state_revision,
                "phase_state_revision": expected_phase_state_revision,
            }
            self._remember_price_experiment_idempotency(
                connection, scope, key, request_hash, result, now,
            )
            connection.commit()
            return result
        except sqlite3.IntegrityError:
            connection.rollback()
            return self._error("PLANNING_PRICE_EXPERIMENT_RESULT_CONFLICT")
        except (ValueError, TypeError, OverflowError):
            connection.rollback()
            return self._error("PLANNING_CLOCK_UNAVAILABLE")
        except sqlite3.Error:
            connection.rollback()
            return self._error("PLANNING_STORAGE_UNAVAILABLE")
        finally:
            connection.close()

    @classmethod
    def _normalize_price_experiment_comparison_guard(cls, value):
        if value is None:
            return None
        fields = {
            "baseline_phase_id", "baseline_state_revision", "baseline_result_revision",
            "baseline_collection_id", "candidate_collection_id",
            "baseline_control_event_revision", "candidate_control_event_revision",
        }
        if (not isinstance(value, dict) or set(value) != fields
                or not cls._valid_uuid_hex(value.get("baseline_phase_id"))
                or any(type(value.get(key)) is not int or value[key] < minimum for key, minimum in (
                    ("baseline_state_revision", 1), ("baseline_result_revision", 0),
                    ("baseline_control_event_revision", 0),
                    ("candidate_control_event_revision", 0),
                ))
                or any(not isinstance(value.get(key), str)
                       or re.fullmatch(r"[a-f0-9]{64}", value[key]) is None
                       for key in ("baseline_collection_id", "candidate_collection_id"))):
            return None
        return dict(value)

    def get_price_experiment(
        self, experiment_id, *, owner_id=None, store_id=None,
    ):
        scope = self._scope(owner_id, store_id)
        if scope.get("error") or not self._valid_uuid_hex(experiment_id):
            return self._error("PLANNING_PRICE_EXPERIMENT_NOT_FOUND")
        try:
            connection = self.get_connection()
        except (sqlite3.Error, OSError):
            return self._error("PLANNING_STORAGE_UNAVAILABLE")
        try:
            row = connection.execute(
                "SELECT * FROM planning_price_experiments WHERE experiment_id=? "
                "AND owner_id=? AND store_id=?",
                (experiment_id, scope["owner_id"], scope["store_id"]),
            ).fetchone()
            if row is None:
                return self._error("PLANNING_PRICE_EXPERIMENT_NOT_FOUND")
            decoded = self._decode_price_experiment(row, scope)
            if decoded.get("error"):
                return decoded
            return {"error": False, "experiment": decoded["experiment"]}
        except sqlite3.Error:
            return self._error("PLANNING_STORAGE_UNAVAILABLE")
        finally:
            connection.close()

    def get_price_experiment_plan_readiness(
        self, experiment_id, *, owner_id=None, store_id=None,
    ):
        """Return the fixed RUB/unit readiness gates for one saved experiment."""
        result = self.get_price_experiment(
            experiment_id, owner_id=owner_id, store_id=store_id,
        )
        if result.get("error"):
            return result
        experiment = result["experiment"]
        readiness = UnitEconomicsExperimentPlanService.evaluate(
            experiment["config"],
        )
        if readiness.get("error"):
            return self._error("PLANNING_PRICE_EXPERIMENT_PLAN_CORRUPT")
        return {
            "error": False, "experiment_id": experiment_id,
            "status": readiness["status"],
            "eligible_for_ready": readiness["eligible_for_ready"],
            "target_metric": readiness["target_metric"],
            "planned_duration_days": readiness["planned_duration_days"],
            "minimum_maturity_days": readiness["minimum_maturity_days"],
            "minimum_maturity_units": readiness["minimum_maturity_units"],
            "reason_codes": readiness["reason_codes"], "read_only": True,
        }

    def get_price_experiment_frozen_snapshot(
        self, experiment_id, *, owner_id=None, store_id=None,
    ):
        """Reopen the exact persisted inputs referenced by an experiment.

        This deliberately resolves only immutable local revisions. It never
        refreshes a plan, tariff, observation, or expense snapshot from a
        provider; callers must request a separate refresh explicitly.
        """
        experiment_result = self.get_price_experiment(
            experiment_id, owner_id=owner_id, store_id=store_id,
        )
        if experiment_result.get("error"):
            return experiment_result
        experiment = experiment_result["experiment"]
        references = experiment["config"]["source_references"]
        identity = {
            key: experiment[key]
            for key in ("owner_id", "store_id", "product_id", "offer_id", "sku", "sale_schema")
        }

        plan_ref = references["plan"]
        plan_result = self.get_document(
            plan_ref["document_id"], revision=plan_ref["revision"],
            owner_id=identity["owner_id"], store_id=identity["store_id"],
        )
        if plan_result.get("error"):
            return self._error("PLANNING_PRICE_EXPERIMENT_FROZEN_PLAN_UNAVAILABLE")
        plan = plan_result["document"]
        if not self._saved_plan_contains_observation_identity(
            self._encode(plan["payload"]), identity, identity["store_id"],
        ):
            return self._error("PLANNING_PRICE_EXPERIMENT_FROZEN_PLAN_SCOPE_MISMATCH")

        snapshot_id = references["expense_snapshot_id"]
        expense_result = self.get_unit_economics_expense_snapshot(
            snapshot_id, owner_id=identity["owner_id"], store_id=identity["store_id"],
        )
        if expense_result.get("error"):
            return self._error("PLANNING_PRICE_EXPERIMENT_FROZEN_EXPENSE_UNAVAILABLE")
        expense_payload = expense_result["payload"]
        expense_identity = expense_payload["identity"]
        if any(expense_identity.get(key) != identity[key] for key in (
            "owner_id", "store_id", "product_id", "offer_id", "sku", "sale_schema",
        )):
            return self._error("PLANNING_PRICE_EXPERIMENT_FROZEN_EXPENSE_SCOPE_MISMATCH")

        tariff_result = None
        tariff_ref = references["tariff"]
        if tariff_ref is not None:
            tariff_result = self.get_tariff_profile(
                tariff_ref["profile_id"], revision=tariff_ref["revision"],
                owner_id=identity["owner_id"], store_id=identity["store_id"],
            )
            if tariff_result.get("error"):
                return self._error("PLANNING_PRICE_EXPERIMENT_FROZEN_TARIFF_UNAVAILABLE")
            tariff_identity = tariff_result["profile"]["identity"]
            if any(tariff_identity.get(key) != identity[key] for key in (
                "product_id", "offer_id", "sku",
            )) or tariff_result["profile"].get("sale_schema") != identity["sale_schema"]:
                return self._error("PLANNING_PRICE_EXPERIMENT_FROZEN_TARIFF_SCOPE_MISMATCH")

        observation_result = None
        observation_ref = references["observation"]
        if observation_ref is not None:
            observation_result = self.get_unit_price_observation(
                observation_ref["observation_id"],
                result_revision=observation_ref["result_revision"],
                owner_id=identity["owner_id"], store_id=identity["store_id"],
            )
            if observation_result.get("error"):
                return self._error("PLANNING_PRICE_EXPERIMENT_FROZEN_QUANTITY_UNAVAILABLE")
            observation = observation_result["observation"]
            observation_identity = observation.get("identity", {})
            if observation.get("store_id") != identity["store_id"] or any(
                observation_identity.get(key) != identity[key] for key in (
                    "product_id", "offer_id", "sku", "sale_schema",
                )
            ) or observation_result.get("result") is None:
                return self._error("PLANNING_PRICE_EXPERIMENT_FROZEN_QUANTITY_SCOPE_MISMATCH")

        frozen_inputs = {
            "plan": {
                "document_id": plan["document_id"], "revision": plan["revision"],
                "schema_version": plan["payload"]["schema_version"],
                "calculation_version": plan["payload"]["calculation_version"],
                "payload": plan["payload"],
            },
            "expense_snapshot": {
                "snapshot_id": expense_result["snapshot_id"],
                "schema_version": expense_result["schema_version"],
                "payload": expense_payload,
            },
            "tariff": None if tariff_result is None else {
                "profile_id": tariff_ref["profile_id"],
                "revision": tariff_ref["revision"],
                "profile": tariff_result["profile"],
            },
            "quantity": None if observation_result is None else {
                "observation_id": observation_ref["observation_id"],
                "result_revision": observation_ref["result_revision"],
                "observation": observation_result["observation"],
                "result": observation_result["result"]["payload"],
            },
        }
        encoded = self._encode(frozen_inputs)
        if (encoded is None or len(encoded.encode("utf-8"))
                > 4 * self.MAX_PRICE_EXPERIMENT_PAYLOAD_BYTES + 4096):
            return self._error("PLANNING_PRICE_EXPERIMENT_FROZEN_SNAPSHOT_TOO_LARGE")
        return {
            "error": False, "experiment": experiment,
            "frozen_inputs": frozen_inputs, "read_only": True,
            "source_io": False,
        }

    def list_price_experiment_revisions(
        self, experiment_id, *, limit=10, offset=0, owner_id=None, store_id=None,
    ):
        scope = self._scope(owner_id, store_id)
        if (scope.get("error") or not self._valid_uuid_hex(experiment_id)
                or type(limit) is not int or not 1 <= limit <= self.MAX_PAGE_SIZE
                or type(offset) is not int or offset < 0):
            return self._error("PLANNING_PRICE_EXPERIMENT_INPUT_INVALID")
        try:
            connection = self.get_connection()
        except (sqlite3.Error, OSError):
            return self._error("PLANNING_STORAGE_UNAVAILABLE")
        try:
            if connection.execute(
                "SELECT 1 FROM planning_price_experiments WHERE experiment_id=? "
                "AND owner_id=? AND store_id=?",
                (experiment_id, scope["owner_id"], scope["store_id"]),
            ).fetchone() is None:
                return self._error("PLANNING_PRICE_EXPERIMENT_NOT_FOUND")
            rows = connection.execute(
                "SELECT revision, state_revision, payload_json, created_at "
                "FROM planning_price_experiment_revisions WHERE experiment_id=? "
                "AND owner_id=? AND store_id=? ORDER BY revision DESC LIMIT ? OFFSET ?",
                (experiment_id, scope["owner_id"], scope["store_id"], limit + 1, offset),
            ).fetchall()
            items = []
            for row in rows[:limit]:
                try:
                    payload = json.loads(row["payload_json"])
                except (ValueError, TypeError):
                    return self._error("PLANNING_PRICE_EXPERIMENT_REVISION_CORRUPT")
                revision_payload = payload if isinstance(payload, dict) else {}
                resume_target = revision_payload.get("resume_target")
                normalized = PlanningUnitEconomicsExperimentAdapter.normalize_experiment(
                    revision_payload.get("config"), scope,
                    allow_incomplete=revision_payload.get("state") in {
                        "DRAFT", "CANCELLED", "ARCHIVED",
                    },
                )
                if (normalized is None or payload.get("schema_version") != 1
                        or payload.get("experiment_id") != experiment_id
                        or payload.get("state") not in {
                            "DRAFT", "READY", "BASELINE_ACTIVE", "BASELINE_REVIEW",
                            "CANDIDATE_READY", "CANDIDATE_ACTIVE", "CANDIDATE_REVIEW",
                            "PAUSED", "CANCELLED", "COMPLETED", "ARCHIVED",
                        }
                        or payload.get("state_revision") != row["state_revision"]):
                    return self._error("PLANNING_PRICE_EXPERIMENT_REVISION_CORRUPT")
                if (resume_target not in {None, "READY", "CANDIDATE_READY"}
                        or (payload["state"] == "PAUSED") != (resume_target is not None)):
                    return self._error("PLANNING_PRICE_EXPERIMENT_REVISION_CORRUPT")
                items.append({
                    "revision": row["revision"], "state_revision": row["state_revision"],
                    "status": payload["state"], "created_at": row["created_at"],
                    "resume_target": resume_target,
                    "config": normalized,
                })
            return {
                "error": False, "items": items, "has_more": len(rows) > limit,
                "next_offset": offset + limit if len(rows) > limit else None,
            }
        except sqlite3.Error:
            return self._error("PLANNING_STORAGE_UNAVAILABLE")
        finally:
            connection.close()

    def list_price_experiment_events(
        self, experiment_id, *, phase_id=None, limit=10, offset=0,
        owner_id=None, store_id=None,
    ):
        scope = self._scope(owner_id, store_id)
        if (scope.get("error") or not self._valid_uuid_hex(experiment_id)
                or (phase_id is not None and not self._valid_uuid_hex(phase_id))
                or type(limit) is not int or not 1 <= limit <= self.MAX_PAGE_SIZE
                or type(offset) is not int or offset < 0):
            return self._error("PLANNING_PRICE_EXPERIMENT_EVENT_INPUT_INVALID")
        try:
            connection = self.get_connection()
        except (sqlite3.Error, OSError):
            return self._error("PLANNING_STORAGE_UNAVAILABLE")
        try:
            if connection.execute(
                "SELECT 1 FROM planning_price_experiments WHERE experiment_id=? "
                "AND owner_id=? AND store_id=?",
                (experiment_id, scope["owner_id"], scope["store_id"]),
            ).fetchone() is None:
                return self._error("PLANNING_PRICE_EXPERIMENT_NOT_FOUND")
            clauses = ["experiment_id=?", "owner_id=?", "store_id=?"]
            params = [experiment_id, scope["owner_id"], scope["store_id"]]
            if phase_id is not None:
                clauses.append("phase_id=?")
                params.append(phase_id)
            rows = connection.execute(
                "SELECT * FROM planning_price_experiment_events WHERE "
                + " AND ".join(clauses)
                + " ORDER BY event_revision DESC LIMIT ? OFFSET ?",
                (*params, limit + 1, offset),
            ).fetchall()
            items = []
            for row in rows[:limit]:
                try:
                    raw_payload = json.loads(row["payload_json"])
                except (TypeError, ValueError):
                    return self._error("PLANNING_PRICE_EXPERIMENT_EVENT_CORRUPT")
                if row["event_kind"] == "CONTROL_UPDATE":
                    payload = UnitEconomicsExperimentControlService.normalize_event(
                        raw_payload, expected_phase_id=row["phase_id"],
                    )
                elif row["event_kind"] == "PAUSE":
                    payload = UnitEconomicsExperimentControlService.normalize_pause_event(
                        raw_payload, expected_phase_id=row["phase_id"],
                    )
                elif row["event_kind"] == "RESUME_SEGMENT_PREPARED":
                    payload = UnitEconomicsExperimentControlService.normalize_resume_event(
                        raw_payload,
                    )
                else:
                    payload = None
                digest = hashlib.sha256(row["payload_json"].encode("utf-8")).hexdigest()
                if (payload is None or payload.get("event_kind") != row["event_kind"]
                        or payload.get("phase_id") != row["phase_id"]
                        or digest != row["payload_hash"]
                        or type(row["event_revision"]) is not int
                        or not 1 <= row["event_revision"] <= self.MAX_PRICE_EXPERIMENT_EVENTS):
                    return self._error("PLANNING_PRICE_EXPERIMENT_EVENT_CORRUPT")
                if not self._valid_uuid_hex(row["event_id"]):
                    return self._error("PLANNING_PRICE_EXPERIMENT_EVENT_CORRUPT")
                items.append({
                    "event_id": row["event_id"],
                    "event_revision": row["event_revision"],
                    "event_kind": row["event_kind"],
                    "created_at": row["created_at"], "payload": payload,
                })
            return {
                "error": False, "items": items,
                "has_more": len(rows) > limit,
                "next_offset": offset + limit if len(rows) > limit else None,
            }
        except sqlite3.Error:
            return self._error("PLANNING_STORAGE_UNAVAILABLE")
        finally:
            connection.close()

    def list_price_experiments(
        self, *, include_archived=False, limit=10, offset=0,
        owner_id=None, store_id=None,
    ):
        scope = self._scope(owner_id, store_id)
        if (scope.get("error") or type(include_archived) is not bool
                or type(limit) is not int or not 1 <= limit <= self.MAX_PAGE_SIZE
                or type(offset) is not int or offset < 0):
            return self._error("PLANNING_PRICE_EXPERIMENT_INPUT_INVALID")
        clauses = ["owner_id=?", "store_id=?"]
        params = [scope["owner_id"], scope["store_id"]]
        if not include_archived:
            clauses.append("status!='ARCHIVED'")
        try:
            connection = self.get_connection()
        except (sqlite3.Error, OSError):
            return self._error("PLANNING_STORAGE_UNAVAILABLE")
        try:
            rows = connection.execute(
                "SELECT * FROM planning_price_experiments WHERE " + " AND ".join(clauses)
                + " ORDER BY updated_at DESC, experiment_id LIMIT ? OFFSET ?",
                (*params, limit + 1, offset),
            ).fetchall()
            items = []
            for row in rows[:limit]:
                decoded = self._decode_price_experiment(row, scope)
                if decoded.get("error"):
                    return decoded
                items.append(decoded["experiment"])
            return {
                "error": False, "items": items, "has_more": len(rows) > limit,
                "next_offset": offset + limit if len(rows) > limit else None,
            }
        except sqlite3.Error:
            return self._error("PLANNING_STORAGE_UNAVAILABLE")
        finally:
            connection.close()

    def list_price_experiment_phases(
        self, experiment_id, *, limit=10, offset=0, owner_id=None, store_id=None,
    ):
        scope = self._scope(owner_id, store_id)
        if (scope.get("error") or not self._valid_uuid_hex(experiment_id)
                or type(limit) is not int or not 1 <= limit <= self.MAX_PAGE_SIZE
                or type(offset) is not int or offset < 0):
            return self._error("PLANNING_PRICE_EXPERIMENT_PHASE_INPUT_INVALID")
        try:
            connection = self.get_connection()
        except (sqlite3.Error, OSError):
            return self._error("PLANNING_STORAGE_UNAVAILABLE")
        try:
            if connection.execute(
                "SELECT 1 FROM planning_price_experiments WHERE experiment_id=? "
                "AND owner_id=? AND store_id=?",
                (experiment_id, scope["owner_id"], scope["store_id"]),
            ).fetchone() is None:
                return self._error("PLANNING_PRICE_EXPERIMENT_NOT_FOUND")
            rows = connection.execute(
                "SELECT * FROM planning_price_experiment_phases WHERE experiment_id=? "
                "AND owner_id=? AND store_id=? ORDER BY segment_number LIMIT ? OFFSET ?",
                (experiment_id, scope["owner_id"], scope["store_id"], limit + 1, offset),
            ).fetchall()
            items = []
            for row in rows[:limit]:
                decoded = self._decode_price_experiment_phase(row)
                if decoded.get("error"):
                    return decoded
                items.append(decoded["phase"])
            return {
                "error": False, "items": items, "has_more": len(rows) > limit,
                "next_offset": offset + limit if len(rows) > limit else None,
            }
        except sqlite3.Error:
            return self._error("PLANNING_STORAGE_UNAVAILABLE")
        finally:
            connection.close()

    def list_price_experiment_phase_revisions(
        self, experiment_id, phase_id, *, limit=10, offset=0,
        owner_id=None, store_id=None,
    ):
        scope = self._scope(owner_id, store_id)
        if (scope.get("error") or not self._valid_uuid_hex(experiment_id)
                or not self._valid_uuid_hex(phase_id) or type(limit) is not int
                or not 1 <= limit <= self.MAX_PAGE_SIZE
                or type(offset) is not int or offset < 0):
            return self._error("PLANNING_PRICE_EXPERIMENT_PHASE_INPUT_INVALID")
        try:
            connection = self.get_connection()
        except (sqlite3.Error, OSError):
            return self._error("PLANNING_STORAGE_UNAVAILABLE")
        try:
            phase = connection.execute(
                "SELECT product_id, offer_id, sku, sale_schema FROM "
                "planning_price_experiment_phases WHERE phase_id=? AND experiment_id=? "
                "AND owner_id=? AND store_id=?",
                (phase_id, experiment_id, scope["owner_id"], scope["store_id"]),
            ).fetchone()
            if phase is None:
                return self._error("PLANNING_PRICE_EXPERIMENT_PHASE_NOT_FOUND")
            rows = connection.execute(
                "SELECT revision, state_revision, result_revision, payload_json, created_at "
                "FROM planning_price_experiment_phase_revisions WHERE phase_id=? "
                "AND experiment_id=? AND owner_id=? AND store_id=? "
                "ORDER BY revision DESC LIMIT ? OFFSET ?",
                (phase_id, experiment_id, scope["owner_id"], scope["store_id"],
                 limit + 1, offset),
            ).fetchall()
            items = []
            for row in rows[:limit]:
                try:
                    payload = json.loads(row["payload_json"])
                except (ValueError, TypeError):
                    return self._error("PLANNING_PRICE_EXPERIMENT_PHASE_REVISION_CORRUPT")
                normalized = PlanningUnitEconomicsExperimentAdapter.normalize_phase(
                    payload.get("phase") if isinstance(payload, dict) else None, {},
                )
                confirmation = None
                observation_id = None
                if isinstance(payload, dict):
                    observation_id = payload.get("observation_id")
                    raw_confirmation = payload.get("confirmation")
                    if raw_confirmation is not None:
                        confirmation = (
                            UnitEconomicsExperimentPhaseConfirmationService
                            .normalize_confirmation(raw_confirmation, normalized)
                            if normalized is not None else None
                        )
                if (normalized is None or payload.get("schema_version") != 1
                        or payload.get("phase_id") != phase_id
                        or payload.get("experiment_id") != experiment_id
                        or payload.get("state") not in {
                            "PLANNED", "ACTIVE", "FINISHED", "PAUSED", "ARCHIVED",
                        }
                        or payload.get("state_revision") != row["state_revision"]
                        or payload.get("result_revision") != row["result_revision"]
                        or row["result_revision"] > 20
                        or ("confirmation" in payload and payload.get("confirmation") is not None
                            and confirmation is None)
                        or ("observation_id" in payload and (
                            not isinstance(observation_id, str)
                            or self._valid_uuid_hex(observation_id) is not True
                        ))
                        or (confirmation is None) != (observation_id is None)):
                    return self._error("PLANNING_PRICE_EXPERIMENT_PHASE_REVISION_CORRUPT")
                items.append({
                    "revision": row["revision"], "state_revision": row["state_revision"],
                    "result_revision": row["result_revision"], "status": payload["state"],
                    "created_at": row["created_at"], "config": normalized,
                    "observation_id": observation_id,
                    "confirmation": confirmation,
                    "identity": dict(phase),
                })
            return {
                "error": False, "items": items, "has_more": len(rows) > limit,
                "next_offset": offset + limit if len(rows) > limit else None,
            }
        except sqlite3.Error:
            return self._error("PLANNING_STORAGE_UNAVAILABLE")
        finally:
            connection.close()

    def list_price_experiment_results(
        self, experiment_id, phase_id, *, limit=10, offset=0,
        owner_id=None, store_id=None,
    ):
        scope = self._scope(owner_id, store_id)
        if (scope.get("error") or not self._valid_uuid_hex(experiment_id)
                or not self._valid_uuid_hex(phase_id) or type(limit) is not int
                or not 1 <= limit <= self.MAX_PAGE_SIZE
                or type(offset) is not int or offset < 0):
            return self._error("PLANNING_PRICE_EXPERIMENT_RESULT_INPUT_INVALID")
        try:
            connection = self.get_connection()
        except (sqlite3.Error, OSError):
            return self._error("PLANNING_STORAGE_UNAVAILABLE")
        try:
            phase_exists = connection.execute(
                "SELECT product_id, offer_id, sku, sale_schema FROM "
                "planning_price_experiment_phases WHERE experiment_id=? AND phase_id=? "
                "AND owner_id=? AND store_id=?",
                (experiment_id, phase_id, scope["owner_id"], scope["store_id"]),
            ).fetchone()
            if phase_exists is None:
                return self._error("PLANNING_PRICE_EXPERIMENT_PHASE_NOT_FOUND")
            rows = connection.execute(
                "SELECT result_revision, payload_json, content_hash, created_at "
                "FROM planning_price_experiment_results WHERE experiment_id=? AND phase_id=? "
                "AND owner_id=? AND store_id=? ORDER BY result_revision DESC LIMIT ? OFFSET ?",
                (experiment_id, phase_id, scope["owner_id"], scope["store_id"],
                 limit + 1, offset),
            ).fetchall()
            items = []
            for row in rows[:limit]:
                try:
                    payload = json.loads(row["payload_json"])
                except (ValueError, TypeError):
                    return self._error("PLANNING_PRICE_EXPERIMENT_RESULT_CORRUPT")
                normalized = PlanningUnitEconomicsExperimentAdapter.normalize_result(payload)
                digest = hashlib.sha256(row["payload_json"].encode("utf-8")).hexdigest()
                if normalized is None or digest != row["content_hash"]:
                    return self._error("PLANNING_PRICE_EXPERIMENT_RESULT_CORRUPT")
                for snapshot_id in normalized["snapshot_refs"]:
                    reference_identity = {
                        "experiment_id": experiment_id,
                        "product_id": phase_exists["product_id"],
                        "offer_id": phase_exists["offer_id"],
                        "sku": phase_exists["sku"],
                        "sale_schema": phase_exists["sale_schema"],
                    }
                    if not self._price_experiment_snapshot_ref_exists(
                        connection, snapshot_id, scope, reference_identity,
                    ):
                        return self._error("PLANNING_PRICE_EXPERIMENT_RESULT_CORRUPT")
                items.append({
                    "result_revision": row["result_revision"],
                    "created_at": row["created_at"], "content_hash": digest,
                    "payload": normalized,
                })
            return {
                "error": False, "items": items, "has_more": len(rows) > limit,
                "next_offset": offset + limit if len(rows) > limit else None,
            }
        except sqlite3.Error:
            return self._error("PLANNING_STORAGE_UNAVAILABLE")
        finally:
            connection.close()

    def record_price_experiment_owner_decision(
        self, experiment_id, payload, *, expected_state_revision, idempotency_key,
        owner_id=None, store_id=None,
    ):
        """Append an owner choice bound to the latest candidate comparison result."""
        scope = self._scope(owner_id, store_id)
        key = self._idempotency_key(idempotency_key)
        normalized = PlanningUnitEconomicsExperimentAdapter.normalize_owner_decision(payload)
        if (scope.get("error") or key is None or not self._valid_uuid_hex(experiment_id)
                or type(expected_state_revision) is not int or expected_state_revision < 1
                or normalized is None):
            return self._error("PLANNING_PRICE_EXPERIMENT_DECISION_INVALID")
        request_hash = self._price_experiment_request_hash({
            "operation": "owner_decision", "experiment_id": experiment_id,
            "expected_state_revision": expected_state_revision, "payload": normalized,
        })
        if request_hash is None:
            return self._error("PLANNING_PRICE_EXPERIMENT_DECISION_INVALID")
        try:
            connection = self.get_connection()
        except (sqlite3.Error, OSError):
            return self._error("PLANNING_STORAGE_UNAVAILABLE")
        try:
            connection.execute("BEGIN IMMEDIATE")
            replay = self._price_experiment_idempotent_result(connection, scope, key, request_hash)
            if replay is not None:
                connection.commit()
                return replay
            experiment = connection.execute(
                "SELECT * FROM planning_price_experiments WHERE experiment_id=? "
                "AND owner_id=? AND store_id=?",
                (experiment_id, scope["owner_id"], scope["store_id"]),
            ).fetchone()
            if experiment is None:
                connection.rollback()
                return self._error("PLANNING_PRICE_EXPERIMENT_NOT_FOUND")
            if (experiment["state_revision"] != expected_state_revision
                    or experiment["status"] != "CANDIDATE_REVIEW"):
                connection.rollback()
                return self._error("PLANNING_PRICE_EXPERIMENT_DECISION_STATE_CONFLICT")
            candidate = connection.execute(
                "SELECT * FROM planning_price_experiment_phases WHERE phase_id=? "
                "AND experiment_id=? AND owner_id=? AND store_id=?",
                (normalized["result_phase_id"], experiment_id,
                 scope["owner_id"], scope["store_id"]),
            ).fetchone()
            if (candidate is None or candidate["kind"] != "CANDIDATE"
                    or candidate["status"] != "FINISHED"):
                connection.rollback()
                return self._error("PLANNING_PRICE_EXPERIMENT_DECISION_RESULT_INVALID")
            latest_result = connection.execute(
                "SELECT MAX(result_revision) FROM planning_price_experiment_results "
                "WHERE experiment_id=? AND phase_id=? AND owner_id=? AND store_id=?",
                (experiment_id, normalized["result_phase_id"],
                 scope["owner_id"], scope["store_id"]),
            ).fetchone()[0]
            if latest_result != normalized["result_revision"]:
                connection.rollback()
                return self._error("PLANNING_PRICE_EXPERIMENT_DECISION_RESULT_STALE")
            result_row = connection.execute(
                "SELECT payload_json, content_hash FROM planning_price_experiment_results "
                "WHERE experiment_id=? AND phase_id=? AND owner_id=? AND store_id=? "
                "AND result_revision=?",
                (experiment_id, normalized["result_phase_id"], scope["owner_id"],
                 scope["store_id"], normalized["result_revision"]),
            ).fetchone()
            try:
                result_payload = json.loads(result_row["payload_json"]) if result_row else None
            except (TypeError, ValueError):
                result_payload = None
            result_payload = PlanningUnitEconomicsExperimentAdapter.normalize_result(result_payload)
            if (result_payload is None or result_row is None
                    or hashlib.sha256(result_row["payload_json"].encode("utf-8")).hexdigest()
                    != result_row["content_hash"]):
                connection.rollback()
                return self._error("PLANNING_PRICE_EXPERIMENT_DECISION_RESULT_INVALID")

            decision_type = normalized["decision_type"]
            selected_phase_id = normalized["selected_phase_id"]
            if decision_type == "KEEP_BASELINE_PRICE":
                selected = connection.execute(
                    "SELECT kind, segment_number FROM planning_price_experiment_phases "
                    "WHERE phase_id=? AND experiment_id=? AND owner_id=? AND store_id=?",
                    (selected_phase_id, experiment_id, scope["owner_id"], scope["store_id"]),
                ).fetchone()
                if (selected is None or selected["kind"] != "BASELINE"
                        or selected["segment_number"] != 1):
                    connection.rollback()
                    return self._error("PLANNING_PRICE_EXPERIMENT_DECISION_SELECTION_INVALID")
            elif decision_type == "SELECT_EVALUATED_CANDIDATE":
                if (selected_phase_id != normalized["result_phase_id"]
                        or result_payload["outcome"] not in {
                            "NO_CLEAR_DIFFERENCE", "CANDIDATE_BETTER_IN_MODEL",
                            "BASELINE_BETTER_IN_MODEL",
                        }
                        or result_payload.get("comparison") is None):
                    connection.rollback()
                    return self._error("PLANNING_PRICE_EXPERIMENT_DECISION_SELECTION_INVALID")

            count = connection.execute(
                "SELECT COUNT(*) FROM planning_price_experiment_decisions "
                "WHERE experiment_id=? AND owner_id=? AND store_id=?",
                (experiment_id, scope["owner_id"], scope["store_id"]),
            ).fetchone()[0]
            decision_revision = count + 1
            if decision_revision > self.MAX_PRICE_EXPERIMENT_DECISIONS:
                connection.rollback()
                return self._error("PLANNING_PRICE_EXPERIMENT_DECISION_QUOTA_REACHED")
            now = self._timestamp()
            encoded = self._encode(normalized)
            if (encoded is None or len(encoded.encode("utf-8"))
                    > self.MAX_PRICE_EXPERIMENT_PAYLOAD_BYTES):
                connection.rollback()
                return self._error("PLANNING_PRICE_EXPERIMENT_DECISION_INVALID")
            decision_id = uuid4().hex
            digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
            connection.execute(
                """INSERT INTO planning_price_experiment_decisions
                   (decision_id, experiment_id, owner_id, store_id, decision_revision,
                    state_revision, decision_type, result_phase_id, result_revision,
                    selected_phase_id, payload_json, content_hash, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (decision_id, experiment_id, scope["owner_id"], scope["store_id"],
                 decision_revision, expected_state_revision, decision_type,
                 normalized["result_phase_id"], normalized["result_revision"],
                 selected_phase_id, encoded, digest, now),
            )
            response = {
                "error": False, "decision_id": decision_id,
                "experiment_id": experiment_id, "decision_revision": decision_revision,
                "state_revision": expected_state_revision, "payload": normalized,
            }
            self._remember_price_experiment_idempotency(
                connection, scope, key, request_hash, response, now,
            )
            connection.commit()
            return response
        except sqlite3.IntegrityError:
            connection.rollback()
            return self._error("PLANNING_PRICE_EXPERIMENT_DECISION_CONFLICT")
        except (ValueError, TypeError, OverflowError):
            connection.rollback()
            return self._error("PLANNING_CLOCK_UNAVAILABLE")
        except sqlite3.Error:
            connection.rollback()
            return self._error("PLANNING_STORAGE_UNAVAILABLE")
        finally:
            connection.close()

    def list_price_experiment_owner_decisions(
        self, experiment_id, *, limit=10, offset=0, owner_id=None, store_id=None,
    ):
        scope = self._scope(owner_id, store_id)
        if (scope.get("error") or not self._valid_uuid_hex(experiment_id)
                or type(limit) is not int or not 1 <= limit <= self.MAX_PAGE_SIZE
                or type(offset) is not int or offset < 0):
            return self._error("PLANNING_PRICE_EXPERIMENT_DECISION_INPUT_INVALID")
        try:
            connection = self.get_connection()
        except (sqlite3.Error, OSError):
            return self._error("PLANNING_STORAGE_UNAVAILABLE")
        try:
            exists = connection.execute(
                "SELECT 1 FROM planning_price_experiments WHERE experiment_id=? "
                "AND owner_id=? AND store_id=?",
                (experiment_id, scope["owner_id"], scope["store_id"]),
            ).fetchone()
            if exists is None:
                return self._error("PLANNING_PRICE_EXPERIMENT_NOT_FOUND")
            rows = connection.execute(
                "SELECT decision_id, decision_revision, state_revision, decision_type, "
                "result_phase_id, result_revision, selected_phase_id, payload_json, "
                "content_hash, created_at FROM planning_price_experiment_decisions "
                "WHERE experiment_id=? AND owner_id=? AND store_id=? "
                "ORDER BY decision_revision DESC LIMIT ? OFFSET ?",
                (experiment_id, scope["owner_id"], scope["store_id"], limit + 1, offset),
            ).fetchall()
            items = []
            for row in rows[:limit]:
                try:
                    payload = json.loads(row["payload_json"])
                except (TypeError, ValueError):
                    return self._error("PLANNING_PRICE_EXPERIMENT_DECISION_CORRUPT")
                normalized = PlanningUnitEconomicsExperimentAdapter.normalize_owner_decision(payload)
                digest = hashlib.sha256(row["payload_json"].encode("utf-8")).hexdigest()
                if (normalized is None or digest != row["content_hash"]
                        or normalized["result_phase_id"] != row["result_phase_id"]
                        or normalized["result_revision"] != row["result_revision"]
                        or normalized["decision_type"] != row["decision_type"]
                        or normalized["selected_phase_id"] != row["selected_phase_id"]
                        or not self._valid_uuid_hex(row["decision_id"])):
                    return self._error("PLANNING_PRICE_EXPERIMENT_DECISION_CORRUPT")
                items.append({
                    "decision_id": row["decision_id"],
                    "decision_revision": row["decision_revision"],
                    "state_revision": row["state_revision"],
                    "created_at": row["created_at"], "content_hash": digest,
                    "payload": normalized,
                })
            return {
                "error": False, "items": items, "has_more": len(rows) > limit,
                "next_offset": offset + limit if len(rows) > limit else None,
            }
        except sqlite3.Error:
            return self._error("PLANNING_STORAGE_UNAVAILABLE")
        finally:
            connection.close()

    def transition_price_experiment(
        self, experiment_id, action, *, expected_state_revision, idempotency_key,
        owner_id=None, store_id=None,
    ):
        """Apply draft readiness/cancellation and owner-confirmed completion atomically."""
        scope = self._scope(owner_id, store_id)
        key = self._idempotency_key(idempotency_key)
        if (scope.get("error") or not self._valid_uuid_hex(experiment_id)
                or action not in {"cancel", "mark_ready", "complete"} or key is None
                or type(expected_state_revision) is not int or expected_state_revision < 1):
            return self._error("PLANNING_PRICE_EXPERIMENT_TRANSITION_INPUT_INVALID")
        request_hash = self._price_experiment_request_hash({
            "operation": action, "experiment_id": experiment_id,
            "expected_state_revision": expected_state_revision,
        })
        if request_hash is None:
            return self._error("PLANNING_PRICE_EXPERIMENT_TRANSITION_INPUT_INVALID")
        try:
            connection = self.get_connection()
        except (sqlite3.Error, OSError):
            return self._error("PLANNING_STORAGE_UNAVAILABLE")
        try:
            connection.execute("BEGIN IMMEDIATE")
            replay = self._price_experiment_idempotent_result(connection, scope, key, request_hash)
            if replay is not None:
                connection.commit()
                return replay
            row = connection.execute(
                "SELECT * FROM planning_price_experiments WHERE experiment_id=? "
                "AND owner_id=? AND store_id=?",
                (experiment_id, scope["owner_id"], scope["store_id"]),
            ).fetchone()
            if row is None:
                connection.rollback()
                return self._error("PLANNING_PRICE_EXPERIMENT_NOT_FOUND")
            if row["state_revision"] != expected_state_revision:
                connection.rollback()
                return self._error("PLANNING_PRICE_EXPERIMENT_STATE_CONFLICT")
            decoded = self._decode_price_experiment(row, scope)
            if decoded.get("error"):
                connection.rollback()
                return decoded
            readiness_passed = False
            decision_recorded = False
            if action == "mark_ready":
                readiness = UnitEconomicsExperimentPlanService.evaluate(
                    decoded["experiment"]["config"],
                )
                if readiness.get("error") or not readiness["eligible_for_ready"]:
                    connection.rollback()
                    return {
                        "error": True,
                        "code": "PLANNING_PRICE_EXPERIMENT_PLAN_INCOMPLETE",
                        "reason_codes": readiness.get("reason_codes", []),
                    }
                reference_error = self._validate_price_experiment_references(
                    connection, decoded["experiment"]["config"], scope,
                )
                if reference_error:
                    connection.rollback()
                    return self._error(reference_error)
                readiness_passed = True
            elif action == "complete":
                decision_row = connection.execute(
                    "SELECT * FROM planning_price_experiment_decisions "
                    "WHERE experiment_id=? AND owner_id=? AND store_id=? "
                    "ORDER BY decision_revision DESC LIMIT 1",
                    (experiment_id, scope["owner_id"], scope["store_id"]),
                ).fetchone()
                if decision_row is not None:
                    try:
                        decision_payload = json.loads(decision_row["payload_json"])
                    except (TypeError, ValueError):
                        decision_payload = None
                    decision_payload = PlanningUnitEconomicsExperimentAdapter.normalize_owner_decision(
                        decision_payload,
                    )
                    decision_hash = (hashlib.sha256(
                        decision_row["payload_json"].encode("utf-8"),
                    ).hexdigest() if decision_row is not None else None)
                    if (decision_payload is not None
                            and decision_hash == decision_row["content_hash"]
                            and decision_payload["decision_type"] == decision_row["decision_type"]
                            and decision_payload["result_phase_id"] == decision_row["result_phase_id"]
                            and decision_payload["result_revision"] == decision_row["result_revision"]
                            and decision_payload["selected_phase_id"] == decision_row["selected_phase_id"]
                            and decision_row["state_revision"] == expected_state_revision
                            and decision_payload["decision_type"] in {
                                "KEEP_BASELINE_PRICE", "SELECT_EVALUATED_CANDIDATE",
                                "STOP_WITHOUT_PRICE_CHANGE",
                            }):
                        latest_result = connection.execute(
                            "SELECT MAX(result_revision) FROM planning_price_experiment_results "
                            "WHERE experiment_id=? AND phase_id=? AND owner_id=? AND store_id=?",
                            (experiment_id, decision_payload["result_phase_id"],
                             scope["owner_id"], scope["store_id"]),
                        ).fetchone()[0]
                        decision_recorded = latest_result == decision_payload["result_revision"]
            decision = UnitEconomicsExperimentStateMachine.transition(
                row["status"], action, readiness_passed=readiness_passed,
                decision_recorded=decision_recorded,
            )
            if decision.get("error"):
                connection.rollback()
                return self._error("PLANNING_PRICE_EXPERIMENT_TRANSITION_NOT_ALLOWED")
            now = self._timestamp()
            next_state = expected_state_revision + 1
            changed = connection.execute(
                "UPDATE planning_price_experiments SET status=?, resume_target=NULL, "
                "state_revision=?, updated_at=? "
                "WHERE experiment_id=? AND owner_id=? AND store_id=? AND state_revision=? "
                "AND status=?",
                (decision["to_state"], next_state, now, experiment_id,
                 scope["owner_id"], scope["store_id"], expected_state_revision, row["status"]),
            ).rowcount
            if changed != 1:
                connection.rollback()
                return self._error("PLANNING_PRICE_EXPERIMENT_STATE_CONFLICT")
            self._insert_price_experiment_revision(
                connection, experiment_id, scope, next_state, next_state,
                decision["to_state"], decoded["experiment"]["config"], now,
            )
            result = {
                "error": False, "experiment_id": experiment_id,
                "status": decision["to_state"], "state_revision": next_state,
                "result_revision": row["result_revision"],
            }
            self._remember_price_experiment_idempotency(
                connection, scope, key, request_hash, result, now,
            )
            connection.commit()
            return result
        except sqlite3.IntegrityError:
            connection.rollback()
            return self._error("PLANNING_PRICE_EXPERIMENT_STATE_CONFLICT")
        except (ValueError, TypeError, OverflowError):
            connection.rollback()
            return self._error("PLANNING_CLOCK_UNAVAILABLE")
        except sqlite3.Error:
            connection.rollback()
            return self._error("PLANNING_STORAGE_UNAVAILABLE")
        finally:
            connection.close()

    def archive_price_experiment(
        self, experiment_id, *, expected_state_revision, idempotency_key,
        owner_id=None, store_id=None,
    ):
        scope = self._scope(owner_id, store_id)
        key = self._idempotency_key(idempotency_key)
        if (scope.get("error") or not self._valid_uuid_hex(experiment_id)
                or key is None or type(expected_state_revision) is not int
                or expected_state_revision < 1):
            return self._error("PLANNING_PRICE_EXPERIMENT_INPUT_INVALID")
        request_hash = self._price_experiment_request_hash({
            "operation": "archive", "experiment_id": experiment_id,
            "expected_state_revision": expected_state_revision,
        })
        try:
            connection = self.get_connection()
        except (sqlite3.Error, OSError):
            return self._error("PLANNING_STORAGE_UNAVAILABLE")
        try:
            connection.execute("BEGIN IMMEDIATE")
            replay = self._price_experiment_idempotent_result(
                connection, scope, key, request_hash,
            )
            if replay is not None:
                connection.commit()
                return replay
            row = connection.execute(
                "SELECT * FROM planning_price_experiments WHERE experiment_id=? "
                "AND owner_id=? AND store_id=?",
                (experiment_id, scope["owner_id"], scope["store_id"]),
            ).fetchone()
            if row is None:
                connection.rollback()
                return self._error("PLANNING_PRICE_EXPERIMENT_NOT_FOUND")
            if row["state_revision"] != expected_state_revision:
                connection.rollback()
                return self._error("PLANNING_PRICE_EXPERIMENT_STATE_CONFLICT")
            if row["status"] in {"BASELINE_ACTIVE", "CANDIDATE_ACTIVE"}:
                connection.rollback()
                return self._error("PLANNING_PRICE_EXPERIMENT_ACTIVE_CANNOT_ARCHIVE")
            if row["status"] == "ARCHIVED":
                connection.rollback()
                return self._error("PLANNING_PRICE_EXPERIMENT_ALREADY_ARCHIVED")
            decision = UnitEconomicsExperimentStateMachine.transition(
                row["status"], "archive",
            )
            if decision.get("error"):
                connection.rollback()
                return self._error("PLANNING_PRICE_EXPERIMENT_STATE_INVALID")
            next_state = expected_state_revision + 1
            revision = row["state_revision"] + 1
            now = self._timestamp()
            changed = connection.execute(
                "UPDATE planning_price_experiments SET status='ARCHIVED', resume_target=NULL, "
                "state_revision=?, updated_at=? WHERE experiment_id=? AND owner_id=? "
                "AND store_id=? AND state_revision=?",
                (next_state, now, experiment_id, scope["owner_id"], scope["store_id"],
                 expected_state_revision),
            ).rowcount
            if changed != 1:
                connection.rollback()
                return self._error("PLANNING_PRICE_EXPERIMENT_STATE_CONFLICT")
            decoded = self._decode_price_experiment(row, scope)
            if decoded.get("error"):
                connection.rollback()
                return decoded
            self._insert_price_experiment_revision(
                connection, experiment_id, scope, revision, next_state,
                "ARCHIVED", decoded["experiment"]["config"], now,
            )
            result = {
                "error": False, "experiment_id": experiment_id,
                "status": "ARCHIVED", "state_revision": next_state,
                "result_revision": row["result_revision"],
            }
            self._remember_price_experiment_idempotency(
                connection, scope, key, request_hash, result, now,
            )
            connection.commit()
            return result
        except sqlite3.IntegrityError:
            connection.rollback()
            return self._error("PLANNING_PRICE_EXPERIMENT_STATE_CONFLICT")
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
        legacy_candidate_fields = {
            "index", "result_revision", "status", "window_days", "successful_units",
            "price_cents", "evidence_age_days", "reasons", "warnings",
        }
        candidate_fields = legacy_candidate_fields | {
            "extended_cost_mode", "extended_cost_origin", "extended_cost_per_unit",
        }
        for item in quality["candidates"]:
            if (not isinstance(item, dict)
                    or frozenset(item) not in {
                        frozenset(legacy_candidate_fields), frozenset(candidate_fields),
                    }
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
            if set(item) == candidate_fields:
                if (item.get("extended_cost_mode") not in {
                        "NOT_APPLIED", "WINDOW_COST_ALLOCATION", "STRICT_RETAINED_COHORT",
                    }
                        or item.get("extended_cost_origin") not in {
                            "NOT_APPLIED", "CONFIRMED", "MANUAL_ASSUMPTION", "UNCONFIRMED",
                        }
                        or (item.get("extended_cost_per_unit") is not None and (
                            not isinstance(item["extended_cost_per_unit"], str)
                            or cls._decimal_string(item["extended_cost_per_unit"]) is False
                        ))):
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
        supported_versions = {1: 1, 2: 2, 3: 2, 4: 2}
        if (type(schema) is not int or schema not in supported_versions
                or type(calc) is not int or supported_versions[schema] != calc):
            return None
        if schema == 3 and kind != "single":
            return None
        has_extended_scenario = False
        normalized_items = []
        seen = set()
        for item in items:
            if not isinstance(item, dict) or set(item) - {
                "row_id", "identity", "inputs", "provenance", "sources", "projection",
                "extended_scenario", "strict_return_evidence",
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
            if schema == 3 or (schema == 4 and "tariff_resolution" in clean_sources):
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
                if advertising_basis is None and schema == 3:
                    return None
                if advertising_basis is not None and not isinstance(advertising_basis, dict):
                    return None
                if isinstance(advertising_basis, dict) and advertising_basis.get("mode") == "SAME_DRR":
                    if (set(advertising_basis) != {"mode", "revenue_basis", "rate", "origin"}
                            or advertising_basis.get("revenue_basis") != "SELLER_REVENUE"
                            or advertising_basis.get("rate") != clean_inputs.get("advertising_rate")
                            or advertising_basis.get("origin") != clean_provenance.get("advertising_rate")
                            or "advertising_mode" in clean_inputs
                            or "advertising_cost_per_unit" in clean_inputs):
                        return None
                elif isinstance(advertising_basis, dict) and advertising_basis.get("mode") == "ABSOLUTE_PER_SUCCESSFUL_UNIT":
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
                elif isinstance(advertising_basis, dict):
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
            extended_scenario = item.get("extended_scenario")
            strict_return_evidence = item.get("strict_return_evidence")
            if schema == 4:
                from services.planning_extended_scenario_adapter import PlanningExtendedScenarioAdapter
                if extended_scenario is not None:
                    extended_scenario = PlanningExtendedScenarioAdapter.project_extended(
                        extended_scenario
                    )
                    if extended_scenario is None:
                        return None
                    has_extended_scenario = True
                    if strict_return_evidence is not None:
                        expected_strict_identity = {
                            "owner_id": scope["owner_id"],
                            "store_id": scope["store_id"],
                            "product_id": product_id,
                            "offer_id": offer_id,
                            "sku": sku,
                            "sale_schema": str(identity.get("scheme") or "FBO").upper(),
                        }
                        strict_return_evidence = (
                            PlanningExtendedScenarioAdapter.project_strict_evidence(
                                strict_return_evidence, expected_strict_identity,
                            )
                        )
                        if strict_return_evidence is None:
                            return None
                elif strict_return_evidence is not None:
                    return None
            elif "extended_scenario" in item or "strict_return_evidence" in item:
                return None
            row_id = self._short_text(item.get("row_id"), 64, optional=True)
            normalized_item = {
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
            }
            if schema == 4 and extended_scenario is not None:
                normalized_item["extended_scenario"] = extended_scenario
                if strict_return_evidence is not None:
                    normalized_item["strict_return_evidence"] = strict_return_evidence
            normalized_items.append(normalized_item)
        if schema == 4 and not has_extended_scenario:
            return None
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
            connection.execute("""CREATE TABLE IF NOT EXISTS planning_unit_economics_snapshots (
                snapshot_id TEXT NOT NULL CHECK(length(snapshot_id)=64),
                owner_id TEXT NOT NULL,
                store_id TEXT NOT NULL,
                product_id TEXT NOT NULL,
                offer_id TEXT NOT NULL,
                sku TEXT NOT NULL,
                sale_schema TEXT NOT NULL CHECK(sale_schema IN ('FBO','FBS')),
                schema_version INTEGER NOT NULL CHECK(schema_version >= 1),
                payload_json TEXT NOT NULL CHECK(length(CAST(payload_json AS BLOB)) <= 65536),
                created_at TEXT NOT NULL,
                PRIMARY KEY(snapshot_id, owner_id, store_id),
                UNIQUE(snapshot_id, owner_id, store_id, product_id, offer_id, sku, sale_schema)
            )""")
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_unit_economics_snapshots_scope "
                "ON planning_unit_economics_snapshots(owner_id, store_id, product_id, offer_id, sku, created_at DESC)"
            )
            connection.execute("""CREATE TABLE IF NOT EXISTS planning_price_experiments (
                experiment_id TEXT NOT NULL CHECK(length(experiment_id)=32),
                owner_id TEXT NOT NULL,
                store_id TEXT NOT NULL,
                product_id TEXT NOT NULL,
                offer_id TEXT NOT NULL,
                sku TEXT NOT NULL,
                sale_schema TEXT NOT NULL CHECK(sale_schema IN ('FBO','FBS')),
                status TEXT NOT NULL CHECK(status IN (
                    'DRAFT','READY','BASELINE_ACTIVE','BASELINE_REVIEW','CANDIDATE_READY',
                    'CANDIDATE_ACTIVE','CANDIDATE_REVIEW','PAUSED','CANCELLED','COMPLETED','ARCHIVED'
                )),
                resume_target TEXT CHECK(resume_target IS NULL OR resume_target IN (
                    'READY','CANDIDATE_READY'
                )),
                state_revision INTEGER NOT NULL CHECK(state_revision >= 1),
                result_revision INTEGER NOT NULL DEFAULT 0 CHECK(result_revision >= 0),
                schema_version INTEGER NOT NULL CHECK(schema_version >= 1),
                calculation_mode TEXT NOT NULL CHECK(calculation_mode IN (
                    'WINDOW_COST_ALLOCATION','STRICT_RETAINED_COHORT'
                )),
                plan_document_id TEXT NOT NULL,
                plan_revision INTEGER NOT NULL CHECK(plan_revision >= 1),
                expense_snapshot_id TEXT NOT NULL,
                tariff_profile_id TEXT,
                tariff_revision INTEGER,
                observation_id TEXT,
                observation_result_revision INTEGER,
                config_json TEXT NOT NULL CHECK(length(CAST(config_json AS BLOB)) <= 65536),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY(experiment_id, owner_id, store_id),
                UNIQUE(experiment_id, owner_id, store_id, product_id, offer_id, sku, sale_schema),
                FOREIGN KEY(plan_document_id, owner_id, store_id, plan_revision)
                    REFERENCES planning_revisions(document_id, owner_id, store_id, revision),
                FOREIGN KEY(expense_snapshot_id, owner_id, store_id, product_id, offer_id, sku, sale_schema)
                    REFERENCES planning_unit_economics_snapshots(
                        snapshot_id, owner_id, store_id, product_id, offer_id, sku, sale_schema
                    ),
                FOREIGN KEY(tariff_profile_id, owner_id, store_id, tariff_revision)
                    REFERENCES planning_tariff_profile_revisions(profile_id, owner_id, store_id, revision),
                FOREIGN KEY(observation_id, owner_id, store_id, observation_result_revision)
                    REFERENCES planning_unit_price_observation_results(
                        observation_id, owner_id, store_id, result_revision
                    ),
                CHECK((tariff_profile_id IS NULL) = (tariff_revision IS NULL)),
                CHECK((observation_id IS NULL) = (observation_result_revision IS NULL))
            )""")
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_price_experiments_scope "
                "ON planning_price_experiments(owner_id, store_id, status, updated_at DESC)"
            )
            connection.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_price_experiments_one_active_sku "
                "ON planning_price_experiments(owner_id, store_id, product_id, offer_id, sku, sale_schema) "
                "WHERE status IN ('BASELINE_ACTIVE','CANDIDATE_ACTIVE')"
            )
            connection.execute("""CREATE TABLE IF NOT EXISTS planning_active_sku_guards (
                owner_id TEXT NOT NULL,
                store_id TEXT NOT NULL,
                product_id TEXT NOT NULL,
                offer_id TEXT NOT NULL,
                sku TEXT NOT NULL,
                sale_schema TEXT NOT NULL CHECK(sale_schema IN ('FBO','FBS')),
                operation_kind TEXT NOT NULL CHECK(operation_kind IN (
                    'OBSERVATION','EXPERIMENT','CONFLICT'
                )),
                operation_id TEXT,
                created_at TEXT NOT NULL,
                PRIMARY KEY(owner_id, store_id, product_id, offer_id, sku, sale_schema),
                CHECK((operation_kind='CONFLICT' AND operation_id IS NULL)
                    OR (operation_kind IN ('OBSERVATION','EXPERIMENT') AND operation_id IS NOT NULL))
            )""")
            connection.execute("""CREATE TABLE IF NOT EXISTS planning_price_experiment_revisions (
                experiment_id TEXT NOT NULL,
                owner_id TEXT NOT NULL,
                store_id TEXT NOT NULL,
                revision INTEGER NOT NULL CHECK(revision >= 1),
                state_revision INTEGER NOT NULL CHECK(state_revision >= 1),
                payload_json TEXT NOT NULL CHECK(length(CAST(payload_json AS BLOB)) <= 65536),
                created_at TEXT NOT NULL,
                PRIMARY KEY(experiment_id, owner_id, store_id, revision),
                UNIQUE(experiment_id, owner_id, store_id, state_revision),
                FOREIGN KEY(experiment_id, owner_id, store_id)
                    REFERENCES planning_price_experiments(experiment_id, owner_id, store_id)
            )""")
            connection.execute("""CREATE TABLE IF NOT EXISTS planning_price_experiment_phases (
                phase_id TEXT NOT NULL CHECK(length(phase_id)=32),
                experiment_id TEXT NOT NULL,
                owner_id TEXT NOT NULL,
                store_id TEXT NOT NULL,
                product_id TEXT NOT NULL,
                offer_id TEXT NOT NULL,
                sku TEXT NOT NULL,
                sale_schema TEXT NOT NULL CHECK(sale_schema IN ('FBO','FBS')),
                segment_number INTEGER NOT NULL CHECK(segment_number BETWEEN 1 AND 10),
                kind TEXT NOT NULL CHECK(kind IN ('BASELINE','CANDIDATE')),
                status TEXT NOT NULL CHECK(status IN ('PLANNED','ACTIVE','FINISHED','PAUSED','ARCHIVED')),
                state_revision INTEGER NOT NULL CHECK(state_revision >= 1),
                result_revision INTEGER NOT NULL DEFAULT 0 CHECK(result_revision >= 0),
                expense_snapshot_id TEXT NOT NULL,
                payload_json TEXT NOT NULL CHECK(length(CAST(payload_json AS BLOB)) <= 65536),
                observation_id TEXT,
                confirmation_json TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY(phase_id, owner_id, store_id),
                UNIQUE(experiment_id, owner_id, store_id, segment_number),
                UNIQUE(phase_id, experiment_id, owner_id, store_id),
                FOREIGN KEY(experiment_id, owner_id, store_id, product_id, offer_id, sku, sale_schema)
                    REFERENCES planning_price_experiments(
                        experiment_id, owner_id, store_id, product_id, offer_id, sku, sale_schema
                    ),
                FOREIGN KEY(expense_snapshot_id, owner_id, store_id, product_id, offer_id, sku, sale_schema)
                    REFERENCES planning_unit_economics_snapshots(
                        snapshot_id, owner_id, store_id, product_id, offer_id, sku, sale_schema
                    )
            )""")
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_price_experiment_phases_scope "
                "ON planning_price_experiment_phases(experiment_id, owner_id, store_id, segment_number)"
            )
            connection.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_price_experiment_first_baseline "
                "ON planning_price_experiment_phases(experiment_id, owner_id, store_id) "
                "WHERE kind='BASELINE' AND segment_number=1"
            )
            connection.execute("""CREATE TABLE IF NOT EXISTS planning_price_experiment_phase_revisions (
                phase_id TEXT NOT NULL,
                experiment_id TEXT NOT NULL,
                owner_id TEXT NOT NULL,
                store_id TEXT NOT NULL,
                revision INTEGER NOT NULL CHECK(revision >= 1),
                state_revision INTEGER NOT NULL CHECK(state_revision >= 1),
                result_revision INTEGER NOT NULL CHECK(result_revision >= 0),
                payload_json TEXT NOT NULL CHECK(length(CAST(payload_json AS BLOB)) <= 65536),
                created_at TEXT NOT NULL,
                PRIMARY KEY(phase_id, owner_id, store_id, revision),
                FOREIGN KEY(phase_id, experiment_id, owner_id, store_id)
                    REFERENCES planning_price_experiment_phases(
                        phase_id, experiment_id, owner_id, store_id
                    )
            )""")
            connection.execute("""CREATE TABLE IF NOT EXISTS planning_price_experiment_results (
                experiment_id TEXT NOT NULL,
                phase_id TEXT NOT NULL,
                owner_id TEXT NOT NULL,
                store_id TEXT NOT NULL,
                result_revision INTEGER NOT NULL CHECK(result_revision BETWEEN 1 AND 20),
                payload_json TEXT NOT NULL CHECK(length(CAST(payload_json AS BLOB)) <= 65536),
                content_hash TEXT NOT NULL CHECK(length(content_hash)=64),
                created_at TEXT NOT NULL,
                PRIMARY KEY(phase_id, owner_id, store_id, result_revision),
                FOREIGN KEY(phase_id, experiment_id, owner_id, store_id)
                    REFERENCES planning_price_experiment_phases(
                        phase_id, experiment_id, owner_id, store_id
                    )
            )""")
            connection.execute("""CREATE TABLE IF NOT EXISTS planning_price_experiment_decisions (
                decision_id TEXT NOT NULL CHECK(length(decision_id)=32),
                experiment_id TEXT NOT NULL,
                owner_id TEXT NOT NULL,
                store_id TEXT NOT NULL,
                decision_revision INTEGER NOT NULL
                    CHECK(decision_revision BETWEEN 1 AND 100),
                state_revision INTEGER NOT NULL CHECK(state_revision >= 1),
                decision_type TEXT NOT NULL CHECK(decision_type IN (
                    'KEEP_BASELINE_PRICE', 'SELECT_EVALUATED_CANDIDATE',
                    'CONTINUE_TEST', 'STOP_WITHOUT_PRICE_CHANGE'
                )),
                result_phase_id TEXT NOT NULL,
                result_revision INTEGER NOT NULL CHECK(result_revision BETWEEN 1 AND 20),
                selected_phase_id TEXT,
                payload_json TEXT NOT NULL CHECK(length(CAST(payload_json AS BLOB)) <= 65536),
                content_hash TEXT NOT NULL CHECK(length(content_hash)=64),
                created_at TEXT NOT NULL,
                PRIMARY KEY(decision_id, owner_id, store_id),
                UNIQUE(experiment_id, owner_id, store_id, decision_revision),
                FOREIGN KEY(experiment_id, owner_id, store_id)
                    REFERENCES planning_price_experiments(experiment_id, owner_id, store_id),
                FOREIGN KEY(result_phase_id, owner_id, store_id, result_revision)
                    REFERENCES planning_price_experiment_results(
                        phase_id, owner_id, store_id, result_revision
                    ),
                FOREIGN KEY(selected_phase_id, owner_id, store_id)
                    REFERENCES planning_price_experiment_phases(phase_id, owner_id, store_id),
                CHECK((decision_type IN ('KEEP_BASELINE_PRICE','SELECT_EVALUATED_CANDIDATE')
                        AND selected_phase_id IS NOT NULL)
                    OR (decision_type IN ('CONTINUE_TEST','STOP_WITHOUT_PRICE_CHANGE')
                        AND selected_phase_id IS NULL))
            )""")
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_price_experiment_decisions_scope "
                "ON planning_price_experiment_decisions(experiment_id, owner_id, store_id, "
                "decision_revision DESC)"
            )
            connection.execute("""CREATE TABLE IF NOT EXISTS planning_price_experiment_idempotency (
                owner_id TEXT NOT NULL,
                store_id TEXT NOT NULL,
                idempotency_key TEXT NOT NULL,
                request_hash TEXT NOT NULL CHECK(length(request_hash)=64),
                result_json TEXT NOT NULL CHECK(length(CAST(result_json AS BLOB)) <= 65536),
                created_at TEXT NOT NULL,
                PRIMARY KEY(owner_id, store_id, idempotency_key)
            )""")
            connection.execute("""CREATE TABLE IF NOT EXISTS planning_price_experiment_events (
                event_id TEXT NOT NULL CHECK(length(event_id)=32),
                experiment_id TEXT NOT NULL,
                owner_id TEXT NOT NULL,
                store_id TEXT NOT NULL,
                phase_id TEXT NOT NULL,
                event_revision INTEGER NOT NULL CHECK(event_revision BETWEEN 1 AND 100),
                event_kind TEXT NOT NULL CHECK(event_kind IN (
                    'CONTROL_UPDATE','PAUSE','RESUME_SEGMENT_PREPARED'
                )),
                payload_json TEXT NOT NULL CHECK(length(CAST(payload_json AS BLOB)) <= 65536),
                payload_hash TEXT NOT NULL CHECK(length(payload_hash)=64),
                created_at TEXT NOT NULL,
                PRIMARY KEY(event_id, owner_id, store_id),
                UNIQUE(experiment_id, owner_id, store_id, event_revision),
                FOREIGN KEY(experiment_id, owner_id, store_id)
                    REFERENCES planning_price_experiments(experiment_id, owner_id, store_id),
                FOREIGN KEY(phase_id, experiment_id, owner_id, store_id)
                    REFERENCES planning_price_experiment_phases(
                        phase_id, experiment_id, owner_id, store_id
                    )
            )""")
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_price_experiment_events_phase "
                "ON planning_price_experiment_events(experiment_id, owner_id, store_id, "
                "phase_id, event_revision DESC)"
            )
            connection.execute("""CREATE TABLE IF NOT EXISTS planning_price_experiment_phase_collections (
                experiment_id TEXT NOT NULL,
                phase_id TEXT NOT NULL,
                owner_id TEXT NOT NULL,
                store_id TEXT NOT NULL,
                collection_revision INTEGER NOT NULL CHECK(collection_revision BETWEEN 1 AND 20),
                collection_id TEXT NOT NULL CHECK(length(collection_id)=64),
                payload_json TEXT NOT NULL CHECK(length(CAST(payload_json AS BLOB)) <= 65536),
                content_hash TEXT NOT NULL CHECK(length(content_hash)=64),
                created_at TEXT NOT NULL,
                PRIMARY KEY(phase_id, owner_id, store_id, collection_revision),
                UNIQUE(experiment_id, owner_id, store_id, collection_id),
                FOREIGN KEY(phase_id, experiment_id, owner_id, store_id)
                    REFERENCES planning_price_experiment_phases(
                        phase_id, experiment_id, owner_id, store_id
                    )
            )""")
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_price_experiment_collections_phase "
                "ON planning_price_experiment_phase_collections(experiment_id, owner_id, "
                "store_id, phase_id, collection_revision DESC)"
            )
            if version < 7:
                self._migrate_active_sku_guards(connection)
            if version < 8:
                connection.execute(
                    "DROP TRIGGER IF EXISTS trg_price_experiments_immutable_config"
                )
            if version < 9:
                phase_columns = {
                    row[1] for row in connection.execute(
                        "PRAGMA table_info(planning_price_experiment_phases)"
                    )
                }
                if "observation_id" not in phase_columns:
                    connection.execute(
                        "ALTER TABLE planning_price_experiment_phases "
                        "ADD COLUMN observation_id TEXT"
                    )
                if "confirmation_json" not in phase_columns:
                    connection.execute(
                        "ALTER TABLE planning_price_experiment_phases "
                        "ADD COLUMN confirmation_json TEXT"
                    )
                connection.execute(
                    "CREATE INDEX IF NOT EXISTS idx_price_experiment_phase_observation "
                    "ON planning_price_experiment_phases(observation_id) "
                    "WHERE observation_id IS NOT NULL"
                )
            if version < 10:
                experiment_columns = {
                    row[1] for row in connection.execute(
                        "PRAGMA table_info(planning_price_experiments)"
                    )
                }
                if "resume_target" not in experiment_columns:
                    connection.execute(
                        "ALTER TABLE planning_price_experiments ADD COLUMN resume_target TEXT "
                        "CHECK(resume_target IS NULL OR resume_target IN "
                        "('READY','CANDIDATE_READY'))"
                    )
                connection.execute(
                    "DROP INDEX IF EXISTS idx_price_experiment_one_baseline"
                )
                connection.execute(
                    "CREATE UNIQUE INDEX IF NOT EXISTS idx_price_experiment_first_baseline "
                    "ON planning_price_experiment_phases(experiment_id, owner_id, store_id) "
                    "WHERE kind='BASELINE' AND segment_number=1"
                )
            connection.execute("""CREATE TRIGGER IF NOT EXISTS trg_unit_economics_snapshots_no_update
                BEFORE UPDATE ON planning_unit_economics_snapshots
                BEGIN SELECT RAISE(ABORT, 'immutable expense snapshot'); END""")
            connection.execute("""CREATE TRIGGER IF NOT EXISTS trg_unit_economics_snapshots_no_delete
                BEFORE DELETE ON planning_unit_economics_snapshots
                BEGIN SELECT RAISE(ABORT, 'immutable expense snapshot'); END""")
            connection.execute("""CREATE TRIGGER IF NOT EXISTS trg_price_experiment_revisions_no_update
                BEFORE UPDATE ON planning_price_experiment_revisions
                BEGIN SELECT RAISE(ABORT, 'immutable experiment revision'); END""")
            connection.execute("""CREATE TRIGGER IF NOT EXISTS trg_price_experiment_revisions_no_delete
                BEFORE DELETE ON planning_price_experiment_revisions
                BEGIN SELECT RAISE(ABORT, 'immutable experiment revision'); END""")
            connection.execute("""CREATE TRIGGER IF NOT EXISTS trg_price_experiment_phase_revisions_no_update
                BEFORE UPDATE ON planning_price_experiment_phase_revisions
                BEGIN SELECT RAISE(ABORT, 'immutable experiment phase revision'); END""")
            connection.execute("""CREATE TRIGGER IF NOT EXISTS trg_price_experiment_phase_revisions_no_delete
                BEFORE DELETE ON planning_price_experiment_phase_revisions
                BEGIN SELECT RAISE(ABORT, 'immutable experiment phase revision'); END""")
            connection.execute("""CREATE TRIGGER IF NOT EXISTS trg_price_experiment_results_no_update
                BEFORE UPDATE ON planning_price_experiment_results
                BEGIN SELECT RAISE(ABORT, 'immutable experiment result'); END""")
            connection.execute("""CREATE TRIGGER IF NOT EXISTS trg_price_experiment_results_no_delete
                BEFORE DELETE ON planning_price_experiment_results
                BEGIN SELECT RAISE(ABORT, 'immutable experiment result'); END""")
            connection.execute("""CREATE TRIGGER IF NOT EXISTS trg_price_experiment_events_no_update
                BEFORE UPDATE ON planning_price_experiment_events
                BEGIN SELECT RAISE(ABORT, 'immutable experiment event'); END""")
            connection.execute("""CREATE TRIGGER IF NOT EXISTS trg_price_experiment_events_no_delete
                BEFORE DELETE ON planning_price_experiment_events
                BEGIN SELECT RAISE(ABORT, 'immutable experiment event'); END""")
            connection.execute("""CREATE TRIGGER IF NOT EXISTS trg_price_experiments_immutable_identity
                BEFORE UPDATE OF owner_id, store_id, product_id, offer_id, sku, sale_schema,
                    schema_version, calculation_mode, plan_document_id, plan_revision,
                    expense_snapshot_id, tariff_profile_id, tariff_revision, observation_id,
                    observation_result_revision, created_at
                ON planning_price_experiments
                BEGIN SELECT RAISE(ABORT, 'immutable experiment configuration'); END""")
            connection.execute("""CREATE TRIGGER IF NOT EXISTS trg_price_experiments_immutable_config
                BEFORE UPDATE OF config_json ON planning_price_experiments
                WHEN OLD.status != 'DRAFT' OR NEW.status != 'DRAFT'
                BEGIN SELECT RAISE(ABORT, 'only draft configuration may change'); END""")
            connection.execute("""CREATE TRIGGER IF NOT EXISTS trg_price_experiments_no_delete
                BEFORE DELETE ON planning_price_experiments
                BEGIN SELECT RAISE(ABORT, 'preserve experiment history'); END""")
            connection.execute("""CREATE TRIGGER IF NOT EXISTS trg_price_experiment_phases_immutable_config
                BEFORE UPDATE OF experiment_id, owner_id, store_id, product_id, offer_id, sku,
                    sale_schema, segment_number, kind, expense_snapshot_id, payload_json, created_at
                ON planning_price_experiment_phases
                BEGIN SELECT RAISE(ABORT, 'immutable experiment phase configuration'); END""")
            connection.execute("""CREATE TRIGGER IF NOT EXISTS trg_price_experiment_phases_no_delete
                BEFORE DELETE ON planning_price_experiment_phases
                BEGIN SELECT RAISE(ABORT, 'preserve experiment phase history'); END""")
            connection.execute("""CREATE TRIGGER IF NOT EXISTS trg_price_experiment_collections_no_update
                BEFORE UPDATE ON planning_price_experiment_phase_collections
                BEGIN SELECT RAISE(ABORT, 'immutable phase collection'); END""")
            connection.execute("""CREATE TRIGGER IF NOT EXISTS trg_price_experiment_collections_no_delete
                BEFORE DELETE ON planning_price_experiment_phase_collections
                BEGIN SELECT RAISE(ABORT, 'preserve phase collection history'); END""")
            connection.execute("""CREATE TRIGGER IF NOT EXISTS trg_price_experiment_decisions_no_update
                BEFORE UPDATE ON planning_price_experiment_decisions
                BEGIN SELECT RAISE(ABORT, 'immutable owner decision'); END""")
            connection.execute("""CREATE TRIGGER IF NOT EXISTS trg_price_experiment_decisions_no_delete
                BEFORE DELETE ON planning_price_experiment_decisions
                BEGIN SELECT RAISE(ABORT, 'preserve owner decision history'); END""")
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

    @staticmethod
    def _migrate_active_sku_guards(connection):
        """Backfill the shared lock without rewriting pre-existing active records."""
        active = {}
        observation_rows = connection.execute(
            "SELECT owner_id, store_id, product_id, offer_id, sku, sale_schema, "
            "observation_id, started_at FROM planning_unit_price_observations "
            "WHERE status='ACTIVE'"
        ).fetchall()
        for row in observation_rows:
            key = tuple(row[field] for field in (
                "owner_id", "store_id", "product_id", "offer_id", "sku", "sale_schema",
            ))
            active.setdefault(key, []).append(("OBSERVATION", row["observation_id"], row["started_at"]))
        experiment_rows = connection.execute(
            "SELECT owner_id, store_id, product_id, offer_id, sku, sale_schema, "
            "experiment_id, created_at FROM planning_price_experiments "
            "WHERE status IN ('BASELINE_ACTIVE','CANDIDATE_ACTIVE')"
        ).fetchall()
        for row in experiment_rows:
            key = tuple(row[field] for field in (
                "owner_id", "store_id", "product_id", "offer_id", "sku", "sale_schema",
            ))
            active.setdefault(key, []).append(("EXPERIMENT", row["experiment_id"], row["created_at"]))
        for key, operations in active.items():
            if len(operations) == 1:
                kind, operation_id, created_at = operations[0]
            else:
                kind, operation_id = "CONFLICT", None
                created_at = min(operation[2] for operation in operations)
            connection.execute(
                "INSERT INTO planning_active_sku_guards "
                "(owner_id, store_id, product_id, offer_id, sku, sale_schema, "
                "operation_kind, operation_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(owner_id, store_id, product_id, offer_id, sku, sale_schema) "
                "DO UPDATE SET operation_kind=excluded.operation_kind, "
                "operation_id=excluded.operation_id, created_at=excluded.created_at",
                (*key, kind, operation_id, created_at),
            )

    @staticmethod
    def _active_guard_identity(scope, identity):
        return (
            scope["owner_id"], scope["store_id"], identity["product_id"],
            identity["offer_id"], identity["sku"], identity["sale_schema"],
        )

    @classmethod
    def _claim_active_sku_guard(
        cls, connection, scope, identity, operation_kind, operation_id, created_at,
    ):
        if operation_kind not in {"OBSERVATION", "EXPERIMENT"}:
            return False
        key = cls._active_guard_identity(scope, identity)
        existing = connection.execute(
            "SELECT operation_kind, operation_id FROM planning_active_sku_guards "
            "WHERE owner_id=? AND store_id=? AND product_id=? AND offer_id=? AND sku=? "
            "AND sale_schema=?", key,
        ).fetchone()
        if existing is not None:
            return False
        connection.execute(
            "INSERT INTO planning_active_sku_guards "
            "(owner_id, store_id, product_id, offer_id, sku, sale_schema, "
            "operation_kind, operation_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (*key, operation_kind, operation_id, created_at),
        )
        return True

    @classmethod
    def _sync_active_sku_guard(cls, connection, scope, identity):
        """Reconcile a released/transitioned lock against both active resource tables."""
        key = cls._active_guard_identity(scope, identity)
        connection.execute(
            "DELETE FROM planning_active_sku_guards WHERE owner_id=? AND store_id=? "
            "AND product_id=? AND offer_id=? AND sku=? AND sale_schema=?", key,
        )
        operations = connection.execute(
            "SELECT 'OBSERVATION' AS operation_kind, observation_id AS operation_id, started_at AS created_at "
            "FROM planning_unit_price_observations WHERE owner_id=? AND store_id=? AND product_id=? "
            "AND offer_id=? AND sku=? AND sale_schema=? AND status='ACTIVE' "
            "AND NOT EXISTS (SELECT 1 FROM planning_price_experiment_phases p "
            "JOIN planning_price_experiments e ON e.experiment_id=p.experiment_id "
            "AND e.owner_id=p.owner_id AND e.store_id=p.store_id "
            "WHERE p.observation_id=planning_unit_price_observations.observation_id "
            "AND e.status IN ('BASELINE_ACTIVE','CANDIDATE_ACTIVE')) "
            "UNION ALL SELECT 'EXPERIMENT', experiment_id, created_at FROM planning_price_experiments "
            "WHERE owner_id=? AND store_id=? AND product_id=? AND offer_id=? AND sku=? "
            "AND sale_schema=? AND status IN ('BASELINE_ACTIVE','CANDIDATE_ACTIVE')", (*key, *key),
        ).fetchall()
        if not operations:
            return
        if len(operations) == 1:
            operation = operations[0]
            kind, operation_id, created_at = (
                operation["operation_kind"], operation["operation_id"], operation["created_at"],
            )
        else:
            kind, operation_id = "CONFLICT", None
            created_at = min(operation["created_at"] for operation in operations)
        connection.execute(
            "INSERT INTO planning_active_sku_guards "
            "(owner_id, store_id, product_id, offer_id, sku, sale_schema, "
            "operation_kind, operation_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (*key, kind, operation_id, created_at),
        )

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
        if not cls._valid_observation_extended_cost_basis(payload["metrics"]):
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
    def _valid_observation_extended_cost_basis(cls, metrics):
        fields = {
            "extended_cost_mode", "extended_cost_origin",
            "extended_cost_signature", "extended_cost_per_unit",
        }
        present = fields.intersection(metrics)
        if not present:
            return True  # Preserve immutable legacy result schemas.
        if present != fields:
            return False
        mode = metrics.get("extended_cost_mode")
        origin = metrics.get("extended_cost_origin")
        signature = metrics.get("extended_cost_signature")
        per_unit = metrics.get("extended_cost_per_unit")
        if mode == "NOT_APPLIED":
            return (
                origin == "NOT_APPLIED" and signature is None and per_unit is None
            )
        if (mode not in {"WINDOW_COST_ALLOCATION", "STRICT_RETAINED_COHORT"}
                or origin not in {
                    "CONFIRMED", "MANUAL_ASSUMPTION", "UNCONFIRMED",
                }
                or not isinstance(signature, str)
                or re.fullmatch(r"[a-f0-9]{64}", signature) is None
                or not isinstance(per_unit, str) or len(per_unit) > 32):
            return False
        try:
            amount = Decimal(per_unit)
        except (InvalidOperation, TypeError, ValueError):
            return False
        return amount.is_finite() and Decimal("0") <= amount <= Decimal("999999999999.99")

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

    @classmethod
    def _price_experiment_request_hash(cls, payload):
        encoded = cls._encode(payload)
        if encoded is None or len(encoded.encode("utf-8")) > cls.MAX_PRICE_EXPERIMENT_PAYLOAD_BYTES:
            return None
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    @staticmethod
    def _price_experiment_idempotent_result(connection, scope, key, request_hash):
        row = connection.execute(
            "SELECT request_hash, result_json FROM planning_price_experiment_idempotency "
            "WHERE owner_id=? AND store_id=? AND idempotency_key=?",
            (scope["owner_id"], scope["store_id"], key),
        ).fetchone()
        if row is None:
            return None
        if row["request_hash"] != request_hash:
            return PlanningWorkspaceRepository._error(
                "PLANNING_PRICE_EXPERIMENT_IDEMPOTENCY_CONFLICT"
            )
        try:
            result = json.loads(row["result_json"])
        except (TypeError, ValueError):
            return PlanningWorkspaceRepository._error(
                "PLANNING_PRICE_EXPERIMENT_IDEMPOTENCY_RECORD_CORRUPT"
            )
        if not isinstance(result, dict) or type(result.get("error")) is not bool:
            return PlanningWorkspaceRepository._error(
                "PLANNING_PRICE_EXPERIMENT_IDEMPOTENCY_RECORD_CORRUPT"
            )
        return result

    @classmethod
    def _remember_price_experiment_idempotency(
        cls, connection, scope, key, request_hash, result, now,
    ):
        encoded = cls._encode(result)
        if (encoded is None or len(encoded.encode("utf-8"))
                > cls.MAX_PRICE_EXPERIMENT_PAYLOAD_BYTES):
            raise ValueError("idempotency result exceeds storage bound")
        connection.execute(
            "INSERT INTO planning_price_experiment_idempotency "
            "(owner_id, store_id, idempotency_key, request_hash, result_json, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (scope["owner_id"], scope["store_id"], key, request_hash, encoded, now),
        )
        connection.execute(
            """DELETE FROM planning_price_experiment_idempotency
               WHERE owner_id=? AND store_id=? AND idempotency_key IN (
                 SELECT idempotency_key FROM planning_price_experiment_idempotency
                 WHERE owner_id=? AND store_id=? ORDER BY created_at DESC, idempotency_key DESC
                 LIMIT -1 OFFSET ?)""",
            (scope["owner_id"], scope["store_id"], scope["owner_id"],
             scope["store_id"], cls.MAX_PRICE_EXPERIMENT_IDEMPOTENCY_PER_STORE),
        )

    @classmethod
    def _insert_price_experiment_event(
        cls, connection, scope, experiment_id, phase_id, payload, now,
    ):
        encoded = cls._encode(payload)
        if (encoded is None or len(encoded.encode("utf-8"))
                > cls.MAX_PRICE_EXPERIMENT_EVENT_PAYLOAD_BYTES):
            return cls._error("PLANNING_PRICE_EXPERIMENT_EVENT_INVALID")
        last_revision = connection.execute(
            "SELECT MAX(event_revision) FROM planning_price_experiment_events "
            "WHERE experiment_id=? AND owner_id=? AND store_id=?",
            (experiment_id, scope["owner_id"], scope["store_id"]),
        ).fetchone()[0]
        event_revision = (last_revision or 0) + 1
        if event_revision > cls.MAX_PRICE_EXPERIMENT_EVENTS:
            return cls._error("PLANNING_PRICE_EXPERIMENT_EVENT_QUOTA_REACHED")
        event_id = uuid4().hex
        payload_hash = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
        connection.execute(
            "INSERT INTO planning_price_experiment_events "
            "(event_id, experiment_id, owner_id, store_id, phase_id, event_revision, "
            "event_kind, payload_json, payload_hash, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (event_id, experiment_id, scope["owner_id"], scope["store_id"], phase_id,
             event_revision, payload["event_kind"], encoded, payload_hash, now),
        )
        return {
            "error": False, "event_id": event_id,
            "event_revision": event_revision,
            "event_kind": payload["event_kind"], "created_at": now,
        }

    @staticmethod
    def _valid_uuid_hex(value):
        return isinstance(value, str) and re.fullmatch(r"[a-f0-9]{32}", value) is not None

    def _decode_price_experiment(self, row, scope):
        try:
            payload = json.loads(row["config_json"])
        except (ValueError, TypeError):
            return self._error("PLANNING_PRICE_EXPERIMENT_CORRUPT")
        normalized = PlanningUnitEconomicsExperimentAdapter.normalize_experiment(
            payload, scope,
            allow_incomplete=row["status"] in {"DRAFT", "CANCELLED", "ARCHIVED"},
        )
        if normalized is None:
            return self._error("PLANNING_PRICE_EXPERIMENT_CORRUPT")
        if any(
            normalized["identity"][key] != row[key]
            for key in ("owner_id", "store_id", "product_id", "offer_id", "sku", "sale_schema")
        ):
            return self._error("PLANNING_PRICE_EXPERIMENT_CORRUPT")
        if (row["schema_version"] != normalized["schema_version"]
                or row["calculation_mode"] != normalized["calculation_mode"]):
            return self._error("PLANNING_PRICE_EXPERIMENT_CORRUPT")
        references = normalized["source_references"]
        tariff = references["tariff"]
        observation = references["observation"]
        resume_target = row["resume_target"]
        if (row["status"] not in {
                "DRAFT", "READY", "BASELINE_ACTIVE", "BASELINE_REVIEW",
                "CANDIDATE_READY", "CANDIDATE_ACTIVE", "CANDIDATE_REVIEW",
                "PAUSED", "CANCELLED", "COMPLETED", "ARCHIVED",
            }
                or type(row["state_revision"]) is not int or row["state_revision"] < 1
                or type(row["result_revision"]) is not int or row["result_revision"] < 0
                or row["plan_document_id"] != references["plan"]["document_id"]
                or row["plan_revision"] != references["plan"]["revision"]
                or row["expense_snapshot_id"] != references["expense_snapshot_id"]
                or row["tariff_profile_id"] != (tariff["profile_id"] if tariff else None)
                or row["tariff_revision"] != (tariff["revision"] if tariff else None)
                or row["observation_id"] != (observation["observation_id"] if observation else None)
                or row["observation_result_revision"] != (
                    observation["result_revision"] if observation else None
                )
                or resume_target not in {None, "READY", "CANDIDATE_READY"}
                or (row["status"] == "PAUSED") != (resume_target is not None)):
            return self._error("PLANNING_PRICE_EXPERIMENT_CORRUPT")
        return {
            "error": False,
            "experiment": {
                "experiment_id": row["experiment_id"], "owner_id": row["owner_id"],
                "store_id": row["store_id"], "product_id": row["product_id"],
                "offer_id": row["offer_id"], "sku": row["sku"],
                "sale_schema": row["sale_schema"], "status": row["status"],
                "resume_target": resume_target,
                "state_revision": row["state_revision"],
                "result_revision": row["result_revision"],
                "schema_version": row["schema_version"],
                "created_at": row["created_at"], "updated_at": row["updated_at"],
                "config": normalized,
            },
        }

    @staticmethod
    def _decode_price_experiment_phase(row):
        try:
            payload = json.loads(row["payload_json"])
        except (ValueError, TypeError):
            return PlanningWorkspaceRepository._error(
                "PLANNING_PRICE_EXPERIMENT_PHASE_CORRUPT"
            )
        normalized = PlanningUnitEconomicsExperimentAdapter.normalize_phase(
            payload, {},
        )
        observation_id = row["observation_id"]
        confirmation = None
        if row["confirmation_json"] is not None:
            try:
                raw_confirmation = json.loads(row["confirmation_json"])
            except (TypeError, ValueError):
                raw_confirmation = None
            confirmation = (
                UnitEconomicsExperimentPhaseConfirmationService.normalize_confirmation(
                    raw_confirmation, normalized,
                ) if normalized is not None else None
            )
        if (normalized is None or payload.get("schema_version") != 1
                or row["status"] not in {"PLANNED", "ACTIVE", "FINISHED", "PAUSED", "ARCHIVED"}
                or type(row["state_revision"]) is not int or row["state_revision"] < 1
                or type(row["result_revision"]) is not int
                or not 0 <= row["result_revision"] <= 20
                or normalized["expense_snapshot_id"] != row["expense_snapshot_id"]
                or normalized["kind"] != row["kind"]
                or normalized["segment_number"] != row["segment_number"]
                or (row["confirmation_json"] is not None and confirmation is None)
                or (confirmation is None) != (observation_id is None)
                or (row["status"] == "ACTIVE" and confirmation is None)
                or (observation_id is not None and not PlanningWorkspaceRepository._valid_uuid_hex(
                    observation_id,
                ))):
            return PlanningWorkspaceRepository._error(
                "PLANNING_PRICE_EXPERIMENT_PHASE_CORRUPT"
            )
        return {
            "error": False,
            "phase": {
                "phase_id": row["phase_id"], "experiment_id": row["experiment_id"],
                "owner_id": row["owner_id"], "store_id": row["store_id"],
                "product_id": row["product_id"], "offer_id": row["offer_id"],
                "sku": row["sku"], "sale_schema": row["sale_schema"],
                "segment_number": row["segment_number"], "kind": row["kind"],
                "status": row["status"], "state_revision": row["state_revision"],
                "result_revision": row["result_revision"],
                "observation_id": observation_id, "confirmation": confirmation,
                "created_at": row["created_at"], "updated_at": row["updated_at"],
                "config": normalized,
            },
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
