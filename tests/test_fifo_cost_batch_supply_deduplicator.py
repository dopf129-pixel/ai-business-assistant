from dataclasses import replace
import hashlib

from cryptography.fernet import Fernet

from services.fifo_cost_batch_rule_contracts import (
    DispatchTimeStatus,
    SupplyMembership,
    SupplySkuObservation,
)
from services.fifo_cost_batch_supply_deduplicator import (
    FifoCostBatchSupplyDeduplicator,
    OwnerOrderControlStatus,
    SupplyLinkStatus,
)
from services.fifo_cost_transition_contracts import (
    EvidenceCompleteness,
    EvidenceSourceKind,
    NormalizedSupplyStatus,
    ScopeIdentity,
    SupplyDeclaration,
    SupplyReferenceKind,
    TransitionMetadata,
)


_SCOPE = ScopeIdentity(
    owner_id="dedup-owner", store_id="store-a", sku="sku-a",
    product_id="product-a", offer_id="offer-a",
)
_CASE_ID = "dedup-case-a"
_FERNET = Fernet(Fernet.generate_key())


def _digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _observation(
    supply="supply-a", *, order="order-a", quantity=100, captured_at="2026-11-13T10:00:00Z",
    source="source-a", accepted=None, scope=_SCOPE, record_key=None,
    dispatch_date="2026-11-05",
):
    supply_digest = _digest(supply)
    return SupplySkuObservation(
        scope=scope,
        record_key=(record_key or FifoCostBatchSupplyDeduplicator.canonical_record_key(
            scope, supply_digest,
        )),
        order_ref_digest=_digest(order),
        supply_ref_digest=supply_digest,
        encrypted_lookup_payload=_FERNET.encrypt(supply.encode()).decode("ascii"),
        source_profile_version="synthetic-v1",
        source_fingerprint=_digest(source),
        captured_at=captured_at,
        source_as_of=None,
        source_status="IN_TRANSIT",
        normalized_status=NormalizedSupplyStatus.IN_TRANSIT,
        is_crossdock=True,
        dispatch_local_date=dispatch_date,
        dispatch_local_time=None,
        dispatch_time_status=DispatchTimeStatus.CONFIRMED,
        planned_declared_quantity=quantity,
        shipped_composition_quantity=quantity,
        accepted_quantity=accepted,
        quantity_source_kind=EvidenceSourceKind.OZON_API,
        quantity_coverage=EvidenceCompleteness.COMPLETE,
        acceptance_fingerprint=None if accepted is None else _digest(f"accept-{accepted}"),
        acceptance_version=None if accepted is None else 1,
        explicit_zero_fields=(),
        membership=SupplyMembership.ELIGIBLE,
        issues=(),
    )


def _declaration(reference, kind, units, *, declaration_id=None, revision=1, date="2026-11-05", scope=_SCOPE):
    kind = kind if isinstance(kind, SupplyReferenceKind) else SupplyReferenceKind(kind)
    return SupplyDeclaration(
        metadata=TransitionMetadata(
            scope=scope, source_kind=EvidenceSourceKind.OWNER_INPUT,
            completeness=EvidenceCompleteness.COMPLETE,
            source_fingerprint=_digest(f"decl-{declaration_id or reference}-{revision}-{units}"),
        ),
        case_id=_CASE_ID,
        declaration_id=declaration_id or f"decl-{reference}",
        revision=revision,
        reference_kind=kind,
        reference_digest=_digest(reference),
        encrypted_lookup_reference=_FERNET.encrypt(reference.encode()).decode("ascii"),
        declared_shipped_units=units,
        dispatch_date=date,
        provenance=EvidenceSourceKind.OWNER_INPUT,
    )


def test_canonical_supply_sku_key_is_stable_and_distinct_across_scope_and_supply():
    supply = _digest("one-supply")
    base = FifoCostBatchSupplyDeduplicator.canonical_record_key(_SCOPE, supply)
    assert FifoCostBatchSupplyDeduplicator.canonical_record_key(_SCOPE, supply) == base
    assert FifoCostBatchSupplyDeduplicator.canonical_record_key(
        _SCOPE, _digest("another-supply"),
    ) != base
    assert FifoCostBatchSupplyDeduplicator.canonical_record_key(
        replace(_SCOPE, sku="sku-b"), supply,
    ) != base


def test_duplicate_pages_and_capture_timestamp_only_refresh_are_one_supply():
    first = _observation()
    refreshed = replace(first, captured_at="2026-11-13T11:00:00Z")
    result = FifoCostBatchSupplyDeduplicator.reconcile(
        scope=_SCOPE, case_id=_CASE_ID,
        observations=(first, refreshed), declarations=(),
    )
    assert result.code == "FIFO_BATCH_DEDUP_COMPLETE"
    assert len(result.records) == 1
    assert len(result.records[0].observations) == 1
    assert result.records[0].current_observation.captured_at == refreshed.captured_at
    assert result.records[0].status is SupplyLinkStatus.API_ONLY


def test_same_supply_cumulative_acceptance_versions_do_not_sum():
    versions = (
        _observation(quantity=100, accepted=40, source="accept-40", captured_at="2026-11-13T10:00:00Z"),
        _observation(quantity=100, accepted=70, source="accept-70", captured_at="2026-11-13T11:00:00Z"),
        _observation(quantity=100, accepted=100, source="accept-100", captured_at="2026-11-13T12:00:00Z"),
        _observation(quantity=100, accepted=70, source="accept-70", captured_at="2026-11-13T12:01:00Z"),
    )
    result = FifoCostBatchSupplyDeduplicator.reconcile(
        scope=_SCOPE, case_id=_CASE_ID, observations=versions, declarations=(),
    )
    assert len(result.records) == 1
    assert result.records[0].current_observation.accepted_quantity == 70
    assert result.records[0].effective_accepted_quantity == 100
    assert len(result.records[0].observations) == 3


def test_novel_accepted_quantity_decrease_requires_review_and_keeps_prior_maximum():
    versions = (
        _observation(quantity=100, accepted=100, source="accept-100", captured_at="2026-11-13T10:00:00Z"),
        _observation(quantity=100, accepted=90, source="accept-90", captured_at="2026-11-13T11:00:00Z"),
    )
    result = FifoCostBatchSupplyDeduplicator.reconcile(
        scope=_SCOPE, case_id=_CASE_ID, observations=versions, declarations=(),
    )
    assert result.status == "REVIEW_REQUIRED"
    assert result.records[0].effective_accepted_quantity == 100
    assert "FIFO_BATCH_ACCEPTANCE_DECREASE_REQUIRES_REVIEW" in result.records[0].issues


def test_decrease_to_previously_seen_quantity_with_new_source_fingerprint_requires_review():
    versions = (
        _observation(quantity=100, accepted=70, source="accept-70-first", captured_at="2026-11-13T10:00:00Z"),
        _observation(quantity=100, accepted=100, source="accept-100", captured_at="2026-11-13T11:00:00Z"),
        _observation(quantity=100, accepted=70, source="accept-70-correction", captured_at="2026-11-13T12:00:00Z"),
    )
    result = FifoCostBatchSupplyDeduplicator.reconcile(
        scope=_SCOPE, case_id=_CASE_ID, observations=versions, declarations=(),
    )
    assert result.records[0].status is SupplyLinkStatus.REVIEW_REQUIRED
    assert result.records[0].effective_accepted_quantity == 100


def test_owner_supply_declaration_matches_api_without_doubling_quantity():
    observation = _observation(quantity=100)
    declaration = _declaration(
        "supply-a", SupplyReferenceKind.SUPPLY, 100,
    )
    result = FifoCostBatchSupplyDeduplicator.reconcile(
        scope=_SCOPE, case_id=_CASE_ID,
        observations=(observation,), declarations=(declaration,),
    )
    assert len(result.records) == 1
    record = result.records[0]
    assert record.status is SupplyLinkStatus.RECONCILED
    assert record.current_observation.shipped_composition_quantity == 100
    assert record.owner_declared_units == 100
    assert record.owner_declaration_refs == ((declaration.declaration_id, 1),)
    assert len(record.observations) == 1


def test_owner_and_api_quantity_disagreement_requires_review_and_keeps_both_values():
    observation = _observation(quantity=100)
    declaration = _declaration(
        "supply-a", SupplyReferenceKind.SUPPLY, 98,
    )
    result = FifoCostBatchSupplyDeduplicator.reconcile(
        scope=_SCOPE, case_id=_CASE_ID,
        observations=(observation,), declarations=(declaration,),
    )
    assert result.status == "REVIEW_REQUIRED"
    assert result.records[0].status is SupplyLinkStatus.REVIEW_REQUIRED
    assert result.records[0].owner_declared_units == 98
    assert result.records[0].current_observation.shipped_composition_quantity == 100
    assert "FIFO_BATCH_OWNER_API_QUANTITY_CONFLICT" in result.records[0].issues


def test_owner_and_api_dispatch_date_disagreement_requires_review():
    observation = _observation(dispatch_date="2026-11-05")
    declaration = _declaration(
        "supply-a", SupplyReferenceKind.SUPPLY, 100, date="2026-11-06",
    )
    result = FifoCostBatchSupplyDeduplicator.reconcile(
        scope=_SCOPE, case_id=_CASE_ID,
        observations=(observation,), declarations=(declaration,),
    )
    assert result.records[0].status is SupplyLinkStatus.REVIEW_REQUIRED
    assert "FIFO_BATCH_OWNER_API_DISPATCH_DATE_CONFLICT" in result.records[0].issues


def test_order_declaration_is_control_over_two_child_supplies_not_a_third_supply():
    observations = (
        _observation("supply-1", order="order-a", quantity=100, source="source-1"),
        _observation("supply-2", order="order-a", quantity=200, source="source-2"),
    )
    declaration = _declaration(
        "order-a", SupplyReferenceKind.ORDER, 300,
    )
    result = FifoCostBatchSupplyDeduplicator.reconcile(
        scope=_SCOPE, case_id=_CASE_ID,
        observations=observations, declarations=(declaration,),
    )
    assert len(result.records) == 2
    assert sum(record.current_observation.shipped_composition_quantity for record in result.records) == 300
    assert len(result.order_controls) == 1
    control = result.order_controls[0]
    assert control.status is OwnerOrderControlStatus.RECONCILED
    assert control.declared_units == 300
    assert control.api_shipped_units == 300
    assert len(control.child_record_keys) == 2


def test_order_control_dispatch_date_conflict_requires_review():
    observations = (
        _observation("supply-1", order="order-a", quantity=100, source="source-1"),
        _observation("supply-2", order="order-a", quantity=200, source="source-2"),
    )
    declaration = _declaration(
        "order-a", SupplyReferenceKind.ORDER, 300, date="2026-11-06",
    )
    result = FifoCostBatchSupplyDeduplicator.reconcile(
        scope=_SCOPE, case_id=_CASE_ID,
        observations=observations, declarations=(declaration,),
    )
    control = result.order_controls[0]
    assert control.status is OwnerOrderControlStatus.REVIEW_REQUIRED
    assert control.api_shipped_units == 300
    assert "FIFO_BATCH_OWNER_API_DISPATCH_DATE_CONFLICT" in control.issues


def test_one_order_with_distinct_supplies_keeps_each_supply_once():
    observations = (
        _observation("supply-1", order="order-a", source="source-1"),
        _observation("supply-2", order="order-a", source="source-2"),
    )
    result = FifoCostBatchSupplyDeduplicator.reconcile(
        scope=_SCOPE, case_id=_CASE_ID, observations=observations, declarations=(),
    )
    assert len(result.records) == 2
    assert len({record.record_key for record in result.records}) == 2


def test_owner_supply_only_and_unresolved_order_remain_separate_from_api_facts():
    supply_declaration = _declaration(
        "manual-only-supply", SupplyReferenceKind.SUPPLY, 25,
    )
    order_declaration = _declaration(
        "unseen-order", SupplyReferenceKind.ORDER, 50,
    )
    result = FifoCostBatchSupplyDeduplicator.reconcile(
        scope=_SCOPE, case_id=_CASE_ID, observations=(),
        declarations=(supply_declaration, order_declaration),
    )
    assert len(result.records) == 1
    assert result.records[0].status is SupplyLinkStatus.OWNER_ONLY
    assert result.records[0].current_observation is None
    assert len(result.order_controls) == 1
    assert result.order_controls[0].status is OwnerOrderControlStatus.UNRESOLVED
    assert result.order_controls[0].api_shipped_units is None


def test_wrong_scope_or_noncanonical_key_fails_closed():
    wrong_scope = _observation(scope=replace(_SCOPE, sku="sku-b"))
    scope_result = FifoCostBatchSupplyDeduplicator.reconcile(
        scope=_SCOPE, case_id=_CASE_ID,
        observations=(wrong_scope,), declarations=(),
    )
    assert scope_result.code == "FIFO_BATCH_SCOPE_MISMATCH"

    wrong_key = _observation(record_key=_digest("not-canonical"))
    key_result = FifoCostBatchSupplyDeduplicator.reconcile(
        scope=_SCOPE, case_id=_CASE_ID,
        observations=(wrong_key,), declarations=(),
    )
    assert key_result.code == "FIFO_BATCH_SUPPLY_RECORD_KEY_MISMATCH"


def test_same_source_fingerprint_with_changed_content_requires_review():
    original = _observation(quantity=100, source="same-source")
    conflicting = replace(
        original, shipped_composition_quantity=90, planned_declared_quantity=90,
    )
    result = FifoCostBatchSupplyDeduplicator.reconcile(
        scope=_SCOPE, case_id=_CASE_ID,
        observations=(original, conflicting), declarations=(),
    )
    assert result.status == "REVIEW_REQUIRED"
    assert result.records[0].status is SupplyLinkStatus.REVIEW_REQUIRED
    assert "FIFO_BATCH_DUPLICATE_SOURCE_FINGERPRINT_CONFLICT" in result.records[0].issues


def test_same_manual_declaration_revision_with_changed_payload_is_rejected():
    first = _declaration("supply-a", SupplyReferenceKind.SUPPLY, 100)
    changed = replace(first, declared_shipped_units=90)
    result = FifoCostBatchSupplyDeduplicator.reconcile(
        scope=_SCOPE, case_id=_CASE_ID, observations=(),
        declarations=(first, changed),
    )
    assert result.code == "FIFO_BATCH_OWNER_DECLARATION_REVISION_CONFLICT"
