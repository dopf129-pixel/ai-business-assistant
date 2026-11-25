from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal

from services.fifo_cost_provisional_contracts import (
    ProvisionalRangeAssumptions,
    ProvisionalStatus,
    ProvisionalSummaryRequest,
)
from services.fifo_cost_provisional_fbo_csv_import_service import (
    FifoCostProvisionalFboCsvImportService,
)
from services.fifo_cost_provisional_movements_import_service import (
    FifoCostProvisionalMovementsImportService,
)
from services.fifo_cost_provisional_summary_service import FifoCostProvisionalSummaryService
from services.fifo_cost_provisional_timeline_service import FifoCostProvisionalTimelineService
from services.fifo_cost_transition_contracts import (
    EvidenceCompleteness,
    EvidenceSourceKind,
    PeriodProvenance,
    ReportEvidence,
    ReportType,
    ScopeIdentity,
    TransitionMetadata,
)


SCOPE = ScopeIdentity(
    owner_id="owner-test", store_id="store-test", product_id="1",
    offer_id="hook", sku="3921245627",
)
TZ = "Europe/Moscow"
EMPTY = {
    "available": 0, "expiring": 0, "defective": 0, "checking": 0,
    "internal_transfer": 0, "seller_withdrawal": 0,
    "buyer_return_transit": 0, "buyer_delivery": 0,
}
OPENING = {**EMPTY, "available": 2}


def _report(*, start, end, opening, closing, receipts, redeemed, digest):
    expenses = {column: 0 for column in "UVWXYZ"}
    opening_total = sum(opening.values())
    closing_total = sum(closing.values())
    receipts_total = sum(receipts.values())
    expenses_total = redeemed + sum(expenses.values())
    difference = opening_total + receipts_total - expenses_total - closing_total
    return ReportEvidence(
        metadata=TransitionMetadata(
            scope=SCOPE, source_kind=EvidenceSourceKind.OWNER_IMPORTED,
            completeness=EvidenceCompleteness.COMPLETE,
            source_fingerprint=digest, store_timezone=TZ,
        ),
        report_type=ReportType.TURNOVER,
        period_from=start, period_to=end,
        period_provenance=PeriodProvenance.OWNER_CONFIRMED,
        captured_at=datetime(2026, 11, 22, tzinfo=timezone.utc),
        file_sha256=digest, parser_version="timeline-test-v1", cell_references=(),
        normalized_fields={
            "opening_buckets": opening, "opening_total": opening_total,
            "receipt_components_by_column": receipts,
            "receipts_total": receipts_total, "excluded_compensation_receipt": 0,
            "redeemed_units": redeemed,
            "non_sale_expense_components_by_column": expenses,
            "expenses_total": expenses_total, "excluded_compensation_expense": 0,
            "closing_buckets": closing, "closing_total": closing_total,
            "reported_balance_difference": difference,
            "computed_balance_difference": difference,
            "balance_status": "BALANCED" if difference == 0 else "DISCREPANCY",
            "component_controls_match": True,
        },
    )


def _case():
    snapshot = _report(
        start="2026-11-05", end="2026-11-05", opening=OPENING,
        closing=OPENING, receipts={column: 0 for column in "LMNOPQR"},
        redeemed=0, digest="a" * 64,
    )
    movement = _report(
        start="2026-11-06", end="2026-11-06", opening=OPENING,
        closing=EMPTY,
        receipts={"L": 1, "M": 0, "N": 0, "O": 0, "P": 0, "Q": 0, "R": 0},
        redeemed=3, digest="b" * 64,
    )
    request = ProvisionalSummaryRequest(
        scope=SCOPE, store_timezone=TZ, snapshot=snapshot,
        movement_report=movement,
        old_unit_cost_rub=Decimal("21.00"), new_unit_cost_rub=Decimal("14.65"),
        assumptions=ProvisionalRangeAssumptions(
            opening_all_old=True, all_period_supply_receipts_new=True,
            closing_old_min=0, closing_old_max=0,
        ),
    )
    summary = FifoCostProvisionalSummaryService().calculate(request)
    header = "Номер отправления;SKU;Количество;Статус;Дата передачи в доставку;Дата доставки"
    fbo_csv = (
        header + "\n"
        "posting-1;3921245627;3;Доставлен;2026-11-06 12:00:00;2026-11-06 13:00:00\n"
    ).encode()
    fbo = FifoCostProvisionalFboCsvImportService().parse_csv(
        filename="orders.csv", payload=fbo_csv, scope=SCOPE, timezone_name=TZ,
    ).document
    parser = FifoCostProvisionalMovementsImportService()
    movement_csv = (
        ";".join(parser.HEADER) + "\n"
        f"SUPPLY_RECEIVED;receipt-1;2026-11-06T10:00:00+03:00;{SCOPE.sku};1;;available;;source-1\n"
    ).encode()
    movements = parser.parse_csv(
        filename="movements.csv", payload=movement_csv,
        scope=SCOPE, timezone_name=TZ,
    ).document
    return snapshot, movement, summary, fbo, movements


def _calculate(*, summary_override=None, coverage=True, fbo_window=("2026-11-06", "2026-11-06")):
    snapshot, movement, summary, fbo, movements = _case()
    return FifoCostProvisionalTimelineService().calculate(
        scope=SCOPE, timezone_name=TZ, case_id="case-1",
        snapshot_report=snapshot, movement_report=movement,
        summary_result=summary_override or summary, fbo_document=fbo,
        fbo_coverage_from=fbo_window[0], fbo_coverage_to=fbo_window[1],
        movement_document=movements, confirmed_reports=(snapshot, movement),
        physical_sales_status="MISSING", owner_confirmed_coverage=coverage,
    )


def _summary_for(snapshot, movement, *, closing_old=0):
    return FifoCostProvisionalSummaryService().calculate(ProvisionalSummaryRequest(
        scope=SCOPE, store_timezone=TZ, snapshot=snapshot, movement_report=movement,
        old_unit_cost_rub=Decimal("21.00"), new_unit_cost_rub=Decimal("14.65"),
        assumptions=ProvisionalRangeAssumptions(
            opening_all_old=True, all_period_supply_receipts_new=True,
            closing_old_min=closing_old, closing_old_max=closing_old,
        ),
    ))


def _calculate_reports(snapshot, movement, summary, fbo, movements):
    return FifoCostProvisionalTimelineService().calculate(
        scope=SCOPE, timezone_name=TZ, case_id="case-1",
        snapshot_report=snapshot, movement_report=movement,
        summary_result=summary, fbo_document=fbo,
        fbo_coverage_from="2026-11-06", fbo_coverage_to="2026-11-06",
        movement_document=movements, confirmed_reports=(snapshot, movement),
        physical_sales_status="MISSING", owner_confirmed_coverage=True,
    )


def test_complete_timeline_returns_model_only_after_event_and_bucket_reconciliation():
    result = _calculate()
    assert result.status is ProvisionalStatus.TIMELINE_MODEL
    assert (result.redeemed_units, result.old_sold_units, result.new_sold_units) == (3, 2, 1)
    assert result.gross_cogs_rub == Decimal("56.65")
    assert result.ending_available_units == 0
    assert result.read_only is True and result.factual_writes == 0


def test_timeline_fifo_cost_split_must_fit_owner_confirmed_closing_old_range():
    snapshot = _report(
        start="2026-11-05", end="2026-11-05", opening=OPENING,
        closing=OPENING, receipts={column: 0 for column in "LMNOPQR"},
        redeemed=0, digest="c" * 64,
    )
    closing = {**EMPTY, "available": 3}
    movement = _report(
        start="2026-11-06", end="2026-11-06", opening=OPENING,
        closing=closing,
        receipts={"L": 2, "M": 0, "N": 0, "O": 0, "P": 0, "Q": 0, "R": 0},
        redeemed=1, digest="d" * 64,
    )
    summary = FifoCostProvisionalSummaryService().calculate(ProvisionalSummaryRequest(
        scope=SCOPE, store_timezone=TZ, snapshot=snapshot, movement_report=movement,
        old_unit_cost_rub=Decimal("21.00"), new_unit_cost_rub=Decimal("14.65"),
        assumptions=ProvisionalRangeAssumptions(
            opening_all_old=True, all_period_supply_receipts_new=True,
            closing_old_min=2, closing_old_max=2,
        ),
    ))
    assert summary.status is ProvisionalStatus.SUMMARY_RANGE
    assert (summary.old_sold_min, summary.old_sold_max) == (0, 0)
    fbo_csv = (
        "Номер отправления;SKU;Количество;Статус;Дата передачи в доставку;Дата доставки\n"
        "posting-1;3921245627;1;Доставлен;2026-11-06 10:00:00;2026-11-06 11:00:00\n"
    ).encode()
    fbo = FifoCostProvisionalFboCsvImportService().parse_csv(
        filename="orders.csv", payload=fbo_csv, scope=SCOPE, timezone_name=TZ,
    ).document
    parser = FifoCostProvisionalMovementsImportService()
    movement_csv = (
        ";".join(parser.HEADER) + "\n"
        f"SUPPLY_RECEIVED;receipt-1;2026-11-06T09:00:00+03:00;{SCOPE.sku};2;;available;;source-1\n"
    ).encode()
    movements = parser.parse_csv(
        filename="movements.csv", payload=movement_csv,
        scope=SCOPE, timezone_name=TZ,
    ).document
    result = FifoCostProvisionalTimelineService().calculate(
        scope=SCOPE, timezone_name=TZ, case_id="case-1",
        snapshot_report=snapshot, movement_report=movement,
        summary_result=summary, fbo_document=fbo,
        fbo_coverage_from="2026-11-06", fbo_coverage_to="2026-11-06",
        movement_document=movements, confirmed_reports=(snapshot, movement),
        physical_sales_status="MISSING", owner_confirmed_coverage=True,
    )
    assert result.status is ProvisionalStatus.SOURCE_CONFLICT
    assert result.issue_codes == ("TIMELINE_SUMMARY_OLD_SOLD_CONFLICT",)
    assert result.old_sold_units is None
    assert result.gross_cogs_rub is None


def test_unconfirmed_coverage_never_exposes_partial_cogs_as_timeline_result():
    result = _calculate(coverage=False)
    assert result.status is ProvisionalStatus.NEED_INPUT
    assert result.issue_codes == ("OWNER_COVERAGE_CONFIRMATION_REQUIRED",)
    assert result.gross_cogs_rub is None
    assert result.redeemed_units is None


def test_closing_category_mismatch_blocks_timeline_money():
    changed = {**EMPTY, "checking": 1}
    snapshot, movement, summary, _fbo, _movements = _case()
    result = FifoCostProvisionalTimelineService().calculate(
        scope=SCOPE, timezone_name=TZ, case_id="case-1",
        snapshot_report=snapshot, movement_report=movement,
        summary_result=replace(summary, closing_buckets=changed),
        fbo_document=_case()[3], fbo_coverage_from="2026-11-06",
        fbo_coverage_to="2026-11-06", movement_document=_case()[4],
        confirmed_reports=(snapshot, movement), physical_sales_status="MISSING",
        owner_confirmed_coverage=True,
    )
    assert result.status is ProvisionalStatus.SOURCE_CONFLICT
    assert "CLOSING_BUCKETS_DO_NOT_MATCH" in result.issue_codes
    assert result.gross_cogs_rub is None


def test_fbo_csv_period_may_be_wider_when_it_contains_statement_window():
    result = _calculate(fbo_window=("2026-10-01", "2026-12-31"))
    assert result.status is ProvisionalStatus.TIMELINE_MODEL
    assert result.gross_cogs_rub == Decimal("56.65")


def test_fbo_csv_period_must_contain_the_complete_statement_window():
    result = _calculate(fbo_window=("2026-11-07", "2026-11-07"))
    assert result.status is ProvisionalStatus.NEED_INPUT
    assert "FBO_COVERAGE_WINDOW_MISMATCH" in result.issue_codes
    assert result.gross_cogs_rub is None


def test_unlinked_opening_buyer_delivery_remainder_is_kept_untouched():
    opening = {**EMPTY, "available": 2, "buyer_delivery": 1}
    closing = {**EMPTY, "buyer_delivery": 1}
    snapshot = _report(
        start="2026-11-05", end="2026-11-05", opening=opening,
        closing=opening, receipts={column: 0 for column in "LMNOPQR"},
        redeemed=0, digest="c" * 64,
    )
    movement = _report(
        start="2026-11-06", end="2026-11-06", opening=opening,
        closing=closing,
        receipts={"L": 1, "M": 0, "N": 0, "O": 0, "P": 0, "Q": 0, "R": 0},
        redeemed=3, digest="d" * 64,
    )
    _snapshot, _movement, _old_summary, fbo, movements = _case()
    summary = _summary_for(snapshot, movement, closing_old=1)

    result = _calculate_reports(snapshot, movement, summary, fbo, movements)

    assert result.status is ProvisionalStatus.TIMELINE_MODEL, (
        result.issue_codes, result.supplied_events, result.processed_events,
        result.redeemed_units,
    )
    assert result.ending_buyer_delivery_units == 1
    assert result.ending_available_units == 0
    assert result.redeemed_units == 3
    assert result.gross_cogs_rub == Decimal("56.65")


def test_delivery_after_report_cutoff_keeps_in_window_dispatch_pending():
    opening = {**EMPTY, "available": 3}
    closing = {**EMPTY, "available": 1, "buyer_delivery": 3}
    snapshot = _report(
        start="2026-11-05", end="2026-11-05", opening=opening,
        closing=opening, receipts={column: 0 for column in "LMNOPQR"},
        redeemed=0, digest="e" * 64,
    )
    movement = _report(
        start="2026-11-06", end="2026-11-06", opening=opening,
        closing=closing,
        receipts={"L": 1, "M": 0, "N": 0, "O": 0, "P": 0, "Q": 0, "R": 0},
        redeemed=0, digest="f" * 64,
    )
    fbo_csv = (
        "Номер отправления;SKU;Количество;Статус;Дата передачи в доставку;Дата доставки\n"
        "posting-future;3921245627;3;Доставлен;2026-11-06 12:00:00;2026-11-07 13:00:00\n"
    ).encode()
    fbo_parse = FifoCostProvisionalFboCsvImportService().parse_csv(
        filename="orders.csv", payload=fbo_csv, scope=SCOPE, timezone_name=TZ,
    )
    assert fbo_parse.status == "COMPLETE", fbo_parse.issue_codes
    fbo = fbo_parse.document
    movement_parse = FifoCostProvisionalMovementsImportService().parse_csv(
        filename="movements.csv", payload=(
            ";".join(FifoCostProvisionalMovementsImportService.HEADER) + "\n"
            "SUPPLY_RECEIVED;receipt-future;2026-11-06T10:00:00+03:00;"
            "3921245627;1;;available;;source-2\n"
        ).encode(),
        scope=SCOPE, timezone_name=TZ,
    )
    assert movement_parse.status == "COMPLETE", movement_parse.issue_codes
    movements = movement_parse.document
    summary = _summary_for(snapshot, movement, closing_old=3)

    result = _calculate_reports(snapshot, movement, summary, fbo, movements)

    assert result.status is ProvisionalStatus.TIMELINE_MODEL, (
        result.issue_codes, result.supplied_events, result.processed_events,
        result.redeemed_units,
    )
    assert result.ending_buyer_delivery_units == 3
    assert result.ending_available_units == 1
    assert result.redeemed_units == 0
    assert result.gross_cogs_rub == Decimal("0.00")
