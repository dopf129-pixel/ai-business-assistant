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
    MAX_BATCH_OBSERVATIONS,
    MAX_RULE_REVISIONS,
    BatchMembershipDecision,
    BatchRuleRevision,
    SupplyScanCoverage,
    SupplySkuObservation,
)
from services.fifo_cost_transition_contracts import ScopeIdentity


_HEX = re.compile(r"^[0-9a-f]{64}$")
_OPAQUE = re.compile(r"^[A-Za-z0-9_-]{8,128}$")
_SCAN_STATUSES = frozenset({"STAGING", "PARTIAL", "PUBLISHED", "FAILED", "EXPIRED"})


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
        observation_id: str, recorded_at: str,
    ) -> dict:
        cls._require_transaction(connection)
        if not isinstance(observation, SupplySkuObservation):
            raise TypeError("FIFO_BATCH_OBSERVATION_INVALID")
        cls._validate_scope_inputs(observation.scope, None, tenant_fingerprint)
        cls._validate_opaque(observation_id)
        cls._validate_time_text(recorded_at)
        owner_fingerprint = cls._digest(observation.scope.owner_id)
        case = cls._case_row(
            connection, observation.scope, None, owner_fingerprint, tenant_fingerprint,
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
            not isinstance(token, bytes) or not 80 <= len(token) <= 8192
            or not token.startswith(b"gAAAA")
        ):
            raise ValueError("FIFO_BATCH_SCAN_TOKEN_INVALID")
        if (coverage.resumable_token is None) != (token is None):
            raise ValueError("FIFO_BATCH_SCAN_TOKEN_INVALID")
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
            "SELECT revision FROM fifo_cost_batch_supply_scans WHERE case_id=? AND scan_id=?",
            (coverage.case_id, coverage.scan_id),
        ).fetchone()
        current_revision = 0 if existing is None else existing["revision"]
        if current_revision != expected_revision:
            return cls._error("FIFO_BATCH_SCAN_REVISION_CONFLICT")
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
            None if token is None else sqlite3.Binary(token), status, expires_at, updated_at,
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
        return {
            "error": False, "code": "FIFO_BATCH_SCAN_STORED",
            "scan_id": coverage.scan_id, "revision": coverage.revision,
        }

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
            """SELECT scan_id, revision, rule_id, rule_revision, requested_from,
                      requested_through, captured_at, source_as_of,
                      observation_set_fingerprint, status, expires_at, updated_at,
                      encrypted_resumable_token
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
