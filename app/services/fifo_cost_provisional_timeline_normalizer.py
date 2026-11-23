"""Redacted event candidates and aggregate anchors for provisional FIFO replay."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from hashlib import sha256
from types import MappingProxyType
from typing import Mapping

from services.fifo_cost_cutoff_bridge_service import (
    FifoDocumentedPhysicalSaleDocument,
    FifoPhysicalSaleDocumentConfirmation,
)
from services.fifo_cost_provisional_fbo_csv_import_service import ProvisionalFboDocument
from services.fifo_cost_provisional_movements_import_service import ProvisionalMovementsDocument
from services.fifo_cost_provisional_timeline_contracts import (
    ProvisionalEventSource,
    ProvisionalTimelineAnchor,
    ProvisionalTimelineEvent,
    ProvisionalTimelineEventKind as Kind,
    ProvisionalTimelineIssue as Issue,
    ProvisionalStockZone,
    scope_fingerprint,
)
from services.fifo_cost_transition_contracts import (
    EvidenceCompleteness,
    PeriodProvenance,
    ReportEvidence,
    ReportType,
    ScopeIdentity,
    normalize_store_timezone,
)


@dataclass(frozen=True, slots=True)
class ProvisionalTimelineNormalizationResult:
    events: tuple[ProvisionalTimelineEvent, ...]
    anchors: tuple[ProvisionalTimelineAnchor, ...]
    issue_codes: tuple[Issue, ...]
    scope_fingerprint: str | None
    posting_capacities: Mapping[str, int] = field(default_factory=dict)
    read_only: bool = True
    factual_writes: int = 0

    def __post_init__(self):
        object.__setattr__(
            self, "posting_capacities", MappingProxyType(dict(self.posting_capacities)),
        )

class FifoCostProvisionalTimelineNormalizer:
    """Combines event-level sources without promoting aggregates to events."""

    def normalize(self, *, scope, timezone_name, model_start, fbo_document=None,
                  movement_document=None, confirmed_reports=(),
                  confirmed_physical_sales=None, physical_sales_status=None,
                  case_id=None):
        if not isinstance(scope, ScopeIdentity):
            return self._result((), (), (Issue.FBO_SCOPE_MISMATCH,), None)
        try:
            timezone_name = normalize_store_timezone(timezone_name)
            if not isinstance(model_start, date):
                raise ValueError
            expected_scope = scope_fingerprint(scope, timezone_name)
        except (TypeError, ValueError):
            return self._result((), (), (Issue.FBO_SCOPE_MISMATCH,), None)

        issues: set[Issue] = set()
        anchors = self._anchors(
            confirmed_reports, scope=scope, timezone_name=timezone_name,
            expected_scope=expected_scope, issues=issues,
        )
        fbo_by_posting = {}
        if fbo_document is not None:
            if (not isinstance(fbo_document, ProvisionalFboDocument)
                    or fbo_document.scope_fingerprint != expected_scope
                    or fbo_document.timezone_name != timezone_name):
                issues.add(Issue.FBO_SCOPE_MISMATCH)
            else:
                for row in fbo_document.rows:
                    if row.finance_sku != scope.sku or row.posting_key in fbo_by_posting:
                        issues.add(Issue.FBO_SCOPE_MISMATCH)
                        continue
                    fbo_by_posting[row.posting_key] = row
        owner_events = ()
        if movement_document is not None:
            if (not isinstance(movement_document, ProvisionalMovementsDocument)
                    or movement_document.scope_fingerprint != expected_scope
                    or movement_document.timezone_name != timezone_name):
                issues.add(Issue.MOVEMENT_SCOPE_MISMATCH)
            else:
                owner_events = movement_document.events
        if physical_sales_status not in {None, "CONFIRMED", "MISSING", "NOT_CONFIGURED"}:
            issues.add(Issue.SAVED_EVIDENCE_UNAVAILABLE)
        physical_events = self._physical_sale_events(
            confirmed_physical_sales,
            scope=scope,
            timezone_name=timezone_name,
            expected_scope=expected_scope,
            model_start=model_start,
            case_id=case_id,
            fbo_by_posting=fbo_by_posting,
            issues=issues,
        )

        opening_links = {}
        return_units = {}
        accepted_owner_events = []
        for event in owner_events:
            if (event.scope_fingerprint != expected_scope or event.finance_sku != scope.sku):
                issues.add(Issue.MOVEMENT_SCOPE_MISMATCH)
                continue
            if event.event_kind is Kind.OPENING_TRANSIT_LINK:
                row = fbo_by_posting.get(event.posting_key)
                if row is None:
                    issues.add(Issue.EVENT_REFERENCE_UNMATCHED)
                    continue
                if row.dispatch is None or row.dispatch.local_date >= model_start:
                    issues.add(Issue.EVENT_ORDER_CONFLICT)
                    continue
                if (row.dispatch.local_date != event.local_date
                        or (row.dispatch.utc_timestamp is not None
                            and row.dispatch.utc_timestamp != event.effective_at_utc)):
                    issues.add(Issue.EVENT_ORDER_CONFLICT)
                    continue
                opening_links[event.posting_key] = opening_links.get(event.posting_key, 0) + event.quantity
                if opening_links[event.posting_key] > row.quantity:
                    issues.add(Issue.EVENT_QUANTITY_EXCEEDS_POSTING)
                    continue
            elif event.event_kind in {Kind.NON_BUYOUT_RESTOCK, Kind.SALE_RETURN_RESTOCK}:
                row = fbo_by_posting.get(event.posting_key)
                if row is None:
                    issues.add(Issue.EVENT_REFERENCE_UNMATCHED)
                    continue
                expected_status = "CANCELLED" if event.event_kind is Kind.NON_BUYOUT_RESTOCK else "DELIVERED"
                if row.status_kind != expected_status:
                    issues.add(Issue.EVENT_STATUS_MISMATCH)
                    continue
                return_units[event.posting_key] = return_units.get(event.posting_key, 0) + event.quantity
                if return_units[event.posting_key] > row.quantity:
                    issues.add(Issue.EVENT_QUANTITY_EXCEEDS_POSTING)
                    continue
            if (event.event_kind is not Kind.OPENING_TRANSIT_LINK
                    and event.local_date < model_start):
                # The opening snapshot already includes events before this
                # window. Keep their exact source validation but do not replay
                # them a second time.
                continue
            accepted_owner_events.append(event)

        fbo_events = []
        for posting_key, row in fbo_by_posting.items():
            if row.dispatch is None:
                issues.add(Issue.FBO_DISPATCH_TIME_MISSING)
            elif row.dispatch.local_date < model_start:
                cancelled_after_start = any(
                    event.event_kind is Kind.NON_BUYOUT_RESTOCK
                    and event.posting_key == posting_key
                    and event.local_date >= model_start
                    for event in accepted_owner_events
                )
                still_open_at_start = (
                    row.status_kind != "CANCELLED"
                    and (row.delivered is None or row.delivered.local_date >= model_start)
                ) or cancelled_after_start
                linked_units = opening_links.get(posting_key, 0)
                if still_open_at_start and linked_units != row.quantity:
                    issues.add(Issue.FBO_OPENING_LINK_REQUIRED)
            else:
                fbo_events.append(self._fbo_event(
                    fbo_document, scope, expected_scope, posting_key, row,
                    Kind.BUYER_DISPATCH, row.dispatch,
                ))
            if row.status_kind == "DELIVERED":
                if row.delivered is None:
                    issues.add(Issue.FBO_DELIVERY_TIME_MISSING)
                elif row.delivered.local_date >= model_start:
                    buyout_quantity = (
                        opening_links.get(posting_key, 0)
                        if row.dispatch is not None and row.dispatch.local_date < model_start
                        else row.quantity
                    )
                    if buyout_quantity <= 0:
                        issues.add(Issue.FBO_OPENING_LINK_REQUIRED)
                        continue
                    fbo_events.append(self._fbo_event(
                        fbo_document, scope, expected_scope, posting_key, row,
                        Kind.BUYOUT, row.delivered, quantity=buyout_quantity,
                    ))
            elif row.status_kind == "CANCELLED":
                if return_units.get(posting_key, 0) < row.quantity:
                    issues.add(Issue.FBO_CANCELLED_UNRESOLVED)
            elif row.status_kind == "UNKNOWN":
                issues.add(Issue.FBO_UNKNOWN_STATUS)

        combined, duplicate_issues = self._deduplicate(
            fbo_events + list(physical_events) + accepted_owner_events,
        )
        issues.update(duplicate_issues)
        if anchors and not combined:
            issues.add(Issue.REPORTS_ARE_AGGREGATE_ONLY)
        return self._result(
            tuple(sorted(combined, key=self._sort_key)), anchors,
            tuple(sorted(issues, key=lambda item: item.value)), expected_scope,
            {key: row.quantity for key, row in fbo_by_posting.items()},
        )

    @classmethod
    def _fbo_event(cls, document, scope, expected_scope, posting_key, row, kind, moment,
                   *, quantity=None):
        payload = f"fbo:{document.document_fingerprint}:{posting_key}:{kind.value}"
        event_key = sha256(payload.encode("utf-8")).hexdigest()
        source_key = sha256(document.document_fingerprint.encode("ascii")).hexdigest()
        return ProvisionalTimelineEvent(
            event_key=event_key,
            source_key=source_key,
            scope_fingerprint=expected_scope,
            event_kind=kind,
            finance_sku=scope.sku,
            quantity=row.quantity if quantity is None else quantity,
            local_date=moment.local_date,
            effective_at_utc=moment.utc_timestamp,
            time_precision=moment.precision,
            source=ProvisionalEventSource.FBO_CSV,
            posting_key=posting_key,
        )

    @classmethod
    def _anchors(cls, reports, *, scope, timezone_name, expected_scope, issues):
        if reports is None:
            issues.add(Issue.SAVED_EVIDENCE_UNAVAILABLE)
            return ()
        anchors = []
        try:
            for item in reports:
                report = item.get("report") if isinstance(item, dict) else item
                if (not isinstance(report, ReportEvidence)
                        or report.report_type not in {ReportType.TURNOVER, ReportType.STOCK_MANAGEMENT}
                        or report.metadata.scope != scope
                        or report.metadata.store_timezone != timezone_name
                        or report.metadata.completeness is not EvidenceCompleteness.COMPLETE
                        or report.period_provenance is not PeriodProvenance.OWNER_CONFIRMED
                        or not report.period_from or not report.period_to):
                    issues.add(Issue.SAVED_EVIDENCE_UNAVAILABLE)
                    continue
                fields = report.normalized_fields
                # Whitelist only aggregate integers/booleans; report rows and
                # arbitrary importer metadata are never projected as events.
                names = (
                    ("opening_total", "closing_total", "redeemed_units", "receipts_total",
                     "expenses_total", "reported_balance_difference")
                    if report.report_type is ReportType.TURNOVER else
                    ("available_units", "fbs_return_available_units", "removed_from_sale_units")
                )
                aggregate_fields = {}
                for name in names:
                    value = fields.get(name)
                    if type(value) is int and 0 <= value <= 1_000_000:
                        aggregate_fields[name] = value
                anchors.append(ProvisionalTimelineAnchor(
                    report_type=report.report_type.value,
                    file_fingerprint=report.file_sha256,
                    period_from=report.period_from,
                    period_to=report.period_to,
                    scope_fingerprint=expected_scope,
                    aggregate_fields=aggregate_fields,
                ))
        except (TypeError, ValueError, AttributeError):
            issues.add(Issue.SAVED_EVIDENCE_UNAVAILABLE)
        anchors.sort(key=lambda anchor: (
            anchor.period_from, anchor.period_to, anchor.report_type,
            anchor.file_fingerprint,
        ))
        versions = {}
        for anchor in anchors:
            key = (anchor.report_type, anchor.period_from, anchor.period_to)
            prior = versions.get(key)
            if prior is not None and prior != anchor.file_fingerprint:
                issues.add(Issue.SAVED_REPORT_VERSION_CONFLICT)
            versions[key] = anchor.file_fingerprint
        return tuple(anchors)

    @staticmethod
    def _physical_sale_events(
        evidence, *, scope, timezone_name, expected_scope, model_start,
        case_id, fbo_by_posting, issues,
    ):
        if evidence is None:
            return ()
        try:
            document, confirmation = evidence
            if (not isinstance(document, FifoDocumentedPhysicalSaleDocument)
                    or not isinstance(confirmation, FifoPhysicalSaleDocumentConfirmation)
                    or document.scope != scope
                    or confirmation.scope != scope
                    or document.metadata.store_timezone != timezone_name
                    or confirmation.metadata.store_timezone != timezone_name
                    or document.metadata.completeness is not EvidenceCompleteness.COMPLETE
                    or confirmation.metadata.completeness is not EvidenceCompleteness.COMPLETE
                    or document.document_fingerprint != confirmation.document_fingerprint
                    or document.case_id != case_id
                    or confirmation.case_id != case_id
                    or confirmation.owner_id != scope.owner_id
                    or confirmation.physical_date_semantics != "PHYSICAL_OUTFLOW"
                    or confirmation.physical_date_precision != "STORE_LOCAL_DATE"
                    or confirmation.physical_date_timezone != timezone_name):
                raise ValueError("scope")
            row_refs = tuple(sorted(row.row_reference for row in document.rows))
            if (tuple(sorted(confirmation.confirmed_row_references)) != row_refs
                    or "posting_number" not in confirmation.confirmed_fields
                    or "finance_sku" not in confirmation.confirmed_fields
                    or "quantity" not in confirmation.confirmed_fields
                    or "physical_effective_date" not in confirmation.confirmed_fields):
                raise ValueError("confirmation")
            source_key = sha256(document.document_fingerprint.encode("ascii")).hexdigest()
            events = []
            for row in document.rows:
                if row.finance_sku != scope.sku:
                    raise ValueError("sku")
                effective_date = date.fromisoformat(row.physical_effective_date)
                if effective_date < model_start:
                    continue
                posting_key = sha256(row.posting_number.encode("utf-8")).hexdigest()
                fbo_row = fbo_by_posting.get(posting_key)
                if fbo_by_posting and fbo_row is None:
                    issues.add(Issue.EVENT_REFERENCE_UNMATCHED)
                    continue
                if fbo_row is not None and (
                    fbo_row.finance_sku != row.finance_sku
                    or fbo_row.quantity != row.quantity
                    or fbo_row.status_kind != "DELIVERED"
                    or fbo_row.delivered is None
                    or fbo_row.delivered.local_date != effective_date
                ):
                    issues.add(Issue.EVENT_DUPLICATE_CONFLICT)
                    continue
                event_key = sha256((
                    f"owner-sale-v1:{document.document_fingerprint}:"
                    f"{row.row_reference}"
                ).encode("utf-8")).hexdigest()
                events.append(ProvisionalTimelineEvent(
                    event_key=event_key,
                    source_key=source_key,
                    scope_fingerprint=expected_scope,
                    event_kind=Kind.BUYOUT,
                    finance_sku=row.finance_sku,
                    quantity=row.quantity,
                    local_date=effective_date,
                    effective_at_utc=None,
                    time_precision="DAY",
                    source=ProvisionalEventSource.SAVED_TYPED_EVIDENCE,
                    posting_key=posting_key,
                ))
            return tuple(events)
        except (TypeError, ValueError, AttributeError):
            issues.add(Issue.SAVED_EVIDENCE_UNAVAILABLE)
            return ()

    @staticmethod
    def _deduplicate(events):
        buyouts_by_posting = {}
        conflicted_postings = set()
        issues = set()
        for event in events:
            if event.event_kind is not Kind.BUYOUT or event.posting_key is None:
                continue
            if event.posting_key in conflicted_postings:
                continue
            prior = buyouts_by_posting.get(event.posting_key)
            if prior is None:
                buyouts_by_posting[event.posting_key] = event
                continue
            same_event = (
                prior.quantity == event.quantity
                and prior.local_date == event.local_date
            )
            if not same_event:
                issues.add(Issue.EVENT_DUPLICATE_CONFLICT)
                conflicted_postings.add(event.posting_key)
                buyouts_by_posting[event.posting_key] = None
            elif prior.source != event.source:
                # Prefer the higher precision of the exact per-posting source.
                if event.time_precision == "INSTANT" and prior.time_precision != "INSTANT":
                    buyouts_by_posting[event.posting_key] = event
        buyouts = [event for event in buyouts_by_posting.values() if event is not None]
        events = [event for event in events if event.event_kind is not Kind.BUYOUT] + buyouts
        by_signature = {}
        conflicts = set(issues)
        for event in events:
            signature = (
                event.scope_fingerprint, event.event_kind, event.posting_key,
                event.finance_sku, event.quantity, event.local_date,
                event.effective_at_utc, event.stock_zone, event.resellable,
            )
            prior = by_signature.get(signature)
            if prior is None:
                by_signature[signature] = event
            elif prior.source != event.source:
                # The same exact event in two documents is one physical move.
                continue
            elif prior.event_key != event.event_key:
                conflicts.add(Issue.EVENT_DUPLICATE_CONFLICT)
        return tuple(by_signature.values()), conflicts

    @staticmethod
    def _sort_key(event):
        return (
            event.local_date.isoformat(),
            event.effective_at_utc.isoformat() if event.effective_at_utc else "",
            event.event_kind.value,
            event.event_key,
        )

    @staticmethod
    def _result(events, anchors, issues, scope_digest, posting_capacities=None):
        return ProvisionalTimelineNormalizationResult(
            events=tuple(events), anchors=tuple(anchors),
            issue_codes=tuple(issues), scope_fingerprint=scope_digest,
            posting_capacities=posting_capacities or {},
            read_only=True, factual_writes=0,
        )
