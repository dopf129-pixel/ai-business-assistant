from decimal import Decimal
from dataclasses import replace
import hashlib
import sqlite3

import pytest

from services.fifo_cost_batch_rule_contracts import (
    BatchMembershipDecision,
    BatchRuleEventKind,
    BatchRuleRevision,
    BatchStartDayPolicy,
    DispatchTimeStatus,
    MembershipDecisionKind,
    MembershipDecisionSource,
    SupplyMembership,
    SupplyScanCoverage,
    SupplySkuObservation,
)
from services.fifo_cost_batch_supply_store import FifoCostBatchSupplyStore
from services.fifo_cost_repository import FifoCostRepository
from services.fifo_cost_transition_contracts import (
    EvidenceCompleteness,
    EvidenceSourceKind,
    NormalizedSupplyStatus,
    ScopeIdentity,
)


_OWNER = "batch-owner"
_TENANT = "batch-tenant"
_OWNER_FP = hashlib.sha256(_OWNER.encode()).hexdigest()
_TENANT_FP = hashlib.sha256(_TENANT.encode()).hexdigest()
_CASE_ID = "case-batch-1"
_RULE_ID = "rule-batch-1"
_SCOPE = ScopeIdentity(
    owner_id=_OWNER, store_id="store-1", sku="sku-1",
    product_id="product-1", offer_id="offer-1",
)


def _digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def _seed_case(connection):
    connection.execute(
        """INSERT INTO fifo_cost_transition_cases (
            case_id, schema_version, owner_fingerprint, tenant_fingerprint,
            store_id, product_id, offer_id, sku, current_revision, current_state,
            created_at, updated_at
        ) VALUES (?, 1, ?, ?, ?, ?, ?, ?, 1, 'DRAFT', 'now', 'now')""",
        (
            _CASE_ID, _OWNER_FP, _TENANT_FP, _SCOPE.store_id,
            _SCOPE.product_id, _SCOPE.offer_id, _SCOPE.sku,
        ),
    )


def _rule():
    return BatchRuleRevision(
        scope=_SCOPE,
        case_id=_CASE_ID,
        rule_id=_RULE_ID,
        rule_revision=1,
        policy_version=1,
        start_local_date="2026-11-05",
        store_timezone="Europe/Moscow",
        start_day_policy=BatchStartDayPolicy.ALL_OWNER_CONFIRMED,
        new_unit_cost_rub=Decimal("14.65"),
        cost_input_fingerprint=_digest("cost-input"),
        old_home_confirmed_zero=True,
        old_transit_confirmed_zero=True,
        boundary_supply_digests=(_digest("supply"),),
        predecessor_rule_id=None,
        predecessor_rule_revision=None,
        event_kind=BatchRuleEventKind.CONFIRM,
        end_local_date_exclusive=None,
        owner_confirmation_fingerprint=_digest("owner-confirmation"),
        confirmed_at_utc="2026-11-13T10:00:00Z",
        rule_fingerprint=_digest("rule"),
    )


def _observation(*, captured_at="2026-11-13T10:01:00Z"):
    return SupplySkuObservation(
        scope=_SCOPE,
        record_key=_digest("supply-sku"),
        order_ref_digest=_digest("order"),
        supply_ref_digest=_digest("supply"),
        encrypted_lookup_payload="gAAAA" + "A" * 96,
        source_profile_version="synthetic-v1",
        source_fingerprint=_digest("source-observation"),
        captured_at=captured_at,
        source_as_of=None,
        source_status="COMPLETED",
        normalized_status=NormalizedSupplyStatus.IN_TRANSIT,
        is_crossdock=True,
        dispatch_local_date="2026-11-05",
        dispatch_local_time=None,
        dispatch_time_status=DispatchTimeStatus.CONFIRMED,
        planned_declared_quantity=100,
        shipped_composition_quantity=100,
        accepted_quantity=None,
        quantity_source_kind=EvidenceSourceKind.OZON_API,
        quantity_coverage=EvidenceCompleteness.COMPLETE,
        acceptance_fingerprint=None,
        acceptance_version=None,
        explicit_zero_fields=(),
        membership=SupplyMembership.ELIGIBLE,
        issues=(),
    )


def test_batch_store_scopes_appends_and_deduplicates_observation_refresh(tmp_path):
    repository = FifoCostRepository(db_path=tmp_path / "batch-store.sqlite")
    connection = repository.get_connection()
    try:
        _seed_case(connection)
        connection.commit()
        connection.execute("BEGIN IMMEDIATE")
        rule_result = FifoCostBatchSupplyStore.append_rule_revision(
            connection, _rule(), tenant_fingerprint=_TENANT_FP,
            idempotency_key="rule-confirm-key-1", recorded_at="2026-11-13T10:00:01Z",
        )
        assert rule_result["code"] == "FIFO_BATCH_RULE_STORED"
        replay = FifoCostBatchSupplyStore.append_rule_revision(
            connection, _rule(), tenant_fingerprint=_TENANT_FP,
            idempotency_key="rule-confirm-key-1", recorded_at="2026-11-13T10:00:02Z",
        )
        assert replay["code"] == "FIFO_BATCH_IDEMPOTENT_REPLAY"
        first = FifoCostBatchSupplyStore.append_observation(
            connection, _observation(), tenant_fingerprint=_TENANT_FP,
            observation_id="observation-1", recorded_at="2026-11-13T10:01:01Z",
        )
        refreshed = FifoCostBatchSupplyStore.append_observation(
            connection, _observation(captured_at="2026-11-13T10:02:00Z"),
            tenant_fingerprint=_TENANT_FP, observation_id="observation-2",
            recorded_at="2026-11-13T10:02:01Z",
        )
        assert first["observation_revision"] == 1
        assert refreshed["observation_revision"] == 1
        assert refreshed["replayed"] is True
        connection.commit()

        rows = FifoCostBatchSupplyStore.read_observation_metadata(
            connection, scope=_SCOPE, case_id=_CASE_ID,
            tenant_fingerprint=_TENANT_FP,
        )
        assert len(rows) == 1
        assert rows[0]["accepted_quantity"] is None
        assert connection.execute("SELECT COUNT(*) FROM fifo_cost_events").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM fifo_cost_rate_changes").fetchone()[0] == 0
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute(
                "UPDATE fifo_cost_batch_supply_observations "
                "SET membership='EXCLUDED' WHERE observation_id='observation-1'"
            )
        other_store = ScopeIdentity(
            owner_id=_OWNER, store_id="store-2", sku="sku-1",
            product_id="product-1", offer_id="offer-1",
        )
        assert FifoCostBatchSupplyStore.read_observation_metadata(
            connection, scope=other_store, case_id=_CASE_ID,
            tenant_fingerprint=_TENANT_FP,
        ) == ()
    finally:
        connection.close()


def test_batch_store_rejects_cross_tenant_scope_without_persisting_rule(tmp_path):
    repository = FifoCostRepository(db_path=tmp_path / "batch-scope.sqlite")
    connection = repository.get_connection()
    try:
        _seed_case(connection)
        connection.commit()
        connection.execute("BEGIN IMMEDIATE")
        result = FifoCostBatchSupplyStore.append_rule_revision(
            connection, _rule(), tenant_fingerprint=_digest("other-tenant"),
            idempotency_key="rule-confirm-key-2", recorded_at="2026-11-13T10:00:01Z",
        )
        assert result == {"error": True, "code": "FIFO_BATCH_SCOPE_MISMATCH"}
        assert connection.execute(
            "SELECT COUNT(*) FROM fifo_cost_batch_rule_revisions"
        ).fetchone()[0] == 0
        connection.rollback()
    finally:
        connection.close()


def test_batch_store_persists_exact_decision_references_and_scan_cas(tmp_path):
    repository = FifoCostRepository(db_path=tmp_path / "batch-decisions.sqlite")
    connection = repository.get_connection()
    try:
        _seed_case(connection)
        connection.commit()
        observation = _observation()
        connection.execute("BEGIN IMMEDIATE")
        FifoCostBatchSupplyStore.append_rule_revision(
            connection, _rule(), tenant_fingerprint=_TENANT_FP,
            idempotency_key="rule-confirm-key-3", recorded_at="2026-11-13T10:00:01Z",
        )
        FifoCostBatchSupplyStore.append_observation(
            connection, observation, tenant_fingerprint=_TENANT_FP,
            observation_id="observation-3", recorded_at="2026-11-13T10:01:01Z",
        )
        decision = BatchMembershipDecision(
            decision_id="decision-batch-1",
            revision=1,
            scope=_SCOPE,
            case_id=_CASE_ID,
            rule_id=_RULE_ID,
            rule_revision=1,
            decision=MembershipDecisionKind.INCLUDED,
            source=MembershipDecisionSource.OWNER_SELECTED_SET,
            record_keys=(observation.record_key,),
            relevant_source_fingerprints=((observation.record_key, observation.source_fingerprint),),
            candidate_set_fingerprint=_digest("candidate-set"),
            membership_binding_fingerprint=_digest("membership-binding"),
            idempotency_key="decision-key-1",
            confirmed_at="2026-11-13T10:03:00Z",
        )
        result = FifoCostBatchSupplyStore.append_membership_decision(
            connection, decision, tenant_fingerprint=_TENANT_FP,
            recorded_at="2026-11-13T10:03:01Z",
        )
        assert result["code"] == "FIFO_BATCH_DECISION_STORED"
        assert connection.execute(
            "SELECT COUNT(*) FROM fifo_cost_batch_membership_decision_observations"
        ).fetchone()[0] == 1
        missing_key = _digest("unseen-observation")
        missing_observation = replace(
            decision,
            decision_id="decision-batch-2",
            revision=2,
            record_keys=(missing_key,),
            relevant_source_fingerprints=((missing_key, _digest("unseen-source")),),
            idempotency_key="decision-key-2",
        )
        missing = FifoCostBatchSupplyStore.append_membership_decision(
            connection, missing_observation, tenant_fingerprint=_TENANT_FP,
            recorded_at="2026-11-13T10:03:02Z",
        )
        assert missing == {"error": True, "code": "FIFO_BATCH_OBSERVATION_NOT_FOUND"}
        assert connection.execute(
            "SELECT COUNT(*) FROM fifo_cost_batch_membership_decisions"
        ).fetchone()[0] == 1
        coverage = SupplyScanCoverage(
            scan_id="scan-batch-1", revision=1, scope=_SCOPE, case_id=_CASE_ID,
            rule_revision=1, requested_from="2026-11-05", requested_through="2026-11-13",
            captured_at="2026-11-13T10:04:00Z", source_as_of=None,
            supported_state_profile=("COMPLETED",), list_pagination_complete=True,
            details_complete=True, sku_composition_complete=True,
            historical_window_proven=False, membership_complete=False,
            quantity_complete=False, physical_receipt_timing_complete=False,
            observation_set_fingerprint=_digest("observation-set"),
            source_contract_version="synthetic-v1", orders_seen=1, supplies_seen=1,
            sku_rows_seen=1, unknown_order_count=0, unknown_supply_count=0,
            unknown_quantity_supply_count=0, issue_codes=("SOURCE_DATE_NOT_PROVEN",),
            resumable_token="opaque-token-1",
        )
        scan = FifoCostBatchSupplyStore.write_scan_checkpoint(
            connection, coverage, tenant_fingerprint=_TENANT_FP,
            expected_revision=0, status="PARTIAL", expires_at="2026-11-13T10:34:00Z",
            updated_at="2026-11-13T10:04:01Z", encrypted_resumable_token=b"gAAAA" + b"A" * 95,
        )
        assert scan == {
            "error": False, "code": "FIFO_BATCH_SCAN_STORED",
            "scan_id": "scan-batch-1", "revision": 1,
        }
        conflict = FifoCostBatchSupplyStore.write_scan_checkpoint(
            connection, coverage, tenant_fingerprint=_TENANT_FP,
            expected_revision=0, status="PARTIAL", expires_at="2026-11-13T10:34:00Z",
            updated_at="2026-11-13T10:04:02Z",
            encrypted_resumable_token=b"gAAAA" + b"A" * 95,
        )
        assert conflict["code"] == "FIFO_BATCH_SCAN_REVISION_CONFLICT"
        connection.commit()
    finally:
        connection.close()
