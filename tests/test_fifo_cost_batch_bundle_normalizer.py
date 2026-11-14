from cryptography.fernet import Fernet
import hashlib

from services.fifo_cost_batch_bundle_normalizer import FifoCostBatchBundleNormalizer
from services.fifo_cost_batch_rule_contracts import (
    DispatchTimeStatus,
    SupplyMembership,
    SupplySkuObservation,
)
from services.fifo_cost_transition_contracts import (
    EvidenceCompleteness,
    EvidenceSourceKind,
    NormalizedSupplyStatus,
    ScopeIdentity,
)


TARGET = ScopeIdentity(
    owner_id="owner-1", store_id="store-1", product_id="product-a",
    offer_id="offer-a", sku="sku-a",
)
OTHER_SKU = ScopeIdentity(
    owner_id="owner-1", store_id="store-1", product_id="product-b",
    offer_id="offer-b", sku="sku-b",
)
SUPPLY_REF = "a" * 64
ORDER_REF = "b" * 64


def _observation(
    scope=TARGET, *, planned=100, shipped=80,
    completeness=EvidenceCompleteness.COMPLETE, explicit_zero=(),
    supply_ref=SUPPLY_REF, order_ref=ORDER_REF, source_kind=EvidenceSourceKind.OZON_API,
):
    key = Fernet.generate_key()
    record_key = hashlib.sha256(
        f"{scope.sku}:{planned}:{shipped}".encode("utf-8"),
    ).hexdigest()
    return SupplySkuObservation(
        scope=scope,
        record_key=record_key,
        order_ref_digest=order_ref,
        supply_ref_digest=supply_ref,
        encrypted_lookup_payload=Fernet(key).encrypt(b"synthetic-reference").decode("ascii"),
        source_profile_version="SYNTHETIC_NORMALIZED_V1",
        source_fingerprint="d" * 64,
        captured_at="2026-11-14T10:00:00Z",
        source_as_of=None,
        source_status="COMPLETED",
        normalized_status=NormalizedSupplyStatus.UNKNOWN,
        is_crossdock=None,
        dispatch_local_date=None,
        dispatch_local_time=None,
        dispatch_time_status=DispatchTimeStatus.UNKNOWN,
        planned_declared_quantity=planned,
        shipped_composition_quantity=shipped,
        accepted_quantity=None,
        quantity_source_kind=source_kind,
        quantity_coverage=completeness,
        acceptance_fingerprint=None,
        acceptance_version=None,
        explicit_zero_fields=tuple(explicit_zero),
        membership=SupplyMembership.NEEDS_CONFIRMATION,
    )


def test_bundle_normalizer_maps_only_the_exact_target_sku_and_keeps_both_quantities():
    rows = (
        _observation(TARGET, planned=100, shipped=80),
        _observation(OTHER_SKU, planned=900, shipped=700),
    )
    result = FifoCostBatchBundleNormalizer.normalize(
        TARGET, SUPPLY_REF, rows, composition_complete=True,
    )
    reordered = FifoCostBatchBundleNormalizer.normalize(
        TARGET, SUPPLY_REF, tuple(reversed(rows)), composition_complete=True,
    )

    assert result.status == "COMPLETE"
    assert result.planned_quantity == 100
    assert result.shipped_quantity == 80
    assert result.planned_explicit_zero is False
    assert result.shipped_explicit_zero is False
    assert result.actual_http_attempts == 0
    assert (reordered.planned_quantity, reordered.shipped_quantity) == (100, 80)


def test_planned_only_quantity_never_becomes_shipped_quantity():
    result = FifoCostBatchBundleNormalizer.normalize(
        TARGET, SUPPLY_REF,
        (_observation(
            TARGET, planned=100, shipped=None,
            completeness=EvidenceCompleteness.PARTIAL,
        ),),
        composition_complete=False,
    )

    assert result.status == "PARTIAL"
    assert result.planned_quantity == 100
    assert result.shipped_quantity is None
    assert result.issue_codes == ("FIFO_BATCH_BUNDLE_COMPOSITION_INCOMPLETE",)


def test_empty_or_raw_unverified_rows_are_unknown_not_zero():
    empty = FifoCostBatchBundleNormalizer.normalize(
        TARGET, SUPPLY_REF, (), composition_complete=True,
    )
    raw_shape = FifoCostBatchBundleNormalizer.normalize(
        TARGET, SUPPLY_REF, ({"sku": "sku-a", "quantity": 100},),
        composition_complete=True,
    )

    for result in (empty, raw_shape):
        assert result.status == "UNKNOWN"
        assert result.planned_quantity is None
        assert result.shipped_quantity is None


def test_incomplete_composition_can_show_a_known_row_without_claiming_complete_coverage():
    result = FifoCostBatchBundleNormalizer.normalize(
        TARGET, SUPPLY_REF, (_observation(TARGET),), composition_complete=False,
    )

    assert result.status == "PARTIAL"
    assert result.planned_quantity == 100
    assert result.shipped_quantity == 80
    assert result.issue_codes == ("FIFO_BATCH_BUNDLE_COMPOSITION_INCOMPLETE",)


def test_explicit_zero_is_distinct_from_missing_zero_proof():
    proven_zero = FifoCostBatchBundleNormalizer.normalize(
        TARGET, SUPPLY_REF,
        (_observation(
            TARGET, planned=0, shipped=0,
            explicit_zero=("planned_declared_quantity", "shipped_composition_quantity"),
        ),),
        composition_complete=True,
    )
    unproven_zero = FifoCostBatchBundleNormalizer.normalize(
        TARGET, SUPPLY_REF, (_observation(TARGET, planned=0, shipped=0),),
        composition_complete=True,
    )

    assert proven_zero.status == "COMPLETE"
    assert proven_zero.planned_quantity == 0
    assert proven_zero.shipped_quantity == 0
    assert proven_zero.planned_explicit_zero is True
    assert proven_zero.shipped_explicit_zero is True
    assert unproven_zero.status == "UNKNOWN"
    assert unproven_zero.planned_quantity is None
    assert unproven_zero.shipped_quantity is None


def test_scope_supply_and_order_mismatches_fail_closed():
    other_store = ScopeIdentity(
        owner_id="owner-1", store_id="store-2", product_id="product-a",
        offer_id="offer-a", sku="sku-a",
    )
    results = (
        FifoCostBatchBundleNormalizer.normalize(
            TARGET, SUPPLY_REF, (_observation(other_store),), composition_complete=True,
        ),
        FifoCostBatchBundleNormalizer.normalize(
            TARGET, SUPPLY_REF, (_observation(supply_ref="e" * 64),),
            composition_complete=True,
        ),
        FifoCostBatchBundleNormalizer.normalize(
            TARGET, SUPPLY_REF,
            (_observation(TARGET), _observation(OTHER_SKU, order_ref="f" * 64)),
            composition_complete=True,
        ),
    )

    assert all(item.status == "UNKNOWN" for item in results)
    assert all(item.planned_quantity is None for item in results)


def test_duplicate_sku_rows_are_not_summed():
    result = FifoCostBatchBundleNormalizer.normalize(
        TARGET, SUPPLY_REF,
        (_observation(TARGET, planned=100, shipped=80),
         _observation(TARGET, planned=101, shipped=81)),
        composition_complete=True,
    )

    assert result.status == "UNKNOWN"
    assert result.planned_quantity is None
    assert result.issue_codes == ("FIFO_BATCH_BUNDLE_DUPLICATE_SKU_MAPPING",)
