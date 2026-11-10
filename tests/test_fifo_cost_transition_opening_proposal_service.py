from services.fifo_cost_transition_contracts import (
    CostInputMode,
    EvidenceCompleteness,
    EvidenceSourceKind,
    EvidencePresence,
    NormalizedSupplyStatus,
    PeriodProvenance,
    ReportEvidence,
    ReportType,
    ScopeIdentity,
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
from services.fifo_cost_transition_opening_proposal_service import (
    FifoCostTransitionOpeningProposalService,
)
from services.fifo_cost_transition_supply_reconciliation_service import (
    FifoCostTransitionSupplyReconciliationService,
)


SCOPE = ScopeIdentity(
    "owner-test", "store-test", "1000000001", product_id="101", offer_id="test-a",
)
CASE_ID = "case_test_0001"


def _metadata(kind, *, scope=SCOPE, completeness=EvidenceCompleteness.COMPLETE, marker="m"):
    return TransitionMetadata(
        scope=scope,
        source_kind=kind,
        completeness=completeness,
        source_fingerprint=source_fingerprint(marker),
    )


def _case(*, state=TransitionState.AWAITING_EVIDENCE):
    unknown = {
        "new_home_quantity": UnknownValue(
            TransitionReasonCode.SOURCE_PROOF_UNAVAILABLE,
            EvidenceSourceKind.OWNER_INPUT,
        ),
    }
    return TransitionCase(
        metadata=_metadata(EvidenceSourceKind.OWNER_INPUT, completeness=EvidenceCompleteness.PARTIAL),
        case_id=CASE_ID,
        case_revision=3,
        state=state,
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


def _stock_report(*, day="2026-11-07", provenance=PeriodProvenance.OWNER_CONFIRMED, scope=SCOPE):
    return ReportEvidence(
        metadata=_metadata(EvidenceSourceKind.OWNER_IMPORTED, scope=scope, marker=f"stock-{day}"),
        report_type=ReportType.STOCK_MANAGEMENT,
        period_from=day,
        period_to=day,
        period_provenance=provenance,
        captured_at=f"{day}T18:00:00Z",
        file_sha256=source_fingerprint(f"stock-file-{day}-{provenance.value}-{scope.store_id}"),
        parser_version="stock-test-v1",
        cell_references=("M5", "N5", "V5", "W5"),
        normalized_fields={
            "stock_buckets": {
                "available": 1191,
                "reserved": None,
                "preparing": 18,
                "checking": 5,
                "supplier_planned": 600,
                "supplier_transit": 6234,
                "buyer_delivery": 1689,
                "buyer_return_transit": 43,
                "removed_from_sale": 41,
            },
            "fbs_return_available_units": 9,
            "fbs_return_is_subset_of_available": True,
            "warehouse_control": {"status": "MATCH"},
        },
    )


def _turnover_report(
    *, period_provenance=PeriodProvenance.FILENAME_CANDIDATE,
    completeness=EvidenceCompleteness.COMPLETE,
    period_from="2026-11-04", period_to="2026-11-05",
    balance_difference=0, scope=SCOPE,
):
    return ReportEvidence(
        metadata=_metadata(EvidenceSourceKind.OWNER_IMPORTED, scope=scope, completeness=completeness, marker=f"turnover-{period_to}"),
        report_type=ReportType.TURNOVER,
        period_from=period_from,
        period_to=period_to,
        period_provenance=period_provenance,
        captured_at="2026-11-08T12:00:00Z",
        file_sha256=source_fingerprint(f"turnover-file-{period_to}-{scope.store_id}"),
        parser_version="turnover-test-v1",
        cell_references=("AJ4", "T4", "V4", "AM4", "AN4"),
        normalized_fields={
            "opening_total": 4492,
            "receipts_total": 0,
            "expenses_total": 780,
            "redeemed_units": 775,
            "non_sale_expense_units": 5,
            "withdrawal_units": 5,
            "closing_total": 3712,
            "closing_buckets": {
                "buyer_delivery": 1646,
                "buyer_return_transit": 70,
            },
            "reported_balance_difference": balance_difference,
            "computed_balance_difference": balance_difference,
            "balance_status": "BALANCED" if balance_difference == 0 else "DISCREPANCY",
        },
    )


def _supply_declaration():
    return SupplyDeclaration(
        metadata=_metadata(EvidenceSourceKind.OWNER_INPUT, completeness=EvidenceCompleteness.COMPLETE, marker="decl-148"),
        case_id=CASE_ID,
        declaration_id="declaration-148",
        revision=1,
        reference_kind=SupplyReferenceKind.SUPPLY,
        reference_digest="a" * 64,
        encrypted_lookup_reference="gAAAA" + "A" * 90,
        declared_shipped_units=148,
        dispatch_date="2026-11-05",
        provenance=EvidenceSourceKind.OWNER_INPUT,
    )


def _supply_observation():
    return SupplyObservation(
        metadata=_metadata(EvidenceSourceKind.OZON_API, marker="obs-148"),
        declaration_id="declaration-148",
        captured_at="2026-11-08T12:00:00Z",
        source_as_of="2026-11-08T11:59:00Z",
        raw_status="RECEIVING",
        normalized_status=NormalizedSupplyStatus.RECEIVING,
        declared_quantity=148,
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


def _supply_reconciliation(stock_reports=(), declarations=None, observations=None):
    return FifoCostTransitionSupplyReconciliationService().reconcile(
        scope=SCOPE,
        case_id=CASE_ID,
        owner_declared_total=6982,
        declarations=tuple(declarations or ()),
        observations=tuple(observations or ()),
        stock_reports=tuple(stock_reports),
    )


def _propose(*, stock=None, turnover=None, cutoff="2026-11-07", initialized=False,
             case=None, composition=None):
    stock_rows = (stock,) if stock is not None else (_stock_report(),)
    turnover_rows = (turnover,) if turnover is not None else (_turnover_report(),)
    return FifoCostTransitionOpeningProposalService().propose(
        case=case or _case(),
        fifo_initialized=initialized,
        owner_confirmed_cutoff_date=cutoff,
        confirmed_opening_composition=composition,
        stock_reports=stock_rows,
        turnover_reports=turnover_rows,
        supply_reconciliation=_supply_reconciliation(
            stock_rows, declarations=(_supply_declaration(),),
            observations=(_supply_observation(),),
        ),
    )


def test_confirmed_opening_composition_resolves_only_the_bound_reserved_unknown():
    stock = _stock_report()
    composition = {
        "confirmed": True,
        "case_id": CASE_ID,
        "scope": {
            "owner_id": SCOPE.owner_id,
            "store_id": SCOPE.store_id,
            "product_id": SCOPE.product_id,
            "offer_id": SCOPE.offer_id,
            "sku": SCOPE.sku,
        },
        "opening_date": "2026-11-07",
        "stock_report_fingerprint": stock.file_sha256,
        "composition_fingerprint": "a" * 64,
        "owner_confirmed_total_ozon_units": 1200,
        "owner_confirmed_reserved_units": 9,
        "layers": ({"ozon_units": 1200},),
    }

    proposal = _propose(stock=stock, composition=composition)
    resolved = proposal.stock_snapshots[0]

    assert resolved.stock_buckets["reserved"] == 9
    assert resolved.owner_confirmed_reserved_units == 9
    assert resolved.owner_confirmed_total_ozon_units == 1200
    assert resolved.opening_composition_fingerprint == "a" * 64
    assert resolved.opening_composition_report_fingerprint == stock.file_sha256
    assert resolved.opening_composition_date == "2026-11-07"
    assert "RESERVED_BUCKET_UNKNOWN" not in proposal.requirements
    assert stock.normalized_fields["stock_buckets"]["reserved"] is None

    unconfirmed = _propose(stock=stock)
    assert unconfirmed.stock_snapshots[0].stock_buckets["reserved"] is None
    assert "RESERVED_BUCKET_UNKNOWN" in unconfirmed.requirements

    stale = _propose(
        stock=stock,
        composition={**composition, "stock_report_fingerprint": "b" * 64},
    )
    assert stale.stock_snapshots[0].stock_buckets["reserved"] is None
    assert "RESERVED_BUCKET_UNKNOWN" in stale.requirements


def test_control_numbers_are_separate_review_evidence_not_fifo_opening():
    case = _case()
    proposal = _propose()

    assert proposal.status == "REVIEW_ONLY"
    assert proposal.preview_only is True
    assert proposal.ready_to_apply is False
    assert proposal.fifo_opening_units is None
    assert proposal.is_atomic_snapshot is False
    assert case.state is TransitionState.AWAITING_EVIDENCE
    assert proposal.old_home_units == 0
    assert proposal.old_transit_units == 0
    assert proposal.new_home_units is None
    assert proposal.owner_declared_shipped_total == 6982
    assert proposal.owner_unassigned_shipped_units == 6834
    assert len(proposal.supply_declarations) == 1
    assert proposal.supply_declarations[0].declared_quantity == 148
    assert proposal.supply_declarations[0].observed_status is NormalizedSupplyStatus.RECEIVING
    assert proposal.supply_declarations[0].accepted_quantity is None
    assert proposal.supply_declarations[0].pending_quantity is None
    stock = proposal.stock_snapshots[0]
    assert stock.stock_buckets["available"] == 1191
    assert stock.fbs_return_available_units == 9
    assert stock.fbs_return_is_subset_of_available is True
    assert stock.stock_buckets["supplier_planned"] == 600
    assert stock.stock_buckets["supplier_transit"] == 6234
    assert stock.eligible_as_cutoff_snapshot is True
    turnover = proposal.turnover_controls[0]
    assert turnover.opening_total == 4492
    assert turnover.receipts_total == 0
    assert turnover.expenses_total == 780
    assert turnover.closing_total == 3712
    assert turnover.redeemed_units == 775
    assert turnover.non_sale_expense_units == 5
    assert turnover.withdrawal_units == 5
    assert turnover.closing_buyer_delivery_units == 1646
    assert turnover.closing_buyer_return_transit_units == 70
    assert turnover.reported_control_difference == 0
    assert turnover.computed_control_difference == 0
    assert proposal.turnover_coverage_gap is None
    assert proposal.turnover_candidate_gap == ("2026-11-06", "2026-11-07")
    assert "SALE_CUTOFF_BRIDGE_REQUIRED" in proposal.requirements
    assert "PHYSICAL_FIFO_OPENING_NOT_PROVEN" in proposal.requirements


def test_filename_candidate_date_is_not_accepted_as_cutoff_or_stock_proof():
    proposal = _propose(stock=_stock_report(provenance=PeriodProvenance.FILENAME_CANDIDATE))

    assert proposal.confirmed_cutoff_date == "2026-11-07"
    assert proposal.stock_snapshots[0].eligible_as_cutoff_snapshot is False
    assert "OWNER_CONFIRMED_STOCK_SNAPSHOT_FOR_CUTOFF_REQUIRED" in proposal.requirements


def test_missing_owner_cutoff_is_not_inferred_from_report_date():
    proposal = _propose(cutoff=None)

    assert proposal.confirmed_cutoff_date is None
    assert proposal.stock_snapshots[0].eligible_as_cutoff_snapshot is False
    assert "OWNER_CUTOFF_DATE_REQUIRED" in proposal.requirements


def test_invalid_owner_cutoff_blocks_proposal_instead_of_falling_back_to_report_date():
    proposal = _propose(cutoff="07.11.2026")

    assert proposal.status == "BLOCKED"
    assert proposal.confirmed_cutoff_date is None
    assert proposal.stock_snapshots[0].eligible_as_cutoff_snapshot is False
    assert "OWNER_CUTOFF_DATE_INVALID" in proposal.issue_codes


def test_existing_fifo_queue_blocks_opening_proposal():
    proposal = _propose(initialized=True)

    assert proposal.status == "BLOCKED"
    assert proposal.fifo_opening_units is None
    assert proposal.ready_to_apply is False
    assert "FIFO_ALREADY_INITIALIZED" in proposal.issue_codes


def test_cutoff_period_gap_is_explicit_and_buyer_delivery_is_separate():
    turnover = _turnover_report(
        period_provenance=PeriodProvenance.OWNER_CONFIRMED,
    )
    proposal = _propose(turnover=turnover)

    assert proposal.turnover_coverage_gap == ("2026-11-06", "2026-11-07")
    assert proposal.turnover_candidate_gap is None
    assert proposal.turnover_controls[0].closing_total == 3712
    assert proposal.turnover_controls[0].closing_buyer_delivery_units == 1646
    assert proposal.turnover_controls[0].closing_buyer_return_transit_units == 70
    assert "CUSTOMER_DELIVERY_OR_RETURN_NOT_FIFO_OPENING" in proposal.requirements
    assert "TURNOVER_COVERAGE_GAP" in proposal.requirements


def test_incomplete_turnover_keeps_unknown_values_and_signed_difference():
    turnover = _turnover_report(
        completeness=EvidenceCompleteness.PARTIAL,
        balance_difference=-3,
    )
    fields = dict(turnover.normalized_fields)
    fields["opening_total"] = None
    partial = ReportEvidence(
        metadata=turnover.metadata,
        report_type=turnover.report_type,
        period_from=turnover.period_from,
        period_to=turnover.period_to,
        period_provenance=turnover.period_provenance,
        captured_at=turnover.captured_at,
        file_sha256=turnover.file_sha256,
        parser_version=turnover.parser_version,
        cell_references=turnover.cell_references,
        normalized_fields=fields,
    )
    proposal = _propose(turnover=partial)

    assert proposal.turnover_controls[0].opening_total is None
    assert proposal.turnover_controls[0].computed_control_difference == -3
    assert "TURNOVER_REPORT_PARTIAL" in proposal.requirements
    assert "TURNOVER_BALANCE_CONTROL_FAILED" in proposal.requirements


def test_other_store_report_is_excluded_and_proposal_is_blocked():
    other_scope = ScopeIdentity(
        "owner-test", "other-store", "1000000001", product_id="101", offer_id="test-a",
    )
    proposal = _propose(stock=_stock_report(scope=other_scope))

    assert proposal.status == "BLOCKED"
    assert proposal.stock_snapshots == ()
    assert "STOCK_REPORT_SCOPE_MISMATCH" in proposal.issue_codes


def test_two_stock_reports_remain_two_snapshots_and_are_not_summed():
    first = _stock_report(day="2026-11-06")
    second = _stock_report(day="2026-11-07")
    reports = (first, second)
    reconciliation = _supply_reconciliation(reports)
    proposal = FifoCostTransitionOpeningProposalService().propose(
        case=_case(),
        fifo_initialized=False,
        owner_confirmed_cutoff_date="2026-11-07",
        stock_reports=reports,
        turnover_reports=(_turnover_report(),),
        supply_reconciliation=reconciliation,
    )

    assert len(proposal.stock_snapshots) == 2
    assert [row.stock_buckets["available"] for row in proposal.stock_snapshots] == [1191, 1191]
    assert [row.eligible_as_cutoff_snapshot for row in proposal.stock_snapshots] == [False, True]
    assert not hasattr(proposal, "available_units_total")
