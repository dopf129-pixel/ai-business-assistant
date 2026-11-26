from __future__ import annotations

from datetime import date, datetime, timezone

from services.fifo_cost_cutoff_bridge_service import (
    FifoDocumentedPhysicalSaleDocument,
    FifoDocumentedPhysicalSaleRow,
    FifoPhysicalSaleDocumentConfirmation,
)
from services.fifo_cost_provisional_fbo_csv_import_service import FifoCostProvisionalFboCsvImportService
from services.fifo_cost_provisional_movements_import_service import FifoCostProvisionalMovementsImportService
from services.fifo_cost_provisional_timeline_contracts import (
    ProvisionalTimelineEventKind as Kind,
    ProvisionalTimelineIssue as Issue,
)
from services.fifo_cost_provisional_timeline_normalizer import FifoCostProvisionalTimelineNormalizer
from services.fifo_cost_transition_contracts import (
    EvidenceCompleteness, EvidenceSourceKind, PeriodProvenance, ReportEvidence,
    ReportType, ScopeIdentity, TransitionMetadata,
)


SCOPE = ScopeIdentity(owner_id="owner", store_id="store", product_id="1", offer_id="hook", sku="3921245627")
FBO = FifoCostProvisionalFboCsvImportService()
MOVEMENTS = FifoCostProvisionalMovementsImportService()
NORMALIZER = FifoCostProvisionalTimelineNormalizer()


def _fbo(*rows, scope=SCOPE):
    header = "Номер отправления;SKU;Количество;Статус;Дата передачи в доставку;Дата доставки"
    content = header + "\n" + "".join(";".join(row) + "\n" for row in rows)
    return FBO.parse_csv(
        filename="orders.csv", payload=content.encode(), scope=scope,
        timezone_name="Europe/Moscow",
    ).document


def _movement(kind, *, posting="posting-1", qty="2", effective="2026-11-05T10:00:00+03:00",
              reference="event-1", zone="", resellable=""):
    header = ";".join(MOVEMENTS.HEADER)
    row = ";".join((kind, reference, effective, SCOPE.sku, qty, posting, zone,
                     resellable, "source-row-1"))
    return MOVEMENTS.parse_csv(
        filename="movements.csv", payload=(header + "\n" + row + "\n").encode(),
        scope=SCOPE, timezone_name="Europe/Moscow",
    ).document


def _report(*, scope=SCOPE, kind=ReportType.TURNOVER, fields=None, digest="a" * 64):
    return ReportEvidence(
        metadata=TransitionMetadata(
            scope=scope, source_kind=EvidenceSourceKind.OWNER_IMPORTED,
            completeness=EvidenceCompleteness.COMPLETE, source_fingerprint=digest,
            store_timezone="Europe/Moscow",
        ),
        report_type=kind, period_from="2026-11-05", period_to="2026-11-05",
        period_provenance=PeriodProvenance.OWNER_CONFIRMED,
        captured_at=datetime(2026, 11, 22, tzinfo=timezone.utc).isoformat(),
        file_sha256=digest, parser_version="provisional-test-v1",
        cell_references=(), normalized_fields=fields or {"redeemed_units": 21, "source_row": 999},
    )


def _physical_sales(*, scope=SCOPE, quantity=2, effective_date="2026-11-07"):
    case_id = "case-1234"
    digest = "b" * 64
    doc = FifoDocumentedPhysicalSaleDocument(
        metadata=TransitionMetadata(
            scope=scope, source_kind=EvidenceSourceKind.OWNER_IMPORTED,
            completeness=EvidenceCompleteness.COMPLETE, source_fingerprint=digest,
            store_timezone="Europe/Moscow",
        ),
        case_id=case_id, document_kind="OWNER_DOCUMENTED_PHYSICAL_SALES_V1",
        document_fingerprint=digest, parser_version="fifo-owner-physical-sales-v1",
        period_from=effective_date, period_to=effective_date,
        rows=(FifoDocumentedPhysicalSaleRow(
            posting_number="posting-1", finance_sku=scope.sku, quantity=quantity,
            physical_effective_date=effective_date, row_reference="row-1",
        ),),
    )
    confirmation = FifoPhysicalSaleDocumentConfirmation(
        metadata=TransitionMetadata(
            scope=scope, source_kind=EvidenceSourceKind.OWNER_INPUT,
            completeness=EvidenceCompleteness.COMPLETE, source_fingerprint=digest,
            store_timezone="Europe/Moscow",
        ),
        owner_id=scope.owner_id, case_id=case_id, document_fingerprint=digest,
        confirmed_row_references=("row-1",),
        confirmed_fields=frozenset({
            "posting_number", "finance_sku", "quantity", "physical_effective_date",
        }),
        physical_date_semantics="PHYSICAL_OUTFLOW",
        physical_date_timezone="Europe/Moscow",
        physical_date_precision="STORE_LOCAL_DATE",
        confirmed_at="2026-11-22T10:00:00Z",
    )
    return doc, confirmation


def test_exact_opening_transit_link_matches_posting_quantity_and_avoids_second_dispatch():
    document = _fbo(("posting-1", SCOPE.sku, "2", "Доставлен", "2026-11-05 10:00:00", "2026-11-07 12:00:00"))
    movements = _movement("OPENING_TRANSIT_LINK")
    result = NORMALIZER.normalize(
        scope=SCOPE, timezone_name="Europe/Moscow", model_start=date(2026, 11, 6),
        fbo_document=document, movement_document=movements,
    )
    assert not result.issue_codes, result.issue_codes
    assert len(result.events) == 2
    by_kind = {event.event_kind: event for event in result.events}
    assert set(by_kind) == {Kind.OPENING_TRANSIT_LINK, Kind.BUYOUT}
    assert by_kind[Kind.BUYOUT].quantity == 2
    assert by_kind[Kind.BUYOUT].time_precision == "INSTANT"
    assert result.read_only is True and result.factual_writes == 0
    assert result.posting_capacities == {by_kind[Kind.OPENING_TRANSIT_LINK].posting_key: 2}
    assert "posting-1" not in repr(result)


def test_pre_snapshot_posting_without_exact_opening_link_is_a_gap():
    document = _fbo(("posting-1", SCOPE.sku, "2", "Доставлен", "2026-11-05", "2026-11-07"))
    result = NORMALIZER.normalize(
        scope=SCOPE, timezone_name="Europe/Moscow", model_start=date(2026, 11, 6),
        fbo_document=document,
    )
    assert result.events == ()
    # A date-only delivery is not fabricated into a posting link.
    assert {issue.value for issue in result.issue_codes} == {"FBO_OPENING_LINK_REQUIRED"}


def test_opening_link_wrong_quantity_status_or_date_never_becomes_a_valid_link():
    fbo = _fbo(("posting-1", SCOPE.sku, "2", "Доставлен", "2026-11-05 10:00:00", "2026-11-07 12:00:00"))
    excessive = _movement("OPENING_TRANSIT_LINK", qty="3")
    result = NORMALIZER.normalize(
        scope=SCOPE, timezone_name="Europe/Moscow", model_start=date(2026, 11, 6),
        fbo_document=fbo, movement_document=excessive,
    )
    assert "EVENT_QUANTITY_EXCEEDS_POSTING" in {issue.value for issue in result.issue_codes}
    assert "FBO_OPENING_LINK_REQUIRED" in {issue.value for issue in result.issue_codes}


    in_window_link = _movement(
        "OPENING_TRANSIT_LINK", effective="2026-11-06T10:00:00+03:00",
    )
    result = NORMALIZER.normalize(
        scope=SCOPE, timezone_name="Europe/Moscow", model_start=date(2026, 11, 6),
        fbo_document=fbo, movement_document=in_window_link,
    )
    assert "EVENT_ORDER_CONFLICT" in {issue.value for issue in result.issue_codes}

    cancelled = _fbo(("posting-1", SCOPE.sku, "2", "Отменён", "2026-11-05 10:00:00", ""))
    result = NORMALIZER.normalize(
        scope=SCOPE, timezone_name="Europe/Moscow", model_start=date(2026, 11, 6),
        fbo_document=cancelled,
    )
    assert "FBO_CANCELLED_UNRESOLVED" in {issue.value for issue in result.issue_codes}

    cancelled_restocked = _movement(
        "NON_BUYOUT_RESTOCK", qty="2", effective="2026-11-08T10:00:00+03:00",
        resellable="true",
    )
    result = NORMALIZER.normalize(
        scope=SCOPE, timezone_name="Europe/Moscow", model_start=date(2026, 11, 6),
        fbo_document=cancelled, movement_document=cancelled_restocked,
    )
    assert Issue.FBO_OPENING_LINK_REQUIRED in result.issue_codes


def test_pre_window_cancelled_posting_returning_during_window_still_requires_opening_link():
    fbo = _fbo((
        "posting-1", SCOPE.sku, "2", "\u041e\u0442\u043c\u0435\u043d\u0451\u043d",
        "2026-11-05 10:00:00", "",
    ))
    header = ";".join(MOVEMENTS.HEADER)
    rows = "\n".join((
        "OPENING_TRANSIT_LINK;opening-link;2026-11-05T10:00:00+03:00;"
        f"{SCOPE.sku};2;posting-1;;;source-row-1",
        "NON_BUYOUT_RESTOCK;restock;2026-11-08T10:00:00+03:00;"
        f"{SCOPE.sku};2;posting-1;;true;source-row-2",
    ))
    movements = MOVEMENTS.parse_csv(
        filename="movements.csv", payload=(header + "\n" + rows + "\n").encode(),
        scope=SCOPE, timezone_name="Europe/Moscow",
    ).document
    without_link = NORMALIZER.normalize(
        scope=SCOPE, timezone_name="Europe/Moscow", model_start=date(2026, 11, 6),
        fbo_document=fbo,
        movement_document=_movement(
            "NON_BUYOUT_RESTOCK", qty="2", effective="2026-11-08T10:00:00+03:00",
            resellable="true",
        ),
    )
    with_link = NORMALIZER.normalize(
        scope=SCOPE, timezone_name="Europe/Moscow", model_start=date(2026, 11, 6),
        fbo_document=fbo, movement_document=movements,
    )

    assert Issue.FBO_OPENING_LINK_REQUIRED in without_link.issue_codes
    assert not with_link.issue_codes
    assert {event.event_kind for event in with_link.events} == {
        Kind.OPENING_TRANSIT_LINK, Kind.NON_BUYOUT_RESTOCK,
    }


def test_owner_restock_is_joined_by_exact_posting_and_checked_against_quantity_and_status():
    delivered = _fbo(("posting-1", SCOPE.sku, "2", "Доставлен", "2026-11-06 10:00:00", "2026-11-07 12:00:00"))
    correct = _movement("SALE_RETURN_RESTOCK", effective="2026-11-08T10:00:00+03:00", resellable="true")
    result = NORMALIZER.normalize(
        scope=SCOPE, timezone_name="Europe/Moscow", model_start=date(2026, 11, 6),
        fbo_document=delivered, movement_document=correct,
    )
    assert not result.issue_codes, result.issue_codes
    assert {item.event_kind for item in result.events} == {Kind.BUYER_DISPATCH, Kind.BUYOUT, Kind.SALE_RETURN_RESTOCK}

    wrong_status = _movement("NON_BUYOUT_RESTOCK", effective="2026-11-08T10:00:00+03:00", resellable="true")
    result = NORMALIZER.normalize(
        scope=SCOPE, timezone_name="Europe/Moscow", model_start=date(2026, 11, 6),
        fbo_document=delivered, movement_document=wrong_status,
    )
    assert "EVENT_STATUS_MISMATCH" in {issue.value for issue in result.issue_codes}

    excessive = _movement("SALE_RETURN_RESTOCK", qty="3", effective="2026-11-08T10:00:00+03:00", resellable="false")
    result = NORMALIZER.normalize(
        scope=SCOPE, timezone_name="Europe/Moscow", model_start=date(2026, 11, 6),
        fbo_document=delivered, movement_document=excessive,
    )
    assert "EVENT_QUANTITY_EXCEEDS_POSTING" in {issue.value for issue in result.issue_codes}


def test_aggregate_reports_are_exact_scope_anchors_not_timeline_events():
    other_scope = ScopeIdentity(owner_id="other", store_id="store", product_id="1", offer_id="hook", sku=SCOPE.sku)
    report = _report(fields={"redeemed_units": 21, "source_row": 999})
    result = NORMALIZER.normalize(
        scope=SCOPE, timezone_name="Europe/Moscow", model_start=date(2026, 11, 6),
        confirmed_reports=(report,),
    )
    assert result.events == ()
    assert result.anchors[0].aggregate_fields == {"redeemed_units": 21}
    assert "REPORTS_ARE_AGGREGATE_ONLY" in {issue.value for issue in result.issue_codes}
    version_conflict = NORMALIZER.normalize(
        scope=SCOPE, timezone_name="Europe/Moscow", model_start=date(2026, 11, 6),
        confirmed_reports=(_report(digest="a" * 64), _report(digest="c" * 64)),
    )
    assert "SAVED_REPORT_VERSION_CONFLICT" in {issue.value for issue in version_conflict.issue_codes}
    result = NORMALIZER.normalize(
        scope=SCOPE, timezone_name="Europe/Moscow", model_start=date(2026, 11, 6),
        fbo_document=_fbo(("posting-1", SCOPE.sku, "1", "Доставлен", "2026-11-06 10:00:00", "2026-11-07 12:00:00"), scope=other_scope),
    )
    assert "FBO_SCOPE_MISMATCH" in {issue.value for issue in result.issue_codes}


def test_saved_confirmed_physical_sales_are_day_precision_and_joined_without_double_count():
    evidence = _physical_sales()
    owner_only = NORMALIZER.normalize(
        scope=SCOPE, timezone_name="Europe/Moscow", model_start=date(2026, 11, 6),
        confirmed_physical_sales=evidence, case_id="case-1234",
    )
    assert not owner_only.issue_codes, owner_only.issue_codes
    assert len(owner_only.events) == 1
    assert owner_only.events[0].event_kind is Kind.BUYOUT
    assert owner_only.events[0].time_precision == "DAY"
    assert owner_only.events[0].effective_at_utc is None
    assert "posting-1" not in repr(owner_only)

    fbo = _fbo(("posting-1", SCOPE.sku, "2", "Доставлен", "2026-11-06 10:00:00", "2026-11-07 12:00:00"))
    joined = NORMALIZER.normalize(
        scope=SCOPE, timezone_name="Europe/Moscow", model_start=date(2026, 11, 6),
        fbo_document=fbo, confirmed_physical_sales=evidence, case_id="case-1234",
    )
    assert not joined.issue_codes, joined.issue_codes
    buyouts = [event for event in joined.events if event.event_kind is Kind.BUYOUT]
    assert len(buyouts) == 1
    assert buyouts[0].source.value == "FBO_CSV"
    assert buyouts[0].time_precision == "INSTANT"
    assert len(joined.events) == 2  # one dispatch and one deduplicated buyout


def test_saved_physical_sales_conflicts_with_fbo_quantity_and_stays_a_gap():
    evidence = _physical_sales(quantity=3)
    fbo = _fbo(("posting-1", SCOPE.sku, "2", "Доставлен", "2026-11-06 10:00:00", "2026-11-07 12:00:00"))
    result = NORMALIZER.normalize(
        scope=SCOPE, timezone_name="Europe/Moscow", model_start=date(2026, 11, 6),
        fbo_document=fbo, confirmed_physical_sales=evidence, case_id="case-1234",
    )
    assert "EVENT_DUPLICATE_CONFLICT" in {issue.value for issue in result.issue_codes}
