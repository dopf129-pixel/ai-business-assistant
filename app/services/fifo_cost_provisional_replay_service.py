"""Finite, deterministic FIFO replay for the non-authoritative timeline model.

This stage models new receipts, opening in-transit links and buyer dispatches.
Dispatch reserves a cost basis but is deliberately not an expense/COGS event.
It has no database, Ozon, Telegram, or factual FIFO dependencies.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from decimal import Decimal
from hashlib import sha256
from types import MappingProxyType
from typing import Iterable, Mapping
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from services.fifo_cost_provisional_timeline_contracts import (
    ProvisionalStockZone as Zone,
    ProvisionalTimelineEvent,
    ProvisionalTimelineEventKind as Kind,
    ProvisionalTimelineIssue as Issue,
)
from services.fifo_cost_transition_contracts import (
    TransitionContractError,
    normalize_digest,
    normalize_money,
    normalize_quantity,
    normalize_store_timezone,
)


CENT = Decimal("0.01")
ZERO = Decimal("0.00")
MAX_EVENTS = 100_000
MAX_UNITS = 1_000_000
MAX_UNIT_COST = Decimal("1000000000.00")


@dataclass(frozen=True, slots=True)
class ProvisionalFifoAllocation:
    layer_id: str
    quantity: int
    unit_cost_rub: Decimal
    total_cost_rub: Decimal


@dataclass(frozen=True, slots=True)
class ProvisionalFifoLayer:
    layer_id: str
    quantity: int
    unit_cost_rub: Decimal
    effective_date: date
    effective_at_utc: datetime | None
    source_event_key: str


@dataclass(frozen=True, slots=True)
class ProvisionalHeldFifoLayer(ProvisionalFifoLayer):
    stock_zone: Zone
    non_resellable_return: bool = False


@dataclass(frozen=True, slots=True)
class ProvisionalFifoReplayResult:
    """Replay outcome; ``complete`` only means the supplied stream was replayable.

    It does not attest source coverage, inventory reconciliation, factual FIFO
    readiness, or the final timeline status. Those gates belong to PF18.
    """
    status: str
    complete: bool
    issue_codes: tuple[Issue, ...]
    events_processed: int
    available_layers: tuple[ProvisionalFifoLayer, ...]
    held_layers: tuple[ProvisionalHeldFifoLayer, ...]
    opening_transit_reserves: Mapping[str, tuple[ProvisionalFifoAllocation, ...]]
    buyer_dispatch_reserves: Mapping[str, tuple[ProvisionalFifoAllocation, ...]]
    bought_out_allocations: Mapping[str, tuple[ProvisionalFifoAllocation, ...]]
    non_resellable_return_holds: Mapping[str, tuple[ProvisionalFifoAllocation, ...]]
    available_units: int
    held_units_by_zone: Mapping[str, int]
    buyer_dispatch_units_total: int
    pending_reserve_units: int
    pending_reserve_cost_rub: Decimal
    gross_buyout_cogs_rub: Decimal
    sale_returned_units: int
    non_buyout_restocked_units: int
    returned_cost_basis_rub: Decimal
    financial_cogs_reversal_rub: Decimal
    dispatch_cogs_rub: Decimal
    released_hold_units: int
    non_sale_removed_units: int
    non_sale_removed_cost_rub: Decimal
    non_sale_removal_allocations: Mapping[str, tuple[ProvisionalFifoAllocation, ...]]
    supplied_event_count: int
    unprocessed_event_count: int
    read_only: bool = True
    factual_writes: int = 0

    def __post_init__(self):
        object.__setattr__(self, "opening_transit_reserves", MappingProxyType(
            {key: tuple(value) for key, value in dict(self.opening_transit_reserves).items()}
        ))
        object.__setattr__(self, "buyer_dispatch_reserves", MappingProxyType(
            {key: tuple(value) for key, value in dict(self.buyer_dispatch_reserves).items()}
        ))
        object.__setattr__(self, "bought_out_allocations", MappingProxyType(
            {key: tuple(value) for key, value in dict(self.bought_out_allocations).items()}
        ))
        object.__setattr__(self, "non_resellable_return_holds", MappingProxyType(
            {key: tuple(value) for key, value in dict(self.non_resellable_return_holds).items()}
        ))
        object.__setattr__(self, "held_units_by_zone", MappingProxyType(
            dict(self.held_units_by_zone)
        ))
        object.__setattr__(self, "non_sale_removal_allocations", MappingProxyType(
            {key: tuple(value) for key, value in dict(self.non_sale_removal_allocations).items()}
        ))


class FifoCostProvisionalReplayService:
    """Replay finite stock layers and reserve dispatch costs without expensing them."""

    MAX_EVENTS = MAX_EVENTS
    MAX_UNITS = MAX_UNITS

    def replay(
        self,
        *,
        events: Iterable[ProvisionalTimelineEvent],
        scope_fingerprint: str,
        finance_sku: str,
        timezone_name: str,
        model_start: date,
        model_end: date,
        opening_available_units: int,
        old_unit_cost_rub: Decimal | str | int,
        new_unit_cost_rub: Decimal | str | int,
        posting_capacities: Mapping[str, int] | None = None,
        opening_held_units_by_zone: Mapping[str, int] | None = None,
    ) -> ProvisionalFifoReplayResult:
        issues: set[Issue] = set()
        try:
            scope_digest = normalize_digest(scope_fingerprint)
            timezone_name = normalize_store_timezone(timezone_name)
            store_zone = ZoneInfo(timezone_name)
            if (not isinstance(finance_sku, str) or not finance_sku.isdecimal()
                    or not isinstance(model_start, date) or isinstance(model_start, datetime)
                    or not isinstance(model_end, date) or isinstance(model_end, datetime)
                    or model_end < model_start):
                raise ValueError
            opening_units = normalize_quantity(opening_available_units)
            old_cost = normalize_money(old_unit_cost_rub)
            new_cost = normalize_money(new_unit_cost_rub)
            if (old_cost <= 0 or new_cost <= 0
                    or old_cost > MAX_UNIT_COST or new_cost > MAX_UNIT_COST):
                raise ValueError
        except (TypeError, ValueError, TransitionContractError, ZoneInfoNotFoundError):
            issues.add(Issue.TIMELINE_COST_INVALID)
            return self._empty_result(issues)

        if opening_units > self.MAX_UNITS:
            issues.add(Issue.TIMELINE_QUANTITY_LIMIT)
            return self._empty_result(issues)

        capacities = self._normalize_capacities(posting_capacities)
        if capacities is None:
            issues.add(Issue.TIMELINE_OPENING_LINK_INVALID)
            return self._empty_result(issues)
        opening_held = self._normalize_opening_held_units(opening_held_units_by_zone)
        if opening_held is None:
            issues.add(Issue.TIMELINE_OPENING_HELD_INVALID)
            return self._empty_result(issues)

        rows = self._bounded_events(events)
        if rows is None:
            issues.add(Issue.TIMELINE_QUANTITY_LIMIT)
            return self._empty_result(issues)

        unique_events = {}
        for event in rows:
            if not isinstance(event, ProvisionalTimelineEvent):
                issues.add(Issue.TIMELINE_UNSUPPORTED_EVENT)
                continue
            previous = unique_events.get(event.event_key)
            if previous is not None:
                if previous.safe_payload() != event.safe_payload():
                    issues.add(Issue.EVENT_DUPLICATE_CONFLICT)
                # An exact replay of the same normalized source event is idempotent.
                continue
            unique_events[event.event_key] = event

        if issues:
            return self._empty_result(issues)

        opening_links = []
        timeline_events = []
        for event in unique_events.values():
            if (event.scope_fingerprint != scope_digest or event.finance_sku != finance_sku):
                issues.add(Issue.TIMELINE_SCOPE_MISMATCH)
                continue
            if event.time_precision == "INSTANT":
                if (event.effective_at_utc is None
                        or event.effective_at_utc.astimezone(store_zone).date() != event.local_date):
                    issues.add(Issue.TIMESTAMP_PRECISION_INSUFFICIENT)
                    continue
            if event.event_kind is Kind.OPENING_TRANSIT_LINK:
                if event.local_date >= model_start:
                    issues.add(Issue.TIMELINE_OPENING_LINK_INVALID)
                else:
                    opening_links.append(event)
                continue
            if event.event_kind not in {
                Kind.SUPPLY_RECEIVED, Kind.BUYER_DISPATCH, Kind.BUYOUT,
                Kind.NON_BUYOUT_RESTOCK, Kind.SALE_RETURN_RESTOCK,
                Kind.RELEASE_HOLD, Kind.NON_SALE_REMOVE,
            }:
                issues.add(Issue.TIMELINE_UNSUPPORTED_EVENT)
                continue
            if event.local_date < model_start or event.local_date > model_end:
                issues.add(Issue.TIMELINE_EVENT_OUTSIDE_WINDOW)
                continue
            if (event.event_kind in {Kind.RELEASE_HOLD, Kind.NON_SALE_REMOVE}
                    and event.stock_zone is Zone.BUYER_DELIVERY):
                # Buyer-delivery stock must be moved through its exact posting lifecycle.
                issues.add(Issue.TIMELINE_UNSUPPORTED_EVENT)
                continue
            if event.event_kind is Kind.RELEASE_HOLD and event.stock_zone is Zone.AVAILABLE:
                issues.add(Issue.TIMELINE_UNSUPPORTED_EVENT)
                continue
            timeline_events.append(event)

        if issues:
            return self._empty_result(issues)

        ordered_events = sorted(timeline_events, key=self._event_sort_key)
        first_ambiguous_index = self._first_ambiguous_order_index(ordered_events)

        opening_by_posting = {}
        opening_quantities = {}
        for event in opening_links:
            posting_key = event.posting_key
            opening_quantities[posting_key] = opening_quantities.get(posting_key, 0) + event.quantity
            capacity = capacities.get(posting_key)
            if capacity is None or opening_quantities[posting_key] > capacity:
                issues.add(Issue.TIMELINE_OPENING_LINK_INVALID)
                continue
            allocation = self._allocation(
                layer_id=self._layer_id("opening", event.event_key),
                quantity=event.quantity,
                unit_cost=old_cost,
            )
            opening_by_posting.setdefault(posting_key, []).append(allocation)
        if issues:
            return self._empty_result(issues)

        opening_postings = set(opening_by_posting)
        dispatch_postings_seen = set(opening_postings)

        total_stream_units = opening_units + sum(opening_held.values()) + sum(
            event.quantity for event in timeline_events
            if event.event_kind is Kind.SUPPLY_RECEIVED
        )
        total_stream_units += sum(sum(a.quantity for a in values)
                                  for values in opening_by_posting.values())
        if total_stream_units > self.MAX_UNITS:
            issues.add(Issue.TIMELINE_QUANTITY_LIMIT)
            return self._empty_result(issues)

        opening_layer_id = self._layer_id(
            "initial", sha256(f"{scope_digest}:{model_start.isoformat()}".encode()).hexdigest()
        )
        available = []
        if opening_units:
            initial_layer = ProvisionalFifoLayer(
                layer_id=opening_layer_id,
                quantity=opening_units,
                unit_cost_rub=old_cost,
                effective_date=date.min,
                effective_at_utc=None,
                source_event_key=opening_layer_id,
            )
            available.append(initial_layer)
        layer_origins = {layer.layer_id: layer for layer in available}
        held = []
        for zone, quantity in opening_held.items():
            if quantity <= 0:
                continue
            layer_id = self._layer_id(
                "opening-held",
                sha256(f"{scope_digest}:{model_start.isoformat()}:{zone.value}".encode()).hexdigest(),
            )
            origin = ProvisionalFifoLayer(
                layer_id=layer_id,
                quantity=quantity,
                unit_cost_rub=old_cost,
                effective_date=date.min,
                effective_at_utc=None,
                source_event_key=layer_id,
            )
            layer_origins[layer_id] = origin
            held.append(ProvisionalHeldFifoLayer(
                layer_id=origin.layer_id,
                quantity=origin.quantity,
                unit_cost_rub=origin.unit_cost_rub,
                effective_date=origin.effective_date,
                effective_at_utc=origin.effective_at_utc,
                source_event_key=origin.source_event_key,
                stock_zone=zone,
            ))
        for event in opening_links:
            allocation = next(
                item for item in opening_by_posting[event.posting_key]
                if item.layer_id == self._layer_id("opening", event.event_key)
            )
            layer_origins[allocation.layer_id] = ProvisionalFifoLayer(
                layer_id=allocation.layer_id,
                quantity=allocation.quantity,
                unit_cost_rub=allocation.unit_cost_rub,
                effective_date=event.local_date,
                effective_at_utc=event.effective_at_utc,
                source_event_key=event.event_key,
            )
        dispatch_reserves = {}
        active_reserves = {key: list(value) for key, value in opening_by_posting.items()}
        bought_out = {}
        non_buyout_restock_postings = set()
        sale_returned_by_line = {}
        dispatch_units = 0
        gross_buyout_cogs = ZERO
        sale_returned_units = 0
        non_buyout_restocked_units = 0
        returned_cost_basis = ZERO
        non_sale_removed_units = 0
        non_sale_removed_cost = ZERO
        non_sale_allocations = {}
        processed = 0

        released_hold_units = 0
        for event_index, event in enumerate(ordered_events):
            if first_ambiguous_index is not None and event_index == first_ambiguous_index:
                issues.add(Issue.TIMELINE_EVENT_ORDER_AMBIGUOUS)
                break

            if event.event_kind is Kind.SUPPLY_RECEIVED:
                if event.stock_zone is Zone.AVAILABLE:
                    layer = ProvisionalFifoLayer(
                        layer_id=self._layer_id("receipt", event.event_key),
                        quantity=event.quantity,
                        unit_cost_rub=new_cost,
                        effective_date=event.local_date,
                        effective_at_utc=event.effective_at_utc,
                        source_event_key=event.event_key,
                    )
                    if layer.layer_id in layer_origins:
                        issues.add(Issue.EVENT_DUPLICATE_CONFLICT)
                        break
                    layer_origins[layer.layer_id] = layer
                    available.append(layer)
                else:
                    layer = ProvisionalFifoLayer(
                        layer_id=self._layer_id("receipt", event.event_key),
                        quantity=event.quantity,
                        unit_cost_rub=new_cost,
                        effective_date=event.local_date,
                        effective_at_utc=event.effective_at_utc,
                        source_event_key=event.event_key,
                    )
                    if layer.layer_id in layer_origins:
                        issues.add(Issue.EVENT_DUPLICATE_CONFLICT)
                        break
                    layer_origins[layer.layer_id] = layer
                    held.append(ProvisionalHeldFifoLayer(
                        layer_id=layer.layer_id,
                        quantity=layer.quantity,
                        unit_cost_rub=layer.unit_cost_rub,
                        effective_date=layer.effective_date,
                        effective_at_utc=layer.effective_at_utc,
                        source_event_key=layer.source_event_key,
                        stock_zone=event.stock_zone,
                    ))
                processed += 1
                continue

            if event.event_kind is Kind.BUYER_DISPATCH:
                if (event.posting_key in dispatch_postings_seen
                        or event.posting_key in bought_out):
                    issues.add(Issue.TIMELINE_DUPLICATE_POSTING)
                    break
                capacity = capacities.get(event.posting_key)
                if capacity is None or event.quantity > capacity:
                    issues.add(Issue.TIMELINE_DUPLICATE_POSTING)
                    break
                dispatch_postings_seen.add(event.posting_key)
                remaining = event.quantity
                allocations = []
                next_available = []
                for layer in available:
                    if remaining <= 0:
                        next_available.append(layer)
                        continue
                    taken = min(layer.quantity, remaining)
                    if taken:
                        allocations.append(self._allocation(
                            layer_id=layer.layer_id,
                            quantity=taken,
                            unit_cost=layer.unit_cost_rub,
                        ))
                        remaining -= taken
                    if layer.quantity > taken:
                        next_available.append(ProvisionalFifoLayer(
                            layer_id=layer.layer_id,
                            quantity=layer.quantity - taken,
                            unit_cost_rub=layer.unit_cost_rub,
                            effective_date=layer.effective_date,
                            effective_at_utc=layer.effective_at_utc,
                            source_event_key=layer.source_event_key,
                        ))
                if remaining:
                    issues.add(Issue.TIMELINE_NEGATIVE_AVAILABLE_STOCK)
                    break
                available = next_available
                dispatch_reserves[event.posting_key] = list(allocations)
                active_reserves[event.posting_key] = list(allocations)
                dispatch_units += event.quantity
            elif event.event_kind is Kind.BUYOUT:
                if event.posting_key in bought_out:
                    issues.add(Issue.TIMELINE_BUYOUT_DUPLICATE)
                    break
                if event.posting_key in non_buyout_restock_postings:
                    issues.add(Issue.TIMELINE_RESTOCK_AFTER_BUYOUT)
                    break
                reserve = active_reserves.get(event.posting_key)
                if reserve is None:
                    issues.add(Issue.TIMELINE_BUYOUT_UNMATCHED)
                    break
                if sum(item.quantity for item in reserve) != event.quantity:
                    issues.add(Issue.TIMELINE_BUYOUT_QUANTITY_MISMATCH)
                    break
                bought_out[event.posting_key] = tuple(reserve)
                gross_buyout_cogs += sum(
                    (item.total_cost_rub for item in reserve), ZERO,
                )
                active_reserves.pop(event.posting_key, None)
                dispatch_reserves.pop(event.posting_key, None)
            elif event.event_kind in {Kind.NON_BUYOUT_RESTOCK, Kind.SALE_RETURN_RESTOCK}:
                if event.event_kind is Kind.NON_BUYOUT_RESTOCK:
                    if event.posting_key in bought_out:
                        issues.add(Issue.TIMELINE_RESTOCK_AFTER_BUYOUT)
                        break
                    reserve = active_reserves.get(event.posting_key)
                    if reserve is None:
                        issues.add(
                            Issue.TIMELINE_RESTOCK_AFTER_BUYOUT
                            if event.posting_key in bought_out
                            else Issue.TIMELINE_RESTOCK_UNMATCHED
                        )
                        break
                    reserve_units = sum(item.quantity for item in reserve)
                    if event.quantity > reserve_units:
                        issues.add(Issue.TIMELINE_RESTOCK_QUANTITY_EXCEEDS_RESERVE)
                        break
                    if (event.quantity < reserve_units and len(reserve) != 1):
                        issues.add(Issue.TIMELINE_RETURN_ALLOCATION_AMBIGUOUS)
                        break
                    restored = self._take_reserve_allocation(reserve, event.quantity)
                    if event.quantity == reserve_units:
                        active_reserves.pop(event.posting_key, None)
                        dispatch_reserves.pop(event.posting_key, None)
                    else:
                        active_reserves[event.posting_key] = reserve
                        dispatch_reserves[event.posting_key] = list(reserve)
                    non_buyout_restocked_units += event.quantity
                    non_buyout_restock_postings.add(event.posting_key)
                else:
                    if event.posting_key in non_buyout_restock_postings:
                        issues.add(Issue.TIMELINE_RESTOCK_AFTER_BUYOUT)
                        break
                    sale = bought_out.get(event.posting_key)
                    if sale is None:
                        issues.add(Issue.TIMELINE_SALE_RETURN_UNMATCHED)
                        break
                    prior_returned = sum(
                        quantity for (posting, _line), quantity in sale_returned_by_line.items()
                        if posting == event.posting_key
                    )
                    sale_units = sum(item.quantity for item in sale)
                    if prior_returned + event.quantity > sale_units:
                        issues.add(Issue.TIMELINE_SALE_RETURN_EXCEEDS_BUYOUT)
                        break
                    restored = self._take_sale_return_allocation(
                        event.posting_key, sale, sale_returned_by_line, event.quantity,
                    )
                    sale_returned_units += event.quantity

                for allocation in restored:
                    returned_cost_basis += allocation.total_cost_rub
                    origin = layer_origins.get(allocation.layer_id)
                    if origin is None:
                        issues.add(Issue.TIMELINE_ORIGIN_LAYER_MISSING)
                        break
                    if event.resellable:
                        available = self._restore_layer(
                            available, origin, allocation.quantity,
                        )
                    else:
                        held.append(ProvisionalHeldFifoLayer(
                            layer_id=allocation.layer_id,
                            quantity=allocation.quantity,
                            unit_cost_rub=allocation.unit_cost_rub,
                            effective_date=origin.effective_date,
                            effective_at_utc=origin.effective_at_utc,
                            source_event_key=event.event_key,
                            stock_zone=Zone.BUYER_RETURN_TRANSIT,
                            non_resellable_return=True,
                        ))
                if issues:
                    break
            elif event.event_kind is Kind.RELEASE_HOLD:
                held_zone = [layer for layer in held if layer.stock_zone is event.stock_zone]
                allocations, remaining_held, issue = self._take_held_layers(
                    held_zone, event.quantity, release=True,
                )
                if issue is not None:
                    issues.add(issue)
                    break
                held_ids = {id(layer) for layer in held_zone}
                held = [layer for layer in held if id(layer) not in held_ids]
                held.extend(remaining_held)
                for allocation in allocations:
                    origin = layer_origins.get(allocation.layer_id)
                    if origin is None:
                        issues.add(Issue.TIMELINE_ORIGIN_LAYER_MISSING)
                        break
                    available = self._restore_layer(
                        available, origin, allocation.quantity,
                    )
                if issues:
                    break
                released_hold_units += event.quantity
            elif event.event_kind is Kind.NON_SALE_REMOVE:
                if event.stock_zone is Zone.AVAILABLE:
                    allocations, remaining_available = self._take_available_layers(
                        available, event.quantity,
                    )
                    if allocations is None:
                        issues.add(Issue.TIMELINE_NEGATIVE_AVAILABLE_STOCK)
                        break
                    available = remaining_available
                else:
                    held_zone = [layer for layer in held if layer.stock_zone is event.stock_zone]
                    allocations, remaining_held, issue = self._take_held_layers(
                        held_zone, event.quantity, release=False,
                    )
                    if issue is not None:
                        issues.add(issue)
                        break
                    held_ids = {id(layer) for layer in held_zone}
                    held = [layer for layer in held if id(layer) not in held_ids]
                    held.extend(remaining_held)
                non_sale_allocations[event.event_key] = tuple(allocations)
                non_sale_removed_units += event.quantity
                non_sale_removed_cost += sum(
                    (item.total_cost_rub for item in allocations), ZERO,
                )
            processed += 1

        return self._result(
            issues=issues,
            events_processed=processed,
            available=available,
            held=held,
            opening_reserves=opening_by_posting,
            dispatch_reserves=dispatch_reserves,
            dispatch_units=dispatch_units,
            bought_out_allocations=bought_out,
            gross_buyout_cogs=gross_buyout_cogs,
            sale_returned_units=sale_returned_units,
            non_buyout_restocked_units=non_buyout_restocked_units,
            returned_cost_basis=returned_cost_basis,
            active_reserves=active_reserves,
            opening_postings=opening_postings,
            released_hold_units=released_hold_units,
            non_sale_removed_units=non_sale_removed_units,
            non_sale_removed_cost=non_sale_removed_cost,
            non_sale_removal_allocations=non_sale_allocations,
            supplied_event_count=len(ordered_events),
            unprocessed_event_count=max(0, len(ordered_events) - processed),
        )

    @staticmethod
    def _take_reserve_allocation(reserve, quantity):
        remaining = quantity
        restored = []
        # A partial cancellation can only be valued without guessing when its
        # active reserve consists of one source layer. Full cancellation returns
        # every original line exactly.
        for index in range(len(reserve) - 1, -1, -1):
            if remaining <= 0:
                break
            line = reserve[index]
            taken = min(line.quantity, remaining)
            restored.append(FifoCostProvisionalReplayService._allocation(
                layer_id=line.layer_id, quantity=taken, unit_cost=line.unit_cost_rub,
            ))
            left = line.quantity - taken
            if left:
                reserve[index] = FifoCostProvisionalReplayService._allocation(
                    layer_id=line.layer_id, quantity=left, unit_cost=line.unit_cost_rub,
                )
            else:
                reserve.pop(index)
            remaining -= taken
        return tuple(restored)

    @staticmethod
    def _take_sale_return_allocation(posting_key, sale, restored_by_line, quantity):
        remaining = quantity
        restored = []
        for index in range(len(sale) - 1, -1, -1):
            if remaining <= 0:
                break
            line = sale[index]
            key = (posting_key, index)
            prior = restored_by_line.get(key, 0)
            available = line.quantity - prior
            taken = min(available, remaining)
            if taken:
                restored.append(FifoCostProvisionalReplayService._allocation(
                    layer_id=line.layer_id, quantity=taken,
                    unit_cost=line.unit_cost_rub,
                ))
                restored_by_line[key] = prior + taken
                remaining -= taken
        return tuple(restored)

    @staticmethod
    def _restore_layer(available, origin, quantity):
        restored = []
        found = False
        for layer in available:
            if layer.layer_id == origin.layer_id:
                restored.append(ProvisionalFifoLayer(
                    layer_id=layer.layer_id,
                    quantity=layer.quantity + quantity,
                    unit_cost_rub=layer.unit_cost_rub,
                    effective_date=layer.effective_date,
                    effective_at_utc=layer.effective_at_utc,
                    source_event_key=layer.source_event_key,
                ))
                found = True
            else:
                restored.append(layer)
        if not found:
            restored.append(ProvisionalFifoLayer(
                layer_id=origin.layer_id,
                quantity=quantity,
                unit_cost_rub=origin.unit_cost_rub,
                effective_date=origin.effective_date,
                effective_at_utc=origin.effective_at_utc,
                source_event_key=origin.source_event_key,
            ))
        restored.sort(key=FifoCostProvisionalReplayService._layer_sort_key)
        return restored

    @staticmethod
    def _layer_sort_key(layer):
        instant = layer.effective_at_utc or datetime.combine(
            layer.effective_date, time.min, tzinfo=timezone.utc,
        )
        return layer.effective_date, instant, layer.source_event_key

    @classmethod
    def _take_available_layers(cls, available, quantity):
        remaining = quantity
        allocations = []
        next_available = []
        for layer in available:
            taken = min(layer.quantity, remaining)
            if taken:
                allocations.append(cls._allocation(
                    layer_id=layer.layer_id,
                    quantity=taken,
                    unit_cost=layer.unit_cost_rub,
                ))
                remaining -= taken
            if layer.quantity > taken:
                next_available.append(ProvisionalFifoLayer(
                    layer_id=layer.layer_id,
                    quantity=layer.quantity - taken,
                    unit_cost_rub=layer.unit_cost_rub,
                    effective_date=layer.effective_date,
                    effective_at_utc=layer.effective_at_utc,
                    source_event_key=layer.source_event_key,
                ))
        if remaining:
            return None, available
        return tuple(allocations), next_available

    @classmethod
    def _take_held_layers(cls, held, quantity, *, release):
        total = sum(layer.quantity for layer in held)
        if quantity > total:
            return (), held, Issue.TIMELINE_HELD_STOCK_INSUFFICIENT
        costs = {layer.unit_cost_rub for layer in held if layer.quantity}
        if quantity < total and len(costs) > 1:
            issue = (
                Issue.TIMELINE_HELD_RELEASE_AMBIGUOUS
                if release else Issue.TIMELINE_NON_SALE_REMOVE_AMBIGUOUS
            )
            return (), held, issue

        remaining = quantity
        allocations = []
        next_held = []
        for layer in sorted(held, key=cls._layer_sort_key):
            taken = min(layer.quantity, remaining)
            if taken:
                allocations.append(cls._allocation(
                    layer_id=layer.layer_id,
                    quantity=taken,
                    unit_cost=layer.unit_cost_rub,
                ))
                remaining -= taken
            if layer.quantity > taken:
                next_held.append(ProvisionalHeldFifoLayer(
                    layer_id=layer.layer_id,
                    quantity=layer.quantity - taken,
                    unit_cost_rub=layer.unit_cost_rub,
                    effective_date=layer.effective_date,
                    effective_at_utc=layer.effective_at_utc,
                    source_event_key=layer.source_event_key,
                    stock_zone=layer.stock_zone,
                    non_resellable_return=layer.non_resellable_return,
                ))
        return tuple(allocations), next_held, None

    @staticmethod
    def _normalize_opening_held_units(value):
        if value is None:
            return {}
        if not isinstance(value, Mapping) and not hasattr(value, "items"):
            return None
        normalized = {}
        try:
            for key, quantity in value.items():
                zone = key if isinstance(key, Zone) else Zone(key)
                if zone in {Zone.AVAILABLE, Zone.BUYER_DELIVERY} or zone in normalized:
                    return None
                amount = normalize_quantity(quantity)
                if amount < 0 or amount > MAX_UNITS:
                    return None
                if amount:
                    normalized[zone] = amount
        except (TypeError, ValueError, TransitionContractError):
            return None
        if sum(normalized.values()) > MAX_UNITS:
            return None
        return normalized

    @staticmethod
    def _normalize_capacities(value):
        if value is None:
            return {}
        if not isinstance(value, dict) and not hasattr(value, "items"):
            return None
        normalized = {}
        try:
            for key, quantity in value.items():
                digest = normalize_digest(key)
                amount = normalize_quantity(quantity)
                if amount <= 0 or amount > MAX_UNITS or digest in normalized:
                    return None
                normalized[digest] = amount
        except (TypeError, ValueError, TransitionContractError):
            return None
        return normalized

    @classmethod
    def _bounded_events(cls, events):
        if events is None:
            return None
        try:
            rows = tuple(events)
        except TypeError:
            return None
        if len(rows) > cls.MAX_EVENTS:
            return None
        return rows

    @staticmethod
    def _first_ambiguous_order_index(events):
        positions_by_day = {}
        positions_by_instant = {}
        for index, event in enumerate(events):
            positions_by_day.setdefault(event.local_date, []).append((index, event))
            if event.time_precision == "INSTANT":
                positions_by_instant.setdefault(event.effective_at_utc, []).append(index)

        ambiguous_positions = []
        for rows in positions_by_day.values():
            day_only = [index for index, event in rows if event.time_precision == "DAY"]
            if day_only and len(rows) > 1:
                ambiguous_positions.append(min(index for index, _event in rows))
        for positions in positions_by_instant.values():
            if len(positions) > 1:
                ambiguous_positions.append(min(positions))
        return min(ambiguous_positions) if ambiguous_positions else None

    @staticmethod
    def _event_sort_key(event):
        instant = event.effective_at_utc or datetime.combine(
            event.local_date, time.min, tzinfo=timezone.utc,
        )
        return event.local_date, instant, event.event_key

    @staticmethod
    def _layer_id(kind, identifier):
        return sha256(f"fifo-provisional-{kind}-v1:{identifier}".encode()).hexdigest()

    @staticmethod
    def _allocation(*, layer_id, quantity, unit_cost):
        total = (unit_cost * quantity).quantize(CENT)
        return ProvisionalFifoAllocation(
            layer_id=layer_id, quantity=quantity,
            unit_cost_rub=unit_cost, total_cost_rub=total,
        )

    @staticmethod
    def _result(*, issues, events_processed=0, available=(), held=(),
                opening_reserves=None, dispatch_reserves=None, dispatch_units=0,
                bought_out_allocations=None,
                gross_buyout_cogs=ZERO,
                sale_returned_units=0, non_buyout_restocked_units=0,
                returned_cost_basis=ZERO, active_reserves=None, opening_postings=None,
                released_hold_units=0, non_sale_removed_units=0,
                non_sale_removed_cost=ZERO, non_sale_removal_allocations=None,
                supplied_event_count=0, unprocessed_event_count=0):
        issue_codes = tuple(sorted(issues, key=lambda item: item.value))
        held_units = {}
        return_holds = {}
        for layer in held:
            zone_key = (
                "non_resellable_customer_return"
                if layer.non_resellable_return
                else layer.stock_zone.value
            )
            held_units[zone_key] = held_units.get(zone_key, 0) + layer.quantity
            if layer.non_resellable_return:
                return_holds.setdefault(layer.source_event_key, []).append(
                    FifoCostProvisionalReplayService._allocation(
                        layer_id=layer.layer_id,
                        quantity=layer.quantity,
                        unit_cost=layer.unit_cost_rub,
                    )
                )
        active_reserves_supplied = active_reserves is not None
        active_reserves = active_reserves or {}
        opening_postings = opening_postings or set()
        current_opening = {
            key: value for key, value in active_reserves.items()
            if key in opening_postings
        }
        current_dispatch = {
            key: value for key, value in (dispatch_reserves or {}).items()
        }
        pending_units = sum(
            item.quantity for values in active_reserves.values() for item in values
        )
        pending_cost = sum(
            (item.total_cost_rub for values in active_reserves.values() for item in values),
            ZERO,
        ).quantize(CENT)
        available_units = sum(layer.quantity for layer in available)
        complete = not issue_codes
        return ProvisionalFifoReplayResult(
            status="REPLAY_OK" if complete else "REPLAY_GAP",
            complete=complete,
            issue_codes=issue_codes,
            events_processed=events_processed,
            available_layers=tuple(available),
            held_layers=tuple(held),
            opening_transit_reserves=(
                current_opening if active_reserves_supplied else opening_reserves or {}
            ),
            buyer_dispatch_reserves=current_dispatch,
            available_units=available_units,
            held_units_by_zone=held_units,
            buyer_dispatch_units_total=dispatch_units,
            pending_reserve_units=pending_units,
            pending_reserve_cost_rub=pending_cost,
            bought_out_allocations=bought_out_allocations or {},
            non_resellable_return_holds=return_holds,
            gross_buyout_cogs_rub=gross_buyout_cogs.quantize(CENT),
            sale_returned_units=sale_returned_units,
            non_buyout_restocked_units=non_buyout_restocked_units,
            returned_cost_basis_rub=returned_cost_basis.quantize(CENT),
            financial_cogs_reversal_rub=ZERO,
            dispatch_cogs_rub=ZERO,
            released_hold_units=released_hold_units,
            non_sale_removed_units=non_sale_removed_units,
            non_sale_removed_cost_rub=non_sale_removed_cost.quantize(CENT),
            non_sale_removal_allocations=non_sale_removal_allocations or {},
            supplied_event_count=supplied_event_count,
            unprocessed_event_count=unprocessed_event_count,
            read_only=True,
            factual_writes=0,
        )

    @classmethod
    def _empty_result(cls, issues):
        return cls._result(issues=issues)
