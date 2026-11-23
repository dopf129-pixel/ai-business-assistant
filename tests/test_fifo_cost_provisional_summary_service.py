from datetime import datetime, timezone
from decimal import Decimal
from itertools import product
import pytest
from services.fifo_cost_provisional_contracts import (
    ProvisionalIssueCode, ProvisionalRangeAssumptions, ProvisionalStatus, ProvisionalSummaryRequest,
)
from services.fifo_cost_provisional_summary_service import FifoCostProvisionalSummaryService
from services.fifo_cost_transition_contracts import (
    EvidenceCompleteness, EvidenceSourceKind, PeriodProvenance, ReportEvidence, ReportType,
    ScopeIdentity, TransitionMetadata,
)

SCOPE = ScopeIdentity(owner_id="owner-test", store_id="store-test", product_id="1", offer_id=None, sku="SKU-TEST")
TZ = "Europe/Moscow"
SNAPSHOT_BUCKETS = {
    "available": 1988, "expiring": 0, "defective": 2, "checking": 6,
    "internal_transfer": 0, "seller_withdrawal": 0,
    "buyer_return_transit": 70, "buyer_delivery": 1646,
}
MOVEMENT_CLOSING = {
    "available": 10730, "expiring": 0, "defective": 0, "checking": 0,
    "internal_transfer": 0, "seller_withdrawal": 0,
    "buyer_return_transit": 0, "buyer_delivery": 0,
}

def _report(*, start, end, opening, closing, receipts=None, redeemed=0,
            other_expenses=None, excluded_receipt=0, excluded_expense=0,
            provenance=PeriodProvenance.OWNER_CONFIRMED, scope=SCOPE,
            complete=EvidenceCompleteness.COMPLETE, digest=None, tz=TZ):
    receipts = receipts or {column: 0 for column in "LMNOPQR"}
    other_expenses = other_expenses or {column: 0 for column in "UVWXYZ"}
    opening_total, closing_total = sum(opening.values()), sum(closing.values())
    receipts_total = sum(receipts.values())
    expenses_total = redeemed + sum(other_expenses.values())
    difference = opening_total + receipts_total - expenses_total - closing_total
    digest = digest or ("a" if start == "2026-11-05" else "b") * 64
    return ReportEvidence(
        metadata=TransitionMetadata(scope=scope, source_kind=EvidenceSourceKind.OWNER_IMPORTED,
            completeness=complete, source_fingerprint=digest, store_timezone=tz),
        report_type=ReportType.TURNOVER, period_from=start, period_to=end,
        period_provenance=provenance, captured_at=datetime(2026, 11, 22, tzinfo=timezone.utc),
        file_sha256=digest, parser_version="fifo-turnover-v1", cell_references=(),
        normalized_fields={
            "opening_buckets": opening, "opening_component_total": opening_total,
            "opening_total": opening_total, "receipt_components_by_column": receipts,
            "excluded_compensation_receipt": excluded_receipt,
            "receipt_component_total": receipts_total, "receipts_total": receipts_total,
            "redeemed_units": redeemed, "non_sale_expense_components_by_column": other_expenses,
            "non_sale_expense_units": sum(other_expenses.values()),
            "withdrawal_units": other_expenses.get("V", 0),
            "excluded_compensation_expense": excluded_expense,
            "expense_component_total": expenses_total, "expenses_total": expenses_total,
            "closing_buckets": closing, "closing_component_total": closing_total,
            "closing_total": closing_total, "reported_balance_difference": difference,
            "computed_balance_difference": difference,
            "balance_status": "BALANCED" if difference == 0 else "DISCREPANCY",
            "component_controls_match": True,
        },
    )

def _case(*, old_cost=Decimal("21.00"), new_cost=Decimal("14.65"), residual=(21, 21),
          snapshot=None, movement=None, assumptions=None):
    if snapshot is None:
        snapshot = _report(start="2026-11-05", end="2026-11-05", opening=SNAPSHOT_BUCKETS,
                           closing=SNAPSHOT_BUCKETS, digest="a" * 64)
    if movement is None:
        movement = _report(start="2026-11-06", end="2026-11-20", opening=SNAPSHOT_BUCKETS,
            closing=MOVEMENT_CLOSING,
            receipts={"L": 12959, "M": 12, "N": 0, "O": 0, "P": 0, "Q": 0, "R": 0},
            redeemed=5931, other_expenses={"U": 0, "V": 14, "W": 5, "X": 3, "Y": 0, "Z": 0},
            digest="b" * 64)
    assumptions_obj = assumptions or ProvisionalRangeAssumptions(
        opening_all_old=True, all_period_supply_receipts_new=True,
        closing_old_min=residual[0], closing_old_max=residual[1])
    return ProvisionalSummaryRequest(scope=SCOPE, store_timezone=TZ, snapshot=snapshot,
        movement_report=movement, old_unit_cost_rub=old_cost, new_unit_cost_rub=new_cost,
        assumptions=assumptions_obj)

def test_control_scenario_matches_specification_to_the_cent():
    result = FifoCostProvisionalSummaryService().calculate(_case())
    assert result.status is ProvisionalStatus.SUMMARY_RANGE
    assert (result.old_sold_min, result.old_sold_max) == (3669, 3703)
    assert (result.new_sold_min, result.new_sold_max) == (2228, 2262)
    assert (result.gross_cogs_low_rub, result.gross_cogs_high_rub) == (Decimal("110187.30"), Decimal("110403.20"))
    assert (result.opening_total, result.supply_receipts, result.buyer_return_receipts,
            result.redeemed_units, result.other_supported_expenses) == (3712, 12959, 12, 5931, 22)

def test_unknown_closing_old_stock_keeps_wide_range_and_reason_visible():
    result = FifoCostProvisionalSummaryService().calculate(_case(assumptions=ProvisionalRangeAssumptions(
        opening_all_old=True, all_period_supply_receipts_new=True)))
    assert (result.old_sold_min, result.old_sold_max) == (0, 3724)
    assert (result.new_sold_min, result.new_sold_max) == (2207, 5931)
    assert (result.gross_cogs_low_rub, result.gross_cogs_high_rub) == (Decimal("86889.15"), Decimal("110536.55"))
    assert result.issue_codes == (ProvisionalIssueCode.END_OLD_STOCK_UNESTABLISHED,)

def test_higher_new_cost_sorts_money_bounds_and_equal_cost_collapses_them():
    higher = FifoCostProvisionalSummaryService().calculate(_case(new_cost=Decimal("25.00")))
    assert higher.gross_cogs_low_rub <= higher.gross_cogs_high_rub
    equal = FifoCostProvisionalSummaryService().calculate(_case(old_cost=Decimal("14.65")))
    assert equal.gross_cogs_low_rub == equal.gross_cogs_high_rub

def test_manual_residual_31_changes_both_costs_by_63_50():
    base = FifoCostProvisionalSummaryService().calculate(_case())
    other = FifoCostProvisionalSummaryService().calculate(_case(residual=(31, 31)))
    assert (other.gross_cogs_low_rub, other.gross_cogs_high_rub) == (Decimal("110123.80"), Decimal("110339.70"))
    assert base.gross_cogs_low_rub - other.gross_cogs_low_rub == Decimal("63.50")
    assert base.gross_cogs_high_rub - other.gross_cogs_high_rub == Decimal("63.50")

def test_snapshot_boundary_requires_all_eight_buckets_to_match():
    moved = dict(SNAPSHOT_BUCKETS); moved["available"] -= 1; moved["buyer_delivery"] += 1
    movement = _report(start="2026-11-06", end="2026-11-20", opening=moved,
        closing=MOVEMENT_CLOSING,
        receipts={"L": 12959, "M": 12, "N": 0, "O": 0, "P": 0, "Q": 0, "R": 0},
        redeemed=5931, other_expenses={"U": 0, "V": 14, "W": 5, "X": 3, "Y": 0, "Z": 0}, digest="c" * 64)
    result = FifoCostProvisionalSummaryService().calculate(_case(movement=movement))
    assert result.status is ProvisionalStatus.SOURCE_CONFLICT
    assert result.issue_codes == (ProvisionalIssueCode.BUCKET_BOUNDARY_MISMATCH,)
    assert result.gross_cogs_low_rub is None

def test_boolean_quantity_is_not_accepted_by_model():
    opening = dict(SNAPSHOT_BUCKETS); opening["available"] = True
    report = _report(start="2026-11-05", end="2026-11-05", opening=opening,
                     closing=SNAPSHOT_BUCKETS, digest="a" * 64)
    result = FifoCostProvisionalSummaryService().calculate(_case(snapshot=report))
    assert result.status is ProvisionalStatus.SOURCE_CONFLICT

@pytest.mark.parametrize("value", [1.0, "1"])
def test_float_and_text_quantity_are_rejected_by_typed_source_contract(value):
    with pytest.raises((TypeError, ValueError)):
        FifoCostProvisionalSummaryService._quantity(value)
def test_filename_period_candidate_is_not_sufficient():
    snapshot = _report(start="2026-11-05", end="2026-11-05", opening=SNAPSHOT_BUCKETS,
        closing=SNAPSHOT_BUCKETS, provenance=PeriodProvenance.FILENAME_CANDIDATE, digest="a" * 64)
    result = FifoCostProvisionalSummaryService().calculate(_case(snapshot=snapshot))
    assert result.status is ProvisionalStatus.SOURCE_CONFLICT
    assert result.issue_codes == (ProvisionalIssueCode.REPORT_PERIOD_UNCONFIRMED,)

def test_exact_scope_and_adjacent_periods_are_required():
    other_scope = ScopeIdentity(owner_id="owner-test", store_id="another-store", product_id="1", offer_id=None, sku="SKU-TEST")
    snapshot = _report(start="2026-11-05", end="2026-11-05", opening=SNAPSHOT_BUCKETS,
        closing=SNAPSHOT_BUCKETS, scope=other_scope, digest="a" * 64)
    assert FifoCostProvisionalSummaryService().calculate(_case(snapshot=snapshot)).status is ProvisionalStatus.SOURCE_CONFLICT
    gap = _report(start="2026-11-07", end="2026-11-20", opening=SNAPSHOT_BUCKETS,
        closing=MOVEMENT_CLOSING,
        receipts={"L": 12959, "M": 12, "N": 0, "O": 0, "P": 0, "Q": 0, "R": 0},
        redeemed=5931, other_expenses={"U": 0, "V": 14, "W": 5, "X": 3, "Y": 0, "Z": 0}, digest="c" * 64)
    assert FifoCostProvisionalSummaryService().calculate(_case(movement=gap)).issue_codes == (
        ProvisionalIssueCode.REPORT_WINDOW_MISMATCH,)

def test_unsupported_movements_and_unbalanced_report_block_money():
    receipts = {"L": 12958, "M": 12, "N": 1, "O": 0, "P": 0, "Q": 0, "R": 0}
    movement = _report(start="2026-11-06", end="2026-11-20", opening=SNAPSHOT_BUCKETS,
        closing=MOVEMENT_CLOSING, receipts=receipts, redeemed=5931,
        other_expenses={"U": 0, "V": 14, "W": 5, "X": 3, "Y": 0, "Z": 0}, digest="b" * 64)
    result = FifoCostProvisionalSummaryService().calculate(_case(movement=movement))
    assert result.status is ProvisionalStatus.SOURCE_CONFLICT
    assert result.issue_codes == (ProvisionalIssueCode.UNSUPPORTED_RECEIPTS,)
    unbalanced = _report(start="2026-11-06", end="2026-11-20", opening=SNAPSHOT_BUCKETS,
        closing={**MOVEMENT_CLOSING, "available": 10729},
        receipts={"L": 12959, "M": 12, "N": 0, "O": 0, "P": 0, "Q": 0, "R": 0},
        redeemed=5931, other_expenses={"U": 0, "V": 14, "W": 5, "X": 3, "Y": 0, "Z": 0}, digest="d" * 64)
    assert FifoCostProvisionalSummaryService().calculate(_case(movement=unbalanced)).status is ProvisionalStatus.SOURCE_CONFLICT

def test_missing_owner_assumptions_return_need_input_not_an_estimate():
    result = FifoCostProvisionalSummaryService().calculate(_case(assumptions=ProvisionalRangeAssumptions()))
    assert result.status is ProvisionalStatus.NEED_INPUT
    assert result.gross_cogs_low_rub is None
    assert result.issue_codes == (ProvisionalIssueCode.OWNER_OPENING_COMPOSITION_REQUIRED,)

def test_empty_intersection_is_source_conflict():
    result = FifoCostProvisionalSummaryService.derive_old_sold_range(
        opening_old=10, buyer_returns=0, redeemed=2, supported_other_expenses=0,
        closing_old_min=0, closing_old_max=0)
    assert result == (None, None)

def test_exhaustive_small_integer_matrix_matches_all_feasible_old_sale_counts():
    for opening, supply, returns, redeemed, outflow, old_close in product(range(4), repeat=6):
        total_close = opening + supply + returns - redeemed - outflow
        if total_close < 0 or old_close > min(total_close, opening + returns):
            continue
        actual = set()
        for returned_old in range(returns + 1):
            for outflow_old in range(outflow + 1):
                sold_old = opening + returned_old - outflow_old - old_close
                sold_new = redeemed - sold_old
                if min(sold_old, sold_new, total_close - old_close) < 0:
                    continue
                if sold_new <= supply + returns - returned_old - (outflow - outflow_old):
                    actual.add(sold_old)
        expected = FifoCostProvisionalSummaryService.derive_old_sold_range(
            opening_old=opening, buyer_returns=returns, redeemed=redeemed,
            supported_other_expenses=outflow, closing_old_min=old_close, closing_old_max=old_close)
        if actual:
            assert expected == (min(actual), max(actual))
        else:
            assert expected == (None, None)
