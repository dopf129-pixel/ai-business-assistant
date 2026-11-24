"""Read-only readiness gate and result projection for a provisional FIFO timeline."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from collections.abc import Mapping

from services.fifo_cost_provisional_contracts import ProvisionalStatus
from services.fifo_cost_provisional_replay_service import FifoCostProvisionalReplayService
from services.fifo_cost_provisional_timeline_contracts import (
    ProvisionalStockZone,
    ProvisionalTimelineEventKind as Kind,
    ProvisionalTimelineIssue as TimelineIssue,
)
from services.fifo_cost_provisional_timeline_normalizer import (
    FifoCostProvisionalTimelineNormalizer,
)


@dataclass(frozen=True, slots=True)
class ProvisionalTimelineOutcome:
    """Only a fully reconciled stream exposes model money or sold quantities."""

    status: ProvisionalStatus
    issue_codes: tuple[str, ...] = ()
    period_from: str | None = None
    period_to: str | None = None
    supplied_events: int = 0
    processed_events: int = 0
    unprocessed_events: int = 0
    redeemed_units: int | None = None
    old_sold_units: int | None = None
    new_sold_units: int | None = None
    gross_cogs_rub: Decimal | None = None
    returned_units: int | None = None
    non_sale_removed_units: int | None = None
    non_sale_removed_cost_rub: Decimal | None = None
    ending_available_units: int | None = None
    ending_held_units: int | None = None
    ending_buyer_delivery_units: int | None = None
    read_only: bool = True
    factual_writes: int = 0


class FifoCostProvisionalTimelineService:
    """Turn selected, owner-scoped evidence into a gated non-authoritative model."""

    def __init__(self, *, normalizer=None, replay_service=None):
        self.normalizer = normalizer or FifoCostProvisionalTimelineNormalizer()
        self.replay_service = replay_service or FifoCostProvisionalReplayService()

    def calculate(
        self, *, scope, timezone_name, case_id, snapshot_report, movement_report,
        summary_result, fbo_document, fbo_coverage_from, fbo_coverage_to,
        movement_document=None, confirmed_reports=(), confirmed_physical_sales=None,
        physical_sales_status=None, owner_confirmed_coverage=False,
    ):
        if not isinstance(owner_confirmed_coverage, bool) or not owner_confirmed_coverage:
            return self._outcome(ProvisionalStatus.NEED_INPUT, "OWNER_COVERAGE_CONFIRMATION_REQUIRED")
        if summary_result is None or summary_result.status is not ProvisionalStatus.SUMMARY_RANGE:
            status = getattr(summary_result, "status", ProvisionalStatus.NEED_INPUT)
            if status not in {ProvisionalStatus.NEED_INPUT, ProvisionalStatus.SOURCE_CONFLICT}:
                status = ProvisionalStatus.NEED_INPUT
            code = "SUMMARY_INPUT_REQUIRED" if status is ProvisionalStatus.NEED_INPUT else "SUMMARY_SOURCE_CONFLICT"
            return self._outcome(status, code)
        if fbo_document is None:
            return self._outcome(ProvisionalStatus.NEED_INPUT, "FBO_CSV_REQUIRED")
        if (not isinstance(fbo_coverage_from, str) or not isinstance(fbo_coverage_to, str)
                or fbo_coverage_from != summary_result.period_from
                or fbo_coverage_to != summary_result.period_to):
            return self._outcome(ProvisionalStatus.NEED_INPUT, "FBO_COVERAGE_WINDOW_MISMATCH")
        try:
            period_from = date.fromisoformat(summary_result.period_from)
            period_to = date.fromisoformat(summary_result.period_to)
            model_start = period_from
            if model_start != date.fromisoformat(snapshot_report.period_to) + timedelta(days=1):
                raise ValueError
            if date.fromisoformat(movement_report.period_from) != period_from:
                raise ValueError
            if date.fromisoformat(movement_report.period_to) != period_to:
                raise ValueError
            opening = dict(summary_result.opening_buckets)
            closing = dict(summary_result.closing_buckets)
            if set(opening) != set(closing) or len(opening) != 8:
                raise ValueError
            old_cost = summary_result.old_cost_rub
            new_cost = summary_result.new_cost_rub
            if not isinstance(old_cost, Decimal) or not isinstance(new_cost, Decimal):
                raise ValueError
        except (AttributeError, TypeError, ValueError):
            return self._outcome(ProvisionalStatus.SOURCE_CONFLICT, "REPORT_BOUNDARY_INVALID")

        if physical_sales_status not in {None, "CONFIRMED", "MISSING", "NOT_CONFIGURED"}:
            return self._outcome(ProvisionalStatus.TIMELINE_GAP, "PHYSICAL_SALES_EVIDENCE_UNAVAILABLE")
        normalized = self.normalizer.normalize(
            scope=scope,
            timezone_name=timezone_name,
            model_start=model_start,
            model_end=period_to,
            fbo_document=fbo_document,
            movement_document=movement_document,
            confirmed_reports=confirmed_reports,
            confirmed_physical_sales=confirmed_physical_sales,
            physical_sales_status=physical_sales_status,
            case_id=case_id,
        )
        if normalized.issue_codes:
            return self._outcome(
                ProvisionalStatus.TIMELINE_GAP,
                *(issue.value for issue in normalized.issue_codes),
                period_from=model_start.isoformat(), period_to=period_to.isoformat(),
            )

        opening_delivery = opening.get("buyer_delivery", 0)
        linked_delivery = sum(
            event.quantity for event in normalized.events
            if event.event_kind is Kind.OPENING_TRANSIT_LINK
        )
        if linked_delivery > opening_delivery:
            return self._outcome(
                ProvisionalStatus.TIMELINE_GAP, "OPENING_DELIVERY_LINK_INCOMPLETE",
                period_from=model_start.isoformat(), period_to=period_to.isoformat(),
                supplied_events=len(normalized.events),
            )
        unlinked_delivery = opening_delivery - linked_delivery
        expected_held = {
            ProvisionalStockZone(key): value for key, value in opening.items()
            if key not in {"available", "buyer_delivery"}
        }
        try:
            replay = self.replay_service.replay(
                events=normalized.events,
                scope_fingerprint=normalized.scope_fingerprint,
                finance_sku=scope.sku,
                timezone_name=timezone_name,
                model_start=model_start,
                model_end=period_to,
                opening_available_units=opening["available"],
                opening_held_units_by_zone=expected_held,
                old_unit_cost_rub=old_cost,
                new_unit_cost_rub=new_cost,
                posting_capacities=normalized.posting_capacities,
            )
        except (TypeError, ValueError, AttributeError):
            return self._outcome(
                ProvisionalStatus.TIMELINE_GAP, "REPLAY_INPUT_INVALID",
                period_from=model_start.isoformat(), period_to=period_to.isoformat(),
                supplied_events=len(normalized.events),
            )
        progress = {
            "period_from": model_start.isoformat(), "period_to": period_to.isoformat(),
            "supplied_events": replay.supplied_event_count,
            "processed_events": replay.events_processed,
            "unprocessed_events": replay.unprocessed_event_count,
        }
        if not replay.complete:
            return self._outcome(
                ProvisionalStatus.TIMELINE_GAP,
                *(issue.value for issue in replay.issue_codes), **progress,
            )

        fields = movement_report.normalized_fields
        receipts = fields.get("receipt_components_by_column")
        expenses = fields.get("non_sale_expense_components_by_column")
        redeemed = fields.get("redeemed_units")
        if (not isinstance(receipts, Mapping) or not isinstance(expenses, Mapping)
                or type(redeemed) is not int):
            return self._outcome(
                ProvisionalStatus.SOURCE_CONFLICT, "MOVEMENT_REPORT_CONTROL_INVALID", **progress,
            )
        event_totals = {
            kind: sum(event.quantity for event in normalized.events if event.event_kind is kind)
            for kind in Kind
        }
        expected_supplies = receipts.get("L")
        expected_returns = receipts.get("M")
        expected_removals = sum(expenses.get(key, 0) for key in ("V", "W", "X"))
        if (event_totals[Kind.BUYOUT] != redeemed
                or event_totals[Kind.SUPPLY_RECEIVED] != expected_supplies
                or event_totals[Kind.SALE_RETURN_RESTOCK] != expected_returns
                or replay.non_sale_removed_units != expected_removals):
            return self._outcome(
                ProvisionalStatus.TIMELINE_GAP, "EVENT_TOTALS_DO_NOT_MATCH_REPORTS", **progress,
            )

        model_closing = {key: 0 for key in closing}
        model_closing["available"] = replay.available_units
        model_closing["buyer_delivery"] = replay.pending_reserve_units + unlinked_delivery
        for key, value in replay.held_units_by_zone.items():
            bucket = "buyer_return_transit" if key == "non_resellable_customer_return" else key
            if bucket not in model_closing:
                return self._outcome(
                    ProvisionalStatus.SOURCE_CONFLICT, "MODEL_CLOSING_BUCKET_UNKNOWN", **progress,
                )
            model_closing[bucket] += value
        if model_closing != closing:
            return self._outcome(
                ProvisionalStatus.SOURCE_CONFLICT, "CLOSING_BUCKETS_DO_NOT_MATCH", **progress,
            )

        old_units = new_units = 0
        for allocations in replay.bought_out_allocations.values():
            for allocation in allocations:
                if allocation.unit_cost_rub == old_cost and old_cost != new_cost:
                    old_units += allocation.quantity
                elif allocation.unit_cost_rub == new_cost and old_cost != new_cost:
                    new_units += allocation.quantity
                elif old_cost == new_cost:
                    old_units = new_units = None
                    break
            if old_units is None:
                break
        if old_units is not None and old_units + new_units != redeemed:
            return self._outcome(
                ProvisionalStatus.TIMELINE_GAP, "SOLD_LAYER_COSTS_UNCLASSIFIED", **progress,
            )
        return ProvisionalTimelineOutcome(
            status=ProvisionalStatus.TIMELINE_MODEL,
            issue_codes=(),
            **progress,
            redeemed_units=redeemed,
            old_sold_units=old_units,
            new_sold_units=new_units,
            gross_cogs_rub=replay.gross_buyout_cogs_rub,
            returned_units=replay.sale_returned_units,
            non_sale_removed_units=replay.non_sale_removed_units,
            non_sale_removed_cost_rub=replay.non_sale_removed_cost_rub,
            ending_available_units=replay.available_units,
            ending_held_units=sum(replay.held_units_by_zone.values()),
            ending_buyer_delivery_units=replay.pending_reserve_units + unlinked_delivery,
        )

    @staticmethod
    def _outcome(status, *issues, **values):
        return ProvisionalTimelineOutcome(
            status=status,
            issue_codes=tuple(dict.fromkeys(issues)),
            **values,
        )
