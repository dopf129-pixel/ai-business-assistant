"""Scoped SQL helpers for FIFO batch rules and supply observations.

The caller supplies an already-open repository connection and trusted tenant
fingerprints. This module does not open databases, contact Ozon, decrypt lookup
tokens, or write FIFO accounting events.
"""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from decimal import Decimal
from enum import Enum
import hashlib
import json
import re
import sqlite3

from services.fifo_cost_batch_rule_contracts import (
    MAX_BATCH_SCAN_CONTINUATION_BYTES,
    MAX_BATCH_MEMBERSHIP_DECISIONS,
    MAX_BATCH_OBSERVATIONS,
    MAX_BATCH_TOTAL_CONTROLS,
    MAX_RULE_REVISIONS,
    BatchMembershipDecision,
    BatchRuleRevision,
    BatchTotalControl,
    BatchTotalControlStatus,
    SupplyScanCoverage,
    SupplySkuObservation,
)
from services.fifo_cost_transition_contracts import ScopeIdentity


_HEX = re.compile(r"^[0-9a-f]{64}$")
_OPAQUE = re.compile(r"^[A-Za-z0-9_-]{8,128}$")
_SCAN_STATUSES = frozenset({"STAGING", "PARTIAL", "PUBLISHED", "FAILED", "EXPIRED"})
_RESUMABLE_SCAN_STATUSES = frozenset({"STAGING", "PARTIAL"})
_TERMINAL_SCAN_STATUSES = frozenset({"PUBLISHED", "FAILED", "EXPIRED"})
_MAX_SCANS_PER_CASE = 100
_LEGACY_SCAN_TOKEN_BYTES = 8192
_MAX_CONTINUATION_BYTES_PER_CASE = 64 * 1024 * 1024
_SOURCE_FINGERPRINT_ROW_LIMITS = {
    "fifo_cost_batch_rule_revisions": MAX_RULE_REVISIONS,
    "fifo_cost_batch_supply_observations": MAX_BATCH_OBSERVATIONS,
    "fifo_cost_batch_membership_decisions": MAX_BATCH_MEMBERSHIP_DECISIONS,
    "fifo_cost_batch_supply_scans": _MAX_SCANS_PER_CASE,
    "fifo_cost_batch_scan_continuations": _MAX_SCANS_PER_CASE,
    "fifo_cost_batch_total_controls": MAX_BATCH_TOTAL_CONTROLS,
}


class FifoCostBatchSupplyStore:
    """Transaction-bound persistence for immutable business evidence."""

    @classmethod
    def append_rule_revision(
        cls, connection, rule: BatchRuleRevision, *, tenant_fingerprint: str,
        idempotency_key: str, recorded_at: str,
    ) -> dict:
        cls._require_transaction(connection)
        if not isinstance(rule, BatchRuleRevision):
            raise TypeError("FIFO_BATCH_RULE_INVALID")
        cls._validate_scope_inputs(rule.scope, rule.case_id, tenant_fingerprint)
        cls._validate_opaque(idempotency_key)
        cls._validate_time_text(recorded_at)
        scope_fingerprint = cls._scope_fingerprint(rule.scope)
        payload = cls._payload(rule)
        payload_fingerprint = cls._digest(payload)
        owner_fingerprint = cls._digest(rule.scope.owner_id)
        case = cls._case_row(
            connection, rule.scope, rule.case_id, owner_fingerprint, tenant_fingerprint,
        )
        if case is None:
            return cls._error("FIFO_BATCH_SCOPE_MISMATCH")
        replay = cls._idempotent_result(
            connection, "fifo_cost_batch_rule_revisions", rule.case_id,
            idempotency_key, payload_fingerprint, "rule_event_id",
        )
        if replay is not None:
            return replay
        revision_count = connection.execute(
            "SELECT COUNT(*) FROM fifo_cost_batch_rule_revisions WHERE case_id=?",
            (rule.case_id,),
        ).fetchone()[0]
        if revision_count >= MAX_RULE_REVISIONS:
            return cls._error("FIFO_BATCH_RULE_LIMIT_REACHED")
        event_id = f"{rule.rule_id}-r{rule.rule_revision}"
        connection.execute(
            """INSERT INTO fifo_cost_batch_rule_revisions (
                rule_event_id, rule_id, rule_revision, case_id, owner_fingerprint,
                tenant_fingerprint, store_id, sku, product_id, offer_id,
                scope_fingerprint, policy_version, start_local_date, store_timezone,
                start_day_policy, new_unit_cost_rub, cost_input_fingerprint,
                old_home_confirmed_zero, old_transit_confirmed_zero,
                boundary_supply_digests_json, predecessor_rule_id,
                predecessor_rule_revision, event_kind, end_local_date_exclusive,
                owner_confirmation_fingerprint, confirmed_at_utc, rule_fingerprint,
                applied_rate_reference, idempotency_key, payload_fingerprint, recorded_at
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 1, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?, ?, ?
            )""",
            (
                event_id, rule.rule_id, rule.rule_revision, rule.case_id,
                owner_fingerprint, tenant_fingerprint, rule.scope.store_id,
                rule.scope.sku, rule.scope.product_id, rule.scope.offer_id,
                scope_fingerprint, rule.policy_version, rule.start_local_date,
                rule.store_timezone, rule.start_day_policy.value,
                str(rule.new_unit_cost_rub), rule.cost_input_fingerprint,
                cls._json(list(rule.boundary_supply_digests), 65536),
                rule.predecessor_rule_id, rule.predecessor_rule_revision,
                rule.event_kind.value, rule.end_local_date_exclusive,
                rule.owner_confirmation_fingerprint, rule.confirmed_at_utc,
                rule.rule_fingerprint, rule.applied_rate_reference, idempotency_key,
                payload_fingerprint, recorded_at,
            ),
        )
        return {"error": False, "code": "FIFO_BATCH_RULE_STORED", "rule_event_id": event_id}

    @classmethod
    def append_observation(
        cls, connection, observation: SupplySkuObservation, *, tenant_fingerprint: str,
        case_id: str, observation_id: str, recorded_at: str,
    ) -> dict:
        cls._require_transaction(connection)
        if not isinstance(observation, SupplySkuObservation):
            raise TypeError("FIFO_BATCH_OBSERVATION_INVALID")
        cls._validate_scope_inputs(observation.scope, case_id, tenant_fingerprint)
        cls._validate_opaque(observation_id)
        cls._validate_time_text(recorded_at)
        owner_fingerprint = cls._digest(observation.scope.owner_id)
        case = cls._case_row(
            connection, observation.scope, case_id, owner_fingerprint, tenant_fingerprint,
        )
        if case is None:
            return cls._error("FIFO_BATCH_SCOPE_MISMATCH")
        scope_fingerprint = cls._scope_fingerprint(observation.scope)
        existing = connection.execute(
            """SELECT observation_id, observation_revision
               FROM fifo_cost_batch_supply_observations
               WHERE case_id=? AND record_key=? AND source_fingerprint=?""",
            (case["case_id"], observation.record_key, observation.source_fingerprint),
        ).fetchone()
        if existing is not None:
            return {
                "error": False, "code": "FIFO_BATCH_OBSERVATION_STORED",
                "observation_id": existing["observation_id"],
                "observation_revision": existing["observation_revision"],
                "replayed": True,
            }
        observation_count, encrypted_bytes = connection.execute(
            """SELECT COUNT(*), COALESCE(SUM(length(encrypted_lookup_payload)), 0)
               FROM fifo_cost_batch_supply_observations WHERE case_id=?""",
            (case["case_id"],),
        ).fetchone()
        encrypted_lookup = observation.encrypted_lookup_payload.encode("ascii")
        if (
            observation_count >= MAX_BATCH_OBSERVATIONS
            or encrypted_bytes + len(encrypted_lookup) > 64 * 1024 * 1024
        ):
            return cls._error("FIFO_BATCH_OBSERVATION_LIMIT_REACHED")
        revision = connection.execute(
            """SELECT COALESCE(MAX(observation_revision), 0) + 1
               FROM fifo_cost_batch_supply_observations
               WHERE case_id=? AND record_key=?""",
            (case["case_id"], observation.record_key),
        ).fetchone()[0]
        payload_fingerprint = cls._digest(cls._payload(observation))
        if len(encrypted_lookup) > 4096:
            raise ValueError("FIFO_BATCH_LOOKUP_TOKEN_INVALID")
        connection.execute(
            """INSERT INTO fifo_cost_batch_supply_observations (
                observation_id, case_id, owner_fingerprint, tenant_fingerprint,
                store_id, sku, product_id, offer_id, scope_fingerprint, record_key,
                observation_revision, order_ref_digest, supply_ref_digest,
                encrypted_lookup_payload, source_profile_version, source_fingerprint,
                captured_at, source_as_of, source_status, normalized_status,
                is_crossdock, dispatch_local_date, dispatch_local_time,
                dispatch_time_status, planned_declared_quantity,
                shipped_composition_quantity, accepted_quantity, quantity_source_kind,
                quantity_coverage, acceptance_fingerprint, acceptance_version,
                explicit_zero_fields_json, membership, issues_json,
                payload_fingerprint, recorded_at
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )""",
            (
                observation_id, case["case_id"], owner_fingerprint, tenant_fingerprint,
                observation.scope.store_id, observation.scope.sku,
                observation.scope.product_id, observation.scope.offer_id,
                scope_fingerprint, observation.record_key, revision,
                observation.order_ref_digest, observation.supply_ref_digest,
                sqlite3.Binary(encrypted_lookup), observation.source_profile_version,
                observation.source_fingerprint, observation.captured_at,
                observation.source_as_of, observation.source_status,
                observation.normalized_status.value,
                None if observation.is_crossdock is None else int(observation.is_crossdock),
                observation.dispatch_local_date, observation.dispatch_local_time,
                observation.dispatch_time_status.value,
                observation.planned_declared_quantity,
                observation.shipped_composition_quantity, observation.accepted_quantity,
                observation.quantity_source_kind.value, observation.quantity_coverage.value,
                observation.acceptance_fingerprint, observation.acceptance_version,
                cls._json(list(observation.explicit_zero_fields), 1024),
                observation.membership.value, cls._json(list(observation.issues), 8192),
                payload_fingerprint, recorded_at,
            ),
        )
        return {
            "error": False, "code": "FIFO_BATCH_OBSERVATION_STORED",
            "observation_id": observation_id, "observation_revision": revision,
            "replayed": False,
        }

    @classmethod
    def append_membership_decision(
        cls, connection, decision: BatchMembershipDecision, *,
        tenant_fingerprint: str, recorded_at: str,
    ) -> dict:
        cls._require_transaction(connection)
        if not isinstance(decision, BatchMembershipDecision):
            raise TypeError("FIFO_BATCH_DECISION_INVALID")
        cls._validate_scope_inputs(decision.scope, decision.case_id, tenant_fingerprint)
        cls._validate_opaque(decision.idempotency_key)
        cls._validate_time_text(recorded_at)
        owner_fingerprint = cls._digest(decision.scope.owner_id)
        case = cls._case_row(
            connection, decision.scope, decision.case_id,
            owner_fingerprint, tenant_fingerprint,
        )
        if case is None:
            return cls._error("FIFO_BATCH_SCOPE_MISMATCH")
        rule = connection.execute(
            """SELECT rule_fingerprint FROM fifo_cost_batch_rule_revisions
               WHERE case_id=? AND rule_id=? AND rule_revision=?""",
            (decision.case_id, decision.rule_id, decision.rule_revision),
        ).fetchone()
        if rule is None:
            return cls._error("FIFO_BATCH_RULE_NOT_FOUND")
        observations = []
        for record_key, fingerprint in decision.relevant_source_fingerprints:
            row = connection.execute(
                """SELECT 1 FROM fifo_cost_batch_supply_observations
                   WHERE case_id=? AND record_key=? AND source_fingerprint=?""",
                (decision.case_id, record_key, fingerprint),
            ).fetchone()
            if row is None:
                return cls._error("FIFO_BATCH_OBSERVATION_NOT_FOUND")
            observations.append((record_key, fingerprint))
        payload_fingerprint = cls._digest(cls._payload(decision))
        replay = cls._idempotent_result(
            connection, "fifo_cost_batch_membership_decisions", decision.case_id,
            decision.idempotency_key, payload_fingerprint, "decision_id",
        )
        if replay is not None:
            return replay
        scope_fingerprint = cls._scope_fingerprint(decision.scope)
        connection.execute(
            """INSERT INTO fifo_cost_batch_membership_decisions (
                decision_id, revision, case_id, owner_fingerprint, tenant_fingerprint,
                store_id, sku, product_id, offer_id, scope_fingerprint, rule_id,
                rule_revision, rule_fingerprint, decision, source, record_keys_json,
                relevant_source_fingerprints_json, candidate_set_fingerprint,
                membership_binding_fingerprint, idempotency_key, confirmed_at,
                previous_decision_ref, payload_fingerprint, recorded_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                decision.decision_id, decision.revision, decision.case_id,
                owner_fingerprint, tenant_fingerprint, decision.scope.store_id,
                decision.scope.sku, decision.scope.product_id, decision.scope.offer_id,
                scope_fingerprint, decision.rule_id, decision.rule_revision,
                rule["rule_fingerprint"], decision.decision.value, decision.source.value,
                cls._json(list(decision.record_keys), 8192),
                cls._json([list(pair) for pair in decision.relevant_source_fingerprints], 8192),
                decision.candidate_set_fingerprint, decision.membership_binding_fingerprint,
                decision.idempotency_key, decision.confirmed_at,
                decision.previous_decision_ref, payload_fingerprint, recorded_at,
            ),
        )
        for record_key, fingerprint in observations:
            connection.execute(
                """INSERT INTO fifo_cost_batch_membership_decision_observations (
                    decision_id, case_id, record_key, source_fingerprint
                ) VALUES (?, ?, ?, ?)""",
                (decision.decision_id, decision.case_id, record_key, fingerprint),
            )
        return {
            "error": False, "code": "FIFO_BATCH_DECISION_STORED",
            "decision_id": decision.decision_id, "replayed": False,
        }

    @classmethod
    def append_total_control(
        cls, connection, control: BatchTotalControl, *,
        tenant_fingerprint: str, recorded_at: str,
    ) -> dict:
        """Append one scoped owner control without turning it into a lasting cap."""
        cls._require_transaction(connection)
        if not isinstance(control, BatchTotalControl):
            raise TypeError("FIFO_BATCH_TOTAL_CONTROL_INVALID")
        cls._validate_scope_inputs(control.scope, control.case_id, tenant_fingerprint)
        cls._validate_opaque(control.idempotency_key)
        cls._validate_time_text(recorded_at)
        owner_fingerprint = cls._digest(control.scope.owner_id)
        case = cls._case_row(
            connection, control.scope, control.case_id,
            owner_fingerprint, tenant_fingerprint,
        )
        if case is None:
            return cls._error("FIFO_BATCH_SCOPE_MISMATCH")

        payload = cls._payload(control)
        payload_fingerprint = cls._digest(payload)
        replay = cls._idempotent_result(
            connection, "fifo_cost_batch_total_controls", control.case_id,
            control.idempotency_key, payload_fingerprint, "control_id",
        )
        if replay is not None:
            return replay

        count = connection.execute(
            "SELECT COUNT(*) FROM fifo_cost_batch_total_controls WHERE case_id=?",
            (control.case_id,),
        ).fetchone()[0]
        if count >= MAX_BATCH_TOTAL_CONTROLS:
            return cls._error("FIFO_BATCH_TOTAL_CONTROL_LIMIT_REACHED")
        previous = connection.execute(
            """SELECT control_revision, total_units, window_from, window_through,
                      control_kind, control_status, source_proof_fingerprint
               FROM fifo_cost_batch_total_controls
               WHERE case_id=? AND control_id=? ORDER BY control_revision DESC LIMIT 1""",
            (control.case_id, control.control_id),
        ).fetchone()
        expected_revision = 1 if previous is None else previous["control_revision"] + 1
        if control.control_revision != expected_revision:
            return cls._error("FIFO_BATCH_CONTROL_REVISION_CONFLICT")
        if previous is None:
            if control.control_status is not BatchTotalControlStatus.OWNER_CONFIRMED:
                return cls._error("FIFO_BATCH_CONTROL_STATUS_CONFLICT")
        elif (
            previous["control_revision"] != 1
            or previous["control_status"] != BatchTotalControlStatus.OWNER_CONFIRMED.value
            or control.control_status not in {
                BatchTotalControlStatus.SUPERSEDED,
                BatchTotalControlStatus.REVOKED,
            }
            or previous["total_units"] != control.total_units
            or previous["window_from"] != control.window_from
            or previous["window_through"] != control.window_through
            or previous["control_kind"] != control.control_kind.value
            or previous["source_proof_fingerprint"] != control.source_proof_fingerprint
        ):
            return cls._error("FIFO_BATCH_CONTROL_STATUS_CONFLICT")

        scope_fingerprint = cls._scope_fingerprint(control.scope)
        connection.execute(
            """INSERT INTO fifo_cost_batch_total_controls (
                control_id, control_revision, case_id, owner_fingerprint,
                tenant_fingerprint, store_id, sku, product_id, offer_id,
                scope_fingerprint, total_units, window_from, window_through,
                control_kind, control_status, source_proof_fingerprint,
                owner_confirmation_fingerprint, idempotency_key,
                payload_fingerprint, confirmed_at, recorded_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                control.control_id, control.control_revision, control.case_id,
                owner_fingerprint, tenant_fingerprint, control.scope.store_id,
                control.scope.sku, control.scope.product_id, control.scope.offer_id,
                scope_fingerprint, control.total_units, control.window_from,
                control.window_through, control.control_kind.value,
                control.control_status.value, control.source_proof_fingerprint,
                control.owner_confirmation_fingerprint, control.idempotency_key,
                payload_fingerprint, control.confirmed_at, recorded_at,
            ),
        )
        return {
            "error": False, "code": "FIFO_BATCH_TOTAL_CONTROL_STORED",
            "control_id": control.control_id,
            "control_revision": control.control_revision,
            "replayed": False,
        }

    @classmethod
    def write_scan_checkpoint(
        cls, connection, coverage: SupplyScanCoverage, *, tenant_fingerprint: str,
        expected_revision: int, status: str, expires_at: str, updated_at: str,
        encrypted_resumable_token: bytes | None = None,
    ) -> dict:
        cls._require_transaction(connection)
        if not isinstance(coverage, SupplyScanCoverage):
            raise TypeError("FIFO_BATCH_SCAN_INVALID")
        cls._validate_scope_inputs(coverage.scope, coverage.case_id, tenant_fingerprint)
        cls._validate_time_text(expires_at)
        cls._validate_time_text(updated_at)
        if type(expected_revision) is not int or expected_revision < 0:
            raise ValueError("FIFO_BATCH_SCAN_REVISION_INVALID")
        if coverage.revision != expected_revision + 1:
            return cls._error("FIFO_BATCH_SCAN_REVISION_CONFLICT")
        if status not in _SCAN_STATUSES:
            raise ValueError("FIFO_BATCH_SCAN_STATUS_INVALID")
        token = encrypted_resumable_token
        if token is not None and (
            not isinstance(token, bytes)
            or not 80 <= len(token) <= MAX_BATCH_SCAN_CONTINUATION_BYTES
            or not token.startswith(b"gAAAA")
        ):
            raise ValueError("FIFO_BATCH_SCAN_TOKEN_INVALID")
        if (coverage.resumable_token is None) != (token is None):
            raise ValueError("FIFO_BATCH_SCAN_TOKEN_INVALID")
        legacy_token = (
            token if token is not None and len(token) <= _LEGACY_SCAN_TOKEN_BYTES
            else None
        )
        owner_fingerprint = cls._digest(coverage.scope.owner_id)
        case = cls._case_row(
            connection, coverage.scope, coverage.case_id,
            owner_fingerprint, tenant_fingerprint,
        )
        if case is None:
            return cls._error("FIFO_BATCH_SCOPE_MISMATCH")
        rule = connection.execute(
            """SELECT rule_fingerprint FROM fifo_cost_batch_rule_revisions
               WHERE case_id=? AND rule_revision=?
               ORDER BY rule_id LIMIT 2""",
            (coverage.case_id, coverage.rule_revision),
        ).fetchall()
        if len(rule) != 1:
            return cls._error("FIFO_BATCH_RULE_NOT_FOUND")
        existing = connection.execute(
            "SELECT revision, status FROM fifo_cost_batch_supply_scans "
            "WHERE case_id=? AND scan_id=?",
            (coverage.case_id, coverage.scan_id),
        ).fetchone()
        current_revision = 0 if existing is None else existing["revision"]
        if current_revision != expected_revision:
            return cls._error("FIFO_BATCH_SCAN_REVISION_CONFLICT")
        if status in _RESUMABLE_SCAN_STATUSES and token is None:
            return cls._error("FIFO_BATCH_SCAN_TOKEN_INVALID")
        if status in _TERMINAL_SCAN_STATUSES and token is not None:
            return cls._error("FIFO_BATCH_SCAN_TOKEN_INVALID")
        if existing is not None:
            if existing["status"] in _TERMINAL_SCAN_STATUSES:
                return cls._error("FIFO_BATCH_SCAN_TERMINAL")
            allowed_next = {
                "STAGING": {"STAGING", "PARTIAL", "PUBLISHED", "FAILED", "EXPIRED"},
                "PARTIAL": {"STAGING", "PARTIAL", "PUBLISHED", "FAILED", "EXPIRED"},
            }
            if status not in allowed_next.get(existing["status"], set()):
                return cls._error("FIFO_BATCH_SCAN_STATUS_CONFLICT")
        elif connection.execute(
            "SELECT COUNT(*) FROM fifo_cost_batch_supply_scans WHERE case_id=?",
            (coverage.case_id,),
        ).fetchone()[0] >= _MAX_SCANS_PER_CASE:
            return cls._error("FIFO_BATCH_SCAN_LIMIT_REACHED")
        rule_id = connection.execute(
            """SELECT rule_id FROM fifo_cost_batch_rule_revisions
               WHERE case_id=? AND rule_revision=? LIMIT 1""",
            (coverage.case_id, coverage.rule_revision),
        ).fetchone()["rule_id"]
        scope_fingerprint = cls._scope_fingerprint(coverage.scope)
        values = (
            owner_fingerprint, tenant_fingerprint, coverage.scope.store_id,
            coverage.scope.sku, coverage.scope.product_id, coverage.scope.offer_id,
            scope_fingerprint, coverage.revision, rule_id, coverage.rule_revision,
            rule[0]["rule_fingerprint"], coverage.requested_from,
            coverage.requested_through, coverage.captured_at, coverage.source_as_of,
            cls._json(list(coverage.supported_state_profile), 8192),
            int(coverage.list_pagination_complete), int(coverage.details_complete),
            int(coverage.sku_composition_complete), int(coverage.historical_window_proven),
            int(coverage.membership_complete), int(coverage.quantity_complete),
            int(coverage.physical_receipt_timing_complete),
            coverage.observation_set_fingerprint, coverage.source_contract_version,
            coverage.orders_seen, coverage.supplies_seen, coverage.sku_rows_seen,
            coverage.unknown_order_count, coverage.unknown_supply_count,
            coverage.unknown_quantity_supply_count,
            cls._json(list(coverage.issue_codes), 8192),
            None if legacy_token is None else sqlite3.Binary(legacy_token),
            status, expires_at, updated_at,
        )
        if existing is None:
            connection.execute(
                """INSERT INTO fifo_cost_batch_supply_scans (
                    scan_id, case_id, owner_fingerprint, tenant_fingerprint, store_id, sku,
                    product_id, offer_id, scope_fingerprint, revision, rule_id,
                    rule_revision, rule_fingerprint, requested_from, requested_through,
                    captured_at, source_as_of, supported_state_profile_json,
                    list_pagination_complete, details_complete, sku_composition_complete,
                    historical_window_proven, membership_complete, quantity_complete,
                    physical_receipt_timing_complete, observation_set_fingerprint,
                    source_contract_version, orders_seen, supplies_seen, sku_rows_seen,
                    unknown_order_count, unknown_supply_count,
                    unknown_quantity_supply_count, issue_codes_json,
                    encrypted_resumable_token, status, expires_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                          ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (coverage.scan_id, coverage.case_id, *values),
            )
        else:
            cursor = connection.execute(
                """UPDATE fifo_cost_batch_supply_scans SET
                    owner_fingerprint=?, tenant_fingerprint=?, store_id=?, sku=?,
                    product_id=?, offer_id=?, scope_fingerprint=?, revision=?, rule_id=?,
                    rule_revision=?, rule_fingerprint=?, requested_from=?, requested_through=?,
                    captured_at=?, source_as_of=?, supported_state_profile_json=?,
                    list_pagination_complete=?, details_complete=?, sku_composition_complete=?,
                    historical_window_proven=?, membership_complete=?, quantity_complete=?,
                    physical_receipt_timing_complete=?, observation_set_fingerprint=?,
                    source_contract_version=?, orders_seen=?, supplies_seen=?, sku_rows_seen=?,
                    unknown_order_count=?, unknown_supply_count=?,
                    unknown_quantity_supply_count=?, issue_codes_json=?,
                    encrypted_resumable_token=?, status=?, expires_at=?, updated_at=?
                   WHERE case_id=? AND scan_id=? AND revision=?""",
                (*values, coverage.case_id, coverage.scan_id, expected_revision),
            )
            if cursor.rowcount != 1:
                return cls._error("FIFO_BATCH_SCAN_REVISION_CONFLICT")
        if token is not None and len(token) > _LEGACY_SCAN_TOKEN_BYTES:
            stored_bytes = connection.execute(
                """SELECT COALESCE(SUM(length(encrypted_resumable_token)), 0)
                   FROM fifo_cost_batch_scan_continuations
                   WHERE case_id=? AND scan_id<>?""",
                (coverage.case_id, coverage.scan_id),
            ).fetchone()[0]
            if stored_bytes + len(token) > _MAX_CONTINUATION_BYTES_PER_CASE:
                return cls._error("FIFO_BATCH_SCAN_TOKEN_QUOTA_EXCEEDED")
            connection.execute(
                """INSERT INTO fifo_cost_batch_scan_continuations (
                       case_id, scan_id, encrypted_resumable_token, updated_at
                   ) VALUES (?, ?, ?, ?)
                   ON CONFLICT(case_id, scan_id) DO UPDATE SET
                       encrypted_resumable_token=excluded.encrypted_resumable_token,
                       updated_at=excluded.updated_at""",
                (
                    coverage.case_id, coverage.scan_id,
                    sqlite3.Binary(token), updated_at,
                ),
            )
        else:
            connection.execute(
                "DELETE FROM fifo_cost_batch_scan_continuations "
                "WHERE case_id=? AND scan_id=?",
                (coverage.case_id, coverage.scan_id),
            )
        return {
            "error": False, "code": "FIFO_BATCH_SCAN_STORED",
            "scan_id": coverage.scan_id, "revision": coverage.revision,
        }

    @classmethod
    def append_scan_observation(
        cls, connection, *, scope: ScopeIdentity, case_id: str,
        tenant_fingerprint: str, scan_id: str, record_key: str,
        source_fingerprint: str, linked_at: str, allow_finalizing: bool = False,
    ) -> dict:
        """Link immutable source evidence to one staged scan, idempotently."""
        cls._require_transaction(connection)
        cls._validate_scope_inputs(scope, case_id, tenant_fingerprint)
        cls._validate_opaque(scan_id)
        cls._validate_time_text(linked_at)
        record_key = cls._require_digest(record_key, "FIFO_BATCH_RECORD_KEY_INVALID")
        source_fingerprint = cls._require_digest(
            source_fingerprint, "FIFO_BATCH_SOURCE_FINGERPRINT_INVALID",
        )
        case = cls._case_row(
            connection, scope, case_id, cls._digest(scope.owner_id), tenant_fingerprint,
        )
        if case is None:
            return cls._error("FIFO_BATCH_SCOPE_MISMATCH")
        scan = connection.execute(
            """SELECT status FROM fifo_cost_batch_supply_scans
               WHERE case_id=? AND scan_id=? AND owner_fingerprint=?
                 AND tenant_fingerprint=? AND store_id=? AND sku=?
                 AND scope_fingerprint=?""",
            (
                case_id, scan_id, cls._digest(scope.owner_id), tenant_fingerprint,
                scope.store_id, scope.sku, cls._scope_fingerprint(scope),
            ),
        ).fetchone()
        if scan is None:
            return cls._error("FIFO_BATCH_SCAN_NOT_FOUND")
        if (
            scan["status"] not in _RESUMABLE_SCAN_STATUSES
            and not (allow_finalizing is True and scan["status"] == "PUBLISHED")
        ):
            return cls._error("FIFO_BATCH_SCAN_NOT_STAGING")
        observation = connection.execute(
            """SELECT observation_revision FROM fifo_cost_batch_supply_observations
               WHERE case_id=? AND record_key=? AND source_fingerprint=?
                 AND owner_fingerprint=? AND tenant_fingerprint=?
                 AND store_id=? AND sku=? AND scope_fingerprint=?""",
            (
                case_id, record_key, source_fingerprint, cls._digest(scope.owner_id),
                tenant_fingerprint, scope.store_id, scope.sku,
                cls._scope_fingerprint(scope),
            ),
        ).fetchone()
        if observation is None:
            return cls._error("FIFO_BATCH_OBSERVATION_NOT_FOUND")
        existing = connection.execute(
            """SELECT observation_revision FROM fifo_cost_batch_scan_observations
               WHERE case_id=? AND scan_id=? AND record_key=?
                 AND source_fingerprint=?""",
            (case_id, scan_id, record_key, source_fingerprint),
        ).fetchone()
        if existing is not None:
            if existing["observation_revision"] != observation["observation_revision"]:
                return cls._error("FIFO_BATCH_SCAN_OBSERVATION_CONFLICT")
            return {
                "error": False, "code": "FIFO_BATCH_SCAN_OBSERVATION_STORED",
                "observation_revision": existing["observation_revision"],
                "replayed": True,
            }
        if connection.execute(
            """SELECT COUNT(*) FROM fifo_cost_batch_scan_observations
               WHERE case_id=? AND scan_id=?""",
            (case_id, scan_id),
        ).fetchone()[0] >= 10_000:
            return cls._error("FIFO_BATCH_SCAN_OBSERVATION_LIMIT_REACHED")
        connection.execute(
            """INSERT INTO fifo_cost_batch_scan_observations (
                   case_id, scan_id, record_key, source_fingerprint,
                   observation_revision, linked_at
               ) VALUES (?, ?, ?, ?, ?, ?)""",
            (
                case_id, scan_id, record_key, source_fingerprint,
                observation["observation_revision"], linked_at,
            ),
        )
        return {
            "error": False, "code": "FIFO_BATCH_SCAN_OBSERVATION_STORED",
            "observation_revision": observation["observation_revision"],
            "replayed": False,
        }

    @classmethod
    def read_observation_revision(
        cls, connection, *, scope: ScopeIdentity, case_id: str,
        tenant_fingerprint: str, record_key: str, source_fingerprint: str,
    ) -> int | None:
        cls._validate_scope_inputs(scope, case_id, tenant_fingerprint)
        record_key = cls._require_digest(record_key, "FIFO_BATCH_RECORD_KEY_INVALID")
        source_fingerprint = cls._require_digest(
            source_fingerprint, "FIFO_BATCH_SOURCE_FINGERPRINT_INVALID",
        )
        if cls._case_row(
            connection, scope, case_id, cls._digest(scope.owner_id), tenant_fingerprint,
        ) is None:
            return None
        row = connection.execute(
            """SELECT observation_revision
               FROM fifo_cost_batch_supply_observations
               WHERE case_id=? AND record_key=? AND source_fingerprint=?
                 AND owner_fingerprint=? AND tenant_fingerprint=?
                 AND store_id=? AND sku=? AND scope_fingerprint=?""",
            (
                case_id, record_key, source_fingerprint, cls._digest(scope.owner_id),
                tenant_fingerprint, scope.store_id, scope.sku,
                cls._scope_fingerprint(scope),
            ),
        ).fetchone()
        return None if row is None else row["observation_revision"]

    @classmethod
    def next_observation_revision(
        cls, connection, *, scope: ScopeIdentity, case_id: str,
        tenant_fingerprint: str, record_key: str,
    ) -> int | None:
        cls._validate_scope_inputs(scope, case_id, tenant_fingerprint)
        record_key = cls._require_digest(record_key, "FIFO_BATCH_RECORD_KEY_INVALID")
        if cls._case_row(
            connection, scope, case_id, cls._digest(scope.owner_id), tenant_fingerprint,
        ) is None:
            return None
        row = connection.execute(
            """SELECT COALESCE(MAX(observation_revision), 0) + 1 AS next_revision
               FROM fifo_cost_batch_supply_observations
               WHERE case_id=? AND record_key=? AND owner_fingerprint=?
                 AND tenant_fingerprint=? AND store_id=? AND sku=?
                 AND scope_fingerprint=?""",
            (
                case_id, record_key, cls._digest(scope.owner_id), tenant_fingerprint,
                scope.store_id, scope.sku, cls._scope_fingerprint(scope),
            ),
        ).fetchone()
        return None if row is None else row["next_revision"]

    @classmethod
    def read_scan_observation_refs(
        cls, connection, *, scope: ScopeIdentity, case_id: str,
        tenant_fingerprint: str, scan_id: str, limit: int = 10_000,
    ) -> tuple[dict, ...]:
        cls._validate_scope_inputs(scope, case_id, tenant_fingerprint)
        cls._validate_opaque(scan_id)
        if type(limit) is not int or not 1 <= limit <= 10_000:
            raise ValueError("FIFO_BATCH_READ_LIMIT_INVALID")
        if cls._case_row(
            connection, scope, case_id, cls._digest(scope.owner_id), tenant_fingerprint,
        ) is None:
            return ()
        rows = connection.execute(
            """SELECT link.record_key, link.source_fingerprint,
                      link.observation_revision, link.linked_at
               FROM fifo_cost_batch_scan_observations AS link
               JOIN fifo_cost_batch_supply_scans AS scan
                 ON scan.case_id=link.case_id AND scan.scan_id=link.scan_id
               WHERE link.case_id=? AND link.scan_id=?
                 AND scan.owner_fingerprint=? AND scan.tenant_fingerprint=?
                 AND scan.store_id=? AND scan.sku=? AND scan.scope_fingerprint=?
               ORDER BY link.record_key, link.observation_revision,
                        link.source_fingerprint LIMIT ?""",
            (
                case_id, scan_id, cls._digest(scope.owner_id), tenant_fingerprint,
                scope.store_id, scope.sku, cls._scope_fingerprint(scope), limit,
            ),
        ).fetchall()
        return tuple(dict(row) for row in rows)

    @classmethod
    def read_latest_scan_checkpoint(
        cls, connection, *, scope: ScopeIdentity, case_id: str,
        tenant_fingerprint: str,
    ) -> dict | None:
        """Read the newest scoped scan, including incomplete scans.

        Callers must not fall back to an older published scan when a newer
        scan is partial, failed, or belongs to a prior rule revision.
        """
        cls._validate_scope_inputs(scope, case_id, tenant_fingerprint)
        if cls._case_row(
            connection, scope, case_id, cls._digest(scope.owner_id), tenant_fingerprint,
        ) is None:
            return None
        rows = connection.execute(
            """SELECT scan_id, updated_at, captured_at
               FROM fifo_cost_batch_supply_scans
               WHERE case_id=? AND owner_fingerprint=? AND tenant_fingerprint=?
                 AND store_id=? AND sku=? AND scope_fingerprint=?
               ORDER BY updated_at DESC, captured_at DESC, scan_id DESC LIMIT 2""",
            (
                case_id, cls._digest(scope.owner_id), tenant_fingerprint,
                scope.store_id, scope.sku, cls._scope_fingerprint(scope),
            ),
        ).fetchall()
        if not rows:
            return None
        if len(rows) > 1 and (
            rows[0]["updated_at"], rows[0]["captured_at"]
        ) == (
            rows[1]["updated_at"], rows[1]["captured_at"]
        ):
            return None
        return cls.read_scan_checkpoint(
            connection, scope=scope, case_id=case_id,
            tenant_fingerprint=tenant_fingerprint, scan_id=rows[0]["scan_id"],
        )

    @classmethod
    def read_scope_source_fingerprint(
        cls, connection, *, scope: ScopeIdentity, case_id: str,
        tenant_fingerprint: str,
    ) -> str:
        """Fingerprint every persisted batch input that can affect a manifest.

        The caller may run this inside the FIFO transition's ``BEGIN IMMEDIATE``
        transaction. That makes the comparison an atomic seal check against
        concurrent rule, scan, observation, membership, or control writes.
        Ciphertext is reduced to a digest before entering the canonical input.
        """
        cls._validate_scope_inputs(scope, case_id, tenant_fingerprint)
        owner_fingerprint = cls._digest(scope.owner_id)
        scope_fingerprint = cls._scope_fingerprint(scope)
        scoped_where = (
            "case_id=? AND owner_fingerprint=? AND tenant_fingerprint=? "
            "AND store_id=? AND sku=? AND product_id IS ? AND offer_id IS ? "
            "AND scope_fingerprint=?"
        )
        scoped_values = (
            case_id, owner_fingerprint, tenant_fingerprint, scope.store_id,
            scope.sku, scope.product_id, scope.offer_id, scope_fingerprint,
        )
        parent_where = (
            "parent.case_id=? AND parent.owner_fingerprint=? "
            "AND parent.tenant_fingerprint=? AND parent.store_id=? "
            "AND parent.sku=? AND parent.product_id IS ? "
            "AND parent.offer_id IS ? AND parent.scope_fingerprint=?"
        )
        sources = []
        scoped_tables = (
            (
                "fifo_cost_batch_rule_revisions",
                "rule_event_id, rule_id, rule_revision, rule_fingerprint, payload_fingerprint",
                "rule_id, rule_revision",
            ),
            (
                "fifo_cost_batch_supply_observations",
                "observation_id, record_key, observation_revision, source_fingerprint, payload_fingerprint",
                "record_key, observation_revision",
            ),
            (
                "fifo_cost_batch_membership_decisions",
                "decision_id, revision, rule_id, rule_revision, rule_fingerprint, "
                "candidate_set_fingerprint, membership_binding_fingerprint, payload_fingerprint",
                "decision_id, revision",
            ),
            ("fifo_cost_batch_supply_scans", "*", "scan_id"),
            (
                "fifo_cost_batch_total_controls",
                "control_id, control_revision, control_status, window_from, "
                "window_through, payload_fingerprint",
                "control_id, control_revision",
            ),
        )
        for table, selected, order_by in scoped_tables:
            row_limit = _SOURCE_FINGERPRINT_ROW_LIMITS[table]
            rows = connection.execute(
                f"SELECT {selected} FROM {table} WHERE {scoped_where} "
                f"ORDER BY {order_by} LIMIT ?",
                (*scoped_values, row_limit + 1),
            ).fetchall()
            if len(rows) > row_limit:
                raise ValueError("FIFO_BATCH_MANIFEST_SEAL_ROW_LIMIT_REACHED")
            sources.append({
                "table": table,
                "rows": [cls._fingerprint_row(row) for row in rows],
            })

        continuation_rows = connection.execute(
            """SELECT continuation.case_id, continuation.scan_id,
                      continuation.encrypted_resumable_token, continuation.updated_at
               FROM fifo_cost_batch_scan_continuations AS continuation
               JOIN fifo_cost_batch_supply_scans AS parent
                 ON parent.case_id=continuation.case_id
                AND parent.scan_id=continuation.scan_id
               WHERE """ + parent_where + " ORDER BY continuation.scan_id LIMIT ?",
            (*scoped_values, _MAX_SCANS_PER_CASE + 1),
        ).fetchall()
        if len(continuation_rows) > _MAX_SCANS_PER_CASE:
            raise ValueError("FIFO_BATCH_MANIFEST_SEAL_ROW_LIMIT_REACHED")
        sources.append({
            "table": "fifo_cost_batch_scan_continuations",
            "rows": [cls._fingerprint_row(row) for row in continuation_rows],
        })

        latest_scan = cls.read_latest_scan_checkpoint(
            connection, scope=scope, case_id=case_id,
            tenant_fingerprint=tenant_fingerprint,
        )
        latest_scan_id = latest_scan.get("scan_id") if latest_scan else None
        if latest_scan_id is not None:
            link_count = connection.execute(
                """SELECT COUNT(*)
                   FROM fifo_cost_batch_scan_observations AS link
                   JOIN fifo_cost_batch_supply_scans AS parent
                     ON parent.case_id=link.case_id AND parent.scan_id=link.scan_id
                   WHERE """ + parent_where + " AND parent.scan_id=?",
                (*scoped_values, latest_scan_id),
            ).fetchone()[0]
            if type(link_count) is not int or link_count > 10_000:
                raise ValueError("FIFO_BATCH_MANIFEST_SEAL_LINK_LIMIT_REACHED")
            rows = connection.execute(
                """SELECT link.*
                   FROM fifo_cost_batch_scan_observations AS link
                   JOIN fifo_cost_batch_supply_scans AS parent
                     ON parent.case_id=link.case_id AND parent.scan_id=link.scan_id
                   WHERE """ + parent_where + " AND parent.scan_id=? "
                "ORDER BY link.scan_id, link.record_key, link.source_fingerprint",
                (*scoped_values, latest_scan_id),
            ).fetchall()
            sources.append({
                "table": "fifo_cost_batch_scan_observations",
                "rows": [cls._fingerprint_row(row) for row in rows],
            })
        material = {
            "schema_version": 1,
            "case_id": case_id,
            "owner_fingerprint": owner_fingerprint,
            "tenant_fingerprint": tenant_fingerprint,
            "store_id": scope.store_id,
            "product_id": scope.product_id,
            "offer_id": scope.offer_id,
            "sku": scope.sku,
            "scope_fingerprint": scope_fingerprint,
            "sources": sources,
        }
        encoded = json.dumps(
            material, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    @staticmethod
    def _fingerprint_row(row):
        """Return a stable row map without exposing stored ciphertext."""
        def normalize(value):
            if isinstance(value, (bytes, bytearray, memoryview)):
                raw = bytes(value)
                return {
                    "bytes_sha256": hashlib.sha256(raw).hexdigest(),
                    "bytes_length": len(raw),
                }
            return value

        return {key: normalize(row[key]) for key in sorted(row.keys())}

    @classmethod
    def read_scan_observations(
        cls, connection, *, scope: ScopeIdentity, case_id: str,
        tenant_fingerprint: str, scan_id: str, limit: int = 10_000,
    ) -> tuple[dict, ...]:
        """Read bounded, typed-source columns linked to one exact scan.

        The encrypted lookup token is included only for rehydrating the typed
        contract inside the caller. It must never be rendered or returned to
        the owner.
        """
        cls._validate_scope_inputs(scope, case_id, tenant_fingerprint)
        cls._validate_opaque(scan_id)
        if type(limit) is not int or not 1 <= limit <= 10_000:
            raise ValueError("FIFO_BATCH_READ_LIMIT_INVALID")
        if cls._case_row(
            connection, scope, case_id, cls._digest(scope.owner_id), tenant_fingerprint,
        ) is None:
            return ()
        rows = connection.execute(
            """SELECT observation.record_key, observation.order_ref_digest,
                      observation.supply_ref_digest, observation.encrypted_lookup_payload,
                      observation.source_profile_version, observation.source_fingerprint,
                      observation.captured_at, observation.source_as_of,
                      observation.source_status, observation.normalized_status,
                      observation.is_crossdock, observation.dispatch_local_date,
                      observation.dispatch_local_time, observation.dispatch_time_status,
                      observation.planned_declared_quantity,
                      observation.shipped_composition_quantity,
                      observation.accepted_quantity, observation.quantity_source_kind,
                      observation.quantity_coverage, observation.acceptance_fingerprint,
                      observation.acceptance_version, observation.explicit_zero_fields_json,
                      observation.membership, observation.issues_json,
                      observation.observation_revision
               FROM fifo_cost_batch_scan_observations AS link
               JOIN fifo_cost_batch_supply_observations AS observation
                 ON observation.case_id=link.case_id
                AND observation.record_key=link.record_key
                AND observation.source_fingerprint=link.source_fingerprint
                AND observation.observation_revision=link.observation_revision
               JOIN fifo_cost_batch_supply_scans AS scan
                 ON scan.case_id=link.case_id AND scan.scan_id=link.scan_id
               WHERE link.case_id=? AND link.scan_id=?
                 AND scan.owner_fingerprint=observation.owner_fingerprint
                 AND scan.tenant_fingerprint=observation.tenant_fingerprint
                 AND scan.store_id=observation.store_id AND scan.sku=observation.sku
                 AND scan.scope_fingerprint=observation.scope_fingerprint
                 AND scan.owner_fingerprint=? AND scan.tenant_fingerprint=?
                 AND scan.store_id=? AND scan.sku=? AND scan.scope_fingerprint=?
               ORDER BY observation.record_key, observation.observation_revision,
                        observation.source_fingerprint LIMIT ?""",
            (
                case_id, scan_id, cls._digest(scope.owner_id), tenant_fingerprint,
                scope.store_id, scope.sku, cls._scope_fingerprint(scope), limit,
            ),
        ).fetchall()
        return tuple(dict(row) for row in rows)

    @classmethod
    def read_scan_observation_history(
        cls, connection, *, scope: ScopeIdentity, case_id: str,
        tenant_fingerprint: str, scan_id: str,
        limit: int = MAX_BATCH_OBSERVATIONS,
    ) -> tuple[dict, ...]:
        """Read bounded history for only the supply keys in one exact scan.

        The newest scan determines which supplies participate in the current
        manifest; earlier observations for those same supplies are retained
        so cumulative acceptance can be checked for impossible decreases.
        """
        cls._validate_scope_inputs(scope, case_id, tenant_fingerprint)
        cls._validate_opaque(scan_id)
        if type(limit) is not int or not 1 <= limit <= MAX_BATCH_OBSERVATIONS:
            raise ValueError("FIFO_BATCH_READ_LIMIT_INVALID")
        if cls._case_row(
            connection, scope, case_id, cls._digest(scope.owner_id), tenant_fingerprint,
        ) is None:
            return ()
        rows = connection.execute(
            """WITH current_keys AS (
                   SELECT DISTINCT link.record_key
                   FROM fifo_cost_batch_scan_observations AS link
                   JOIN fifo_cost_batch_supply_scans AS scan
                     ON scan.case_id=link.case_id AND scan.scan_id=link.scan_id
                   WHERE link.case_id=? AND link.scan_id=?
                     AND scan.owner_fingerprint=? AND scan.tenant_fingerprint=?
                     AND scan.store_id=? AND scan.sku=? AND scan.scope_fingerprint=?
               )
               SELECT observation.record_key, observation.order_ref_digest,
                      observation.supply_ref_digest, observation.encrypted_lookup_payload,
                      observation.source_profile_version, observation.source_fingerprint,
                      observation.captured_at, observation.source_as_of,
                      observation.source_status, observation.normalized_status,
                      observation.is_crossdock, observation.dispatch_local_date,
                      observation.dispatch_local_time, observation.dispatch_time_status,
                      observation.planned_declared_quantity,
                      observation.shipped_composition_quantity,
                      observation.accepted_quantity, observation.quantity_source_kind,
                      observation.quantity_coverage, observation.acceptance_fingerprint,
                      observation.acceptance_version, observation.explicit_zero_fields_json,
                      observation.membership, observation.issues_json,
                      observation.observation_revision
               FROM fifo_cost_batch_supply_observations AS observation
               JOIN current_keys ON current_keys.record_key=observation.record_key
               WHERE observation.case_id=? AND observation.owner_fingerprint=?
                 AND observation.tenant_fingerprint=? AND observation.store_id=?
                 AND observation.sku=? AND observation.scope_fingerprint=?
               ORDER BY observation.record_key, observation.captured_at,
                        observation.observation_revision, observation.source_fingerprint
               LIMIT ?""",
            (
                case_id, scan_id, cls._digest(scope.owner_id), tenant_fingerprint,
                scope.store_id, scope.sku, cls._scope_fingerprint(scope),
                case_id, cls._digest(scope.owner_id), tenant_fingerprint,
                scope.store_id, scope.sku, cls._scope_fingerprint(scope), limit + 1,
            ),
        ).fetchall()
        return tuple(dict(row) for row in rows)

    @classmethod
    def read_membership_decisions(
        cls, connection, *, scope: ScopeIdentity, case_id: str,
        tenant_fingerprint: str, limit: int = 20_000,
    ) -> tuple[dict, ...]:
        cls._validate_scope_inputs(scope, case_id, tenant_fingerprint)
        if type(limit) is not int or not 1 <= limit <= 20_000:
            raise ValueError("FIFO_BATCH_READ_LIMIT_INVALID")
        if cls._case_row(
            connection, scope, case_id, cls._digest(scope.owner_id), tenant_fingerprint,
        ) is None:
            return ()
        rows = connection.execute(
            """SELECT decision_id, revision, rule_id, rule_revision,
                      decision, source, record_keys_json,
                      relevant_source_fingerprints_json, candidate_set_fingerprint,
                      membership_binding_fingerprint, idempotency_key, confirmed_at,
                      previous_decision_ref
               FROM fifo_cost_batch_membership_decisions
               WHERE case_id=? AND owner_fingerprint=? AND tenant_fingerprint=?
                 AND store_id=? AND sku=? AND scope_fingerprint=?
               ORDER BY decision_id, revision LIMIT ?""",
            (
                case_id, cls._digest(scope.owner_id), tenant_fingerprint,
                scope.store_id, scope.sku, cls._scope_fingerprint(scope), limit,
            ),
        ).fetchall()
        return tuple(dict(row) for row in rows)

    @classmethod
    def read_scan_candidate_page(
        cls, connection, *, scope: ScopeIdentity, case_id: str,
        tenant_fingerprint: str, scan_id: str, limit: int = 8,
        offset: int = 0, record_keys: tuple[str, ...] | None = None,
    ) -> dict:
        """Read redacted current scan candidates plus the whole-set seal.

        Candidate order is deterministic by opaque record key. Raw Ozon IDs,
        names and barcodes are never selected. A caller may request one page of
        eight rows or a precisely selected set of at most fifty rows.
        """
        cls._validate_scope_inputs(scope, case_id, tenant_fingerprint)
        cls._validate_opaque(scan_id)
        if type(limit) is not int or not 1 <= limit <= 8:
            raise ValueError("FIFO_BATCH_READ_LIMIT_INVALID")
        if type(offset) is not int or not 0 <= offset <= 10_000:
            raise ValueError("FIFO_BATCH_READ_OFFSET_INVALID")
        if record_keys is not None:
            if (
                not isinstance(record_keys, tuple) or not 1 <= len(record_keys) <= 50
                or len(set(record_keys)) != len(record_keys)
            ):
                raise ValueError("FIFO_BATCH_READ_KEYS_INVALID")
            for key in record_keys:
                cls._require_digest(key, "FIFO_BATCH_RECORD_KEY_INVALID")
        if cls._case_row(
            connection, scope, case_id, cls._digest(scope.owner_id), tenant_fingerprint,
        ) is None:
            return {"error": False, "code": "FIFO_BATCH_SCAN_NOT_FOUND", "items": (), "total": 0}
        scan = cls.read_scan_checkpoint(
            connection, scope=scope, case_id=case_id,
            tenant_fingerprint=tenant_fingerprint, scan_id=scan_id,
        )
        if scan is None:
            return {"error": False, "code": "FIFO_BATCH_SCAN_NOT_FOUND", "items": (), "total": 0}
        refs = cls.read_scan_observation_refs(
            connection, scope=scope, case_id=case_id,
            tenant_fingerprint=tenant_fingerprint, scan_id=scan_id,
        )
        latest = {}
        for row in refs:
            key = row["record_key"]
            current = latest.get(key)
            candidate = (row["observation_revision"], row["source_fingerprint"])
            if current is None or candidate[0] > current[0]:
                latest[key] = candidate
        ordered_keys = sorted(latest)
        candidate_fingerprint = hashlib.sha256(json.dumps(
            [(key, latest[key][1]) for key in ordered_keys],
            sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        ).encode("utf-8")).hexdigest()
        selected_keys = (
            list(record_keys) if record_keys is not None
            else ordered_keys[offset:offset + limit]
        )
        scope_fingerprint = cls._scope_fingerprint(scope)
        items = []
        for key in selected_keys:
            current = latest.get(key)
            if current is None:
                continue
            row = connection.execute(
                """SELECT record_key, source_fingerprint, observation_revision,
                          source_status, normalized_status, is_crossdock,
                          dispatch_local_date, dispatch_time_status,
                          planned_declared_quantity, shipped_composition_quantity,
                          accepted_quantity, quantity_coverage, membership, issues_json
                   FROM fifo_cost_batch_supply_observations
                   WHERE case_id=? AND record_key=? AND source_fingerprint=?
                     AND observation_revision=? AND owner_fingerprint=?
                     AND tenant_fingerprint=? AND store_id=? AND sku=?
                     AND scope_fingerprint=?""",
                (
                    case_id, key, current[1], current[0], cls._digest(scope.owner_id),
                    tenant_fingerprint, scope.store_id, scope.sku, scope_fingerprint,
                ),
            ).fetchone()
            if row is not None:
                items.append(dict(row))
        return {
            "error": False, "code": "FIFO_BATCH_SCAN_CANDIDATES_READ",
            "scan_status": scan["status"],
            "scan_revision": scan["revision"],
            "candidate_set_fingerprint": candidate_fingerprint,
            "stored_candidate_set_fingerprint": scan["observation_set_fingerprint"],
            "total": len(ordered_keys),
            "items": tuple(items),
        }

    @classmethod
    def read_membership_decision_by_binding(
        cls, connection, *, scope: ScopeIdentity, case_id: str,
        tenant_fingerprint: str, rule_id: str, rule_revision: int,
        membership_binding_fingerprint: str,
    ) -> dict | None:
        """Read an existing exact owner decision to prevent duplicate outcomes."""
        cls._validate_scope_inputs(scope, case_id, tenant_fingerprint)
        cls._validate_opaque(rule_id)
        if type(rule_revision) is not int or rule_revision < 1:
            raise ValueError("FIFO_BATCH_RULE_REVISION_INVALID")
        binding = cls._require_digest(
            membership_binding_fingerprint,
            "FIFO_BATCH_MEMBERSHIP_BINDING_INVALID",
        )
        row = connection.execute(
            """SELECT decision_id, revision, decision, source,
                      candidate_set_fingerprint, record_keys_json
               FROM fifo_cost_batch_membership_decisions
               WHERE case_id=? AND owner_fingerprint=? AND tenant_fingerprint=?
                 AND store_id=? AND sku=? AND scope_fingerprint=?
                 AND rule_id=? AND rule_revision=?
                 AND membership_binding_fingerprint=?
               ORDER BY revision DESC LIMIT 1""",
            (
                case_id, cls._digest(scope.owner_id), tenant_fingerprint,
                scope.store_id, scope.sku, cls._scope_fingerprint(scope),
                rule_id, rule_revision, binding,
            ),
        ).fetchone()
        return dict(row) if row is not None else None

    @classmethod
    def read_observation_metadata(
        cls, connection, *, scope: ScopeIdentity, case_id: str,
        tenant_fingerprint: str, limit: int = 100,
    ) -> tuple[dict, ...]:
        cls._validate_scope_inputs(scope, case_id, tenant_fingerprint)
        if type(limit) is not int or not 1 <= limit <= 500:
            raise ValueError("FIFO_BATCH_READ_LIMIT_INVALID")
        case = cls._case_row(
            connection, scope, case_id, cls._digest(scope.owner_id), tenant_fingerprint,
        )
        if case is None:
            return ()
        rows = connection.execute(
            """SELECT observation_id, record_key, observation_revision,
                      source_fingerprint, captured_at, normalized_status,
                      planned_declared_quantity, shipped_composition_quantity,
                      accepted_quantity, quantity_coverage, membership, issues_json
               FROM fifo_cost_batch_supply_observations
               WHERE case_id=? AND owner_fingerprint=? AND tenant_fingerprint=?
                 AND store_id=? AND sku=? AND scope_fingerprint=?
               ORDER BY record_key, observation_revision LIMIT ?""",
            (
                case_id, cls._digest(scope.owner_id), tenant_fingerprint,
                scope.store_id, scope.sku, cls._scope_fingerprint(scope), limit,
            ),
        ).fetchall()
        return tuple(dict(row) for row in rows)

    @classmethod
    def read_rule_revisions(
        cls, connection, *, scope: ScopeIdentity, case_id: str,
        tenant_fingerprint: str, limit: int = 100,
    ) -> tuple[dict, ...]:
        cls._validate_scope_inputs(scope, case_id, tenant_fingerprint)
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("FIFO_BATCH_READ_LIMIT_INVALID")
        if cls._case_row(
            connection, scope, case_id, cls._digest(scope.owner_id), tenant_fingerprint,
        ) is None:
            return ()
        rows = connection.execute(
            """SELECT rule_id, rule_revision, policy_version, start_local_date,
                      store_timezone, start_day_policy, new_unit_cost_rub,
                      cost_input_fingerprint, old_home_confirmed_zero,
                      old_transit_confirmed_zero, boundary_supply_digests_json,
                      predecessor_rule_id, predecessor_rule_revision, event_kind,
                      end_local_date_exclusive, owner_confirmation_fingerprint,
                      rule_fingerprint, applied_rate_reference, idempotency_key,
                      payload_fingerprint, confirmed_at_utc, recorded_at
               FROM fifo_cost_batch_rule_revisions
               WHERE case_id=? AND owner_fingerprint=? AND tenant_fingerprint=?
                 AND store_id=? AND sku=? AND scope_fingerprint=?
               ORDER BY rule_id, rule_revision LIMIT ?""",
            (
                case_id, cls._digest(scope.owner_id), tenant_fingerprint,
                scope.store_id, scope.sku, cls._scope_fingerprint(scope), limit,
            ),
        ).fetchall()
        return tuple(dict(row) for row in rows)

    @classmethod
    def read_rule_idempotency(
        cls, connection, *, scope: ScopeIdentity, case_id: str,
        tenant_fingerprint: str, idempotency_key: str,
    ) -> dict | None:
        """Read the exact scoped rule command receipt for retry handling."""
        cls._validate_scope_inputs(scope, case_id, tenant_fingerprint)
        cls._validate_opaque(idempotency_key)
        case = cls._case_row(
            connection, scope, case_id, cls._digest(scope.owner_id), tenant_fingerprint,
        )
        if case is None:
            return None
        row = connection.execute(
            """SELECT rule_event_id, rule_id, rule_revision,
                      owner_confirmation_fingerprint, payload_fingerprint
               FROM fifo_cost_batch_rule_revisions
               WHERE case_id=? AND owner_fingerprint=? AND tenant_fingerprint=?
                 AND store_id=? AND sku=? AND scope_fingerprint=?
                 AND idempotency_key=?""",
            (
                case_id, cls._digest(scope.owner_id), tenant_fingerprint,
                scope.store_id, scope.sku, cls._scope_fingerprint(scope),
                idempotency_key,
            ),
        ).fetchone()
        return dict(row) if row is not None else None

    @classmethod
    def read_scan_checkpoint(
        cls, connection, *, scope: ScopeIdentity, case_id: str,
        tenant_fingerprint: str, scan_id: str,
    ) -> dict | None:
        cls._validate_scope_inputs(scope, case_id, tenant_fingerprint)
        cls._validate_opaque(scan_id)
        if cls._case_row(
            connection, scope, case_id, cls._digest(scope.owner_id), tenant_fingerprint,
        ) is None:
            return None
        row = connection.execute(
            """SELECT scan_id, revision, rule_id, rule_revision, rule_fingerprint,
                      requested_from,
                      requested_through, captured_at, source_as_of,
                      supported_state_profile_json, list_pagination_complete,
                      details_complete, sku_composition_complete,
                      historical_window_proven, membership_complete, quantity_complete,
                      physical_receipt_timing_complete, source_contract_version,
                      orders_seen, supplies_seen, sku_rows_seen, unknown_order_count,
                      unknown_supply_count, unknown_quantity_supply_count, issue_codes_json,
                      observation_set_fingerprint, status, expires_at, updated_at,
                      COALESCE(
                          encrypted_resumable_token,
                          (SELECT continuation.encrypted_resumable_token
                           FROM fifo_cost_batch_scan_continuations AS continuation
                           WHERE continuation.case_id=fifo_cost_batch_supply_scans.case_id
                             AND continuation.scan_id=fifo_cost_batch_supply_scans.scan_id)
                      ) AS encrypted_resumable_token
               FROM fifo_cost_batch_supply_scans
               WHERE case_id=? AND scan_id=? AND owner_fingerprint=?
                 AND tenant_fingerprint=? AND store_id=? AND sku=?
                 AND scope_fingerprint=?""",
            (
                case_id, scan_id, cls._digest(scope.owner_id), tenant_fingerprint,
                scope.store_id, scope.sku, cls._scope_fingerprint(scope),
            ),
        ).fetchone()
        return None if row is None else dict(row)

    @classmethod
    def read_total_controls(
        cls, connection, *, scope: ScopeIdentity, case_id: str,
        tenant_fingerprint: str, limit: int = 100,
    ) -> tuple[dict, ...]:
        cls._validate_scope_inputs(scope, case_id, tenant_fingerprint)
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("FIFO_BATCH_READ_LIMIT_INVALID")
        if cls._case_row(
            connection, scope, case_id, cls._digest(scope.owner_id), tenant_fingerprint,
        ) is None:
            return ()
        rows = connection.execute(
            """SELECT control_id, control_revision, total_units, window_from,
                      window_through, control_kind, control_status,
                      source_proof_fingerprint, owner_confirmation_fingerprint,
                      confirmed_at, recorded_at
               FROM fifo_cost_batch_total_controls
               WHERE case_id=? AND owner_fingerprint=? AND tenant_fingerprint=?
                 AND store_id=? AND sku=? AND scope_fingerprint=?
               ORDER BY window_from, control_revision LIMIT ?""",
            (
                case_id, cls._digest(scope.owner_id), tenant_fingerprint,
                scope.store_id, scope.sku, cls._scope_fingerprint(scope), limit,
            ),
        ).fetchall()
        return tuple(dict(row) for row in rows)

    @staticmethod
    def _require_transaction(connection):
        if not connection.in_transaction:
            raise sqlite3.ProgrammingError("FIFO batch store requires caller transaction")

    @classmethod
    def _case_row(cls, connection, scope, case_id, owner_fingerprint, tenant_fingerprint):
        query = """SELECT case_id, owner_fingerprint, tenant_fingerprint, store_id,
                          product_id, offer_id, sku
                   FROM fifo_cost_transition_cases
                   WHERE owner_fingerprint=? AND tenant_fingerprint=?
                     AND store_id=? AND sku=?"""
        values = (owner_fingerprint, tenant_fingerprint, scope.store_id, scope.sku)
        if case_id is not None:
            query += " AND case_id=?"
            values += (case_id,)
        query += " ORDER BY case_id LIMIT 2"
        rows = connection.execute(query, values).fetchall()
        matches = [
            row for row in rows
            if row["product_id"] == scope.product_id and row["offer_id"] == scope.offer_id
        ]
        return matches[0] if len(matches) == 1 else None

    @classmethod
    def _idempotent_result(
        cls, connection, table, case_id, idempotency_key,
        payload_fingerprint, id_column,
    ):
        row = connection.execute(
            f"SELECT {id_column}, payload_fingerprint FROM {table} "
            "WHERE case_id=? AND idempotency_key=?",
            (case_id, idempotency_key),
        ).fetchone()
        if row is None:
            return None
        if row["payload_fingerprint"] != payload_fingerprint:
            return cls._error("FIFO_BATCH_IDEMPOTENCY_CONFLICT")
        return {
            "error": False, "code": "FIFO_BATCH_IDEMPOTENT_REPLAY",
            id_column: row[id_column], "replayed": True,
        }

    @staticmethod
    def _validate_scope_inputs(scope, case_id, tenant_fingerprint):
        if not isinstance(scope, ScopeIdentity):
            raise TypeError("FIFO_BATCH_SCOPE_INVALID")
        if case_id is not None and (
            not isinstance(case_id, str)
            or re.fullmatch(r"[A-Za-z0-9_-]{8,96}", case_id) is None
        ):
            raise ValueError("FIFO_BATCH_CASE_ID_INVALID")
        if not isinstance(tenant_fingerprint, str) or _HEX.fullmatch(tenant_fingerprint) is None:
            raise ValueError("FIFO_BATCH_TENANT_SCOPE_INVALID")

    @staticmethod
    def _validate_opaque(value):
        if not isinstance(value, str) or _OPAQUE.fullmatch(value) is None:
            raise ValueError("FIFO_BATCH_IDEMPOTENCY_KEY_INVALID")

    @staticmethod
    def _validate_time_text(value):
        if not isinstance(value, str) or not 1 <= len(value) <= 64:
            raise ValueError("FIFO_BATCH_TIMESTAMP_INVALID")

    @staticmethod
    def _scope_fingerprint(scope):
        value = {
            "owner_id": scope.owner_id, "store_id": scope.store_id,
            "sku": scope.sku, "product_id": scope.product_id, "offer_id": scope.offer_id,
        }
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    @staticmethod
    def _digest(value):
        return hashlib.sha256(str(value).encode("utf-8")).hexdigest()

    @staticmethod
    def _require_digest(value, error_code):
        if not isinstance(value, str) or _HEX.fullmatch(value) is None:
            raise ValueError(error_code)
        return value

    @classmethod
    def _payload(cls, value):
        def convert(item):
            if isinstance(item, Enum):
                return item.value
            if isinstance(item, Decimal):
                return format(item, "f")
            if is_dataclass(item):
                return {field.name: convert(getattr(item, field.name)) for field in fields(item)}
            if isinstance(item, (tuple, list)):
                return [convert(part) for part in item]
            return item

        encoded = json.dumps(
            convert(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        )
        if len(encoded.encode("utf-8")) > 65536:
            raise ValueError("FIFO_BATCH_PAYLOAD_LIMIT")
        return encoded

    @staticmethod
    def _json(value, max_bytes):
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        if len(encoded.encode("utf-8")) > max_bytes:
            raise ValueError("FIFO_BATCH_PAYLOAD_LIMIT")
        return encoded

    @staticmethod
    def _error(code):
        return {"error": True, "code": code}
