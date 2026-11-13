"""Bounded, deterministic coordination for immutable FIFO allocations.

This service is intentionally side-effect free. A caller must provide source,
physical-time, event-order, and inventory-cutoff evidence before a replay can be
complete. The repository separately checks the event-stream revision and
current cutoff in one SQLite transaction before it publishes allocation rows.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
import hashlib
import json
from typing import Iterable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from services.fifo_cost_allocation_service import (
    FifoCostAllocationService,
    FifoCostLayer,
    FifoOutflowEvent,
    FifoOpenCostRate,
    FifoRateBoundaryEvent,
    FifoRestockEvent,
    FifoSaleEvent,
)


def _valid_digest(value):
    return (
        isinstance(value, str) and len(value) == 64
        and all(char in "0123456789abcdef" for char in value)
    )


@dataclass(frozen=True)
class FifoDatedAllocationEvent:
    """A core allocation event plus evidence needed to establish causal order."""

    event: FifoSaleEvent | FifoRestockEvent | FifoOutflowEvent
    effective_at: str | None
    effective_date: str | None
    source_identity_digest: str | None = None
    physical_time_confirmed: bool = False
    cutoff_bridge_confirmed: bool = False
    saleable_recovery_confirmed: bool = False
    movement_reason_confirmed: bool = False


@dataclass(frozen=True)
class FifoDatedRateBoundaryEvent:
    """A rate change with an explicit physical-time boundary and proof link."""

    event: FifoRateBoundaryEvent
    effective_at: str | None
    effective_date: str | None
    store_timezone: str
    boundary_kind: str
    boundary_evidence_fingerprint: str

    def __post_init__(self):
        if not isinstance(self.event, FifoRateBoundaryEvent):
            raise ValueError("FIFO_RATE_BOUNDARY_UNPROVEN")
        if not isinstance(self.store_timezone, str) or not self.store_timezone.strip():
            raise ValueError("FIFO_RATE_BOUNDARY_UNPROVEN")
        timezone_name = self.store_timezone.strip()
        try:
            ZoneInfo(timezone_name)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("FIFO_RATE_BOUNDARY_UNPROVEN") from None
        object.__setattr__(self, "store_timezone", timezone_name)
        if not _valid_digest(self.boundary_evidence_fingerprint):
            raise ValueError("FIFO_RATE_BOUNDARY_UNPROVEN")
        if self.boundary_evidence_fingerprint != self.event.reconciliation_evidence_fingerprint:
            raise ValueError("FIFO_RATE_BOUNDARY_UNPROVEN")

        if self.boundary_kind == "EXACT_INSTANT":
            if self.effective_at is None or self.effective_date is not None:
                raise ValueError("FIFO_RATE_BOUNDARY_UNPROVEN")
            if not isinstance(self.effective_at, str):
                raise ValueError("FIFO_RATE_BOUNDARY_UNPROVEN")
            try:
                parsed = datetime.fromisoformat(
                    self.effective_at.replace("Z", "+00:00"),
                )
            except ValueError:
                raise ValueError("FIFO_RATE_BOUNDARY_UNPROVEN") from None
            if parsed.tzinfo is None or parsed.utcoffset() is None:
                raise ValueError("FIFO_RATE_BOUNDARY_UNPROVEN")
            return

        if self.boundary_kind == "END_OF_LOCAL_DATE":
            if self.effective_at is not None or not isinstance(self.effective_date, str):
                raise ValueError("FIFO_RATE_BOUNDARY_UNPROVEN")
            try:
                parsed_date = date.fromisoformat(self.effective_date)
            except ValueError:
                raise ValueError("FIFO_RATE_BOUNDARY_UNPROVEN") from None
            if parsed_date.isoformat() != self.effective_date:
                raise ValueError("FIFO_RATE_BOUNDARY_UNPROVEN")
            return
        raise ValueError("FIFO_RATE_BOUNDARY_UNPROVEN")


class FifoCostReplayService:
    MAX_EVENTS = 100_000
    MAX_ORDER_VARIANTS_PER_GROUP = 120
    MAX_ORDER_ANALYSIS_WORK = 1_000_000
    _DIGEST = frozenset("0123456789abcdef")

    def __init__(self, allocation_service=None):
        self._allocation = allocation_service or FifoCostAllocationService()

    def preview(
        self,
        *,
        layers: Iterable[FifoCostLayer],
        events: Iterable[FifoDatedAllocationEvent],
        stream_revision: int,
        expected_allocation_revision: int,
        source_set_fingerprint: str,
        anchor_cutoff_date: str,
        anchor_status: str,
        cutoff_status: str,
        source_completeness: str,
        unsupported_event_count: int = 0,
        open_rate: FifoOpenCostRate | None = None,
        open_rate_effective_date: str | None = None,
        rate_boundaries: Iterable[FifoDatedRateBoundaryEvent] = (),
        complete_through: str | None = None,
        store_timezone: str | None = None,
    ) -> dict:
        """Create a bounded, stable preview; never mutates inventory state."""

        if type(stream_revision) is not int or stream_revision < 1:
            return self._error("FIFO_REVISION_CONFLICT")
        if type(expected_allocation_revision) is not int or expected_allocation_revision < 0:
            return self._error("FIFO_REVISION_CONFLICT")
        if not self._valid_digest(source_set_fingerprint):
            return self._error("FIFO_SOURCE_FINGERPRINT_INVALID")
        if self._date(anchor_cutoff_date) is None:
            return self._blocked("INVENTORY_CUTOFF_UNRECONCILED")
        if type(unsupported_event_count) is not int or unsupported_event_count < 0:
            return self._error("FIFO_EVENT_INVALID")

        normalized_layers = self._bounded_materialize(layers, 100_000)
        normalized_events = self._bounded_materialize(events, self.MAX_EVENTS)
        normalized_boundaries = self._bounded_materialize(
            rate_boundaries, self.MAX_EVENTS,
        )
        if (
            normalized_layers is None or normalized_events is None
            or normalized_boundaries is None
            or len(normalized_events) + len(normalized_boundaries) > self.MAX_EVENTS
        ):
            return self._blocked("FIFO_REPLAY_INPUT_LIMIT")
        if unsupported_event_count:
            return self._blocked("FIFO_REPLAY_UNSUPPORTED_EVENT")

        has_rate_boundaries = bool(normalized_boundaries)
        timezone_name = None
        if has_rate_boundaries:
            if open_rate is not None or open_rate_effective_date is not None:
                return self._blocked("FIFO_RATE_CHAIN_CONFLICT")
            if not isinstance(store_timezone, str) or not store_timezone.strip():
                return self._blocked("FIFO_RATE_BOUNDARY_UNPROVEN")
            timezone_name = store_timezone.strip()
            try:
                ZoneInfo(timezone_name)
            except (ZoneInfoNotFoundError, ValueError):
                return self._blocked("FIFO_RATE_BOUNDARY_UNPROVEN")
            if self._date(complete_through) is None:
                return self._blocked("FIFO_RATE_BOUNDARY_UNPROVEN")
            store_timezone = timezone_name
        ordered, ambiguous_groups, order_error = self._order_events(
            normalized_events,
            rate_boundaries=normalized_boundaries,
            anchor_cutoff_date=anchor_cutoff_date,
            store_timezone=timezone_name,
        )
        if order_error:
            return self._blocked(order_error)
        if has_rate_boundaries and any(
            (day := self._event_day(item, timezone_name)) is None
            or day > complete_through
            for item in ordered
        ):
            return self._blocked("FIFO_SOURCE_INCOMPLETE")
        if open_rate is not None:
            if self._date(open_rate_effective_date) is None:
                return self._blocked("FIFO_RATE_EFFECTIVE_DATE_UNAVAILABLE")
            if open_rate_effective_date <= anchor_cutoff_date:
                return self._blocked("FIFO_RATE_EFFECTIVE_DATE_CONFLICT")
        core_events = [item.event for item in ordered]

        result = self._allocation.allocate(
            layers=normalized_layers,
            events=core_events,
            anchor_status=anchor_status,
            cutoff_status=cutoff_status,
            event_order_status="PROVEN",
            source_completeness=source_completeness,
            open_rate=open_rate,
        )
        if open_rate is not None and result.complete:
            effective_days = {
                item.event.event_id: self._event_day(item)
                for item in ordered
                if isinstance(item.event, FifoSaleEvent)
            }
            if any(
                line.layer_id == open_rate.layer_id
                and effective_days.get(sale.event_id, "") <= open_rate_effective_date
                for sale in result.sale_allocations
                for line in sale.lines
            ):
                return self._blocked("FIFO_RATE_TRANSITION_ORDER_UNRESOLVED")
        if ambiguous_groups:
            order_error = self._ambiguous_order_error(
                ordered=ordered,
                ambiguous_groups=ambiguous_groups,
                normalized_layers=normalized_layers,
                baseline_result=result,
                anchor_status=anchor_status,
                cutoff_status=cutoff_status,
                source_completeness=source_completeness,
                open_rate=open_rate,
            )
            if order_error is not None:
                return self._blocked(order_error)
        status = "COMPLETE" if result.complete else self._status_for(result.reason_code)
        allocations = []
        for sale in result.sale_allocations:
            allocations.append({
                "event_id": sale.event_id,
                "quantity": sale.quantity,
                "total_cost_rub": format(sale.total_cost_rub, ".2f"),
                "lines": [self._allocation_line(
                    line, open_rate, include_rate_basis=has_rate_boundaries,
                ) for line in sale.lines],
            })
        outflows = []
        for outflow in result.outflow_allocations:
            outflows.append({
                "event_id": outflow.event_id,
                "quantity": outflow.quantity,
                "reason_code": outflow.reason_code,
                "estimated_value_rub": format(outflow.estimated_value_rub, ".2f"),
                "valuation_method": "FIFO_FINITE_LAYER_ESTIMATE",
                "lines": [self._allocation_line(
                    line, open_rate, include_rate_basis=has_rate_boundaries,
                ) for line in outflow.lines],
            })

        preview = {
            "error": False,
            "complete": result.complete,
            "status": status,
            "reason_code": result.reason_code,
            "cutoff_status": cutoff_status,
            "anchor_cutoff_date": anchor_cutoff_date,
            "open_rate_effective_date": open_rate_effective_date,
            "stream_revision": stream_revision,
            "expected_allocation_revision": expected_allocation_revision,
            "source_set_fingerprint": source_set_fingerprint,
            "total_cogs_rub": (
                format(result.total_cogs_rub, ".2f")
                if result.total_cogs_rub is not None else None
            ),
            "non_sale_outflow_value_rub": (
                format(result.non_sale_outflow_value_rub, ".2f")
                if result.non_sale_outflow_value_rub is not None else None
            ),
            "remaining_confirmed_units": result.remaining_confirmed_units,
            "restored_units": result.restored_units,
            "allocations": allocations,
            "outflows": outflows,
        }
        if has_rate_boundaries:
            rate_balances = {
                row.rate_change_id: {
                    "remaining_units": row.remaining_units,
                    "unit_cost_rub": format(row.unit_cost_rub, ".2f"),
                    "reconciliation_evidence_fingerprint": (
                        row.reconciliation_evidence_fingerprint
                    ),
                }
                for row in result.rate_balances
            }
            boundary_material = [{
                "event_id": item.event.event_id,
                "rate_change_id": item.event.new_rate_change_id,
                "unit_cost_rub": format(item.event.new_unit_cost_rub, ".2f"),
                "previous_rate_change_id": item.event.previous_rate_change_id,
                "previous_rate_remaining_units": item.event.previous_rate_remaining_units,
                "expected_older_finite_units": item.event.expected_older_finite_units,
                "effective_at": item.effective_at,
                "effective_date": item.effective_date,
                "store_timezone": item.store_timezone,
                "boundary_kind": item.boundary_kind,
                "evidence_fingerprint": item.boundary_evidence_fingerprint,
            } for item in ordered if isinstance(item, FifoDatedRateBoundaryEvent)]
            preview.update({
                "rate_balances": rate_balances,
                "complete_through": complete_through,
                "store_timezone": timezone_name,
                "rate_boundary_set_fingerprint": self._fingerprint({
                    "boundaries": sorted(
                        boundary_material,
                        key=lambda row: (row["effective_at"] or row["effective_date"], row["event_id"]),
                    ),
                }),
            })
        preview["preview_fingerprint"] = self._fingerprint(preview)
        return preview

    def _order_events(
        self, events, *, anchor_cutoff_date, rate_boundaries=(), store_timezone=None,
    ):
        if len(events) + len(rate_boundaries) > self.MAX_EVENTS:
            return None, (), "FIFO_REPLAY_INPUT_LIMIT"
        if any(not isinstance(item, FifoDatedAllocationEvent) for item in events):
            return None, (), "FIFO_EVENT_INVALID"
        if any(not isinstance(item, FifoDatedRateBoundaryEvent) for item in rate_boundaries):
            return None, (), "FIFO_RATE_BOUNDARY_UNPROVEN"

        unique_events = {}
        for item in events:
            event_id = getattr(item.event, "event_id", None)
            if not isinstance(event_id, str) or not event_id or len(event_id) > 160:
                return None, (), "FIFO_EVENT_INVALID"
            previous = unique_events.get(event_id)
            if previous is not None and previous != item:
                return None, (), "FIFO_EVENT_ID_DUPLICATE"
            unique_events[event_id] = item
        events = tuple(unique_events.values())

        unique_boundaries = {}
        for item in rate_boundaries:
            event_id = item.event.event_id
            previous = unique_boundaries.get(event_id)
            if previous is not None and previous != item:
                return None, (), "FIFO_RATE_CHAIN_CONFLICT"
            unique_boundaries[event_id] = item
        rate_boundaries = tuple(unique_boundaries.values())

        ids = []
        sale_digests = []
        return_digests = []
        movement_digests = []
        normalized = []
        all_items = [*events, *rate_boundaries]
        for item in all_items:
            event = item.event
            event_id = getattr(event, "event_id", None)
            if not isinstance(event_id, str) or not event_id or len(event_id) > 160:
                return None, (), "FIFO_EVENT_INVALID"
            ids.append(event_id)
            if isinstance(item, FifoDatedRateBoundaryEvent):
                if item.store_timezone != store_timezone:
                    return None, (), "FIFO_RATE_BOUNDARY_UNPROVEN"
                position = self._rate_boundary_position(item, store_timezone)
            else:
                position = self._effective_position(
                    item.effective_at, item.effective_date,
                    store_timezone=store_timezone,
                )
            if position is None:
                return None, (), (
                    "FIFO_RATE_BOUNDARY_UNPROVEN"
                    if isinstance(item, FifoDatedRateBoundaryEvent)
                    else "EVENT_ORDER_UNRESOLVED"
                )
            if position[1] <= anchor_cutoff_date:
                return None, (), (
                    "FIFO_RATE_BOUNDARY_UNPROVEN"
                    if isinstance(item, FifoDatedRateBoundaryEvent)
                    else "INVENTORY_CUTOFF_UNRECONCILED"
                )
            if isinstance(item, FifoDatedRateBoundaryEvent):
                continue
            if isinstance(event, FifoSaleEvent):
                if not self._valid_digest(item.source_identity_digest):
                    return None, (), "PHYSICAL_SALE_IDENTITY_UNCONFIRMED"
                if item.physical_time_confirmed is not True:
                    return None, (), "PHYSICAL_SALE_TIME_UNCONFIRMED"
                if item.cutoff_bridge_confirmed is not True:
                    return None, (), "INVENTORY_CUTOFF_UNRECONCILED"
                sale_digests.append(item.source_identity_digest)
            elif isinstance(event, FifoRestockEvent):
                if not self._valid_digest(item.source_identity_digest):
                    return None, (), "FIFO_RETURN_IDENTITY_UNCONFIRMED"
                if item.saleable_recovery_confirmed is not True:
                    return None, (), "FIFO_RETURN_SALEABLE_RECOVERY_UNCONFIRMED"
                if item.physical_time_confirmed is not True:
                    return None, (), "FIFO_RETURN_EFFECTIVE_DATE_UNAVAILABLE"
                if item.cutoff_bridge_confirmed is not True:
                    return None, (), "INVENTORY_CUTOFF_UNRECONCILED"
                return_digests.append(item.source_identity_digest)
            elif isinstance(event, FifoOutflowEvent):
                if not self._valid_digest(item.source_identity_digest):
                    return None, (), "FIFO_MOVEMENT_IDENTITY_UNCONFIRMED"
                if item.movement_reason_confirmed is not True:
                    return None, (), "FIFO_MOVEMENT_REASON_UNCONFIRMED"
                if item.physical_time_confirmed is not True:
                    return None, (), "FIFO_MOVEMENT_EFFECTIVE_DATE_UNAVAILABLE"
                if item.cutoff_bridge_confirmed is not True:
                    return None, (), "INVENTORY_CUTOFF_UNRECONCILED"
                movement_digests.append(item.source_identity_digest)
            else:
                return None, (), "FIFO_EVENT_INVALID"
            normalized.append((position, event_id, item, False))

        boundary_positions = {}
        for item in rate_boundaries:
            position = self._rate_boundary_position(item, store_timezone)
            position_key = position[0]
            prior = boundary_positions.get(position_key)
            if prior is not None and prior != item:
                return None, (), "FIFO_RATE_CHAIN_CONFLICT"
            boundary_positions[position_key] = item
            normalized.append((position, item.event.event_id, item, True))

        if len(set(ids)) != len(ids):
            return None, (), "FIFO_EVENT_ID_DUPLICATE"
        if len(set(sale_digests)) != len(sale_digests):
            return None, (), "FIFO_SALE_IDENTITY_DUPLICATE"
        if len(set(return_digests)) != len(return_digests):
            return None, (), "FIFO_RETURN_IDENTITY_DUPLICATE"
        if len(set(movement_digests)) != len(movement_digests):
            return None, (), "FIFO_MOVEMENT_IDENTITY_DUPLICATE"

        # Date-only evidence may occur anywhere on its calendar day.  When a
        # day also has timed rows, all rows for that day share one ambiguity
        # group; the proof routine preserves order among distinct instants.
        by_day = {}
        by_instant = {}
        for position, _, item, is_boundary in normalized:
            instant_key, day_key, is_date_only, phase = position
            is_end_of_day_boundary = (
                is_boundary and item.boundary_kind == "END_OF_LOCAL_DATE"
            )
            if not is_end_of_day_boundary:
                by_day.setdefault(day_key, []).append((position, item))
            if not is_date_only and not is_end_of_day_boundary:
                by_instant.setdefault((instant_key, phase), []).append((position, item))

        ambiguous_groups = []
        for rows in by_day.values():
            if any(
                position[2] and not (
                    isinstance(item, FifoDatedRateBoundaryEvent)
                    and item.boundary_kind == "END_OF_LOCAL_DATE"
                )
                for position, item in rows
            ):
                if len(rows) > 1:
                    ambiguous_groups.append(tuple(item for _, item in rows))
        for rows in by_instant.values():
            if len(rows) > 1 and not any(position[2] for position, _ in rows):
                ambiguous_groups.append(tuple(item for _, item in rows))

        ordered = [item for _, _, item, _ in sorted(
            normalized,
            key=lambda row: (row[0][0], row[0][3], row[1]),
        )]
        ordered_index = {item.event.event_id: index for index, item in enumerate(ordered)}
        ambiguous_groups.sort(key=lambda group: min(
            ordered_index[item.event.event_id] for item in group
        ))
        return ordered, tuple(ambiguous_groups), None

    def _ambiguous_order_error(
        self, *, ordered, ambiguous_groups, normalized_layers, baseline_result,
        anchor_status, cutoff_status, source_completeness, open_rate,
    ):
        baseline_signature = self._allocation_signature(baseline_result)
        analysis_work_used = 0
        for group in ambiguous_groups:
            variants, exceeded = self._bounded_tie_orderings(
                group, maximum=self.MAX_ORDER_VARIANTS_PER_GROUP,
            )
            if exceeded and baseline_result.complete:
                if self._single_layer_group_is_invariant(
                    ordered=ordered,
                    group=group,
                    normalized_layers=normalized_layers,
                    anchor_status=anchor_status,
                    cutoff_status=cutoff_status,
                    source_completeness=source_completeness,
                    open_rate=open_rate,
                ):
                    continue
            index_by_id = {
                item.event.event_id: index for index, item in enumerate(ordered)
            }
            indices = [index_by_id[item.event.event_id] for item in group]
            for variant in variants:
                candidate = list(ordered)
                for index, item in zip(indices, variant):
                    candidate[index] = item
                analysis_work_used += len(candidate)
                if analysis_work_used > self.MAX_ORDER_ANALYSIS_WORK:
                    return "FIFO_REPLAY_ORDER_ANALYSIS_LIMIT"
                result = self._allocation.allocate(
                    layers=normalized_layers,
                    events=[item.event for item in candidate],
                    anchor_status=anchor_status,
                    cutoff_status=cutoff_status,
                    event_order_status="PROVEN",
                    source_completeness=source_completeness,
                    open_rate=open_rate,
                )
                if self._allocation_signature(result) != baseline_signature:
                    return "EVENT_ORDER_UNRESOLVED"
            if exceeded:
                return "FIFO_REPLAY_ORDER_ANALYSIS_LIMIT"
        return None

    def _single_layer_group_is_invariant(
        self, *, ordered, group, normalized_layers, anchor_status,
        cutoff_status, source_completeness, open_rate,
    ):
        if open_rate is not None or any(
            isinstance(item, FifoDatedRateBoundaryEvent)
            or isinstance(item.event, FifoRestockEvent) for item in ordered
        ):
            return False
        if any(not isinstance(item.event, (FifoSaleEvent, FifoOutflowEvent)) for item in group):
            return False
        group_quantity = sum(item.event.quantity for item in group)
        ordered_index = {
            item.event.event_id: index for index, item in enumerate(ordered)
        }
        group_start = min(ordered_index[item.event.event_id] for item in group)
        prefix = [item.event for item in ordered[:group_start]]
        if any(
            not isinstance(layer, FifoCostLayer)
            or type(layer.quantity) is not int
            or layer.quantity < 0
            or not isinstance(layer.layer_id, str)
            for layer in normalized_layers
        ):
            return False
        remaining = {layer.layer_id: layer.quantity for layer in normalized_layers}
        if prefix:
            prefix_result = self._allocation.allocate(
                layers=normalized_layers,
                events=prefix,
                anchor_status=anchor_status,
                cutoff_status=cutoff_status,
                event_order_status="PROVEN",
                source_completeness=source_completeness,
                open_rate=None,
            )
            if not prefix_result.complete:
                return False
            for allocation in (*prefix_result.sale_allocations, *prefix_result.outflow_allocations):
                lines = allocation.lines
                for line in lines:
                    if line.layer_id in remaining:
                        remaining[line.layer_id] -= line.quantity
        for quantity in remaining.values():
            if quantity < 0:
                return False
        first_available = next(
            (remaining[layer.layer_id] for layer in normalized_layers
             if remaining.get(layer.layer_id, 0) > 0),
            0,
        )
        return first_available >= group_quantity

    @classmethod
    def _bounded_tie_orderings(cls, group, *, maximum):
        date_only = tuple(sorted(
            (item for item in group if cls._effective_position(
                item.effective_at, item.effective_date,
            )[2]),
            key=lambda item: item.event.event_id,
        ))
        timestamp_groups_by_instant = {}
        for item in group:
            position = cls._effective_position(item.effective_at, item.effective_date)
            if not position[2]:
                timestamp_groups_by_instant.setdefault(position[0], []).append(item)
        timestamp_groups = tuple(
            tuple(sorted(rows, key=lambda item: item.event.event_id))
            for _, rows in sorted(timestamp_groups_by_instant.items())
        )
        output = []
        exceeded = False

        def walk(remaining_dates, time_group_index, remaining_times, prefix):
            nonlocal exceeded
            if exceeded:
                return
            if not remaining_dates and time_group_index >= len(timestamp_groups):
                output.append(tuple(prefix))
                if len(output) > maximum:
                    exceeded = True
                return
            choices = list(remaining_dates)
            current_times = remaining_times
            current_index = time_group_index
            while not current_times and current_index < len(timestamp_groups):
                current_times = timestamp_groups[current_index]
                break
            choices.extend(current_times)
            for item in sorted(choices, key=lambda value: value.event.event_id):
                if item in remaining_dates:
                    next_dates = tuple(value for value in remaining_dates if value is not item)
                    walk(next_dates, current_index, current_times, [*prefix, item])
                else:
                    next_times = tuple(value for value in current_times if value is not item)
                    next_index = current_index
                    if not next_times:
                        next_index += 1
                        next_times = ()
                    walk(remaining_dates, next_index, next_times, [*prefix, item])

        walk(date_only, 0, (), [])
        if exceeded:
            return tuple(output[:maximum + 1]), True
        return tuple(output), False

    @staticmethod
    def _allocation_signature(result):
        def line_signature(line):
            return (
                line.layer_id, line.quantity, line.unit_cost_rub,
                line.total_cost_rub, line.origin_sale_event_id,
                line.basis_kind, line.rate_change_id,
            )

        sales = tuple(sorted((
            row.event_id, row.quantity, row.total_cost_rub,
            tuple(line_signature(line) for line in row.lines),
        ) for row in result.sale_allocations))
        outflows = tuple(sorted((
            row.event_id, row.quantity, row.reason_code, row.estimated_value_rub,
            tuple(line_signature(line) for line in row.lines),
        ) for row in result.outflow_allocations))
        return (
            result.status, result.complete, result.reason_code, sales, outflows,
            result.total_cogs_rub, result.non_sale_outflow_value_rub,
            result.inventory_restored_value_rub, result.restored_units,
            result.remaining_confirmed_units, result.total_available_units,
            result.next_unit_cost_rub, result.next_unit_cost_status,
            tuple((row.rate_change_id, row.unit_cost_rub, row.remaining_units,
                   row.reconciliation_evidence_fingerprint)
                  for row in result.rate_balances),
        )

    @staticmethod
    def _effective_position(effective_at, effective_date, *, store_timezone=None):
        if effective_at is not None:
            if not isinstance(effective_at, str):
                return None
            try:
                parsed = datetime.fromisoformat(effective_at.replace("Z", "+00:00"))
            except ValueError:
                return None
            if parsed.tzinfo is None or parsed.utcoffset() is None:
                return None
            if store_timezone is not None:
                try:
                    local_date = parsed.astimezone(ZoneInfo(store_timezone)).date()
                except (ZoneInfoNotFoundError, ValueError):
                    return None
                source_day = local_date.isoformat()
            else:
                source_day = parsed.astimezone(timezone.utc).date().isoformat()
            if effective_date is not None:
                if not isinstance(effective_date, str):
                    return None
                try:
                    if date.fromisoformat(effective_date).isoformat() != source_day:
                        return None
                except ValueError:
                    return None
            return (
                parsed.astimezone(timezone.utc).isoformat(timespec="microseconds"),
                effective_date or source_day, False, 0,
            )
        if not isinstance(effective_date, str):
            return None
        try:
            parsed_date = date.fromisoformat(effective_date)
        except ValueError:
            return None
        if parsed_date.isoformat() != effective_date:
            return None
        try:
            local_start = datetime.combine(
                parsed_date, time.min,
                tzinfo=ZoneInfo(store_timezone) if store_timezone else timezone.utc,
            )
        except (ZoneInfoNotFoundError, ValueError):
            return None
        return (
            local_start.astimezone(timezone.utc).isoformat(timespec="microseconds"),
            effective_date, True, 0,
        )

    @staticmethod
    def _rate_boundary_position(item, store_timezone):
        if not isinstance(item, FifoDatedRateBoundaryEvent):
            return None
        if item.store_timezone != store_timezone:
            return None
        try:
            zone = ZoneInfo(store_timezone)
            if item.boundary_kind == "END_OF_LOCAL_DATE":
                boundary_date = date.fromisoformat(item.effective_date)
                next_midnight = datetime.combine(
                    boundary_date + timedelta(days=1), time.min, tzinfo=zone,
                )
                return (
                    next_midnight.astimezone(timezone.utc).isoformat(
                        timespec="microseconds",
                    ),
                    item.effective_date,
                    False,
                    -1,
                )
            instant = datetime.fromisoformat(
                item.effective_at.replace("Z", "+00:00"),
            )
            if instant.tzinfo is None or instant.utcoffset() is None:
                return None
            local_day = instant.astimezone(zone).date().isoformat()
            return (
                instant.astimezone(timezone.utc).isoformat(timespec="microseconds"),
                local_day,
                False,
                0,
            )
        except (AttributeError, TypeError, ValueError, ZoneInfoNotFoundError):
            return None

    @staticmethod
    def _date(value):
        if not isinstance(value, str):
            return None
        try:
            parsed = date.fromisoformat(value)
        except ValueError:
            return None
        return parsed.isoformat() if parsed.isoformat() == value else None

    @classmethod
    def _event_day(cls, item, store_timezone=None):
        if isinstance(item, FifoDatedRateBoundaryEvent):
            position = cls._rate_boundary_position(item, store_timezone)
            return None if position is None else position[1]
        if item.effective_date is not None:
            return item.effective_date
        position = cls._effective_position(
            item.effective_at, None, store_timezone=store_timezone,
        )
        return None if position is None else position[1]

    @staticmethod
    def _bounded_materialize(values, maximum):
        try:
            result = []
            iterator = iter(values)
            for _ in range(maximum + 1):
                try:
                    result.append(next(iterator))
                except StopIteration:
                    return result
            return None
        except (TypeError, ValueError, OverflowError):
            return None

    @classmethod
    def _valid_digest(cls, value):
        return (
            isinstance(value, str)
            and len(value) == 64
            and all(char in cls._DIGEST for char in value)
        )

    @staticmethod
    def _status_for(reason):
        if reason in {
            "ANCHOR_UNCONFIRMED", "INVENTORY_CUTOFF_UNRECONCILED",
            "EVENT_ORDER_UNRESOLVED", "FIFO_SOURCE_INCOMPLETE",
            "PHYSICAL_SALE_IDENTITY_UNCONFIRMED",
            "PHYSICAL_SALE_TIME_UNCONFIRMED",
            "FIFO_REPLAY_UNSUPPORTED_EVENT",
            "FIFO_RATE_BOUNDARY_UNPROVEN",
            "FIFO_RATE_EFFECTIVE_DATE_UNAVAILABLE",
            "FIFO_RATE_TRANSITION_ORDER_UNRESOLVED",
            "FIFO_REPLAY_ORDER_ANALYSIS_LIMIT",
        }:
            return "SOURCE_BLOCKED"
        return "CONFLICT"

    @staticmethod
    def _allocation_line(line, open_rate, *, include_rate_basis=False):
        is_open_rate = (
            line.basis_kind == "OPEN_RATE"
            or (open_rate is not None and line.layer_id == open_rate.layer_id)
        )
        is_rate_basis = include_rate_basis and line.rate_change_id is not None
        result = {
            "layer_id": None if (is_open_rate or is_rate_basis) else line.layer_id,
            "rate_change_id": (
                line.rate_change_id or (line.layer_id if is_open_rate else None)
            ),
            "quantity": line.quantity,
            "unit_cost_rub": format(line.unit_cost_rub, ".2f"),
            "total_cost_rub": format(line.total_cost_rub, ".2f"),
            "origin_sale_event_id": line.origin_sale_event_id,
        }
        if include_rate_basis:
            result["basis_kind"] = line.basis_kind
            result["rate_change_id"] = line.rate_change_id
        return result

    @staticmethod
    def _fingerprint(payload):
        material = {
            key: value for key, value in payload.items()
            if key not in {"preview_fingerprint", "error"}
        }
        return hashlib.sha256(json.dumps(
            material, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")).hexdigest()

    @classmethod
    def _blocked(cls, reason):
        result = {
            "error": False,
            "complete": False,
            "status": "SOURCE_BLOCKED",
            "reason_code": reason,
            "cutoff_status": "UNRECONCILED",
            "stream_revision": None,
            "expected_allocation_revision": None,
            "source_set_fingerprint": None,
            "total_cogs_rub": None,
            "remaining_confirmed_units": None,
            "restored_units": None,
            "allocations": [],
        }
        result["preview_fingerprint"] = cls._fingerprint(result)
        return result

    @classmethod
    def _error(cls, reason):
        return {"error": True, "code": reason}
