"""Owner-confirmed FIFO batch-rule preview and atomic confirmation.

The rule ledger records boundaries and owner evidence only. It never creates
FIFO rates, layers, allocations, sales, or COGS.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from dataclasses import replace
import hashlib
import json
import re
import secrets
import sqlite3
from threading import RLock

from services.fifo_cost_batch_rule_contracts import (
    BatchRuleEventKind,
    BatchRuleInput,
    BatchRulePreview,
    BatchRuleRevision,
    BatchStartDayPolicy,
    MAX_RULE_REVISIONS,
)
from services.fifo_cost_batch_supply_store import FifoCostBatchSupplyStore
from services.fifo_cost_repository import FifoCostRepository
from services.fifo_cost_transition_contracts import (
    ScopeIdentity,
    SupplyTotalMode,
    TransitionCase,
    TransitionState,
)
from services.fifo_cost_transition_service import FifoCostTransitionService
from services.fifo_cost_transition_store import FifoCostTransitionStore


_IDEMPOTENCY = re.compile(r"^[A-Za-z0-9_-]{8,110}$")
_HEX = re.compile(r"^[0-9a-f]{64}$")


class FifoCostBatchRuleService:
    """Preview and confirm immutable owner-defined batch cost boundaries."""

    PREVIEW_TTL = timedelta(minutes=15)
    MAX_ACTIVE_PREVIEWS = 256

    def __init__(self, repository: FifoCostRepository, *, now_provider=None):
        if not isinstance(repository, FifoCostRepository):
            raise TypeError("FIFO_BATCH_REPOSITORY_INVALID")
        self.repository = repository
        self._now_provider = now_provider or repository._now_provider
        self._lock = RLock()
        self._previews: dict[str, BatchRulePreview] = {}

    def preview_rule(
        self, scope: ScopeIdentity, case_id: str,
        expected_case_revision: int, input: BatchRuleInput,
    ) -> dict:
        """Validate exact case/source assumptions and issue a memory-only ticket."""
        if not isinstance(scope, ScopeIdentity) or not isinstance(input, BatchRuleInput):
            return self._error("FIFO_BATCH_RULE_INPUT_INVALID")
        if (
            not isinstance(case_id, str)
            or not re.fullmatch(r"[A-Za-z0-9_-]{8,96}", case_id)
            or type(expected_case_revision) is not int
            or expected_case_revision < 1
        ):
            return self._error("FIFO_BATCH_RULE_REVISION_INVALID")
        now = self._now()
        case_result = self._read_case(scope, case_id)
        if case_result.get("error"):
            return case_result
        if case_result["case_revision"] != expected_case_revision:
            return self._error("FIFO_BATCH_CASE_REVISION_CONFLICT")
        case = case_result["case"]
        prerequisite_error = self._validate_case(scope, case)
        if prerequisite_error:
            return self._error(prerequisite_error)

        tenant = self.repository._tenant_scope(scope.store_id)
        if tenant.get("error"):
            return tenant
        rows_result = self._read_rules(scope, case_id, tenant["tenant_fingerprint"])
        if rows_result.get("error"):
            return rows_result
        rows = rows_result["items"]
        active = self._active_rule(rows)
        if active.get("error"):
            return active

        if not rows:
            if case.supply_total_mode is not SupplyTotalMode.LEGACY_OWNER_TOTAL:
                return self._error("FIFO_BATCH_RULE_MODE_MISMATCH")
            if input.start_local_date != case.dispatch_date:
                return self._error("FIFO_BATCH_FIRST_BOUNDARY_MUST_MATCH_DISPATCH_DATE")
            rule_revision = 1
            close_revision = None
            predecessor_id = None
            predecessor_revision = None
        else:
            if case.supply_total_mode is not SupplyTotalMode.AUTO_FROM_SUPPLIES:
                return self._error("FIFO_BATCH_RULE_MODE_MISMATCH")
            active_row = active.get("item")
            if active_row is None:
                return self._error("FIFO_BATCH_RULE_HISTORY_NEEDS_REVIEW")
            if active_row["store_timezone"] != case.metadata.store_timezone:
                return self._error("FIFO_BATCH_TIMEZONE_CHANGE_NEEDS_REVIEW")
            if input.start_local_date == active_row["start_local_date"]:
                return self._error("FIFO_BATCH_SAME_DAY_BOUNDARY_NEEDS_REVIEW")
            if input.start_local_date < active_row["start_local_date"]:
                return self._error("FIFO_BATCH_BOUNDARY_DATE_CONFLICT")
            if len(rows) + 2 > MAX_RULE_REVISIONS:
                return self._error("FIFO_BATCH_RULE_LIMIT_REACHED")
            close_revision = max(row["rule_revision"] for row in rows) + 1
            rule_revision = close_revision + 1
            predecessor_id = active_row["rule_id"]
            predecessor_revision = close_revision

        if rule_revision > MAX_RULE_REVISIONS:
            return self._error("FIFO_BATCH_RULE_LIMIT_REACHED")
        now_text = self._iso(now)
        expires = self._iso(now + self.PREVIEW_TTL)
        rule_id = "br_" + secrets.token_hex(16)
        preview_id = "bp_" + secrets.token_hex(16)
        cost_fingerprint = self._cost_fingerprint(case)
        head_fingerprint = self._rule_head_fingerprint(rows)
        material = {
            "preview_id": preview_id,
            "scope": self._scope_payload(scope),
            "case_id": case_id,
            "expected_case_revision": expected_case_revision,
            "rule_id": rule_id,
            "rule_revision": rule_revision,
            "expected_rule_head_revision": max(
                (row["rule_revision"] for row in rows), default=0,
            ),
            "close_active_rule_revision": close_revision,
            "predecessor_rule_id": predecessor_id,
            "predecessor_rule_revision": predecessor_revision,
            "start_local_date": input.start_local_date,
            "store_timezone": case.metadata.store_timezone,
            "start_day_policy": input.start_day_policy.value,
            "new_unit_cost_rub": str(case.new_unit_cost_rub),
            "cost_input_fingerprint": cost_fingerprint,
            "old_home_confirmed_zero": True,
            "old_transit_confirmed_zero": True,
            "boundary_supply_digests": input.boundary_supply_digests,
            "rule_head_fingerprint": head_fingerprint,
            "created_at_utc": now_text,
            "expires_at_utc": expires,
        }
        preview = BatchRulePreview(
            preview_id=preview_id,
            scope=scope,
            case_id=case_id,
            expected_case_revision=expected_case_revision,
            rule_id=rule_id,
            rule_revision=rule_revision,
            expected_rule_head_revision=material["expected_rule_head_revision"],
            close_active_rule_revision=close_revision,
            predecessor_rule_id=predecessor_id,
            predecessor_rule_revision=predecessor_revision,
            start_local_date=input.start_local_date,
            store_timezone=case.metadata.store_timezone,
            start_day_policy=input.start_day_policy,
            new_unit_cost_rub=case.new_unit_cost_rub,
            cost_input_fingerprint=cost_fingerprint,
            old_home_confirmed_zero=True,
            old_transit_confirmed_zero=True,
            boundary_supply_digests=input.boundary_supply_digests,
            rule_head_fingerprint=head_fingerprint,
            preview_fingerprint=self._digest(material),
            created_at_utc=now_text,
            expires_at_utc=expires,
        )
        with self._lock:
            self._purge_expired(now)
            if len(self._previews) >= self.MAX_ACTIVE_PREVIEWS:
                return self._error("FIFO_BATCH_PREVIEW_LIMIT_REACHED")
            self._previews[preview_id] = preview
        return {
            "error": False,
            "code": "FIFO_BATCH_RULE_PREVIEW_READY",
            "preview": preview,
        }

    def confirm_rule(
        self, scope: ScopeIdentity, case_id: str, expected_case_revision: int,
        preview_id: str, preview_fingerprint: str, idempotency_key: str,
    ) -> dict:
        """Atomically append rule confirmation and switch only the case mode."""
        if not isinstance(scope, ScopeIdentity):
            return self._error("FIFO_BATCH_RULE_SCOPE_INVALID")
        if (
            not isinstance(case_id, str)
            or not re.fullmatch(r"[A-Za-z0-9_-]{8,96}", case_id)
            or type(expected_case_revision) is not int
            or expected_case_revision < 1
            or not isinstance(preview_id, str)
            or not re.fullmatch(r"[A-Za-z0-9_-]{8,96}", preview_id)
            or not isinstance(preview_fingerprint, str)
            or not _HEX.fullmatch(preview_fingerprint)
            or not isinstance(idempotency_key, str)
            or not _IDEMPOTENCY.fullmatch(idempotency_key)
        ):
            return self._error("FIFO_BATCH_RULE_CONFIRMATION_INVALID")
        tenant = self.repository._tenant_scope(scope.store_id)
        if tenant.get("error"):
            return tenant
        confirmation_fingerprint = self._digest({
            "action": "CONFIRM_FIFO_BATCH_RULE",
            "scope": self._scope_payload(scope),
            "case_id": case_id,
            "expected_case_revision": expected_case_revision,
            "preview_id": preview_id,
            "preview_fingerprint": preview_fingerprint,
        })
        now = self._now()
        now_text = self._iso(now)

        with self._lock:
            self._purge_expired(now)
            preview = self._previews.get(preview_id)
        ticket_mismatch = preview is not None and (
            preview.scope != scope
            or preview.case_id != case_id
            or preview.expected_case_revision != expected_case_revision
            or preview.preview_fingerprint != preview_fingerprint
        )

        identity = self.repository._normalize_transition_read_identity(
            scope.store_id, product_id=scope.product_id,
            offer_id=scope.offer_id, sku=scope.sku,
        )
        if identity.get("error"):
            return identity

        def operation(connection):
            receipt = FifoCostBatchSupplyStore.read_rule_idempotency(
                connection, scope=scope, case_id=case_id,
                tenant_fingerprint=tenant["tenant_fingerprint"],
                idempotency_key=idempotency_key,
            )
            if receipt is not None:
                if receipt["owner_confirmation_fingerprint"] != confirmation_fingerprint:
                    return self._error("FIFO_BATCH_IDEMPOTENCY_CONFLICT")
                return {
                    "error": False,
                    "code": "FIFO_BATCH_RULE_CONFIRMED",
                    "case_id": case_id,
                    "case_revision": expected_case_revision + 1,
                    "rule_id": receipt["rule_id"],
                    "rule_revision": receipt["rule_revision"],
                    "replayed": True,
                }
            if ticket_mismatch:
                return self._error("FIFO_BATCH_PREVIEW_MISMATCH")
            if preview is None or preview.expires_at_utc <= now_text:
                return self._error("FIFO_BATCH_PREVIEW_EXPIRED_OR_NOT_FOUND")

            current = FifoCostTransitionStore.read_case(
                connection, case_id, tenant, identity,
            )
            if current.get("error"):
                return current
            if current["case_revision"] != expected_case_revision:
                return self._error("FIFO_BATCH_CASE_REVISION_CONFLICT")
            case = self._decode_case(current["case"])
            prerequisite_error = self._validate_case(scope, case)
            if prerequisite_error:
                return self._error(prerequisite_error)
            if self._cost_fingerprint(case) != preview.cost_input_fingerprint:
                return self._error("FIFO_BATCH_COST_CHANGED_AFTER_PREVIEW")

            rows = FifoCostBatchSupplyStore.read_rule_revisions(
                connection, scope=scope, case_id=case_id,
                tenant_fingerprint=tenant["tenant_fingerprint"], limit=100,
            )
            if self._rule_head_fingerprint(rows) != preview.rule_head_fingerprint:
                return self._error("FIFO_BATCH_RULE_HEAD_CHANGED_AFTER_PREVIEW")
            current_head_revision = max(
                (row["rule_revision"] for row in rows), default=0,
            )
            if current_head_revision != preview.expected_rule_head_revision:
                return self._error("FIFO_BATCH_RULE_HEAD_CHANGED_AFTER_PREVIEW")
            active_result = self._active_rule(rows)
            if active_result.get("error"):
                return active_result
            active = active_result.get("item")
            if active is None:
                if case.supply_total_mode is not SupplyTotalMode.LEGACY_OWNER_TOTAL:
                    return self._error("FIFO_BATCH_RULE_MODE_MISMATCH")
                if rows or preview.close_active_rule_revision is not None:
                    return self._error("FIFO_BATCH_RULE_HISTORY_NEEDS_REVIEW")
                if preview.start_local_date != case.dispatch_date:
                    return self._error("FIFO_BATCH_FIRST_BOUNDARY_MUST_MATCH_DISPATCH_DATE")
            else:
                if case.supply_total_mode is not SupplyTotalMode.AUTO_FROM_SUPPLIES:
                    return self._error("FIFO_BATCH_RULE_MODE_MISMATCH")
                if (
                    preview.close_active_rule_revision != current_head_revision + 1
                    or preview.predecessor_rule_id != active["rule_id"]
                    or preview.predecessor_rule_revision
                    != preview.close_active_rule_revision
                    or preview.start_local_date <= active["start_local_date"]
                ):
                    return self._error("FIFO_BATCH_RULE_HEAD_CHANGED_AFTER_PREVIEW")

            if preview.rule_revision != (
                current_head_revision + (2 if active is not None else 1)
            ):
                return self._error("FIFO_BATCH_RULE_HEAD_CHANGED_AFTER_PREVIEW")

            case_scope = case.metadata.scope
            if active is not None:
                close = self._revision(
                    scope=case_scope,
                    case_id=case_id,
                    rule_id=active["rule_id"],
                    rule_revision=preview.close_active_rule_revision,
                    start_local_date=active["start_local_date"],
                    store_timezone=active["store_timezone"],
                    start_day_policy=BatchStartDayPolicy(active["start_day_policy"]),
                    new_unit_cost_rub=active["new_unit_cost_rub"],
                    cost_input_fingerprint=active["cost_input_fingerprint"],
                    boundary_supply_digests=tuple(json.loads(
                        active["boundary_supply_digests_json"],
                    )),
                    predecessor_rule_id=active["rule_id"],
                    predecessor_rule_revision=active["rule_revision"],
                    event_kind=BatchRuleEventKind.CLOSE,
                    end_local_date_exclusive=preview.start_local_date,
                    owner_confirmation_fingerprint=confirmation_fingerprint,
                    confirmed_at_utc=now_text,
                )
                closed = FifoCostBatchSupplyStore.append_rule_revision(
                    connection, close,
                    tenant_fingerprint=tenant["tenant_fingerprint"],
                    idempotency_key=idempotency_key + "-close",
                    recorded_at=now_text,
                )
                if closed.get("error"):
                    return closed

            new_rule = self._revision(
                scope=case_scope,
                case_id=case_id,
                rule_id=preview.rule_id,
                rule_revision=preview.rule_revision,
                start_local_date=preview.start_local_date,
                store_timezone=preview.store_timezone,
                start_day_policy=preview.start_day_policy,
                new_unit_cost_rub=preview.new_unit_cost_rub,
                cost_input_fingerprint=preview.cost_input_fingerprint,
                boundary_supply_digests=preview.boundary_supply_digests,
                predecessor_rule_id=(active["rule_id"] if active is not None else None),
                predecessor_rule_revision=(
                    preview.close_active_rule_revision if active is not None else None
                ),
                event_kind=(
                    BatchRuleEventKind.REPLACE if active is not None
                    else BatchRuleEventKind.CONFIRM
                ),
                end_local_date_exclusive=None,
                owner_confirmation_fingerprint=confirmation_fingerprint,
                confirmed_at_utc=now_text,
            )
            appended = FifoCostBatchSupplyStore.append_rule_revision(
                connection, new_rule,
                tenant_fingerprint=tenant["tenant_fingerprint"],
                idempotency_key=idempotency_key,
                recorded_at=now_text,
            )
            if appended.get("error"):
                return appended

            updated_case = replace(
                case,
                case_revision=expected_case_revision + 1,
                updated_at=max(now_text, case.updated_at),
                supply_total_mode=SupplyTotalMode.AUTO_FROM_SUPPLIES,
            )
            saved = FifoCostTransitionStore.save_case(
                connection, updated_case, tenant,
                expected_revision=expected_case_revision,
                idempotency_key=idempotency_key + "-case",
                recorded_at=now_text,
            )
            if saved.get("error"):
                return saved
            return {
                "error": False,
                "code": "FIFO_BATCH_RULE_CONFIRMED",
                "case_id": case_id,
                "case_revision": updated_case.case_revision,
                "rule_id": new_rule.rule_id,
                "rule_revision": new_rule.rule_revision,
                "replayed": False,
            }

        return self.repository._run_transition_write(operation)

    def _read_case(self, scope: ScopeIdentity, case_id: str) -> dict:
        result = self.repository.read_transition_case(
            case_id=case_id, store_id=scope.store_id,
            product_id=scope.product_id, offer_id=scope.offer_id, sku=scope.sku,
        )
        if result.get("error"):
            return result
        payload_scope = result["case"].get("metadata", {}).get("scope", {})
        if (
            payload_scope.get("store_id") != scope.store_id
            or payload_scope.get("product_id") != scope.product_id
            or payload_scope.get("offer_id") != scope.offer_id
            or payload_scope.get("sku") != scope.sku
        ):
            return self._error("FIFO_BATCH_RULE_SCOPE_MISMATCH")
        try:
            case = self._decode_case(result["case"])
        except (KeyError, TypeError, ValueError):
            return self._error("FIFO_TRANSITION_CASE_CORRUPT")
        if case.metadata.scope.owner_id != scope.owner_id:
            return self._error("FIFO_BATCH_RULE_SCOPE_MISMATCH")
        return {**result, "case": case}

    def _read_rules(self, scope, case_id, tenant_fingerprint) -> dict:
        connection = None
        try:
            connection = self.repository.get_connection()
            rows = FifoCostBatchSupplyStore.read_rule_revisions(
                connection, scope=scope, case_id=case_id,
                tenant_fingerprint=tenant_fingerprint, limit=100,
            )
            return {"error": False, "items": rows}
        except (OSError, sqlite3.Error, ValueError, TypeError):
            return self._error("FIFO_BATCH_RULE_STORAGE_UNAVAILABLE")
        finally:
            if connection is not None:
                connection.close()

    @staticmethod
    def _active_rule(rows: tuple[dict, ...]) -> dict:
        latest_by_rule: dict[str, dict] = {}
        for row in rows:
            current = latest_by_rule.get(row["rule_id"])
            if current is None or row["rule_revision"] > current["rule_revision"]:
                latest_by_rule[row["rule_id"]] = row
        active = [
            row for row in latest_by_rule.values()
            if row["event_kind"] in {"CONFIRM", "REPLACE"}
            and row["end_local_date_exclusive"] is None
        ]
        if len(active) > 1:
            return {"error": True, "code": "FIFO_BATCH_RULE_CHAIN_CONFLICT"}
        return {"error": False, "item": active[0] if active else None}

    @staticmethod
    def _validate_case(scope: ScopeIdentity, case: TransitionCase) -> str | None:
        if case.metadata.scope != scope:
            return "FIFO_BATCH_RULE_SCOPE_MISMATCH"
        if case.state not in {TransitionState.DRAFT, TransitionState.AWAITING_EVIDENCE}:
            return "FIFO_BATCH_CASE_NOT_READY"
        if case.dispatch_date is None:
            return "FIFO_BATCH_DISPATCH_DATE_UNKNOWN"
        if case.old_unit_cost_rub is None or case.new_unit_cost_rub is None:
            return "FIFO_BATCH_COST_UNKNOWN"
        if case.new_unit_cost_rub <= 0:
            return "FIFO_BATCH_COST_INVALID"
        if case.owner_old_home_units != 0:
            return "FIFO_BATCH_OLD_HOME_NOT_CONFIRMED_ZERO"
        if case.owner_old_transit_units != 0:
            return "FIFO_BATCH_OLD_TRANSIT_NOT_CONFIRMED_ZERO"
        if not case.metadata.store_timezone:
            return "FIFO_BATCH_STORE_TIMEZONE_UNKNOWN"
        return None

    @staticmethod
    def _decode_case(payload: dict) -> TransitionCase:
        return FifoCostTransitionService._case_from_payload(payload)

    @staticmethod
    def _scope_payload(scope: ScopeIdentity) -> dict:
        return {
            "owner_id": scope.owner_id,
            "store_id": scope.store_id,
            "product_id": scope.product_id,
            "offer_id": scope.offer_id,
            "sku": scope.sku,
        }

    @classmethod
    def _cost_fingerprint(cls, case: TransitionCase) -> str:
        components = case.cost_components
        return cls._digest({
            "scope": cls._scope_payload(case.metadata.scope),
            "case_id": case.case_id,
            "case_revision": case.case_revision,
            "dispatch_date": case.dispatch_date,
            "store_timezone": case.metadata.store_timezone,
            "cost_input_mode": case.cost_input_mode.value,
            "old_unit_cost_rub": (
                str(case.old_unit_cost_rub) if case.old_unit_cost_rub is not None else None
            ),
            "new_unit_cost_rub": (
                str(case.new_unit_cost_rub) if case.new_unit_cost_rub is not None else None
            ),
            "supply_total_mode": case.supply_total_mode.value,
            "declared_shipped_units": case.declared_shipped_units,
            "cost_components": (
                {
                    "purchase_cost_rub": str(components.purchase_cost_rub),
                    "delivery_cost_rub": str(components.delivery_cost_rub),
                    "packaging_cost_rub": str(components.packaging_cost_rub),
                } if components is not None else None
            ),
            "old_home_units": case.owner_old_home_units,
            "old_transit_units": case.owner_old_transit_units,
        })

    @classmethod
    def _rule_head_fingerprint(cls, rows) -> str:
        return cls._digest({"rule_revisions": [dict(row) for row in rows]})

    @classmethod
    def _revision(
        cls, *, scope, case_id, rule_id, rule_revision, start_local_date,
        store_timezone, start_day_policy, new_unit_cost_rub,
        cost_input_fingerprint, boundary_supply_digests,
        predecessor_rule_id, predecessor_rule_revision, event_kind,
        end_local_date_exclusive, owner_confirmation_fingerprint,
        confirmed_at_utc,
    ) -> BatchRuleRevision:
        payload = {
            "scope": cls._scope_payload(scope),
            "case_id": case_id,
            "rule_id": rule_id,
            "rule_revision": rule_revision,
            "policy_version": 1,
            "start_local_date": start_local_date,
            "store_timezone": store_timezone,
            "start_day_policy": start_day_policy.value,
            "new_unit_cost_rub": str(new_unit_cost_rub),
            "cost_input_fingerprint": cost_input_fingerprint,
            "old_home_confirmed_zero": True,
            "old_transit_confirmed_zero": True,
            "boundary_supply_digests": boundary_supply_digests,
            "predecessor_rule_id": predecessor_rule_id,
            "predecessor_rule_revision": predecessor_rule_revision,
            "event_kind": event_kind.value,
            "end_local_date_exclusive": end_local_date_exclusive,
            "owner_confirmation_fingerprint": owner_confirmation_fingerprint,
            "confirmed_at_utc": confirmed_at_utc,
            "applied_rate_reference": None,
        }
        return BatchRuleRevision(
            scope=scope,
            case_id=case_id,
            rule_id=rule_id,
            rule_revision=rule_revision,
            policy_version=1,
            start_local_date=start_local_date,
            store_timezone=store_timezone,
            start_day_policy=start_day_policy,
            new_unit_cost_rub=new_unit_cost_rub,
            cost_input_fingerprint=cost_input_fingerprint,
            old_home_confirmed_zero=True,
            old_transit_confirmed_zero=True,
            boundary_supply_digests=boundary_supply_digests,
            predecessor_rule_id=predecessor_rule_id,
            predecessor_rule_revision=predecessor_rule_revision,
            event_kind=event_kind,
            end_local_date_exclusive=end_local_date_exclusive,
            owner_confirmation_fingerprint=owner_confirmation_fingerprint,
            confirmed_at_utc=confirmed_at_utc,
            rule_fingerprint=cls._digest(payload),
            applied_rate_reference=None,
        )

    @staticmethod
    def _digest(value) -> str:
        encoded = json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def _now(self) -> datetime:
        value = self._now_provider()
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("FIFO_CLOCK_INVALID")
        return value.astimezone(timezone.utc)

    @staticmethod
    def _iso(value: datetime) -> str:
        return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace(
            "+00:00", "Z",
        )

    def _purge_expired(self, now: datetime) -> None:
        now_text = self._iso(now)
        for preview_id, preview in tuple(self._previews.items()):
            if preview.expires_at_utc <= now_text:
                self._previews.pop(preview_id, None)

    @staticmethod
    def _error(code: str) -> dict:
        return {"error": True, "code": code}
