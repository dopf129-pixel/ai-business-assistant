from dataclasses import replace
from decimal import Decimal
import hashlib

from cryptography.fernet import Fernet

from services.fifo_cost_batch_manifest_builder import FifoCostBatchManifestBuilder
from services.fifo_cost_batch_rule_classifier import FifoCostBatchRuleClassifier
from services.fifo_cost_batch_rule_contracts import (
    BatchRuleEventKind,
    BatchRuleRevision,
    BatchStartDayPolicy,
    BatchTotalControl,
    BatchTotalControlKind,
    BatchTotalControlStatus,
    DispatchTimeStatus,
    ManifestFreshness,
    MembershipDecisionKind,
    MembershipDecisionSource,
    BatchMembershipDecision,
    SupplyMembership,
    SupplyScanCoverage,
    SupplySkuObservation,
    canonical_membership_binding_fingerprint,
)
from services.fifo_cost_batch_supply_deduplicator import FifoCostBatchSupplyDeduplicator
from services.fifo_cost_transition_contracts import (
    CostInputMode,
    EvidenceCompleteness,
    EvidenceSourceKind,
    NormalizedSupplyStatus,
    ScopeIdentity,
    TransitionCase,
    TransitionMetadata,
    TransitionState,
    SupplyTotalMode,
    SupplyDeclaration,
    SupplyReferenceKind,
    UnknownValue,
    TransitionReasonCode,
)


SCOPE = ScopeIdentity(
    owner_id="manifest-owner", store_id="store-a", product_id="product-101",
    offer_id="hook-2", sku="3921245627",
)
CASE_ID = "manifest-case-001"
NOW = "2026-11-14T12:00:00Z"
_FERNET = Fernet(Fernet.generate_key())


def _digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _case(*, legacy_total=None, mode=SupplyTotalMode.AUTO_FROM_SUPPLIES):
    unknown = {
        "new_home_quantity": UnknownValue(
            TransitionReasonCode.SOURCE_PROOF_UNAVAILABLE, EvidenceSourceKind.OWNER_INPUT,
        ),
    }
    if legacy_total is None:
        unknown["declared_shipped_units"] = UnknownValue(
            TransitionReasonCode.SOURCE_PROOF_UNAVAILABLE, EvidenceSourceKind.OWNER_INPUT,
        )
    return TransitionCase(
        metadata=TransitionMetadata(
            scope=SCOPE, source_kind=EvidenceSourceKind.OWNER_INPUT,
            completeness=EvidenceCompleteness.PARTIAL,
            source_fingerprint=_digest("case-source"), store_timezone="Europe/Moscow",
        ),
        case_id=CASE_ID, case_revision=2, state=TransitionState.AWAITING_EVIDENCE,
        created_at="2026-11-05T00:00:00Z", updated_at=NOW,
        dispatch_date="2026-11-05", old_unit_cost_rub=Decimal("21.00"),
        new_unit_cost_rub=Decimal("14.65"), cost_input_mode=CostInputMode.TOTAL_LANDED,
        cost_components=None, owner_old_home_units=0, owner_old_transit_units=0,
        new_home_quantity=None, declared_shipped_units=legacy_total,
        supply_total_mode=mode, unknown_values=unknown,
    )


def _rule():
    return BatchRuleRevision(
        scope=SCOPE, case_id=CASE_ID, rule_id="manifest-rule-001", rule_revision=1,
        policy_version=1, start_local_date="2026-11-05", store_timezone="Europe/Moscow",
        start_day_policy=BatchStartDayPolicy.ALL_OWNER_CONFIRMED,
        new_unit_cost_rub=Decimal("14.65"), cost_input_fingerprint=_digest("cost"),
        old_home_confirmed_zero=True, old_transit_confirmed_zero=True,
        boundary_supply_digests=(), predecessor_rule_id=None, predecessor_rule_revision=None,
        event_kind=BatchRuleEventKind.CONFIRM, end_local_date_exclusive=None,
        owner_confirmation_fingerprint=_digest("owner-confirm"), confirmed_at_utc=NOW,
        rule_fingerprint=_digest("rule"),
    )


def _observation(
    supply, shipped, accepted, *, date="2026-11-05", status=NormalizedSupplyStatus.IN_TRANSIT,
    source=None, captured_at=NOW, planned=None, explicit_zero=(), order=None,
):
    supply_digest = _digest("supply-" + supply)
    return SupplySkuObservation(
        scope=SCOPE,
        record_key=FifoCostBatchSupplyDeduplicator.canonical_record_key(SCOPE, supply_digest),
        order_ref_digest=_digest("order-" + (order or supply)), supply_ref_digest=supply_digest,
        encrypted_lookup_payload=_FERNET.encrypt(supply.encode()).decode("ascii"),
        source_profile_version="synthetic-contract-v1",
        source_fingerprint=_digest(source or f"{supply}-{shipped}-{accepted}-{status.value}"),
        captured_at=captured_at, source_as_of=NOW, source_status=status.value,
        normalized_status=status, is_crossdock=True,
        dispatch_local_date=date, dispatch_local_time=None,
        dispatch_time_status=DispatchTimeStatus.CONFIRMED,
        planned_declared_quantity=planned if planned is not None else shipped,
        shipped_composition_quantity=shipped, accepted_quantity=accepted,
        quantity_source_kind=EvidenceSourceKind.OZON_API,
        quantity_coverage=EvidenceCompleteness.COMPLETE,
        acceptance_fingerprint=None if accepted is None else _digest(f"accept-{supply}-{accepted}"),
        acceptance_version=None if accepted is None else 1,
        explicit_zero_fields=tuple(explicit_zero), membership=SupplyMembership.ELIGIBLE,
        issues=(),
    )


def _coverage(*, date_from="2026-11-05", date_through="2026-11-14", **overrides):
    fields = {
        "scan_id": "manifest-scan-001", "revision": 1, "scope": SCOPE,
        "case_id": CASE_ID, "rule_revision": 1,
        "requested_from": date_from, "requested_through": date_through,
        "captured_at": NOW, "source_as_of": NOW,
        "supported_state_profile": ("IN_TRANSIT", "RECEIVING", "ACCEPTED"),
        "list_pagination_complete": True, "details_complete": True,
        "sku_composition_complete": True, "historical_window_proven": True,
        "membership_complete": True, "quantity_complete": True,
        "physical_receipt_timing_complete": False,
        "observation_set_fingerprint": _digest("observation-set"),
        "source_contract_version": "synthetic-v1", "orders_seen": 2,
        "supplies_seen": 2, "sku_rows_seen": 2, "unknown_order_count": 0,
        "unknown_supply_count": 0, "unknown_quantity_supply_count": 0,
        "issue_codes": (),
    }
    fields.update(overrides)
    return SupplyScanCoverage(**fields)


def _control(total, *, date_from, date_through, kind=BatchTotalControlKind.DECLARED_IN_SHIPPED_SUPPLIES, control_id="control-001"):
    return BatchTotalControl(
        control_id=control_id, control_revision=1, scope=SCOPE, case_id=CASE_ID,
        total_units=total, window_from=date_from, window_through=date_through,
        control_kind=kind, control_status=BatchTotalControlStatus.OWNER_CONFIRMED,
        source_proof_fingerprint=_digest("control-proof"),
        owner_confirmation_fingerprint=_digest("control-owner"),
        idempotency_key="control-key-001", confirmed_at=NOW,
    )


def _order_declaration(order, units):
    return SupplyDeclaration(
        metadata=TransitionMetadata(
            scope=SCOPE, source_kind=EvidenceSourceKind.OWNER_INPUT,
            completeness=EvidenceCompleteness.COMPLETE,
            source_fingerprint=_digest("order-declaration"),
        ),
        case_id=CASE_ID, declaration_id="order-declaration-001", revision=1,
        reference_kind=SupplyReferenceKind.ORDER,
        reference_digest=_digest("order-" + order),
        encrypted_lookup_reference=_FERNET.encrypt(order.encode()).decode("ascii"),
        declared_shipped_units=units, dispatch_date="2026-11-05",
        provenance=EvidenceSourceKind.OWNER_INPUT,
    )


def _build(observations, *, coverage=None, case=None, controls=(), declarations=(), decisions=()):
    rule = _rule()
    dedup = FifoCostBatchSupplyDeduplicator.reconcile(
        scope=SCOPE, case_id=CASE_ID, observations=tuple(observations),
        declarations=tuple(declarations),
    )
    classifications = tuple(
        FifoCostBatchRuleClassifier.classify_supply(
            (rule,), item.current_observation, decisions,
        )
        for item in dedup.records if item.current_observation is not None
    )
    return FifoCostBatchManifestBuilder.build(
        case=case or _case(), rule=rule,
        coverage=coverage or _coverage(), deduplication=dedup,
        classifications=classifications, membership_decisions=decisions,
        total_controls=tuple(controls),
    )


def test_b12_manifest_keeps_known_accepted_subtotal_and_missing_count_separate():
    observations = (
        _observation("s1", 500, 500),
        _observation("s2", 300, 180, date="2026-11-06"),
        _observation("s3", 200, None, date="2026-11-07"),
    )
    result = _build(observations, coverage=_coverage(
        supplies_seen=3, sku_rows_seen=3,
    ))
    manifest = result.manifest
    assert result.status == "PARTIAL"
    assert manifest.declared_in_found_supplies == 1_000
    assert manifest.declared_in_shipped_supplies == 1_000
    assert manifest.accepted_units is None
    assert manifest.known_subtotal == 680
    assert manifest.unknown_quantity_supply_count == 1
    assert manifest.pending_units is None
    assert manifest.freshness is ManifestFreshness.UNKNOWN


def test_b23_historical_control_does_not_cap_later_found_supplies():
    observations = (
        _observation("first-day", 6_982, 0, explicit_zero=("accepted_quantity",)),
        _observation("later", 100, 0, date="2026-11-13", explicit_zero=("accepted_quantity",)),
    )
    result = _build(
        observations, case=_case(legacy_total=6_982),
        controls=(_control(6_982, date_from="2026-11-05", date_through="2026-11-05"),),
    )
    manifest = result.manifest
    assert manifest.declared_in_found_supplies == 7_082
    assert manifest.declared_in_shipped_supplies == 7_082
    assert manifest.owner_control_total is None
    assert result.legacy_control.label == "UNBOUNDED_LEGACY_CONTROL"
    assert result.legacy_control.total_units == 6_982
    assert result.control_assessments[0].status == "WINDOW_NOT_COMPARABLE"


def test_b24_exact_window_control_mismatch_requires_review():
    result = _build(
        (_observation("window", 1_100, 0, explicit_zero=("accepted_quantity",)),),
        coverage=_coverage(date_through="2026-11-05", supplies_seen=1, sku_rows_seen=1),
        controls=(_control(1_000, date_from="2026-11-05", date_through="2026-11-05"),),
    )
    assert result.status == "REVIEW_REQUIRED"
    assert result.control_assessments[0].status == "MISMATCH"
    assert result.manifest.owner_control_status == "MISMATCH"
    assert "FIFO_BATCH_CONTROL_EXACT_WINDOW_MISMATCH" in result.manifest.issues


def test_exact_window_control_is_compared_to_the_same_quantity_kind():
    result = _build(
        (_observation("window", 1_100, 0, explicit_zero=("accepted_quantity",)),),
        coverage=_coverage(date_through="2026-11-05", supplies_seen=1, sku_rows_seen=1),
        controls=(_control(1_100, date_from="2026-11-05", date_through="2026-11-05"),),
    )
    assert result.status == "COMPLETE"
    assert result.control_assessments[0].status == "MATCH"
    assert result.manifest.owner_control_total == 1_100
    assert result.manifest.owner_control_kind == BatchTotalControlKind.DECLARED_IN_SHIPPED_SUPPLIES.value
    assert result.manifest.owner_control_status == "MATCH"


def test_b25_legacy_total_is_labelled_without_inventing_a_window_or_cap():
    result = _build(
        (_observation("one", 100, 0, explicit_zero=("accepted_quantity",)),),
        case=_case(legacy_total=6_982),
    )
    assert result.status == "COMPLETE"
    assert result.manifest.declared_in_shipped_supplies == 100
    assert result.manifest.owner_control_total is None
    assert result.legacy_control == type(result.legacy_control)(
        "UNBOUNDED_LEGACY_CONTROL", 6_982,
    )


def test_order_control_is_not_added_to_child_supply_totals():
    observations = (
        _observation("child-one", 100, 0, order="parent", explicit_zero=("accepted_quantity",)),
        _observation("child-two", 200, 0, order="parent", explicit_zero=("accepted_quantity",)),
    )
    result = _build(
        observations, declarations=(_order_declaration("parent", 300),),
        coverage=_coverage(supplies_seen=2, sku_rows_seen=2),
    )
    assert len(result.manifest.observation_record_keys) == 2
    assert result.manifest.declared_in_found_supplies == 300
    assert result.manifest.declared_in_shipped_supplies == 300
    assert result.manifest.found_supply_count == 2
    assert result.manifest.included_supply_count == 2
    assert result.manifest.issues == ()


def test_b41_empty_partial_scan_is_unknown_not_confirmed_zero():
    coverage = _coverage(
        list_pagination_complete=False, sku_composition_complete=False,
        historical_window_proven=False, membership_complete=False,
        quantity_complete=False, source_as_of=None,
        observation_set_fingerprint=_digest("empty"), orders_seen=0,
        supplies_seen=0, sku_rows_seen=0,
    )
    dedup = FifoCostBatchSupplyDeduplicator.reconcile(
        scope=SCOPE, case_id=CASE_ID, observations=(), declarations=(),
    )
    result = FifoCostBatchManifestBuilder.build(
        case=_case(), rule=_rule(), coverage=coverage, deduplication=dedup,
        classifications=(),
    )
    assert result.status == "UNKNOWN"
    assert result.manifest.declared_in_found_supplies is None
    assert result.manifest.declared_in_shipped_supplies is None
    assert result.manifest.accepted_units is None
    assert result.manifest.known_subtotal == 0
    assert result.manifest.freshness is ManifestFreshness.UNKNOWN
    assert "FIFO_BATCH_SOURCE_EMPTY_NOT_ZERO" in result.manifest.issues


def test_b42_capture_timestamp_refresh_keeps_same_business_manifest_fingerprint():
    first = _observation("stable", 100, 0, explicit_zero=("accepted_quantity",))
    refreshed = replace(first, captured_at="2026-11-14T13:00:00Z")
    first_result = _build((first,))
    refreshed_result = _build((refreshed,))
    assert first_result.manifest.manifest_fingerprint == refreshed_result.manifest.manifest_fingerprint
    assert first_result.manifest.observation_record_keys == refreshed_result.manifest.observation_record_keys


def test_manifest_builder_rejects_malformed_records_before_order_link_validation():
    observation = _observation("malformed-records", 10, 0)
    dedup = FifoCostBatchSupplyDeduplicator.reconcile(
        scope=SCOPE, case_id=CASE_ID, observations=(observation,), declarations=(),
    )
    malformed = replace(dedup, records=[])
    result = FifoCostBatchManifestBuilder.build(
        case=_case(), rule=_rule(), coverage=_coverage(), deduplication=malformed,
        classifications=(),
    )
    assert result.status == "CONFLICT"
    assert result.code == "FIFO_BATCH_MANIFEST_RECORDS_INVALID"
    assert result.manifest is None


def test_manifest_builder_rejects_invalid_supply_digest_without_throwing():
    observation = _observation("invalid-digest", 10, 0)
    dedup = FifoCostBatchSupplyDeduplicator.reconcile(
        scope=SCOPE, case_id=CASE_ID, observations=(observation,), declarations=(),
    )
    malformed_record = replace(dedup.records[0], supply_ref_digest="invalid")
    malformed = replace(dedup, records=(malformed_record,))
    result = FifoCostBatchManifestBuilder.build(
        case=_case(), rule=_rule(), coverage=_coverage(), deduplication=malformed,
        classifications=(),
    )
    assert result.status == "CONFLICT"
    assert result.code == "FIFO_BATCH_MANIFEST_RECORDS_INVALID"
    assert result.manifest is None


def test_manifest_builder_rejects_malformed_owner_order_child_links():
    observation = _observation("bad-order-link", 10, 0, order="parent")
    dedup = FifoCostBatchSupplyDeduplicator.reconcile(
        scope=SCOPE, case_id=CASE_ID, observations=(observation,),
        declarations=(_order_declaration("parent", 10),),
    )
    assert dedup.order_controls
    bad_control = replace(dedup.order_controls[0], child_record_keys=("not-a-digest",))
    malformed = replace(dedup, order_controls=(bad_control,))
    result = FifoCostBatchManifestBuilder.build(
        case=_case(), rule=_rule(), coverage=_coverage(), deduplication=malformed,
        classifications=(),
    )
    assert result.status == "CONFLICT"
    assert result.code == "FIFO_BATCH_MANIFEST_ORDER_CONTROLS_INVALID"
    assert result.manifest is None


def test_owner_membership_binding_survives_normal_status_refresh_without_new_decision():
    rule = _rule()
    first = _observation("status-change", 100, None)
    binding = canonical_membership_binding_fingerprint(
        scope=SCOPE, supply_ref_digest=first.supply_ref_digest,
        rule_id=rule.rule_id, rule_revision=rule.rule_revision,
        rule_fingerprint=rule.rule_fingerprint,
        dispatch_local_date=first.dispatch_local_date, owner_selected=True,
    )
    decision = BatchMembershipDecision(
        decision_id="manifest-decision-001", revision=1, scope=SCOPE,
        case_id=CASE_ID, rule_id=rule.rule_id, rule_revision=rule.rule_revision,
        decision=MembershipDecisionKind.INCLUDED,
        source=MembershipDecisionSource.OWNER_SELECTED_SET,
        record_keys=(first.record_key,),
        relevant_source_fingerprints=((first.record_key, first.source_fingerprint),),
        candidate_set_fingerprint=_digest("candidate-set"),
        membership_binding_fingerprint=binding, idempotency_key="decision-key-001",
        confirmed_at=NOW,
    )
    refreshed = replace(
        first, source_status="ACCEPTED", normalized_status=NormalizedSupplyStatus.ACCEPTED,
        accepted_quantity=100, acceptance_fingerprint=_digest("accepted-100"),
        acceptance_version=1, source_fingerprint=_digest("status-refresh"),
        captured_at="2026-11-14T13:00:00Z",
    )
    classification = FifoCostBatchRuleClassifier.classify_supply(
        (rule,), refreshed, (decision,),
    )
    assert classification.membership is SupplyMembership.ELIGIBLE
    assert classification.decision_ref == "manifest-decision-001-r1"

