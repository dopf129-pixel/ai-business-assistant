from datetime import date, datetime, timezone, timedelta
from decimal import Decimal

import pytest

from services.fifo_cost_transition_contracts import (
    AcceptedQuantityKind,
    BucketSnapshot,
    CostComponents,
    CostInputMode,
    EvidenceCompleteness,
    EvidencePresence,
    EvidenceSourceKind,
    FinancialPreviewBinding,
    NormalizedSupplyStatus,
    PeriodProvenance,
    ReportEvidence,
    ReportType,
    ScopeIdentity,
    SourceProof,
    StockBucket,
    SupplyObservation,
    SupplyDeclaration,
    SupplyReferenceKind,
    TransitionContractError,
    TransitionMetadata,
    TransitionReasonCode,
    TransitionState,
    UnknownValue,
    normalize_date_only,
    normalize_money,
    normalize_quantity,
    normalize_store_timezone,
    normalize_utc_timestamp,
    source_fingerprint,
    utc_now,
)


def _metadata(*, source_kind=EvidenceSourceKind.OWNER_INPUT, completeness=EvidenceCompleteness.PARTIAL):
    return TransitionMetadata(
        scope=ScopeIdentity(
            owner_id="owner-1", store_id="store-1", sku="sku-1",
            product_id="product-1", offer_id="offer-1",
        ),
        source_kind=source_kind,
        completeness=completeness,
        source_fingerprint="a" * 64,
    )


def _unknown(source_kind=EvidenceSourceKind.OWNER_INPUT):
    return UnknownValue(TransitionReasonCode.CASE_NOT_READY, source_kind)


def _api_proof(*, completeness=EvidenceCompleteness.COMPLETE, scope=True, pagination=True):
    return SourceProof(
        metadata=_metadata(
            source_kind=EvidenceSourceKind.OZON_API,
            completeness=completeness,
        ),
        scope_complete=scope,
        pagination_complete=pagination,
        source_as_of="2026-11-07T12:00:00Z",
    )


def test_decimal_money_uses_half_up_and_rejects_float_bool_and_out_of_range():
    assert normalize_money(Decimal("14.645")) == Decimal("14.65")
    assert normalize_money("0") == Decimal("0.00")
    assert normalize_money(Decimal("999999999.99")) == Decimal("999999999.99")

    for invalid in (True, False, 1.25, float("nan"), "NaN", "-0.01", "1000000000.01"):
        with pytest.raises(TransitionContractError) as error:
            normalize_money(invalid)
        assert error.value.reason_code is TransitionReasonCode.MONEY_INVALID


def test_quantity_accepts_explicit_zero_but_rejects_bool_string_and_invalid_ranges():
    assert normalize_quantity(0) == 0
    assert normalize_quantity(1_000_000) == 1_000_000
    for invalid in (None, True, False, "0", -1, 1_000_001, 1.0):
        with pytest.raises(TransitionContractError) as error:
            normalize_quantity(invalid)
        assert error.value.reason_code is TransitionReasonCode.QUANTITY_INVALID


def test_date_only_and_aware_timestamps_keep_distinct_precision():
    assert normalize_date_only("2026-11-05") == "2026-11-05"
    assert normalize_date_only(date(2026, 11, 5)) == "2026-11-05"
    assert normalize_utc_timestamp("2026-11-07T12:00:00+03:00") == (
        "2026-11-07T09:00:00.000000Z"
    )
    assert normalize_utc_timestamp(
        datetime(2026, 11, 7, 9, tzinfo=timezone.utc)
    ) == "2026-11-07T09:00:00.000000Z"

    for invalid in ("2026-11-05", "2026-11-07T12:00:00", datetime(2026, 11, 7), 0):
        with pytest.raises(TransitionContractError) as error:
            normalize_utc_timestamp(invalid)
        assert error.value.reason_code is TransitionReasonCode.TIMESTAMP_INVALID
    with pytest.raises(TransitionContractError) as error:
        normalize_date_only(datetime(2026, 11, 5, tzinfo=timezone.utc))
    assert error.value.reason_code is TransitionReasonCode.DATE_INVALID


def test_store_timezone_and_injected_clock_are_explicit():
    assert normalize_store_timezone() == "Europe/Moscow"
    assert normalize_store_timezone("UTC") == "UTC"
    with pytest.raises(TransitionContractError) as error:
        normalize_store_timezone("Not/A_Timezone")
    assert error.value.reason_code is TransitionReasonCode.TIMEZONE_INVALID

    fixed = datetime(2026, 11, 7, 12, tzinfo=timezone(timedelta(hours=3)))
    assert utc_now(lambda: fixed) == "2026-11-07T09:00:00.000000Z"
    with pytest.raises(TransitionContractError):
        utc_now(lambda: datetime(2026, 11, 7, 12))


def test_owner_input_cannot_be_promoted_to_complete_api_source_proof():
    owner_claim = SourceProof(
        metadata=_metadata(
            source_kind=EvidenceSourceKind.OWNER_INPUT,
            completeness=EvidenceCompleteness.COMPLETE,
        ),
        scope_complete=True,
        pagination_complete=True,
    )
    assert owner_claim.api_read_complete is False
    with pytest.raises(TransitionContractError) as error:
        owner_claim.require_api_read_complete()
    assert error.value.reason_code is TransitionReasonCode.EVENT_COVERAGE_INCOMPLETE

    assert _api_proof().api_read_complete is True
    for partial in (
        _api_proof(completeness=EvidenceCompleteness.PARTIAL),
        _api_proof(scope=False),
        _api_proof(pagination=False),
    ):
        assert partial.api_read_complete is False


def test_transition_case_requires_reason_and_provenance_for_null_values():
    from services.fifo_cost_transition_contracts import TransitionCase

    case = TransitionCase(
        metadata=_metadata(),
        case_id="case000000000001",
        case_revision=1,
        state=TransitionState.AWAITING_EVIDENCE,
        created_at="2026-11-07T12:00:00Z",
        updated_at="2026-11-07T12:00:00Z",
        dispatch_date="2026-11-05",
        old_unit_cost_rub=Decimal("21"),
        new_unit_cost_rub=Decimal("14.65"),
        cost_input_mode=CostInputMode.TOTAL_LANDED,
        cost_components=None,
        owner_old_home_units=0,
        owner_old_transit_units=0,
        new_home_quantity=None,
        declared_shipped_units=6982,
        unknown_values={"new_home_quantity": _unknown()},
    )
    assert case.new_home_quantity is None
    assert case.owner_old_home_units == 0
    assert case.new_unit_cost_rub == Decimal("14.65")
    assert case.cost_components is None

    with pytest.raises(TransitionContractError) as error:
        TransitionCase(
            metadata=_metadata(),
            case_id="case000000000002",
            case_revision=1,
            state=TransitionState.DRAFT,
            created_at="2026-11-07T12:00:00Z",
            updated_at="2026-11-07T12:00:00Z",
            dispatch_date=None,
            old_unit_cost_rub=Decimal("21"),
            new_unit_cost_rub=Decimal("14.65"),
            cost_input_mode=CostInputMode.TOTAL_LANDED,
            cost_components=None,
            owner_old_home_units=0,
            owner_old_transit_units=0,
            new_home_quantity=None,
            declared_shipped_units=6982,
        )
    assert error.value.reason_code is TransitionReasonCode.CONTRACT_INVALID


def test_component_mode_requires_real_breakdown_that_sums_to_unit_cost():
    components = CostComponents(
        purchase_cost_rub=Decimal("10.00"),
        delivery_cost_rub=Decimal("3.25"),
        packaging_cost_rub=Decimal("1.40"),
    )
    assert components.total_rub == Decimal("14.65")

    from services.fifo_cost_transition_contracts import TransitionCase

    valid = TransitionCase(
        metadata=_metadata(),
        case_id="case000000000004",
        case_revision=1,
        state=TransitionState.AWAITING_EVIDENCE,
        created_at="2026-11-07T12:00:00Z",
        updated_at="2026-11-07T12:00:00Z",
        dispatch_date="2026-11-05",
        old_unit_cost_rub=Decimal("21"),
        new_unit_cost_rub=Decimal("14.65"),
        cost_input_mode=CostInputMode.COMPONENTS,
        cost_components=components,
        owner_old_home_units=0,
        owner_old_transit_units=0,
        new_home_quantity=None,
        declared_shipped_units=6982,
        unknown_values={"new_home_quantity": _unknown()},
    )
    assert valid.cost_components.total_rub == valid.new_unit_cost_rub

    with pytest.raises(TransitionContractError) as error:
        TransitionCase(
            metadata=_metadata(),
            case_id="case000000000003",
            case_revision=1,
            state=TransitionState.AWAITING_EVIDENCE,
            created_at="2026-11-07T12:00:00Z",
            updated_at="2026-11-07T12:00:00Z",
            dispatch_date="2026-11-05",
            old_unit_cost_rub=Decimal("21"),
            new_unit_cost_rub=Decimal("14.65"),
            cost_input_mode=CostInputMode.COMPONENTS,
            cost_components=CostComponents(
                purchase_cost_rub=Decimal("14.64"),
                delivery_cost_rub=Decimal("0"),
                packaging_cost_rub=Decimal("0"),
            ),
            owner_old_home_units=0,
            owner_old_transit_units=0,
            new_home_quantity=None,
            declared_shipped_units=6982,
            unknown_values={"new_home_quantity": _unknown()},
        )
    assert error.value.reason_code is TransitionReasonCode.COST_INPUT_INVALID


def test_missing_supply_observation_keeps_quantity_unknown_instead_of_zero():
    observation = SupplyObservation(
        metadata=_metadata(
            source_kind=EvidenceSourceKind.OZON_API,
            completeness=EvidenceCompleteness.PARTIAL,
        ),
        declaration_id="decl000000000001",
        captured_at="2026-11-07T12:00:00Z",
        source_as_of=None,
        raw_status=None,
        normalized_status=NormalizedSupplyStatus.UNKNOWN,
        declared_quantity=None,
        accepted_quantity=None,
        accepted_quantity_kind=None,
        act_reference_digest=None,
        act_version_digest=None,
        scope_complete=False,
        pagination_complete=False,
        presence=EvidencePresence.MISSING,
        unknown_values={
            "declared_quantity": UnknownValue(
                TransitionReasonCode.SUPPLY_OBSERVATION_MISSING,
                EvidenceSourceKind.OZON_API,
            ),
            "accepted_quantity": UnknownValue(
                TransitionReasonCode.SUPPLY_OBSERVATION_MISSING,
                EvidenceSourceKind.OZON_API,
            ),
        },
    )
    assert observation.accepted_quantity is None
    assert observation.presence is EvidencePresence.MISSING
    assert observation.accepted_quantity_kind is None


def test_supply_declaration_stores_only_scoped_digest_and_optional_ciphertext():
    declaration = SupplyDeclaration(
        metadata=_metadata(),
        case_id="case000000000005",
        declaration_id="decl000000000005",
        revision=1,
        reference_kind=SupplyReferenceKind.SUPPLY,
        reference_digest="d" * 64,
        encrypted_lookup_reference=None,
        declared_shipped_units=None,
        dispatch_date="2026-11-05",
        provenance=EvidenceSourceKind.OWNER_INPUT,
        unknown_values={"declared_shipped_units": _unknown()},
    )
    assert declaration.declared_shipped_units is None
    assert declaration.reference_digest == "d" * 64
    assert not hasattr(declaration, "supply_id")
    with pytest.raises(TypeError):
        declaration.unknown_values["declared_shipped_units"] = _unknown()

    with pytest.raises(TransitionContractError) as error:
        SupplyDeclaration(
            metadata=_metadata(),
            case_id="case000000000006",
            declaration_id="decl000000000006",
            revision=1,
            reference_kind=SupplyReferenceKind.SUPPLY,
            reference_digest="d" * 64,
            encrypted_lookup_reference="2000070135564",
            declared_shipped_units=100,
            dispatch_date="2026-11-05",
            provenance=EvidenceSourceKind.OWNER_INPUT,
        )
    assert error.value.reason_code is TransitionReasonCode.CONTRACT_INVALID


def test_report_evidence_keeps_confirmed_period_provenance_and_freezes_fields():
    row = {"units": 148, "amount": Decimal("14.65")}
    report = ReportEvidence(
        metadata=_metadata(
            source_kind=EvidenceSourceKind.OWNER_IMPORTED,
            completeness=EvidenceCompleteness.COMPLETE,
        ),
        report_type=ReportType.STOCK_MANAGEMENT,
        period_from="2026-11-07",
        period_to="2026-11-07",
        period_provenance=PeriodProvenance.FILENAME_CANDIDATE,
        captured_at="2026-11-07T18:00:00+03:00",
        file_sha256="e" * 64,
        parser_version="1.0.0",
        cell_references=("A1", "B2"),
        normalized_fields={"rows": [row]},
    )
    row["units"] = 999
    assert report.normalized_fields["rows"][0]["units"] == 148
    assert report.period_provenance is PeriodProvenance.FILENAME_CANDIDATE
    with pytest.raises(TypeError):
        report.normalized_fields["rows"][0]["units"] = 999


def test_bucket_snapshot_keeps_unknown_buckets_separate_from_confirmed_zero():
    snapshot = BucketSnapshot(
        metadata=_metadata(
            source_kind=EvidenceSourceKind.OWNER_IMPORTED,
            completeness=EvidenceCompleteness.PARTIAL,
        ),
        captured_at="2026-11-07T12:00:00Z",
        source_as_of=None,
        quantities={StockBucket.AVAILABLE: 0, StockBucket.RESERVED: None},
        unknown_values={"reserved": _unknown(EvidenceSourceKind.OWNER_IMPORTED)},
    )
    assert snapshot.quantities[StockBucket.AVAILABLE] == 0
    assert snapshot.quantities[StockBucket.RESERVED] is None


def test_financial_preview_is_bound_to_all_current_revisions_and_tax_policy():
    binding = FinancialPreviewBinding(
        metadata=_metadata(source_kind=EvidenceSourceKind.LOCAL_DERIVED),
        fifo_revision=1,
        case_revision=2,
        evidence_set_fingerprint="b" * 64,
        allocation_revision=3,
        tax_policy_fingerprint="c" * 64,
    )
    assert binding.case_revision == 2
    with pytest.raises(TransitionContractError) as error:
        FinancialPreviewBinding(
            metadata=_metadata(source_kind=EvidenceSourceKind.LOCAL_DERIVED),
            fifo_revision=True,
            case_revision=2,
            evidence_set_fingerprint="b" * 64,
            allocation_revision=3,
            tax_policy_fingerprint="c" * 64,
        )
    assert error.value.reason_code is TransitionReasonCode.CONTRACT_INVALID


def test_source_fingerprint_is_stable_for_normalized_decimal_payload():
    assert source_fingerprint({"cost": Decimal("14.65"), "units": 100}) == (
        source_fingerprint({"units": 100, "cost": Decimal("14.65")})
    )
