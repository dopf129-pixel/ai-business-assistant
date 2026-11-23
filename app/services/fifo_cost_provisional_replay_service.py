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
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from services.fifo_cost_provisional_timeline_contracts import (
    ProvisionalStockZone,
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
    stock_zone: ProvisionalStockZone


@dataclass(frozen=True, slots=True)
class ProvisionalFifoReplayResult:
    """Replay outcome; ``complete`` only means the supplied stream was replayable.

    It does not attest source coverage, inventory reconciliation, factual FIFO
    readiness, or the final timeline status. Those gates belong to PF17/PF18.
    """
    status: str
    complete: bool
    issue_codes: tuple[Issue, ...]
    events_processed: int
    available_layers: tuple[ProvisionalFifoLayer, ...]
    held_layers: tuple[ProvisionalHeldFifoLayer, ...]
    opening_transit_reserves: object
    buyer_dispatch_reserves: object
    available_units: int
    held_units_by_zone: object
    reserved_dispatch_units: int
    reserved_dispatch_cost_rub: Decimal
    dispatch_cogs_rub: Decimal
    read_only: bool = True
    factual_writes: int = 0

    def __post_init__(self):
        object.__setattr__(self, "opening_transit_reserves", MappingProxyType(
            {key: tuple(value) for key, value in dict(self.opening_transit_reserves).items()}
        ))
        object.__setattr__(self, "buyer_dispatch_reserves", MappingProxyType(
            {key: tuple(value) for key, value in dict(self.buyer_dispatch_reserves).items()}
        ))
        object.__setattr__(self, "held_units_by_zone", MappingProxyType(
            dict(self.held_units_by_zone)
        ))


class FifoCostProvisionalReplayService:
    """Replay finite stock layers and reserve dispatch costs without expensing them."""

    MAX_EVENTS = MAX_EVENTS
    MAX_UNITS = MAX_UNITS

    def replay(
        self,
        *,
        events,
        scope_fingerprint,
        finance_sku,
        timezone_name,
        model_start,
        model_end,
        opening_available_units,
        old_unit_cost_rub,
        new_unit_cost_rub,
        posting_capacities=None,
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
            if event.event_kind not in {Kind.SUPPLY_RECEIVED, Kind.BUYER_DISPATCH}:
                issues.add(Issue.TIMELINE_UNSUPPORTED_EVENT)
                continue
            if event.local_date < model_start or event.local_date > model_end:
                issues.add(Issue.TIMELINE_EVENT_OUTSIDE_WINDOW)
                continue
            timeline_events.append(event)

        if issues:
            return self._empty_result(issues)

        if self._has_ambiguous_order(timeline_events):
            issues.add(Issue.TIMELINE_EVENT_ORDER_AMBIGUOUS)
            return self._empty_result(issues)

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
        dispatch_by_posting = {}
        for event in timeline_events:
            if event.event_kind is Kind.BUYER_DISPATCH:
                capacity = capacities.get(event.posting_key)
                if (capacity is None or event.quantity > capacity
                        or event.posting_key in opening_postings
                        or event.posting_key in dispatch_by_posting):
                    issues.add(Issue.TIMELINE_DUPLICATE_POSTING)
                    continue
                dispatch_by_posting[event.posting_key] = event
        if issues:
            return self._empty_result(issues)

        total_stream_units = opening_units + sum(
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
            available.append(ProvisionalFifoLayer(
                layer_id=opening_layer_id,
                quantity=opening_units,
                unit_cost_rub=old_cost,
                effective_date=date.min,
                effective_at_utc=None,
                source_event_key=opening_layer_id,
            ))
        held = []
        dispatch_reserves = {}
        dispatch_units = 0
        dispatch_reserved_cost = ZERO
        processed = 0

        for event in sorted(timeline_events, key=self._event_sort_key):
            if event.event_kind is Kind.SUPPLY_RECEIVED:
                if event.stock_zone is ProvisionalStockZone.AVAILABLE:
                    available.append(ProvisionalFifoLayer(
                        layer_id=self._layer_id("receipt", event.event_key),
                        quantity=event.quantity,
                        unit_cost_rub=new_cost,
                        effective_date=event.local_date,
                        effective_at_utc=event.effective_at_utc,
                        source_event_key=event.event_key,
                    ))
                else:
                    held.append(ProvisionalHeldFifoLayer(
                        layer_id=self._layer_id("held-receipt", event.event_key),
                        quantity=event.quantity,
                        unit_cost_rub=new_cost,
                        effective_date=event.local_date,
                        effective_at_utc=event.effective_at_utc,
                        source_event_key=event.event_key,
                        stock_zone=event.stock_zone,
                    ))
                processed += 1
                continue

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
            dispatch_reserves[event.posting_key] = tuple(allocations)
            dispatch_units += event.quantity
            dispatch_reserved_cost += sum(
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
            dispatch_reserved_cost=dispatch_reserved_cost,
        )

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
    def _has_ambiguous_order(events):
        by_day_precision = {}
        by_instant = {}
        for event in events:
            if event.time_precision == "DAY":
                by_day_precision.setdefault(event.local_date, []).append(event)
            else:
                by_instant.setdefault(event.effective_at_utc, []).append(event)
        for rows in by_day_precision.values():
            if len(rows) > 1:
                return True
        for instant, rows in by_instant.items():
            if len(rows) > 1:
                return True
            if rows[0].local_date in by_day_precision:
                return True
        return False

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
                dispatch_reserved_cost=ZERO):
        issue_codes = tuple(sorted(issues, key=lambda item: item.value))
        held_units = {}
        for layer in held:
            held_units[layer.stock_zone.value] = (
                held_units.get(layer.stock_zone.value, 0) + layer.quantity
            )
        available_units = sum(layer.quantity for layer in available)
        complete = not issue_codes
        return ProvisionalFifoReplayResult(
            status="REPLAY_OK" if complete else "REPLAY_GAP",
            complete=complete,
            issue_codes=issue_codes,
            events_processed=events_processed,
            available_layers=tuple(available),
            held_layers=tuple(held),
            opening_transit_reserves=opening_reserves or {},
            buyer_dispatch_reserves=dispatch_reserves or {},
            available_units=available_units,
            held_units_by_zone=held_units,
            reserved_dispatch_units=dispatch_units,
            reserved_dispatch_cost_rub=dispatch_reserved_cost.quantize(CENT),
            dispatch_cogs_rub=ZERO,
            read_only=True,
            factual_writes=0,
        )

    @classmethod
    def _empty_result(cls, issues):
        return cls._result(issues=issues)
