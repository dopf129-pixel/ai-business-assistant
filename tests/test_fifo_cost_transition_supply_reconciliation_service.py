from services.fifo_cost_supply_acceptance_reconciliation_service import (
    FifoSupplyAcceptanceReconciliation,
)
from services.fifo_cost_transition_contracts import (
    EvidenceCompleteness,
    EvidencePresence,
    EvidenceSourceKind,
    NormalizedSupplyStatus,
    PeriodProvenance,
    ReportEvidence,
    ReportType,
    ScopeIdentity,
    SupplyDeclaration,
    SupplyObservation,
    SupplyReferenceKind,
    TransitionMetadata,
    UnknownValue,
    TransitionReasonCode,
    source_fingerprint,
)
from services.fifo_cost_transition_supply_reconciliation_service import (
    FifoCostTransitionSupplyReconciliationService,
    FifoSupplyAcceptanceSnapshot,
)


SCOPE = ScopeIdentity("owner-a", "store-a", "3921245627", product_id="product-a")
CASE_ID = "case-0000001"
DECLARATION_ID = "declaration-0001"
REFERENCE_DIGEST = "a" * 64


def _metadata(source, *, scope=SCOPE, completeness=EvidenceCompleteness.COMPLETE, marker="x"):
    return TransitionMetadata(
        scope=scope,
        source_kind=source,
        completeness=completeness,
        source_fingerprint=source_fingerprint(marker),
    )


def _declaration(*, quantity=148, revision=1, declaration_id=DECLARATION_ID, scope=SCOPE):
    unknown = {}
    if quantity is None:
        unknown["declared_shipped_units"] = UnknownValue(
            TransitionReasonCode.SOURCE_PROOF_UNAVAILABLE,
            EvidenceSourceKind.OWNER_INPUT,
        )
    return SupplyDeclaration(
        metadata=_metadata(EvidenceSourceKind.OWNER_INPUT, scope=scope, marker=f"decl-{revision}"),
        case_id=CASE_ID,
        declaration_id=declaration_id,
        revision=revision,
        reference_kind=SupplyReferenceKind.SUPPLY,
        reference_digest=REFERENCE_DIGEST,
        encrypted_lookup_reference="gAAAA" + "A" * 90,
        declared_shipped_units=quantity,
        dispatch_date="2026-11-05",
        provenance=EvidenceSourceKind.OWNER_INPUT,
        unknown_values=unknown,
    )


def _observation(
    *, minute=0, status=NormalizedSupplyStatus.RECEIVING, quantity=148,
    presence=EvidencePresence.PRESENT, declaration_id=DECLARATION_ID,
    source_as_of="2026-11-08T10:00:00Z", scope=SCOPE,
):
    unknown = {
        "accepted_quantity": UnknownValue(
            TransitionReasonCode.SUPPLY_OBSERVATION_MISSING,
            EvidenceSourceKind.OZON_API,
        ),
    }
    if presence is EvidencePresence.MISSING:
        quantity = None
        unknown = {
            "declared_quantity": UnknownValue(
                TransitionReasonCode.SUPPLY_OBSERVATION_MISSING,
                EvidenceSourceKind.OZON_API,
            ),
            "accepted_quantity": UnknownValue(
                TransitionReasonCode.SUPPLY_OBSERVATION_MISSING,
                EvidenceSourceKind.OZON_API,
            ),
        }
    return SupplyObservation(
        metadata=_metadata(EvidenceSourceKind.OZON_API, scope=scope, marker=f"obs-{minute}-{presence.value}"),
        declaration_id=declaration_id,
        captured_at=f"2026-11-08T10:{minute:02d}:00Z",
        source_as_of=source_as_of,
        raw_status=status.value,
        normalized_status=status,
        declared_quantity=quantity,
        accepted_quantity=None,
        accepted_quantity_kind=None,
        act_reference_digest=None,
        act_version_digest=None,
        scope_complete=presence is EvidencePresence.PRESENT,
        pagination_complete=presence is EvidencePresence.PRESENT,
        presence=presence,
        unknown_values=unknown,
    )


def _acceptance(
    *, status="PARTIALLY_ACCEPTED", accepted=100, pending=48,
    declared=148,
    minute=1, source_as_of="2026-11-08T10:01:00Z", declaration_id=DECLARATION_ID,
    reference_digest=REFERENCE_DIGEST, completeness=EvidenceCompleteness.COMPLETE,
):
    result = FifoSupplyAcceptanceReconciliation(
        status=status,
        declared_quantity=declared,
        accepted_quantity=accepted,
        candidate_quantity=accepted,
        unaccepted_quantity=pending,
        act_count=1,
        act_reference_digests=("b" * 64,),
        store_id="store-a",
        supply_reference="opaque-internal-reference",
        source_fingerprint="c" * 64,
        issue_codes=(),
        required_action="WAIT_FOR_FINAL_ACCEPTANCE",
    )
    return FifoSupplyAcceptanceSnapshot(
        metadata=_metadata(EvidenceSourceKind.OZON_API, completeness=completeness, marker=f"accept-{minute}"),
        declaration_id=declaration_id,
        declaration_reference_digest=reference_digest,
        captured_at=f"2026-11-08T10:{minute:02d}:30Z",
        source_as_of=source_as_of,
        reconciliation=result,
    )


def _stock_report(*, planned=600, transit=6234, captured_at="2026-11-07T21:16:00Z", scope=SCOPE):
    return ReportEvidence(
        metadata=_metadata(EvidenceSourceKind.OWNER_IMPORTED, scope=scope, marker=f"report-{captured_at}"),
        report_type=ReportType.STOCK_MANAGEMENT,
        period_from="2026-11-07",
        period_to="2026-11-07",
        period_provenance=PeriodProvenance.FILENAME_CANDIDATE,
        captured_at=captured_at,
        file_sha256=source_fingerprint(f"file-{captured_at}"),
        parser_version="stock-test-v1",
        cell_references=("V2", "W2"),
        normalized_fields={"stock_buckets": {
            "supplier_planned": planned,
            "supplier_transit": transit,
            "supplier_receiving": None,
            "reserved": None,
        }},
    )


def _reconcile(**overrides):
    inputs = {
        "scope": SCOPE,
        "case_id": CASE_ID,
        "owner_declared_total": 6982,
        "declarations": (_declaration(),),
        "observations": (_observation(),),
        "acceptance_snapshots": (),
        "stock_reports": (_stock_report(),),
    }
    inputs.update(overrides)
    return FifoCostTransitionSupplyReconciliationService().reconcile(**inputs)


def test_control_case_keeps_owner_linked_receiving_and_report_buckets_separate():
    result = _reconcile()

    assert result.status == "PARTIAL"
    assert result.owner_declared_total == 6982
    assert result.known_declared_total == 148
    assert result.owner_undistributed_units == 6834
    assert result.is_atomic_snapshot is False
    assert result.source_as_of_coherence == "DIFFERENT"
    assert len(result.declarations) == 1
    assert result.declarations[0].observed_status is NormalizedSupplyStatus.RECEIVING
    assert result.declarations[0].accepted_quantity is None
    assert result.declarations[0].pending_quantity is None
    assert result.stock_report_snapshots[0].quantities["supplier_planned"] == 600
    assert result.stock_report_snapshots[0].quantities["supplier_transit"] == 6234
    assert "SOURCE_AS_OF_NOT_ATOMIC" in result.issue_codes


def test_latest_missing_observation_preserves_last_known_receiving_without_zeroing():
    result = _reconcile(observations=(
        _observation(minute=0),
        _observation(
            minute=2, presence=EvidencePresence.MISSING,
            status=NormalizedSupplyStatus.UNKNOWN, source_as_of=None,
        ),
    ))

    view = result.declarations[0]
    assert view.observed_status is NormalizedSupplyStatus.RECEIVING
    assert view.observed_declared_quantity == 148
    assert view.observed_presence is EvidencePresence.MISSING
    assert view.observation_freshness == "MISSING_LATEST"
    assert result.declarations[0].accepted_quantity is None


def test_later_present_observation_refreshes_same_declaration_without_duplicate_receipt():
    result = _reconcile(observations=(
        _observation(
            minute=1, presence=EvidencePresence.MISSING,
            status=NormalizedSupplyStatus.UNKNOWN, source_as_of=None,
        ),
        _observation(minute=2),
    ))

    view = result.declarations[0]
    assert result.owner_declared_total == 6982
    assert result.known_declared_total == 148
    assert len(result.declarations) == 1
    assert view.declared_quantity == 148
    assert view.observed_declared_quantity == 148
    assert view.observed_status is NormalizedSupplyStatus.RECEIVING
    assert view.observed_presence is EvidencePresence.PRESENT
    assert view.accepted_quantity is None
    assert result.status == "PARTIAL"


def test_missing_without_any_prior_observation_does_not_invent_unknown_status_as_current():
    result = _reconcile(observations=(
        _observation(
            minute=2, presence=EvidencePresence.MISSING,
            status=NormalizedSupplyStatus.UNKNOWN, source_as_of=None,
        ),
    ))

    view = result.declarations[0]
    assert view.observed_status is None
    assert view.observed_at is None
    assert view.observed_presence is EvidencePresence.MISSING
    assert view.observation_freshness == "MISSING_LATEST"
    assert "SUPPLY_OBSERVATION_NOT_CURRENT" in result.issue_codes


def test_api_declared_quantity_mismatch_is_visible_and_not_overwritten():
    result = _reconcile(observations=(
        _observation(quantity=150),
    ))

    view = result.declarations[0]
    assert view.declared_quantity == 148
    assert view.observed_declared_quantity == 150
    assert view.declaration_quantity_difference == 2
    assert "OWNER_API_DECLARATION_MISMATCH" in result.issue_codes


def test_partial_acceptance_is_not_final_discrepancy_and_pending_is_separate():
    result = _reconcile(acceptance_snapshots=(_acceptance(),))

    view = result.declarations[0]
    assert view.accepted_quantity == 100
    assert view.pending_quantity == 48
    assert view.discrepancy_quantity is None
    assert view.acceptance_is_current is True


def test_final_shortage_is_discrepancy_not_pending():
    final = _acceptance(status="DISCREPANCY", accepted=140, pending=8)
    result = _reconcile(acceptance_snapshots=(final,))

    view = result.declarations[0]
    assert view.accepted_quantity == 140
    assert view.pending_quantity is None
    assert view.discrepancy_quantity == 8


def test_acceptance_declared_quantity_difference_is_reported_separately():
    result = _reconcile(acceptance_snapshots=(
        _acceptance(declared=150),
    ))

    view = result.declarations[0]
    assert view.declared_quantity == 148
    assert view.acceptance_declared_quantity == 150
    assert view.acceptance_declared_quantity_difference == 2
    assert "OWNER_ACCEPTANCE_DECLARATION_MISMATCH" in result.issue_codes


def test_different_capture_and_source_as_of_times_are_not_collapsed():
    result = _reconcile(
        observations=(_observation(source_as_of="2026-11-08T10:00:00Z"),),
        acceptance_snapshots=(_acceptance(source_as_of="2026-11-08T10:01:00Z"),),
        stock_reports=(_stock_report(),),
    )

    assert result.source_as_of_coherence == "DIFFERENT"
    assert result.is_atomic_snapshot is False
    assert result.stock_report_snapshots[0].source_as_of is None
    assert result.declarations[0].observed_source_as_of != result.declarations[0].accepted_source_as_of


def test_unknown_owner_declaration_quantity_does_not_create_undistributed_number():
    result = _reconcile(
        declarations=(_declaration(quantity=None),),
    )

    assert result.known_declared_total == 0
    assert result.declarations_with_unknown_quantity == 1
    assert result.owner_undistributed_units is None
    assert "DECLARATION_QUANTITY_UNKNOWN" in result.issue_codes


def test_acceptance_with_wrong_declaration_digest_is_rejected_from_view():
    result = _reconcile(acceptance_snapshots=(
        _acceptance(reference_digest="d" * 64),
    ))

    assert result.status == "CONFLICT"
    assert result.declarations[0].acceptance_status == "UNAVAILABLE"
    assert result.declarations[0].accepted_quantity is None
    assert "ACCEPTANCE_BINDING_CONFLICT" in result.issue_codes
    assert len(result.acceptance_conflicts) == 1
    assert result.acceptance_conflicts[0].source_fingerprint == source_fingerprint("accept-1")
    assert result.acceptance_conflicts[0].source_as_of == "2026-11-08T10:01:00.000000Z"
    assert result.acceptance_conflicts[0].has_act_reference is True


def test_acceptance_quantity_mismatch_preserves_redacted_conflict_locator():
    result = _reconcile(acceptance_snapshots=(
        _acceptance(declared=150),
    ))

    assert "OWNER_ACCEPTANCE_DECLARATION_MISMATCH" in result.issue_codes
    assert len(result.acceptance_conflicts) == 1
    assert result.acceptance_conflicts[0].issue_codes == (
        "OWNER_ACCEPTANCE_DECLARATION_MISMATCH",
    )


def test_wrong_scope_stock_report_is_not_included():
    other_scope = ScopeIdentity("owner-a", "store-b", "3921245627", product_id="product-a")
    result = _reconcile(stock_reports=(_stock_report(scope=other_scope),))

    assert result.status == "CONFLICT"
    assert result.stock_report_snapshots == ()
    assert "STOCK_REPORT_SCOPE_CONFLICT" in result.issue_codes


def test_same_timestamp_observation_conflict_fails_closed():
    first = _observation(minute=0)
    changed = _observation(minute=0, status=NormalizedSupplyStatus.IN_TRANSIT)
    result = _reconcile(observations=(first, changed))

    assert result.status == "CONFLICT"
    assert "SUPPLY_OBSERVATION_CONFLICT" in result.issue_codes


def test_later_declaration_revision_replaces_only_same_opaque_declaration():
    result = _reconcile(declarations=(
        _declaration(quantity=100, revision=1),
        _declaration(quantity=148, revision=2),
    ))

    assert result.known_declared_total == 148
    assert len(result.declarations) == 1
    assert result.declarations[0].revision == 2
