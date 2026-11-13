from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timezone
from decimal import Decimal

from cryptography.fernet import Fernet
import pytest

from services.fifo_cost_batch_rule_contracts import (
    AutomaticBatchManifest,
    BatchMembershipDecision,
    BatchRuleEventKind,
    BatchRuleRevision,
    BatchStartDayPolicy,
    DispatchTimeStatus,
    ManifestFreshness,
    MembershipDecisionKind,
    MembershipDecisionSource,
    SupplyMembership,
    SupplyScanCoverage,
    SupplySkuObservation,
    SupplyTotalMode,
    canonical_membership_binding_fingerprint,
)
from services.fifo_cost_transition_contracts import (
    EvidenceCompleteness,
    EvidenceSourceKind,
    NormalizedSupplyStatus,
    ScopeIdentity,
    TransitionContractError,
    TransitionReasonCode,
)


SCOPE = ScopeIdentity(
    owner_id="test-owner-a",
    store_id="test-store-a",
    product_id="101",
    offer_id="test-a",
    sku="1000000001",
)
_TOKEN = Fernet(Fernet.generate_key()).encrypt(b"synthetic-supply-ref").decode("ascii")


def _rule(**overrides):
    fields = {
        "scope": SCOPE,
        "case_id": "case000000000001",
        "rule_id": "rule000000000001",
        "rule_revision": 1,
        "policy_version": 1,
        "start_local_date": "2026-11-05",
        "store_timezone": "Europe/Moscow",
        "start_day_policy": BatchStartDayPolicy.EXPLICIT_SUPPLY_SET,
        "new_unit_cost_rub": Decimal("14.65"),
        "cost_input_fingerprint": "a" * 64,
        "old_home_confirmed_zero": True,
        "old_transit_confirmed_zero": True,
        "boundary_supply_digests": ("b" * 64,),
        "predecessor_rule_id": None,
        "predecessor_rule_revision": None,
        "event_kind": BatchRuleEventKind.CONFIRM,
        "end_local_date_exclusive": None,
        "owner_confirmation_fingerprint": "c" * 64,
        "confirmed_at_utc": "2026-11-13T12:00:00Z",
        "rule_fingerprint": "d" * 64,
    }
    fields.update(overrides)
    return BatchRuleRevision(**fields)


def _observation(**overrides):
    fields = {
        "scope": SCOPE,
        "record_key": "1" * 64,
        "order_ref_digest": "2" * 64,
        "supply_ref_digest": "3" * 64,
        "encrypted_lookup_payload": _TOKEN,
        "source_profile_version": "supply-v3-contract-1",
        "source_fingerprint": "4" * 64,
        "captured_at": "2026-11-13T12:00:00Z",
        "source_as_of": None,
        "source_status": "IN_TRANSIT",
        "normalized_status": NormalizedSupplyStatus.IN_TRANSIT,
        "is_crossdock": True,
        "dispatch_local_date": None,
        "dispatch_local_time": None,
        "dispatch_time_status": DispatchTimeStatus.UNKNOWN,
        "planned_declared_quantity": 20,
        "shipped_composition_quantity": 20,
        "accepted_quantity": None,
        "quantity_source_kind": EvidenceSourceKind.OZON_API,
        "quantity_coverage": EvidenceCompleteness.COMPLETE,
        "acceptance_fingerprint": None,
        "acceptance_version": None,
        "explicit_zero_fields": (),
        "membership": SupplyMembership.NEEDS_CONFIRMATION,
        "issues": (),
    }
    fields.update(overrides)
    return SupplySkuObservation(**fields)


def _coverage(**overrides):
    fields = {
        "scan_id": "scan000000000001",
        "revision": 1,
        "scope": SCOPE,
        "case_id": "case000000000001",
        "rule_revision": 1,
        "requested_from": "2026-11-05",
        "requested_through": "2026-11-13",
        "captured_at": "2026-11-13T12:00:00Z",
        "source_as_of": None,
        "supported_state_profile": ("COMPLETED", "IN_TRANSIT"),
        "list_pagination_complete": True,
        "details_complete": True,
        "sku_composition_complete": False,
        "historical_window_proven": False,
        "membership_complete": False,
        "quantity_complete": False,
        "physical_receipt_timing_complete": False,
        "observation_set_fingerprint": "5" * 64,
        "source_contract_version": "v1",
        "orders_seen": 1,
        "supplies_seen": 1,
        "sku_rows_seen": 1,
        "unknown_order_count": 0,
        "unknown_supply_count": 0,
        "unknown_quantity_supply_count": 1,
        "issue_codes": ("BUNDLE_SCHEMA_UNVERIFIED",),
    }
    fields.update(overrides)
    return SupplyScanCoverage(**fields)


def _manifest(*, coverage=None, **overrides):
    fields = {
        "rule_id": "rule000000000001",
        "rule_revision": 1,
        "rule_fingerprint": "d" * 64,
        "scan_id": "scan000000000001",
        "observation_record_keys": ("1" * 64,),
        "membership_decision_refs": (),
        "owner_control_total": None,
        "owner_control_from": None,
        "owner_control_through": None,
        "owner_control_kind": None,
        "owner_control_status": None,
        "declared_in_found_supplies": 20,
        "declared_in_shipped_supplies": None,
        "accepted_units": None,
        "pending_units": None,
        "planned_units": 20,
        "known_subtotal": 20,
        "unknown_quantity_supply_count": 1,
        "found_supply_count": 1,
        "included_supply_count": 0,
        "undecided_supply_count": 1,
        "coverage": coverage or _coverage(),
        "current_through": "2026-11-13T12:00:00Z",
        "freshness": ManifestFreshness.CURRENT,
        "issues": ("BUNDLE_SCHEMA_UNVERIFIED",),
    }
    fields.update(overrides)
    return AutomaticBatchManifest(**fields)


def test_total_modes_are_explicit_and_legacy_default_is_not_auto():
    assert {value.value for value in SupplyTotalMode} == {
        "LEGACY_OWNER_TOTAL", "AUTO_FROM_SUPPLIES", "OWNER_CONTROL",
    }
    assert SupplyTotalMode("LEGACY_OWNER_TOTAL") is SupplyTotalMode.LEGACY_OWNER_TOTAL


def test_rule_binds_scope_cost_timezone_and_confirmed_old_zero():
    rule = _rule()
    assert rule.scope is SCOPE
    assert rule.new_unit_cost_rub == Decimal("14.65")
    assert rule.store_timezone == "Europe/Moscow"
    assert rule.old_home_confirmed_zero is True
    assert rule.old_transit_confirmed_zero is True

    for invalid in (
        {"old_home_confirmed_zero": False},
        {"old_transit_confirmed_zero": None},
        {"store_timezone": "Not/A_Timezone"},
        {"new_unit_cost_rub": True},
        {"end_local_date_exclusive": "2026-11-05"},
    ):
        with pytest.raises(TransitionContractError):
            _rule(**invalid)


def test_observation_keeps_zero_distinct_from_missing_and_rejects_bool_quantities():
    zero = _observation(
        accepted_quantity=0,
        acceptance_fingerprint="6" * 64,
        acceptance_version=1,
        explicit_zero_fields=("accepted_quantity",),
    )
    missing = _observation(accepted_quantity=None)
    assert zero.accepted_quantity == 0
    assert missing.accepted_quantity is None
    assert zero.explicit_zero_fields == ("accepted_quantity",)

    for invalid in (
        {"planned_declared_quantity": True},
        {"is_crossdock": 1},
        {"dispatch_time_status": DispatchTimeStatus.CONFIRMED},
        {"encrypted_lookup_payload": "raw-supply-id"},
        {"accepted_quantity": 0},
        {"explicit_zero_fields": ("planned_declared_quantity",)},
    ):
        with pytest.raises(TransitionContractError):
            _observation(**invalid)


def test_membership_decision_has_exact_sorted_set_and_dual_fingerprints():
    keys = ("a" * 64, "b" * 64)
    decision = BatchMembershipDecision(
        decision_id="decision00000001",
        revision=1,
        scope=SCOPE,
        case_id="case000000000001",
        rule_id="rule000000000001",
        rule_revision=1,
        decision=MembershipDecisionKind.INCLUDED,
        source=MembershipDecisionSource.OWNER_SELECTED_SET,
        record_keys=tuple(reversed(keys)),
        relevant_source_fingerprints=((keys[1], "d" * 64), (keys[0], "c" * 64)),
        candidate_set_fingerprint="e" * 64,
        membership_binding_fingerprint="f" * 64,
        idempotency_key="idem000000000001",
        confirmed_at="2026-11-13T12:00:00Z",
    )
    assert decision.record_keys == keys
    assert tuple(pair[0] for pair in decision.relevant_source_fingerprints) == keys
    with pytest.raises(TransitionContractError):
        replace(decision, record_keys=(keys[0],))


def test_membership_binding_fingerprint_uses_proof_not_transport_status_or_capture_time():
    args = dict(
        scope=SCOPE,
        supply_ref_digest="3" * 64,
        rule_id="rule000000000001",
        rule_revision=1,
        rule_fingerprint="d" * 64,
        dispatch_local_date="2026-11-06",
        owner_selected=False,
    )
    first = canonical_membership_binding_fingerprint(**args)
    second = canonical_membership_binding_fingerprint(**args)
    assert first == second
    assert first != canonical_membership_binding_fingerprint(**{**args, "dispatch_local_date": "2026-11-07"})


def test_scan_coverage_keeps_independent_gates_and_limits():
    coverage = _coverage()
    assert coverage.list_pagination_complete is True
    assert coverage.sku_composition_complete is False
    assert coverage.historical_window_proven is False
    assert coverage.physical_receipt_timing_complete is False
    assert not hasattr(coverage, "complete")
    with pytest.raises(TransitionContractError):
        _coverage(orders_seen=True)


def test_manifest_fingerprint_is_order_independent_and_ignores_timestamp_only_refresh():
    original = _manifest(
        observation_record_keys=("b" * 64, "a" * 64),
        membership_decision_refs=("decision00000002", "decision00000001"),
    )
    refreshed_coverage = _coverage(
        scan_id="scan000000000002",
        revision=2,
        captured_at="2026-11-14T12:00:00Z",
    )
    refreshed = _manifest(
        coverage=refreshed_coverage,
        scan_id="scan000000000002",
        observation_record_keys=("a" * 64, "b" * 64),
        membership_decision_refs=("decision00000001", "decision00000002"),
    )
    assert original.manifest_fingerprint == refreshed.manifest_fingerprint
    with pytest.raises(FrozenInstanceError):
        original.known_subtotal = 0
    with pytest.raises(TransitionContractError):
        _manifest(read_only=False)
    with pytest.raises(TransitionContractError):
        _manifest(manifest_fingerprint="0" * 64)


def test_aggregate_totals_have_separate_bound_from_each_supply_quantity():
    manifest = _manifest(
        observation_record_keys=("1" * 64, "2" * 64),
        declared_in_found_supplies=1_000_001,
        known_subtotal=1_000_001,
        unknown_quantity_supply_count=0,
        found_supply_count=2,
        included_supply_count=2,
        undecided_supply_count=0,
    )
    assert manifest.declared_in_found_supplies == 1_000_001
    with pytest.raises(TransitionContractError) as error:
        _manifest(known_subtotal=5_000_000_001)
    assert error.value.reason_code is TransitionReasonCode.QUANTITY_INVALID
