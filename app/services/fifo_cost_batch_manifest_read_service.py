"""Rehydrate the newest exact-scope FIFO batch scan for readiness review."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
import json
import sqlite3

from services.fifo_cost_batch_manifest_builder import FifoCostBatchManifestBuilder
from services.fifo_cost_batch_rule_classifier import FifoCostBatchRuleClassifier
from services.fifo_cost_batch_rule_contracts import (
    MAX_BATCH_OBSERVATIONS,
    MAX_BATCH_MEMBERSHIP_DECISIONS,
    BatchMembershipDecision,
    BatchRuleEventKind,
    BatchStartDayPolicy,
    BatchTotalControl,
    BatchTotalControlKind,
    BatchTotalControlStatus,
    DispatchTimeStatus,
    MembershipDecisionKind,
    MembershipDecisionSource,
    SupplyMembership,
    SupplyScanCoverage,
    SupplySkuObservation,
)
from services.fifo_cost_batch_rule_service import FifoCostBatchRuleService
from services.fifo_cost_batch_supply_deduplicator import FifoCostBatchSupplyDeduplicator
from services.fifo_cost_batch_supply_store import FifoCostBatchSupplyStore
from services.fifo_cost_transition_contracts import (
    EvidenceCompleteness,
    EvidenceSourceKind,
    NormalizedSupplyStatus,
    ScopeIdentity,
    SupplyDeclaration,
    SupplyReferenceKind,
    TransitionCase,
    supply_reference_digest,
)
from services.tenant_cipher_provider import decrypt_tenant_value


class FifoCostBatchManifestReadService:
    """Build a preview-only manifest from saved, tenant-scoped evidence.

    This service makes no Ozon calls and writes no evidence or FIFO accounting
    records. The most recent scan is authoritative for freshness: an unfinished
    latest scan never falls back to an earlier published result.
    """

    MAX_RULE_REVISIONS = 100
    MAX_SCAN_OBSERVATIONS = 10_000
    MAX_MEMBERSHIP_DECISIONS = MAX_BATCH_MEMBERSHIP_DECISIONS
    MAX_CONTROLS = 100

    def __init__(self, repository, *, manifest_builder=None, now_provider=None):
        if repository is None:
            raise ValueError("FIFO_BATCH_MANIFEST_REPOSITORY_INVALID")
        self.repository = repository
        self.manifest_builder = manifest_builder or FifoCostBatchManifestBuilder()
        self._now_provider = now_provider or repository._now_provider

    def read_current_manifest(
        self, *, case: TransitionCase,
        declarations: tuple[SupplyDeclaration, ...] = (),
    ) -> dict:
        if not isinstance(case, TransitionCase):
            return self._error("FIFO_BATCH_MANIFEST_CASE_INVALID")
        if not isinstance(declarations, tuple) or len(declarations) > 2_000 or any(
            not isinstance(item, SupplyDeclaration) for item in declarations
        ):
            return self._error("FIFO_BATCH_MANIFEST_DECLARATIONS_INVALID")
        scope = case.metadata.scope
        tenant = self.repository._tenant_scope(scope.store_id)
        if tenant.get("error"):
            return self._error("FIFO_BATCH_MANIFEST_SCOPE_UNAVAILABLE")

        connection = None
        try:
            connection = self.repository.get_connection()
            # Pin all manifest rows and the seal fingerprint to one SQLite
            # snapshot. Without this read transaction a writer can publish a
            # newer scan between these reads and produce a torn sealed result.
            if not connection.in_transaction:
                connection.execute("BEGIN")
            rule_rows = FifoCostBatchSupplyStore.read_rule_revisions(
                connection, scope=scope, case_id=case.case_id,
                tenant_fingerprint=tenant["tenant_fingerprint"],
                limit=self.MAX_RULE_REVISIONS,
            )
            if len(rule_rows) >= self.MAX_RULE_REVISIONS:
                return self._error("FIFO_BATCH_MANIFEST_RULE_HISTORY_LIMIT_REACHED")
            rule_chain, active_rule = self._restore_rule_chain(
                scope=scope, case_id=case.case_id, rows=rule_rows,
            )
            if active_rule is None:
                return {"error": False, "code": "FIFO_BATCH_MANIFEST_RULE_UNAVAILABLE", "manifest": None}

            scan = FifoCostBatchSupplyStore.read_latest_scan_checkpoint(
                connection, scope=scope, case_id=case.case_id,
                tenant_fingerprint=tenant["tenant_fingerprint"],
            )
            if scan is None:
                return {"error": False, "code": "FIFO_BATCH_MANIFEST_SCAN_UNAVAILABLE", "manifest": None}
            if (
                scan.get("status") != "PUBLISHED"
                or scan.get("rule_id") != active_rule.rule_id
                or scan.get("rule_revision") != active_rule.rule_revision
                or scan.get("rule_fingerprint") != active_rule.rule_fingerprint
            ):
                return {"error": False, "code": "FIFO_BATCH_MANIFEST_LATEST_SCAN_NOT_CURRENT", "manifest": None}

            candidate_set = FifoCostBatchSupplyStore.read_scan_candidate_page(
                connection, scope=scope, case_id=case.case_id,
                tenant_fingerprint=tenant["tenant_fingerprint"],
                scan_id=scan["scan_id"], limit=1,
            )
            if (
                candidate_set.get("error")
                or candidate_set.get("scan_status") != "PUBLISHED"
                or candidate_set.get("scan_revision") != scan.get("revision")
                or candidate_set.get("candidate_set_fingerprint")
                != scan.get("observation_set_fingerprint")
                or candidate_set.get("stored_candidate_set_fingerprint")
                != scan.get("observation_set_fingerprint")
            ):
                return self._error("FIFO_BATCH_MANIFEST_SCAN_SET_STALE")

            coverage = self._restore_coverage(scope=scope, case_id=case.case_id, row=scan)
            observation_rows = FifoCostBatchSupplyStore.read_scan_observations(
                connection, scope=scope, case_id=case.case_id,
                tenant_fingerprint=tenant["tenant_fingerprint"], scan_id=scan["scan_id"],
                limit=self.MAX_SCAN_OBSERVATIONS,
            )
            if len(observation_rows) > self.MAX_SCAN_OBSERVATIONS:
                return self._error("FIFO_BATCH_MANIFEST_OBSERVATION_LIMIT_REACHED")
            history_rows = FifoCostBatchSupplyStore.read_scan_observation_history(
                connection, scope=scope, case_id=case.case_id,
                tenant_fingerprint=tenant["tenant_fingerprint"], scan_id=scan["scan_id"],
                limit=MAX_BATCH_OBSERVATIONS,
            )
            if len(history_rows) > MAX_BATCH_OBSERVATIONS:
                return self._error("FIFO_BATCH_MANIFEST_OBSERVATION_LIMIT_REACHED")
            observations = tuple(
                self._restore_observation(scope, row) for row in history_rows
            )
            decision_rows = FifoCostBatchSupplyStore.read_membership_decisions(
                connection, scope=scope, case_id=case.case_id,
                tenant_fingerprint=tenant["tenant_fingerprint"],
                limit=self.MAX_MEMBERSHIP_DECISIONS,
            )
            if len(decision_rows) >= self.MAX_MEMBERSHIP_DECISIONS:
                return self._error("FIFO_BATCH_MANIFEST_DECISION_LIMIT_REACHED")
            decisions = tuple(self._restore_decision(scope, case.case_id, row) for row in decision_rows)
            control_rows = FifoCostBatchSupplyStore.read_total_controls(
                connection, scope=scope, case_id=case.case_id,
                tenant_fingerprint=tenant["tenant_fingerprint"], limit=self.MAX_CONTROLS,
            )
            controls = tuple(self._restore_control(scope, case.case_id, row) for row in control_rows)
            source_storage_fingerprint = (
                FifoCostBatchSupplyStore.read_scope_source_fingerprint(
                    connection, scope=scope, case_id=case.case_id,
                    tenant_fingerprint=tenant["tenant_fingerprint"],
                )
            )
        except (OSError, sqlite3.Error, TypeError, ValueError, KeyError, AttributeError):
            return self._error("FIFO_BATCH_MANIFEST_STORAGE_UNAVAILABLE")
        finally:
            if connection is not None:
                connection.close()

        if len(observations) > self.MAX_SCAN_OBSERVATIONS:
            return self._error("FIFO_BATCH_MANIFEST_OBSERVATION_LIMIT_REACHED")
        if self._scan_expired(scan):
            coverage = replace(
                coverage,
                issue_codes=tuple(sorted(set(coverage.issue_codes) | {"FIFO_BATCH_SCAN_STALE_EXPIRED"})),
            )

        deduplication = FifoCostBatchSupplyDeduplicator.reconcile(
            scope=scope, case_id=case.case_id,
            observations=observations, declarations=declarations,
        )
        classifications = tuple(
            FifoCostBatchRuleClassifier.classify_supply(
                rule_chain, record.current_observation, decisions,
            )
            for record in deduplication.records
            if record.current_observation is not None
        )
        built = self.manifest_builder.build(
            case=case, rule=active_rule, coverage=coverage,
            deduplication=deduplication, classifications=classifications,
            membership_decisions=decisions, total_controls=controls,
            rule_history=rule_chain,
        )
        if built.manifest is None:
            return self._error(built.code)
        seal = self._build_seal(
            manifest=built.manifest,
            source_storage_fingerprint=source_storage_fingerprint,
        )
        return {
            "error": False,
            "code": built.code,
            "status": built.status,
            "manifest": built.manifest,
            "seal": seal,
            "control_assessments": built.control_assessments,
            "issue_codes": built.issue_codes,
        }

    @staticmethod
    def _build_seal(*, manifest, source_storage_fingerprint):
        """Expose a non-identifying, content-addressed source seal."""
        material = {
            "schema_version": 1,
            "rule_revision": manifest.rule_revision,
            "rule_fingerprint": manifest.rule_fingerprint,
            "scan_revision": manifest.coverage.revision,
            "observation_set_fingerprint": (
                manifest.coverage.observation_set_fingerprint
            ),
            "manifest_fingerprint": manifest.manifest_fingerprint,
            "source_storage_fingerprint": source_storage_fingerprint,
        }
        encoded = json.dumps(
            material, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        ).encode("utf-8")
        return {
            **material,
            "seal_fingerprint": FifoCostBatchSupplyStore._digest(
                encoded.decode("utf-8"),
            ),
        }

    @classmethod
    def _restore_rule_chain(cls, *, scope, case_id, rows):
        latest_by_rule = {}
        for row in rows:
            if (
                type(row.get("old_home_confirmed_zero")) is not int
                or row["old_home_confirmed_zero"] != 1
                or type(row.get("old_transit_confirmed_zero")) is not int
                or row["old_transit_confirmed_zero"] != 1
            ):
                raise ValueError("FIFO_BATCH_MANIFEST_RULE_CONFIRMATION_INVALID")
            item = FifoCostBatchRuleService._revision(
                scope=scope, case_id=case_id, rule_id=row["rule_id"],
                rule_revision=row["rule_revision"],
                policy_version=row["policy_version"],
                start_local_date=row["start_local_date"],
                store_timezone=row["store_timezone"],
                start_day_policy=BatchStartDayPolicy(row["start_day_policy"]),
                new_unit_cost_rub=Decimal(row["new_unit_cost_rub"]),
                cost_input_fingerprint=row["cost_input_fingerprint"],
                boundary_supply_digests=tuple(json.loads(row["boundary_supply_digests_json"])),
                predecessor_rule_id=row["predecessor_rule_id"],
                predecessor_rule_revision=row["predecessor_rule_revision"],
                event_kind=BatchRuleEventKind(row["event_kind"]),
                end_local_date_exclusive=row["end_local_date_exclusive"],
                owner_confirmation_fingerprint=row["owner_confirmation_fingerprint"],
                confirmed_at_utc=row["confirmed_at_utc"],
                applied_rate_reference=row["applied_rate_reference"],
            )
            if item.rule_fingerprint != row["rule_fingerprint"]:
                raise ValueError("FIFO_BATCH_MANIFEST_RULE_FINGERPRINT_MISMATCH")
            if item.rule_revision in latest_by_rule:
                raise ValueError("FIFO_BATCH_MANIFEST_RULE_REVISION_DUPLICATE")
            latest_by_rule[item.rule_revision] = item
        chain = tuple(latest_by_rule[key] for key in sorted(latest_by_rule))
        closed_bases = {
            (item.predecessor_rule_id, item.predecessor_rule_revision)
            for item in chain
            if item.event_kind in {BatchRuleEventKind.CLOSE, BatchRuleEventKind.CANCEL}
        }
        active = tuple(
            item for item in chain
            if item.event_kind in {BatchRuleEventKind.CONFIRM, BatchRuleEventKind.REPLACE}
            and item.end_local_date_exclusive is None
            and (item.rule_id, item.rule_revision) not in closed_bases
        )
        if len(active) > 1:
            raise ValueError("FIFO_BATCH_MANIFEST_RULE_CHAIN_CONFLICT")
        return chain, (active[0] if active else None)

    @classmethod
    def _restore_coverage(cls, *, scope, case_id, row):
        return SupplyScanCoverage(
            scan_id=row["scan_id"], revision=row["revision"], scope=scope,
            case_id=case_id, rule_revision=row["rule_revision"],
            requested_from=row["requested_from"], requested_through=row["requested_through"],
            captured_at=row["captured_at"], source_as_of=row["source_as_of"],
            supported_state_profile=cls._json_tuple(row["supported_state_profile_json"]),
            list_pagination_complete=cls._db_bool(row["list_pagination_complete"]),
            details_complete=cls._db_bool(row["details_complete"]),
            sku_composition_complete=cls._db_bool(row["sku_composition_complete"]),
            historical_window_proven=cls._db_bool(row["historical_window_proven"]),
            membership_complete=cls._db_bool(row["membership_complete"]),
            quantity_complete=cls._db_bool(row["quantity_complete"]),
            physical_receipt_timing_complete=cls._db_bool(
                row["physical_receipt_timing_complete"],
            ),
            observation_set_fingerprint=row["observation_set_fingerprint"],
            source_contract_version=row["source_contract_version"],
            orders_seen=row["orders_seen"], supplies_seen=row["supplies_seen"],
            sku_rows_seen=row["sku_rows_seen"], unknown_order_count=row["unknown_order_count"],
            unknown_supply_count=row["unknown_supply_count"],
            unknown_quantity_supply_count=row["unknown_quantity_supply_count"],
            issue_codes=cls._json_tuple(row["issue_codes_json"]),
            resumable_token=None,
        )

    @classmethod
    def _restore_observation(cls, scope, row):
        crossdock = row["is_crossdock"]
        if crossdock is not None:
            if type(crossdock) is not int or crossdock not in (0, 1):
                raise ValueError("FIFO_BATCH_MANIFEST_OBSERVATION_INVALID")
            crossdock = bool(crossdock)
        encrypted_lookup = bytes(row["encrypted_lookup_payload"]).decode("ascii")
        transition_order_digest, transition_supply_digest = cls._transition_reference_digests(
            scope, encrypted_lookup,
        )
        return SupplySkuObservation(
            scope=scope, record_key=row["record_key"],
            order_ref_digest=row["order_ref_digest"],
            supply_ref_digest=row["supply_ref_digest"],
            encrypted_lookup_payload=encrypted_lookup,
            source_profile_version=row["source_profile_version"],
            source_fingerprint=row["source_fingerprint"], captured_at=row["captured_at"],
            source_as_of=row["source_as_of"], source_status=row["source_status"],
            normalized_status=NormalizedSupplyStatus(row["normalized_status"]),
            is_crossdock=crossdock, dispatch_local_date=row["dispatch_local_date"],
            dispatch_local_time=row["dispatch_local_time"],
            dispatch_time_status=DispatchTimeStatus(row["dispatch_time_status"]),
            planned_declared_quantity=row["planned_declared_quantity"],
            shipped_composition_quantity=row["shipped_composition_quantity"],
            accepted_quantity=row["accepted_quantity"],
            quantity_source_kind=EvidenceSourceKind(row["quantity_source_kind"]),
            quantity_coverage=EvidenceCompleteness(row["quantity_coverage"]),
            acceptance_fingerprint=row["acceptance_fingerprint"],
            acceptance_version=row["acceptance_version"],
            explicit_zero_fields=cls._json_tuple(row["explicit_zero_fields_json"]),
            membership=SupplyMembership(row["membership"]),
            issues=cls._json_tuple(row["issues_json"]),
            transition_order_reference_digest=transition_order_digest,
            transition_supply_reference_digest=transition_supply_digest,
        )

    @staticmethod
    def _transition_reference_digests(scope, encrypted_lookup):
        """Recover stable declaration links while preserving legacy record keys."""
        try:
            decrypted = decrypt_tenant_value(encrypted_lookup)
            payload = json.loads(decrypted) if isinstance(decrypted, str) else None
        except (TypeError, ValueError, UnicodeError, json.JSONDecodeError):
            return None, None
        if not isinstance(payload, dict):
            return None, None
        order_digest = supply_reference_digest(
            owner_id=scope.owner_id, store_id=scope.store_id,
            reference_kind=SupplyReferenceKind.ORDER,
            reference_id=payload.get("order_id"),
        )
        supply_digest = supply_reference_digest(
            owner_id=scope.owner_id, store_id=scope.store_id,
            reference_kind=SupplyReferenceKind.SUPPLY,
            reference_id=payload.get("supply_id"),
        )
        return order_digest, supply_digest

    @classmethod
    def _restore_decision(cls, scope, case_id, row):
        pairs = cls._json_tuple(row["relevant_source_fingerprints_json"])
        return BatchMembershipDecision(
            decision_id=row["decision_id"], revision=row["revision"],
            scope=scope, case_id=case_id, rule_id=row["rule_id"],
            rule_revision=row["rule_revision"],
            decision=MembershipDecisionKind(row["decision"]),
            source=MembershipDecisionSource(row["source"]),
            record_keys=cls._json_tuple(row["record_keys_json"]),
            relevant_source_fingerprints=tuple(tuple(pair) for pair in pairs),
            candidate_set_fingerprint=row["candidate_set_fingerprint"],
            membership_binding_fingerprint=row["membership_binding_fingerprint"],
            idempotency_key=row["idempotency_key"], confirmed_at=row["confirmed_at"],
            previous_decision_ref=row["previous_decision_ref"],
        )

    @classmethod
    def _restore_control(cls, scope, case_id, row):
        return BatchTotalControl(
            control_id=row["control_id"], control_revision=row["control_revision"],
            scope=scope, case_id=case_id, total_units=row["total_units"],
            window_from=row["window_from"], window_through=row["window_through"],
            control_kind=BatchTotalControlKind(row["control_kind"]),
            control_status=BatchTotalControlStatus(row["control_status"]),
            source_proof_fingerprint=row["source_proof_fingerprint"],
            owner_confirmation_fingerprint=row["owner_confirmation_fingerprint"],
            idempotency_key=row["idempotency_key"], confirmed_at=row["confirmed_at"],
        )

    @staticmethod
    def _json_tuple(value):
        parsed = json.loads(value)
        if not isinstance(parsed, list):
            raise ValueError("FIFO_BATCH_MANIFEST_STORED_JSON_INVALID")
        return tuple(parsed)

    @staticmethod
    def _db_bool(value):
        if type(value) is not int or value not in (0, 1):
            raise ValueError("FIFO_BATCH_MANIFEST_STORED_BOOLEAN_INVALID")
        return value == 1

    def _scan_expired(self, row):
        expiry = row.get("expires_at")
        if not isinstance(expiry, str):
            return True
        try:
            parsed = datetime.fromisoformat(expiry.replace("Z", "+00:00"))
            now = self._now_provider()
        except (TypeError, ValueError):
            return True
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return True
        if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
            return True
        return parsed.astimezone(timezone.utc) <= now.astimezone(timezone.utc)

    @staticmethod
    def _error(code):
        return {"error": True, "code": code}
