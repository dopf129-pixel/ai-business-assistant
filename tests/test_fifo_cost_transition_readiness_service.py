from services.fifo_cost_supply_acceptance_reconciliation_service import (
    FifoSupplyAcceptanceReconciliation,
)
from dataclasses import replace
from services.fifo_cost_transition_contracts import (
    CostInputMode,
    EvidenceCompleteness,
    EvidencePresence,
    EvidenceSourceKind,
    NormalizedSupplyStatus,
    PeriodProvenance,
    ReportEvidence,
    ReportType,
    ScopeIdentity,
    SupplyTotalMode,
    SupplyDeclaration,
    SupplyObservation,
    SupplyReferenceKind,
    TransitionCase,
    TransitionMetadata,
    TransitionReasonCode,
    TransitionState,
    UnknownValue,
    source_fingerprint,
)
from services.fifo_cost_batch_rule_contracts import (
    AutomaticBatchManifest,
    ManifestFreshness,
    SupplyScanCoverage,
)
from services.fifo_cost_transition_opening_proposal_service import (
    FifoCostTransitionOpeningProposalService,
)
from services.fifo_cost_transition_readiness_service import (
    FifoCostTransitionReadinessService,
)
from services.fifo_cost_transition_supply_reconciliation_service import (
    FifoCostTransitionSupplyReconciliationService,
    FifoSupplyAcceptanceSnapshot,
)


SCOPE = ScopeIdentity(
    "owner-test", "store-test", "1000000001", product_id="101", offer_id="test-a",
)
CASE_ID = "case_test_0001"
DECLARATION_ID = "declaration-148"
REFERENCE_DIGEST = "a" * 64


def _metadata(kind, *, marker, completeness=EvidenceCompleteness.COMPLETE):
    return TransitionMetadata(
        scope=SCOPE,
        source_kind=kind,
        completeness=completeness,
        source_fingerprint=source_fingerprint(marker),
    )


def _case(*, cutoff_evidence=True):
    unknown = {
        "new_home_quantity": UnknownValue(
            TransitionReasonCode.SOURCE_PROOF_UNAVAILABLE,
            EvidenceSourceKind.OWNER_INPUT,
        ),
    }
    return TransitionCase(
        metadata=_metadata(
            EvidenceSourceKind.OWNER_INPUT, marker="case",
            completeness=EvidenceCompleteness.PARTIAL,
        ),
        case_id=CASE_ID,
        case_revision=3,
        state=TransitionState.AWAITING_EVIDENCE,
        created_at="2026-11-08T10:00:00Z",
        updated_at="2026-11-08T11:00:00Z",
        dispatch_date="2026-11-05",
        old_unit_cost_rub="21.00",
        new_unit_cost_rub="14.65",
        cost_input_mode=CostInputMode.TOTAL_LANDED,
        cost_components=None,
        owner_old_home_units=0,
        owner_old_transit_units=0,
        new_home_quantity=None,
        declared_shipped_units=6982,
        unknown_values=unknown,
    )


def _stock_report(*, reserved=None, overlap=True, provenance=PeriodProvenance.OWNER_CONFIRMED):
    return ReportEvidence(
        metadata=_metadata(EvidenceSourceKind.OWNER_IMPORTED, marker="stock"),
        report_type=ReportType.STOCK_MANAGEMENT,
        period_from="2026-11-07",
        period_to="2026-11-07",
        period_provenance=provenance,
        captured_at="2026-11-07T18:00:00Z",
        file_sha256=source_fingerprint(f"stock-{reserved}-{overlap}-{provenance.value}"),
        parser_version="stock-test-v1",
        cell_references=("M5", "N5"),
        normalized_fields={
            "stock_buckets": {
                "available": 1191, "reserved": reserved, "supplier_transit": 6234,
            },
            "fbs_return_available_units": 9,
            "fbs_return_is_subset_of_available": overlap,
        },
    )


def _turnover_report(*, provenance=PeriodProvenance.OWNER_CONFIRMED, end="2026-11-05"):
    return ReportEvidence(
        metadata=_metadata(EvidenceSourceKind.OWNER_IMPORTED, marker=f"turnover-{end}"),
        report_type=ReportType.TURNOVER,
        period_from="2026-11-04",
        period_to=end,
        period_provenance=provenance,
        captured_at="2026-11-08T12:00:00Z",
        file_sha256=source_fingerprint(f"turnover-{end}-{provenance.value}"),
        parser_version="turnover-test-v1",
        cell_references=("AJ4", "AM4", "AN4"),
        normalized_fields={
            "opening_total": 4492,
            "receipts_total": 0,
            "expenses_total": 780,
            "redeemed_units": 775,
            "non_sale_expense_units": 5,
            "withdrawal_units": 5,
            "closing_total": 3712,
            "closing_buckets": {"buyer_delivery": 1646, "buyer_return_transit": 70},
            "reported_balance_difference": 0,
            "computed_balance_difference": 0,
            "balance_status": "BALANCED",
        },
    )


def _declaration():
    return SupplyDeclaration(
        metadata=_metadata(EvidenceSourceKind.OWNER_INPUT, marker="declaration"),
        case_id=CASE_ID,
        declaration_id=DECLARATION_ID,
        revision=1,
        reference_kind=SupplyReferenceKind.SUPPLY,
        reference_digest=REFERENCE_DIGEST,
        encrypted_lookup_reference="gAAAA" + "A" * 90,
        declared_shipped_units=148,
        dispatch_date="2026-11-05",
        provenance=EvidenceSourceKind.OWNER_INPUT,
    )


def _observation(*, quantity=148):
    return SupplyObservation(
        metadata=_metadata(EvidenceSourceKind.OZON_API, marker=f"observation-{quantity}"),
        declaration_id=DECLARATION_ID,
        captured_at="2026-11-08T12:01:00Z",
        source_as_of="2026-11-08T12:00:00Z",
        raw_status="RECEIVING",
        normalized_status=NormalizedSupplyStatus.RECEIVING,
        declared_quantity=quantity,
        accepted_quantity=None,
        accepted_quantity_kind=None,
        act_reference_digest=None,
        act_version_digest=None,
        scope_complete=True,
        pagination_complete=True,
        presence=EvidencePresence.PRESENT,
        unknown_values={
            "accepted_quantity": UnknownValue(
                TransitionReasonCode.SUPPLY_OBSERVATION_MISSING,
                EvidenceSourceKind.OZON_API,
            ),
        },
    )


def _acceptance(*, reference_digest=REFERENCE_DIGEST):
    return FifoSupplyAcceptanceSnapshot(
        metadata=_metadata(EvidenceSourceKind.OZON_API, marker="acceptance"),
        declaration_id=DECLARATION_ID,
        declaration_reference_digest=reference_digest,
        captured_at="2026-11-08T12:02:00Z",
        source_as_of="2026-11-08T12:00:00Z",
        reconciliation=FifoSupplyAcceptanceReconciliation(
            status="PARTIALLY_ACCEPTED",
            declared_quantity=148,
            accepted_quantity=100,
            candidate_quantity=100,
            unaccepted_quantity=48,
            act_count=1,
            act_reference_digests=("b" * 64,),
            store_id=SCOPE.store_id,
            supply_reference="opaque-reference",
            source_fingerprint="c" * 64,
            issue_codes=(),
            required_action="WAIT_FOR_FINAL_ACCEPTANCE",
        ),
    )


def _reconcile(*, stock, declaration=True, observation=True, acceptance=(), owner_total=6982):
    return FifoCostTransitionSupplyReconciliationService().reconcile(
        scope=SCOPE,
        case_id=CASE_ID,
        owner_declared_total=owner_total,
        declarations=(_declaration(),) if declaration else (),
        observations=(_observation(),) if observation else (),
        acceptance_snapshots=tuple(acceptance),
        stock_reports=tuple(stock),
    )


def _assess(*, case=None, cutoff="2026-11-07", turnover=None, stock=None,
            provenance=PeriodProvenance.OWNER_CONFIRMED, acceptance=(),
            automatic_batch_manifest=None):
    case = case or _case()
    stock_reports = (stock or _stock_report(),)
    turnover_reports = (turnover or _turnover_report(provenance=provenance),)
    reconciliation = _reconcile(
        stock=stock_reports, acceptance=acceptance,
        owner_total=case.declared_shipped_units,
    )
    proposal = FifoCostTransitionOpeningProposalService().propose(
        case=case,
        fifo_initialized=False,
        owner_confirmed_cutoff_date=cutoff,
        stock_reports=stock_reports,
        turnover_reports=turnover_reports,
        supply_reconciliation=reconciliation,
    )
    readiness = FifoCostTransitionReadinessService().assess(
        case=case, proposal=proposal, supply_reconciliation=reconciliation,
        automatic_batch_manifest=automatic_batch_manifest,
    )
    return readiness, proposal, reconciliation


def _by_code(readiness):
    return {item.code: item for item in readiness.requirements}


def _auto_case():
    case = _case()
    return replace(
        case,
        declared_shipped_units=None,
        supply_total_mode=SupplyTotalMode.AUTO_FROM_SUPPLIES,
        unknown_values={
            **case.unknown_values,
            "declared_shipped_units": UnknownValue(
                TransitionReasonCode.SOURCE_PROOF_UNAVAILABLE,
                EvidenceSourceKind.OWNER_INPUT,
            ),
        },
    )


def _automatic_manifest(*, coverage_overrides=None, **overrides):
    coverage_fields = {
        "scan_id": "scan000000000001",
        "revision": 1,
        "scope": SCOPE,
        "case_id": CASE_ID,
        "rule_revision": 1,
        "requested_from": "2026-11-05",
        "requested_through": "2026-11-14",
        "captured_at": "2026-11-14T12:00:00Z",
        "source_as_of": "2026-11-14T11:59:00Z",
        "supported_state_profile": ("COMPLETED", "IN_TRANSIT", "RECEIVING"),
        "list_pagination_complete": True,
        "details_complete": True,
        "sku_composition_complete": True,
        "historical_window_proven": True,
        "membership_complete": True,
        "quantity_complete": True,
        "physical_receipt_timing_complete": False,
        "observation_set_fingerprint": "a" * 64,
        "source_contract_version": "synthetic-v1",
        "orders_seen": 1,
        "supplies_seen": 1,
        "sku_rows_seen": 1,
        "unknown_order_count": 0,
        "unknown_supply_count": 0,
        "unknown_quantity_supply_count": 0,
        "issue_codes": (),
    }
    coverage_fields.update(coverage_overrides or {})
    coverage = SupplyScanCoverage(**coverage_fields)
    manifest_fields = {
        "rule_id": "rule000000000001",
        "rule_revision": 1,
        "rule_fingerprint": "b" * 64,
        "scan_id": coverage.scan_id,
        "observation_record_keys": ("c" * 64,),
        "membership_decision_refs": (),
        "owner_control_total": None,
        "owner_control_from": None,
        "owner_control_through": None,
        "owner_control_kind": None,
        "owner_control_status": None,
        "declared_in_found_supplies": 6982,
        "declared_in_shipped_supplies": 6982,
        "accepted_units": 1192,
        "pending_units": 5790,
        "planned_units": 0,
        "known_subtotal": 6982,
        "unknown_quantity_supply_count": 0,
        "found_supply_count": 1,
        "included_supply_count": 1,
        "undecided_supply_count": 0,
        "coverage": coverage,
        "current_through": "2026-11-14T11:59:00Z",
        "freshness": ManifestFreshness.CURRENT,
        "issues": (),
    }
    manifest_fields.update(overrides)
    return AutomaticBatchManifest(**manifest_fields)


def test_owner_case_produces_concrete_missing_requirements_and_preserves_state():
    case = _case()
    result, proposal, _ = _assess(case=case)
    items = _by_code(result)

    assert result.status == "AWAITING_EVIDENCE"
    assert result.case_state_before == result.case_state_after == "AWAITING_EVIDENCE"
    assert case.state is TransitionState.AWAITING_EVIDENCE
    assert items["SUPPLY_MANIFEST_INCOMPLETE"].known_values["unassigned_units"] == 6834
    assert items["SUPPLY_MANIFEST_INCOMPLETE"].already_saved[0].saved_fields
    assert items["TURNOVER_COVERAGE_GAP"].required_period == ("2026-11-06", "2026-11-07")
    assert result.source_data_through == "2026-11-05"
    assert result.complete_through is None
    assert items["STOCK_RESERVED_OR_OVERLAP_UNKNOWN"].already_saved[0].fingerprint
    assert items["SALE_CUTOFF_BRIDGE_REQUIRED"].required_fields
    assert result.ready_to_apply is False
    assert result.preview_only is True
    assert result.is_atomic_snapshot is False
    assert proposal.fifo_opening_units is None


def test_auto_mode_without_manifest_reports_source_gap_without_owner_total_gate():
    case = _auto_case()
    result, _, reconciliation = _assess(case=case)
    items = _by_code(result)

    assert reconciliation.owner_declared_total is None
    assert "AUTO_SUPPLY_MANIFEST_UNAVAILABLE" in items
    assert "SUPPLY_MANIFEST_INCOMPLETE" not in items
    assert items["AUTO_SUPPLY_MANIFEST_UNAVAILABLE"].known_values["owner_total_required"] is False
    assert items["AUTO_SUPPLY_MANIFEST_UNAVAILABLE"].known_values["manual_owner_total_present"] is False
    assert "SALE_CUTOFF_BRIDGE_REQUIRED" in items
    assert result.ready_to_apply is False
    assert result.preview_only is True


def test_auto_mode_empty_or_partial_manifest_never_promotes_known_subtotal_to_total():
    case = _auto_case()
    manifest = _automatic_manifest(
        observation_record_keys=(), found_supply_count=0, included_supply_count=0,
        unknown_quantity_supply_count=0, known_subtotal=148,
        declared_in_shipped_supplies=None,
        coverage_overrides={
            "supplies_seen": 0, "sku_rows_seen": 0,
            "unknown_quantity_supply_count": 0,
        },
    )
    result, _, _ = _assess(case=case, automatic_batch_manifest=manifest)
    items = _by_code(result)
    requirement = items["AUTO_SUPPLY_MANIFEST_INCOMPLETE"]

    assert "AUTO_SUPPLY_MANIFEST_UNAVAILABLE" not in items
    assert "SUPPLY_MANIFEST_INCOMPLETE" not in items
    assert requirement.known_values["known_subtotal_only"] == 148
    assert "owner_declared_total" not in requirement.known_values
    assert "found_supplies" in requirement.known_values["missing_proofs"]
    assert "observation_records" in requirement.known_values["missing_proofs"]
    assert requirement.blocks_apply is True
    assert result.ready_to_apply is False


def test_auto_mode_with_found_but_unknown_quantity_stays_incomplete():
    case = _auto_case()
    manifest = _automatic_manifest(
        observation_record_keys=("c" * 64, "d" * 64),
        found_supply_count=2, included_supply_count=2,
        declared_in_found_supplies=6500,
        known_subtotal=6500, planned_units=0,
        declared_in_shipped_supplies=None,
        unknown_quantity_supply_count=1,
        coverage_overrides={
            "supplies_seen": 2, "sku_rows_seen": 2,
            "quantity_complete": False,
            "unknown_quantity_supply_count": 1,
        },
    )
    result, _, _ = _assess(case=case, automatic_batch_manifest=manifest)
    item = _by_code(result)["AUTO_SUPPLY_MANIFEST_INCOMPLETE"]

    assert item.known_values["known_subtotal_only"] == 6500
    assert item.known_values["unknown_quantity_supply_count"] == 1
    assert "quantity_complete" in item.known_values["missing_proofs"]
    assert item.blocks_apply is True


def test_complete_auto_manifest_removes_only_manifest_gap_and_never_bypasses_r1():
    case = _auto_case()
    result, _, _ = _assess(
        case=case, automatic_batch_manifest=_automatic_manifest(),
    )
    items = _by_code(result)

    assert "AUTO_SUPPLY_MANIFEST_UNAVAILABLE" not in items
    assert "AUTO_SUPPLY_MANIFEST_INCOMPLETE" not in items
    assert "SUPPLY_MANIFEST_INCOMPLETE" not in items
    assert "SALE_CUTOFF_BRIDGE_REQUIRED" in items
    assert _automatic_manifest().coverage.physical_receipt_timing_complete is False
    assert result.ready_to_apply is False
    assert result.preview_only is True


def test_owner_control_mode_is_not_accidentally_treated_as_legacy_owner_total():
    case = replace(_auto_case(), supply_total_mode=SupplyTotalMode.OWNER_CONTROL)
    result, _, _ = _assess(case=case)
    items = _by_code(result)

    assert "SUPPLY_CONTROL_RECONCILIATION_PENDING" in items
    assert "SUPPLY_MANIFEST_INCOMPLETE" not in items
    assert items["SUPPLY_CONTROL_RECONCILIATION_PENDING"].known_values[
        "owner_total_required"
    ] is False


def test_auto_manifest_with_different_case_scope_is_rejected():
    case = _auto_case()
    manifest = _automatic_manifest(
        coverage_overrides={"case_id": "case_other000001"},
    )
    result, proposal, reconciliation = _assess(case=case)

    try:
        FifoCostTransitionReadinessService().assess(
            case=case, proposal=proposal, supply_reconciliation=reconciliation,
            automatic_batch_manifest=manifest,
        )
    except ValueError as exc:
        assert str(exc) == "FIFO_READINESS_INPUT_INVALID"
    else:
        raise AssertionError("manifest from another case must be rejected")


def test_filename_candidate_period_is_not_reported_as_confirmed_missing_coverage():
    result, _, _ = _assess(provenance=PeriodProvenance.FILENAME_CANDIDATE)
    items = _by_code(result)

    assert "TURNOVER_PERIOD_CONFIRMATION_REQUIRED" in items
    assert "TURNOVER_COVERAGE_GAP" not in items
    assert result.source_data_through is None
    assert result.candidate_data_through == "2026-11-05"
    assert result.complete_through is None


def test_owner_confirmed_report_cannot_claim_complete_through_cutoff():
    result, _, _ = _assess(turnover=_turnover_report(end="2026-11-05"))

    assert result.source_data_through == "2026-11-05"
    assert result.cutoff_date == "2026-11-07"
    assert result.complete_through is None
    assert _by_code(result)["TURNOVER_COVERAGE_GAP"].required_period == (
        "2026-11-06", "2026-11-07",
    )


def test_act_binding_conflict_is_an_explicit_conflict_requirement():
    result, _, reconciliation = _assess(acceptance=(_acceptance(reference_digest="d" * 64),))

    assert "ACCEPTANCE_BINDING_CONFLICT" in reconciliation.issue_codes
    assert result.status == "CONFLICT"
    conflict = _by_code(result)["ACCEPTANCE_ACT_CONFLICT"]
    assert conflict.status == "CONFLICT"
    assert conflict.blocks_apply is True
    assert len(conflict.already_saved) == 1
    assert conflict.already_saved[0].fingerprint
    assert conflict.already_saved[0].source_as_of == "2026-11-08T12:00:00.000000Z"


def test_partial_manifest_is_separate_from_missing_or_lagging_api_evidence():
    result, _, reconciliation = _assess()
    items = _by_code(result)

    assert reconciliation.status == "PARTIAL"
    assert items["SUPPLY_MANIFEST_INCOMPLETE"].status == "MISSING"
    assert "SUPPLY_SOURCE_LAG_OR_AS_OF_GAP" in items
    assert "SUPPLY_SOURCE_LAG_OR_AS_OF_GAP" not in items["SUPPLY_MANIFEST_INCOMPLETE"].code


def test_missing_cutoff_is_not_inferred_from_report_name_and_case_stays_saved():
    case = _case()
    result, _, _ = _assess(case=case, cutoff=None)
    items = _by_code(result)

    assert result.cutoff_date is None
    assert items["OWNER_CUTOFF_CONFIRMATION_REQUIRED"].known_values["filename_date_is_cutoff"] is False
    assert result.case_state_after == case.state.value
    assert result.complete_through is None


def test_mismatched_case_or_revision_is_rejected():
    case = _case()
    result, proposal, reconciliation = _assess(case=case)
    wrong_case = replace(case, case_revision=4)

    try:
        FifoCostTransitionReadinessService().assess(
            case=wrong_case, proposal=proposal, supply_reconciliation=reconciliation,
        )
    except ValueError as exc:
        assert str(exc) == "FIFO_READINESS_INPUT_INVALID"
    else:
        raise AssertionError("mismatched case revision must be rejected")


def test_same_sku_and_store_but_different_case_evidence_is_rejected():
    case = _case()
    _, proposal, reconciliation = _assess(case=case)
    wrong_case = replace(case, case_id="case_test_0002")

    try:
        FifoCostTransitionReadinessService().assess(
            case=wrong_case, proposal=proposal, supply_reconciliation=reconciliation,
        )
    except ValueError as exc:
        assert str(exc) == "FIFO_READINESS_INPUT_INVALID"
    else:
        raise AssertionError("evidence from another case must be rejected")


def test_repeated_assessment_is_deterministic():
    first, _, _ = _assess()
    second, _, _ = _assess()

    assert first == second
    assert first.requirements == tuple(sorted(first.requirements, key=lambda item: item.code))


def test_fbs_overlap_conflict_stays_visible_and_blocks_application():
    result, _, _ = _assess(stock=_stock_report(overlap=False))
    item = _by_code(result)["STOCK_RESERVED_OR_OVERLAP_UNKNOWN"]

    assert result.status == "CONFLICT"
    assert item.status == "CONFLICT"
    assert item.known_values["unresolved_snapshots"][0]["fbs_return_is_subset_of_available"] is False


def test_no_saved_report_requests_exact_documents_without_claiming_coverage():
    case = _case()
    reconciliation = _reconcile(stock=(), declaration=False, observation=False)
    proposal = FifoCostTransitionOpeningProposalService().propose(
        case=case,
        fifo_initialized=False,
        owner_confirmed_cutoff_date="2026-11-07",
        stock_reports=(),
        turnover_reports=(),
        supply_reconciliation=reconciliation,
    )
    result = FifoCostTransitionReadinessService().assess(
        case=case, proposal=proposal, supply_reconciliation=reconciliation,
    )
    items = _by_code(result)

    assert "TURNOVER_REPORT_REQUIRED" in items
    assert "STOCK_RESERVED_OR_OVERLAP_UNKNOWN" in items
    assert "SUPPLY_MANIFEST_INCOMPLETE" in items
    assert result.source_data_through is None
    assert result.complete_through is None
