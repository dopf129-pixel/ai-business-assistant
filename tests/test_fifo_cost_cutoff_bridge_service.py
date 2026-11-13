from dataclasses import replace
from decimal import Decimal

import pytest

from services.fifo_cost_cutoff_bridge_service import (
    FifoCostCutoffBridgeService,
    FifoCutoffBridgeDocumentParser,
    FifoCutoffBridgeSourceAdapter,
    FifoCutoffMovementCoverage,
    FifoPhysicalSaleDocumentConfirmation,
)
from services.fifo_cost_transition_contracts import (
    CostInputMode,
    EvidenceCompleteness,
    EvidenceSourceKind,
    PeriodProvenance,
    ReportEvidence,
    ReportType,
    ScopeIdentity,
    SourceProof,
    StockBucket,
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
from services.fifo_cost_transition_activation_proposal_service import (
    FifoCostTransitionActivationProposalService,
)
from services.fifo_cost_transition_readiness_service import (
    FifoCostTransitionReadinessService,
)


SCOPE = ScopeIdentity(
    "owner-test", "store-test", "1000000001", product_id="101", offer_id="offer-a",
)
CASE_ID = "case_bridge_01"
CUTOFF = "2026-11-07"
COMPLETE_THROUGH = "2026-11-08"


def _metadata(kind, marker, *, scope=SCOPE):
    return TransitionMetadata(
        scope=scope,
        source_kind=kind,
        completeness=EvidenceCompleteness.COMPLETE,
        source_fingerprint=source_fingerprint(marker),
    )


def _case():
    return TransitionCase(
        metadata=_metadata(EvidenceSourceKind.OWNER_INPUT, "case", scope=SCOPE),
        case_id=CASE_ID,
        case_revision=2,
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
        unknown_values={
            "new_home_quantity": UnknownValue(
                TransitionReasonCode.SOURCE_PROOF_UNAVAILABLE,
                EvidenceSourceKind.OWNER_INPUT,
            ),
        },
    )


def _stock_report(*, cutoff=CUTOFF, scope=SCOPE):
    buckets = {bucket.value: 0 for bucket in StockBucket}
    buckets.update({"available": 1191, "reserved": 0, "supplier_transit": 0})
    return ReportEvidence(
        metadata=_metadata(EvidenceSourceKind.OWNER_IMPORTED, "stock", scope=scope),
        report_type=ReportType.STOCK_MANAGEMENT,
        period_from=cutoff,
        period_to=cutoff,
        period_provenance=PeriodProvenance.OWNER_CONFIRMED,
        captured_at="2026-11-08T10:00:00Z",
        file_sha256=source_fingerprint("stock-file"),
        parser_version="stock-test-v1",
        cell_references=("M5", "N5"),
        normalized_fields={
            "stock_buckets": buckets,
            "fbs_return_available_units": 0,
            "fbs_return_is_subset_of_available": True,
        },
    )


def _proposal(*, case=None, stock=None, cutoff=CUTOFF, composition=None):
    case = case or _case()
    stock = stock or _stock_report(cutoff=cutoff)
    return FifoCostTransitionOpeningProposalService().propose(
        case=case,
        fifo_initialized=False,
        owner_confirmed_cutoff_date=cutoff,
        confirmed_opening_composition=composition,
        stock_reports=(stock,),
        turnover_reports=(),
        supply_reconciliation=None,
    )


def _finance_batch(*, response=None, scope=SCOPE, complete=True, period_to=COMPLETE_THROUGH):
    metadata = _metadata(EvidenceSourceKind.OZON_API, "finance-proof", scope=scope)
    proof = SourceProof(
        metadata=metadata,
        scope_complete=complete,
        pagination_complete=complete,
        source_as_of="2026-11-08T09:00:00Z",
    )
    response = response or {"error": False, "rows": [
        {"order": {"posting_number": "posting-before"}, "item": {
            "sku": scope.sku, "offer_id": scope.offer_id, "product_id": scope.product_id,
            "quantity": 999, "accrual_date": "2099-01-01",
        }},
        {"order": {"posting_number": "posting-after"}, "item": {
            "sku": scope.sku, "offer_id": scope.offer_id, "product_id": scope.product_id,
        }},
    ]}
    return FifoCutoffBridgeSourceAdapter().parse_realization_postings(
        response=response,
        scope=scope,
        proof=proof,
        period_from="2026-11-05",
        period_to=period_to,
        source_as_of=proof.source_as_of,
    )


def _document_payload(*, rows=None, period_to=COMPLETE_THROUGH, marker="owner-document"):
    rows = rows or [
        {
            "posting_number": "posting-before", "finance_sku": SCOPE.sku,
            "quantity": 2, "physical_effective_date": "2026-11-06",
            "row_reference": "A17",
        },
        {
            "posting_number": "posting-after", "finance_sku": SCOPE.sku,
            "quantity": 3, "physical_effective_date": "2026-11-08",
            "row_reference": "A18",
        },
    ]
    return {
        "document_kind": "OWNER_DOCUMENTED_PHYSICAL_SALES_V1",
        "document_fingerprint": source_fingerprint(marker),
        "parser_version": "fifo-owner-physical-sales-v1",
        "period_from": "2026-11-05",
        "period_to": period_to,
        "rows": rows,
    }


def _document(*, payload=None, case_id=CASE_ID, scope=SCOPE):
    return FifoCutoffBridgeDocumentParser().parse(
        payload=payload or _document_payload(), scope=scope, case_id=case_id,
    )


def _confirmation(document, *, scope=SCOPE, case_id=CASE_ID, refs=None):
    return FifoPhysicalSaleDocumentConfirmation(
        metadata=_metadata(
            EvidenceSourceKind.OWNER_INPUT,
            f"confirmation-{document.document_fingerprint}-{refs}",
            scope=scope,
        ),
        owner_id=scope.owner_id,
        case_id=case_id,
        document_fingerprint=document.document_fingerprint,
        confirmed_row_references=tuple(refs or [row.row_reference for row in document.rows]),
        confirmed_fields=frozenset({
            "posting_number", "finance_sku", "quantity", "physical_effective_date",
        }),
        physical_date_semantics="PHYSICAL_OUTFLOW",
        physical_date_timezone="Europe/Moscow",
        physical_date_precision="STORE_LOCAL_DATE",
        confirmed_at="2026-11-08T12:00:00Z",
    )


def _movement_coverage(
    *, scope=SCOPE, complete=True, movements=(), complete_through=COMPLETE_THROUGH,
):
    metadata = _metadata(EvidenceSourceKind.OZON_API, "movement-proof", scope=scope)
    proof = SourceProof(
        metadata=metadata,
        scope_complete=complete,
        pagination_complete=complete,
        source_as_of="2026-11-08T09:30:00Z",
    )
    return FifoCutoffMovementCoverage(
        scope=scope,
        period_from="2026-11-05",
        complete_through=complete_through,
        source_fingerprint=metadata.source_fingerprint,
        proof=proof,
        movements=tuple(movements),
    )


def _build(**overrides):
    case = overrides.pop("case", None) or _case()
    stock = overrides.pop("stock_evidence", None) or _stock_report()
    proposal = overrides.pop("proposal", None) or _proposal(case=case, stock=stock)
    payload = overrides.pop("physical_sale_document", None)
    document = payload if payload is not None else _document()
    inputs = {
        "case": case,
        "proposal": proposal,
        "stock_evidence": stock,
        "finance_batch": _finance_batch(),
        "physical_sale_document": document,
        "owner_confirmation": _confirmation(document),
        "movement_coverage": _movement_coverage(),
        "requested_complete_through": COMPLETE_THROUGH,
    }
    inputs.update(overrides)
    return FifoCostCutoffBridgeService().build(**inputs)


def test_fl18_exact_document_and_complete_finance_identity_builds_physical_cutoff_bridge():
    result = _build()

    assert result.status == "READY"
    assert result.ready_for_fifo_event is True
    assert result.preview_only is True
    assert result.cutoff_date == CUTOFF
    assert result.cutoff_timezone == "Europe/Moscow"
    assert result.cutoff_precision == "STORE_LOCAL_DATE"
    assert result.cutoff_boundary == "END_OF_LOCAL_DATE"
    assert result.complete_through == COMPLETE_THROUGH
    assert [(item.quantity, item.physical_effective_date) for item in result.pre_cutoff_outflows] == [
        (2, "2026-11-06"),
    ]
    assert [(item.quantity, item.physical_effective_date) for item in result.post_cutoff_events] == [
        (3, "2026-11-08"),
    ]
    assert len(result.finance_to_sale_identity_mappings) == 2
    assert result.unresolved_issues == ()
    assert "posting-before" not in repr(result)
    assert "posting-after" not in repr(result)


def test_fl18_financial_accrual_date_and_unrelated_quantity_are_not_used_as_physical_facts():
    result = _build()

    all_events = (*result.pre_cutoff_outflows, *result.post_cutoff_events)
    assert [item.quantity for item in all_events] == [2, 3]
    assert "2099-01-01" not in repr(result)


def test_fl18_repeated_finance_identity_rows_do_not_create_a_second_physical_sale():
    response = {"error": False, "rows": [
        {"order": {"posting_number": "posting-before"}, "item": {
            "sku": SCOPE.sku, "offer_id": SCOPE.offer_id, "product_id": SCOPE.product_id,
        }},
        {"order": {"posting_number": "posting-before"}, "item": {
            "sku": SCOPE.sku, "offer_id": SCOPE.offer_id, "product_id": SCOPE.product_id,
            "accrual_id": "duplicate-finance-line",
        }},
        {"order": {"posting_number": "posting-after"}, "item": {
            "sku": SCOPE.sku, "offer_id": SCOPE.offer_id, "product_id": SCOPE.product_id,
        }},
    ]}

    result = _build(finance_batch=_finance_batch(response=response))

    assert result.status == "READY"
    assert len(result.pre_cutoff_outflows) + len(result.post_cutoff_events) == 2
    assert sum(item.quantity for item in result.pre_cutoff_outflows) == 2


@pytest.mark.parametrize("change,expected", [
    (lambda batch: replace(batch, proof=replace(batch.proof, pagination_complete=False)),
     "FINANCE_IDENTITY_COVERAGE_INCOMPLETE"),
    (lambda batch: replace(batch, period_to="2026-11-07"), "FINANCE_IDENTITY_END_GAP"),
])
def test_fl18_incomplete_finance_coverage_blocks_event_and_watermark(change, expected):
    batch = change(_finance_batch())
    result = _build(finance_batch=batch)

    assert result.status == "SOURCE_BLOCKED"
    assert expected in result.unresolved_issues
    assert result.complete_through is None
    assert result.pre_cutoff_outflows == result.post_cutoff_events == ()


def test_fl18_incomplete_page_does_not_parse_as_complete_source():
    metadata = _metadata(EvidenceSourceKind.OZON_API, "partial-page")
    proof = SourceProof(metadata, scope_complete=True, pagination_complete=False)
    with pytest.raises(ValueError, match="FIFO_CUTOFF_BRIDGE_COVERAGE_INCOMPLETE"):
        FifoCutoffBridgeSourceAdapter().parse_realization_postings(
            response={"error": False, "rows": []}, scope=SCOPE, proof=proof,
            period_from="2026-11-05", period_to=COMPLETE_THROUGH,
        )


def test_fl18_owner_document_event_after_requested_coverage_does_not_extend_watermark():
    payload = _document_payload(rows=[
        {
            "posting_number": "posting-before", "finance_sku": SCOPE.sku,
            "quantity": 2, "physical_effective_date": "2026-11-06", "row_reference": "A17",
        },
        {
            "posting_number": "posting-after", "finance_sku": SCOPE.sku,
            "quantity": 3, "physical_effective_date": "2026-11-09", "row_reference": "A18",
        },
    ])
    document = _document(payload=payload)
    result = _build(physical_sale_document=document, owner_confirmation=_confirmation(document))

    assert result.status == "SOURCE_BLOCKED"
    assert "PHYSICAL_SALE_DOCUMENT_DATE_OUTSIDE_COVERAGE" in result.unresolved_issues
    assert result.complete_through is None


def test_fl18_missing_owner_confirmation_keeps_sale_date_unproven():
    document = _document()
    confirmation = replace(
        _confirmation(document), confirmed_row_references=("A17",),
    )
    result = _build(owner_confirmation=confirmation)

    assert result.status == "SOURCE_BLOCKED"
    assert "OWNER_PHYSICAL_DATE_CONFIRMATION_REQUIRED" in result.unresolved_issues
    assert result.complete_through is None


def test_fl18_wrong_store_case_sku_and_report_scope_fail_closed():
    foreign_scope = ScopeIdentity(
        "owner-test", "other-store", SCOPE.sku, product_id=SCOPE.product_id,
        offer_id=SCOPE.offer_id,
    )
    doc = _document(scope=foreign_scope)
    result = _build(physical_sale_document=doc)

    assert result.status == "SOURCE_BLOCKED"
    assert "PHYSICAL_SALE_DOCUMENT_SCOPE_UNPROVEN" in result.unresolved_issues

    wrong_stock = _stock_report(scope=foreign_scope)
    result = _build(stock_evidence=wrong_stock)
    assert "STOCK_SCOPE_OR_CUTOFF_UNPROVEN" in result.unresolved_issues


def test_fl18_stock_buckets_must_be_complete_known_and_bound_to_cutoff_proposal():
    stock = _stock_report()
    fields = dict(stock.normalized_fields)
    buckets = dict(fields["stock_buckets"])
    buckets[StockBucket.RESERVED.value] = None
    fields["stock_buckets"] = buckets
    stock_unknown = replace(stock, normalized_fields=fields)
    result = _build(stock_evidence=stock_unknown)

    assert result.status == "SOURCE_BLOCKED"
    assert "STOCK_BUCKET_UNKNOWN" in result.unresolved_issues

    wrong_proposal = replace(_proposal(), case_revision=99)
    result = _build(proposal=wrong_proposal)
    assert "OWNER_CONFIRMED_CUTOFF_OR_CASE_PROPOSAL_MISSING" in result.unresolved_issues


def test_fr27_owner_confirmed_composition_resolves_reserved_in_actual_cutoff_bridge():
    stock = _stock_report()
    fields = dict(stock.normalized_fields)
    buckets = dict(fields["stock_buckets"])
    buckets[StockBucket.RESERVED.value] = None
    fields["stock_buckets"] = buckets
    stock_unknown = replace(stock, normalized_fields=fields)
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
        "opening_date": CUTOFF,
        "stock_report_fingerprint": stock_unknown.file_sha256,
        "composition_fingerprint": "c" * 64,
        "owner_confirmed_total_ozon_units": 1200,
        "owner_confirmed_reserved_units": 9,
        "unknown_new_home_quantity": True,
        "new_home_quantity": None,
        "new_party_transit_units": 0,
        "layers": ({
            "ozon_units": 1200, "transit_units": 0, "home_units": 0,
        },),
    }
    proposal = _proposal(
        stock=stock_unknown, composition=composition,
    )

    result = _build(stock_evidence=stock_unknown, proposal=proposal)

    assert result.status == "READY"
    assert result.confirmed_stock_buckets["available"] == 1191
    assert result.confirmed_stock_buckets["reserved"] == 9
    assert "STOCK_BUCKET_UNKNOWN" not in result.unresolved_issues
    assert stock_unknown.normalized_fields["stock_buckets"]["reserved"] is None


def test_fl18_existing_stock_parser_partial_buckets_are_preserved_as_specific_unknowns():
    report = _stock_report()
    fields = dict(report.normalized_fields)
    fields["stock_buckets"] = {
        "available": 1191,
        "preparing": 18,
        "checking": 5,
        "supplier_planned": 600,
        "supplier_transit": 6234,
        "buyer_delivery": 1689,
        "buyer_return_transit": 43,
        "internal_transfer": 0,
        "removed_from_sale": 41,
        "reserved": None,
        "marking_pending_withdrawal": 0,
        "marking_pending_documents": 0,
        "expiring": 0,
        "defective_supply": 0,
        "defective_stock": 0,
        "unidentified_supply_surplus": 0,
        "seller_withdrawal_preparing": 0,
        "seller_withdrawal_ready": 0,
        "seller_return_transit": 0,
    }
    partial = replace(
        report,
        metadata=replace(report.metadata, completeness=EvidenceCompleteness.PARTIAL),
        normalized_fields=fields,
    )
    result = _build(stock_evidence=partial, proposal=_proposal(stock=partial))

    assert result.status == "SOURCE_BLOCKED"
    assert "STOCK_REPORT_PARTIAL" in result.unresolved_issues
    assert "STOCK_BUCKET_UNKNOWN" in result.unresolved_issues
    assert result.confirmed_stock_buckets["available"] == 1191
    assert result.confirmed_stock_buckets["reserved"] is None
    assert "STOCK_SCOPE_OR_CUTOFF_UNPROVEN" not in result.unresolved_issues


def test_fl18_finance_and_owner_document_identity_sets_must_match_exactly():
    payload = _document_payload(rows=[{
        "posting_number": "unknown-posting", "finance_sku": SCOPE.sku,
        "quantity": 1, "physical_effective_date": "2026-11-06",
        "row_reference": "A19",
    }])
    document = _document(payload=payload)
    result = _build(
        physical_sale_document=document,
        owner_confirmation=_confirmation(document),
    )

    assert result.status == "SOURCE_BLOCKED"
    assert "DOCUMENT_TO_FINANCE_IDENTITY_MISMATCH" in result.unresolved_issues
    assert result.complete_through is None


def test_fl18_duplicate_document_identity_and_unrelated_sku_are_not_double_counted():
    duplicate_payload = _document_payload(rows=[
        {
            "posting_number": "posting-before", "finance_sku": SCOPE.sku,
            "quantity": 2, "physical_effective_date": "2026-11-06", "row_reference": "A17",
        },
        {
            "posting_number": "posting-before", "finance_sku": SCOPE.sku,
            "quantity": 2, "physical_effective_date": "2026-11-06", "row_reference": "A18",
        },
    ])
    document = _document(payload=duplicate_payload)
    result = _build(physical_sale_document=document, owner_confirmation=_confirmation(document))
    assert result.status == "SOURCE_BLOCKED"
    assert "DOCUMENT_TO_FINANCE_IDENTITY_DUPLICATE" in result.unresolved_issues


def test_fl21_confirmed_non_sale_movement_is_preserved_by_the_cutoff_bridge():
    from services.fifo_cost_cutoff_bridge_service import FifoCutoffMovementReference

    movement = FifoCutoffMovementReference(
        movement_kind="SELLER_WITHDRAWAL",
        movement_fingerprint=source_fingerprint("withdrawal"),
        source_identity_digest=source_fingerprint("withdrawal-id"),
        linked_sale_identity_digest=None,
        quantity=1,
        effective_date="2026-11-08",
    )
    result = _build(movement_coverage=_movement_coverage(movements=(movement,)))

    assert result.status == "READY"
    assert result.ready_for_fifo_event is True
    assert result.linked_returns_non_sale_movements == (movement,)


def test_fl21_return_must_link_to_a_later_sale_persisted_by_the_same_bridge():
    from services.fifo_cost_cutoff_bridge_service import FifoCutoffMovementReference

    base = _build()
    sale_digest = base.post_cutoff_events[0].source_identity_digest
    movement = FifoCutoffMovementReference(
        movement_kind="RETURN",
        movement_fingerprint=source_fingerprint("return-after-sale"),
        source_identity_digest=source_fingerprint("return-after-sale-id"),
        linked_sale_identity_digest=sale_digest,
        quantity=1,
        effective_date="2026-11-09",
    )
    payload = _document_payload(
        period_to="2026-11-09", marker="owner-document-through-09",
    )
    document = _document(payload=payload)
    result = _build(
        finance_batch=_finance_batch(period_to="2026-11-09"),
        physical_sale_document=document,
        owner_confirmation=_confirmation(document),
        movement_coverage=_movement_coverage(
            movements=(movement,), complete_through="2026-11-09",
        ),
        requested_complete_through="2026-11-09",
    )

    assert result.status == "READY"
    assert result.linked_returns_non_sale_movements == (movement,)


def test_fl21_return_to_pre_cutoff_sale_stays_blocked_without_reconstructible_basis():
    from services.fifo_cost_cutoff_bridge_service import FifoCutoffMovementReference

    base = _build()
    movement = FifoCutoffMovementReference(
        movement_kind="RETURN",
        movement_fingerprint=source_fingerprint("return-old-sale"),
        source_identity_digest=source_fingerprint("return-old-sale-id"),
        linked_sale_identity_digest=base.pre_cutoff_outflows[0].source_identity_digest,
        quantity=1,
        effective_date="2026-11-08",
    )
    result = _build(movement_coverage=_movement_coverage(movements=(movement,)))

    assert result.status == "SOURCE_BLOCKED"
    assert "FIFO_RETURN_ORIGIN_SALE_NOT_IN_CUTOFF_BRIDGE" in result.unresolved_issues


def test_fl21_transfer_and_unlinked_return_remain_explicit_blockers():
    from services.fifo_cost_cutoff_bridge_service import FifoCutoffMovementReference

    for kind, linked, expected in (
        ("TRANSFER", None, "INVENTORY_TRANSFER_NORMALIZATION_UNAVAILABLE"),
        ("RETURN", None, "FIFO_RETURN_IDENTITY_UNCONFIRMED"),
    ):
        movement = FifoCutoffMovementReference(
            movement_kind=kind,
            movement_fingerprint=source_fingerprint(f"movement-{kind}"),
            source_identity_digest=source_fingerprint(f"movement-id-{kind}"),
            linked_sale_identity_digest=linked,
            quantity=1,
            effective_date="2026-11-08",
        )
        result = _build(movement_coverage=_movement_coverage(movements=(movement,)))
        assert result.status == "SOURCE_BLOCKED"
        assert expected in result.unresolved_issues


def test_fl18_cutoff_date_uses_owner_store_local_calendar_not_utc_timestamp():
    result = _build()

    assert result.cutoff_date == "2026-11-07"
    assert result.cutoff_timezone == "Europe/Moscow"
    assert result.cutoff_boundary == "END_OF_LOCAL_DATE"
    assert result.pre_cutoff_outflows[0].physical_effective_date == "2026-11-06"
    assert result.post_cutoff_events[0].physical_effective_date == "2026-11-08"


def test_fl18_unlinked_or_partial_return_source_blocks_complete_through():
    result = _build(movement_coverage=_movement_coverage(complete=False))

    assert result.status == "SOURCE_BLOCKED"
    assert "RETURN_NONSALE_COVERAGE_INCOMPLETE" in result.unresolved_issues
    assert result.complete_through is None


def test_fl19_unknown_new_home_keeps_new_rate_without_creating_unbounded_stock():
    case = _case()
    opening = _proposal(case=case)
    bridge = _build(case=case, proposal=opening)

    proposal = FifoCostTransitionActivationProposalService().propose(
        case=case, fifo_initialized=False,
        opening_proposal=opening, cutoff_bridge=bridge,
    )

    assert proposal.status == "REVIEW_ONLY"  # price proposal is allowed; opening/replay remain incomplete
    assert proposal.old_unit_cost_rub == Decimal("21.00")
    assert proposal.new_unit_cost_rub == Decimal("14.65")
    assert proposal.cost_components is None  # TOTAL_LANDED stays unbroken down
    assert proposal.old_home_units == proposal.old_transit_units == 0
    assert proposal.new_home_units is None
    assert proposal.owner_declared_shipped_units == 6982
    assert proposal.fifo_opening_units is None
    assert proposal.accepted_supply_units_added_to_snapshot == 0
    assert "NEW_HOME_QUANTITY_UNKNOWN" in proposal.requirements
    assert "FIFO_OPENING_QUANTITY_REQUIRES_REPLAY" in proposal.requirements
    assert "TURNOVER_REPORT_REQUIRED" in proposal.requirements
    assert proposal.ready_to_apply is False
    assert proposal.fifo_initialized is False
    assert proposal.preview_only is True


def test_fl19_review_candidate_preserves_buckets_and_never_adds_accepted_supply_twice():
    case = _case()
    stock = _stock_report()
    opening = _proposal(case=case, stock=stock)
    bridge = _build(case=case, proposal=opening, stock_evidence=stock)
    proposal = FifoCostTransitionActivationProposalService().propose(
        case=case, fifo_initialized=False,
        opening_proposal=opening, cutoff_bridge=bridge,
    )

    assert proposal.status == "REVIEW_ONLY"
    assert proposal.confirmed_stock_buckets == bridge.confirmed_stock_buckets
    assert proposal.owner_declared_shipped_units == 6982
    assert proposal.accepted_supply_units_added_to_snapshot == 0
    assert proposal.new_home_units is None
    assert proposal.fifo_opening_units is None
    assert proposal.ready_to_apply is False
    assert "FIFO_OPENING_QUANTITY_REQUIRES_REPLAY" in proposal.requirements
    assert "TURNOVER_REPORT_REQUIRED" in proposal.requirements


@pytest.mark.parametrize("change,expected", [
    (lambda proposal: replace(proposal, case_revision=99), "OPENING_PROPOSAL_CASE_SCOPE_MISMATCH"),
    (lambda proposal: replace(proposal, confirmed_cutoff_date="2026-11-06"), "OPENING_CUTOFF_MISMATCH"),
])
def test_fl19_stale_or_mismatched_opening_source_cannot_produce_review_ready(change, expected):
    case = _case()
    opening = change(_proposal(case=case))
    bridge = _build(case=case, proposal=_proposal(case=case))

    result = FifoCostTransitionActivationProposalService().propose(
        case=case, fifo_initialized=False,
        opening_proposal=opening, cutoff_bridge=bridge,
    )

    assert result.status == "SOURCE_BLOCKED"
    assert expected in result.requirements
    assert result.fifo_opening_units is None
    assert result.ready_to_apply is False


def test_fl19_existing_fifo_blocks_activation_and_keeps_candidate_rate_visible():
    case = _case()
    opening = _proposal(case=case)
    bridge = _build(case=case, proposal=opening)

    result = FifoCostTransitionActivationProposalService().propose(
        case=case, fifo_initialized=True,
        opening_proposal=opening, cutoff_bridge=bridge,
    )

    assert result.status == "SOURCE_BLOCKED"
    assert result.new_unit_cost_rub == Decimal("14.65")
    assert result.fifo_initialized is True
    assert "FIFO_ALREADY_INITIALIZED" in result.requirements
    assert result.ready_to_apply is False


def test_fl19_cross_store_proposal_is_blocked_without_exposing_foreign_stock_or_watermark():
    foreign_scope = ScopeIdentity(
        "owner-test", "other-store", SCOPE.sku,
        product_id=SCOPE.product_id, offer_id=SCOPE.offer_id,
    )
    foreign_case = replace(
        _case(),
        metadata=_metadata(EvidenceSourceKind.OWNER_INPUT, "foreign-case", scope=foreign_scope),
        case_id="case_bridge_02",
    )
    stock = _stock_report(scope=foreign_scope)
    opening = _proposal(case=foreign_case, stock=stock)
    document = _document(case_id=foreign_case.case_id, scope=foreign_scope)
    bridge = _build(
        case=foreign_case,
        proposal=opening,
        stock_evidence=stock,
        finance_batch=_finance_batch(scope=foreign_scope),
        physical_sale_document=document,
        owner_confirmation=_confirmation(
            document, scope=foreign_scope, case_id=foreign_case.case_id,
        ),
        movement_coverage=_movement_coverage(scope=foreign_scope),
    )

    result = FifoCostTransitionActivationProposalService().propose(
        case=_case(), fifo_initialized=False,
        opening_proposal=opening, cutoff_bridge=bridge,
    )

    assert result.status == "SOURCE_BLOCKED"
    assert "OPENING_PROPOSAL_CASE_SCOPE_MISMATCH" in result.requirements
    assert "CUTOFF_BRIDGE_CASE_SCOPE_MISMATCH" in result.requirements
    assert result.confirmed_stock_buckets == {}
    assert result.cutoff_date is None
    assert result.complete_through is None


def test_fl18_owner_document_parser_rejects_extra_fields_and_untrusted_date_basis():
    payload = _document_payload()
    payload["physical_date_source"] = "accrual_date"
    with pytest.raises(ValueError, match="FIFO_CUTOFF_BRIDGE_DOCUMENT_FORMAT_INVALID"):
        FifoCutoffBridgeDocumentParser().parse(payload=payload, scope=SCOPE, case_id=CASE_ID)

    document = _document()
    with pytest.raises(ValueError, match="FIFO_CUTOFF_BRIDGE_CONFIRMATION_INVALID"):
        replace(_confirmation(document), physical_date_semantics="FINANCIAL_ACCRUAL")


def test_fl18_readiness_accepts_only_current_case_revision_bridge_proof():
    case = _case()
    stock = _stock_report()
    proposal = _proposal(case=case, stock=stock)
    bridge = _build(case=case, stock_evidence=stock, proposal=proposal)
    readiness = FifoCostTransitionReadinessService().assess(
        case=case, proposal=proposal, supply_reconciliation=None,
        cutoff_bridge=bridge,
    )
    codes = {item.code for item in readiness.requirements}

    assert bridge.ready_for_fifo_event is True
    assert "SALE_CUTOFF_BRIDGE_REQUIRED" not in codes
    assert readiness.ready_to_apply is False

    stale_descriptor = replace(
        bridge.cutoff_descriptor, case_revision=bridge.case_revision + 1,
    )
    stale = replace(
        bridge, case_revision=bridge.case_revision + 1,
        cutoff_descriptor=stale_descriptor,
    )
    with pytest.raises(ValueError, match="FIFO_READINESS_INPUT_INVALID"):
        FifoCostTransitionReadinessService().assess(
            case=case, proposal=proposal, supply_reconciliation=None,
            cutoff_bridge=stale,
        )


def test_fl18_production_transition_factory_uses_real_parser_normalizer_and_validator():
    from telegram_assistant_factory import create_fifo_cost_transition_service

    transition_service = create_fifo_cost_transition_service(repository=object())
    stock = _stock_report()
    case = _case()
    response = {"error": False, "rows": [
        {"order": {"posting_number": "posting-before"}, "item": {
            "sku": SCOPE.sku, "offer_id": SCOPE.offer_id, "product_id": SCOPE.product_id,
        }},
        {"order": {"posting_number": "posting-after"}, "item": {
            "sku": SCOPE.sku, "offer_id": SCOPE.offer_id, "product_id": SCOPE.product_id,
        }},
    ]}
    metadata = _metadata(EvidenceSourceKind.OZON_API, "factory-finance")
    proof = SourceProof(metadata, True, True, "2026-11-08T09:00:00Z")
    batch = transition_service.cutoff_bridge_service.source_adapter.parse_realization_postings(
        response=response, scope=SCOPE, proof=proof,
        period_from="2026-11-05", period_to=COMPLETE_THROUGH,
        source_as_of=proof.source_as_of,
    )
    document = transition_service.cutoff_bridge_service.document_parser.parse(
        payload=_document_payload(), scope=SCOPE, case_id=CASE_ID,
    )
    result = transition_service.build_cutoff_bridge(
        case=case, proposal=_proposal(case=case, stock=stock), stock_evidence=stock,
        finance_batch=batch, physical_sale_document=document,
        owner_confirmation=_confirmation(document), movement_coverage=_movement_coverage(),
        requested_complete_through=COMPLETE_THROUGH,
    )

    assert result["error"] is False
    assert result["result"].ready_for_fifo_event is True

    opening = _proposal(case=case, stock=stock)
    activation = transition_service.build_activation_proposal(
        case=case, fifo_initialized=False, opening_proposal=opening,
        cutoff_bridge=result["result"],
    )
    assert activation["error"] is False
    assert activation["result"].new_unit_cost_rub == Decimal("14.65")
    assert activation["result"].new_home_units is None
    assert activation["result"].accepted_supply_units_added_to_snapshot == 0
    assert activation["result"].ready_to_apply is False


def test_finance_sku_alias_is_included_only_with_exact_owner_confirmed_mapping():
    metadata = _metadata(EvidenceSourceKind.OZON_API, "finance-alias-proof")
    proof = SourceProof(metadata, True, True, "2026-11-08T09:00:00Z")
    response = {"error": False, "rows": [{
        "order": {"posting_number": "historical-posting"},
        "item": {
            "sku": "1000000999", "offer_id": SCOPE.offer_id,
            "product_id": SCOPE.product_id,
        },
    }]}
    adapter = FifoCutoffBridgeSourceAdapter()

    with pytest.raises(ValueError, match="FIFO_CUTOFF_BRIDGE_FINANCE_SKU_ALIAS_UNCONFIRMED"):
        adapter.parse_realization_postings(
            response=response, scope=SCOPE, proof=proof,
            period_from="2026-11-05", period_to=COMPLETE_THROUGH,
            source_as_of=proof.source_as_of,
        )

    mapping = {
        "mapping_confirmed": True,
        "seller_confirmed": True,
        "finance_sku": "1000000999",
        "current_product_id": SCOPE.product_id,
        "current_sku": SCOPE.sku,
        "current_offer_id": SCOPE.offer_id,
        "mapping_id": 42,
        "source": "SELLER_CONFIRMED_BOT_TEXT",
        "confirmed_at": "2026-11-08T10:00:00Z",
    }
    batch = adapter.parse_realization_postings(
        response=response, scope=SCOPE, proof=proof,
        period_from="2026-11-05", period_to=COMPLETE_THROUGH,
        source_as_of=proof.source_as_of,
        confirmed_finance_sku_mappings={"1000000999": mapping},
    )
    assert len(batch.rows) == 1
    assert batch.rows[0].finance_sku == "1000000999"

    wrong_store_product_mapping = dict(mapping, current_product_id="other-product")
    with pytest.raises(ValueError, match="FIFO_CUTOFF_BRIDGE_FINANCE_SKU_ALIAS_UNCONFIRMED"):
        adapter.parse_realization_postings(
            response=response, scope=SCOPE, proof=proof,
            period_from="2026-11-05", period_to=COMPLETE_THROUGH,
            source_as_of=proof.source_as_of,
            confirmed_finance_sku_mappings={
                "1000000999": wrong_store_product_mapping,
            },
        )
