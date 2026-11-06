"""Bounded, deterministic coordination for immutable FIFO allocations.

This service is intentionally side-effect free. A caller must provide source,
physical-time, event-order, and inventory-cutoff evidence before a replay can be
complete. The repository separately checks the event-stream revision and
current cutoff in one SQLite transaction before it publishes allocation rows.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
import json
from typing import Iterable

from services.fifo_cost_allocation_service import (
    FifoCostAllocationService,
    FifoCostLayer,
    FifoOpenCostRate,
    FifoRestockEvent,
    FifoSaleEvent,
)


@dataclass(frozen=True)
class FifoDatedAllocationEvent:
    """A core allocation event plus evidence needed to establish causal order."""

    event: FifoSaleEvent | FifoRestockEvent
    effective_at: str | None
    effective_date: str | None
    source_identity_digest: str | None = None
    physical_time_confirmed: bool = False
    cutoff_bridge_confirmed: bool = False


class FifoCostReplayService:
    MAX_EVENTS = 100_000
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
        if normalized_layers is None or normalized_events is None:
            return self._blocked("FIFO_REPLAY_INPUT_LIMIT")
        if unsupported_event_count:
            return self._blocked("FIFO_REPLAY_UNSUPPORTED_EVENT")

        ordered, order_error = self._order_events(
            normalized_events, anchor_cutoff_date=anchor_cutoff_date,
        )
        if order_error:
            return self._blocked(order_error)
        if open_rate is not None:
            if self._date(open_rate_effective_date) is None:
                return self._blocked("FIFO_RATE_EFFECTIVE_DATE_UNAVAILABLE")
            if open_rate_effective_date <= anchor_cutoff_date:
                return self._blocked("FIFO_RATE_EFFECTIVE_DATE_CONFLICT")
            finite_units = sum(layer.quantity for layer in normalized_layers)
            sales_before_rate = sum(
                item.event.quantity for item in ordered
                if isinstance(item.event, FifoSaleEvent)
                and self._event_day(item) <= open_rate_effective_date
            )
            if sales_before_rate > finite_units or any(
                isinstance(item.event, FifoRestockEvent)
                and self._event_day(item) <= open_rate_effective_date
                for item in ordered
            ):
                return self._blocked("FIFO_RATE_TRANSITION_ORDER_UNRESOLVED")
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
        status = "COMPLETE" if result.complete else self._status_for(result.reason_code)
        allocations = []
        for sale in result.sale_allocations:
            allocations.append({
                "event_id": sale.event_id,
                "quantity": sale.quantity,
                "total_cost_rub": format(sale.total_cost_rub, ".2f"),
                "lines": [self._allocation_line(line, open_rate) for line in sale.lines],
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
            "remaining_confirmed_units": result.remaining_confirmed_units,
            "restored_units": result.restored_units,
            "allocations": allocations,
        }
        preview["preview_fingerprint"] = self._fingerprint(preview)
        return preview

    def _order_events(self, events, *, anchor_cutoff_date):
        if len(events) > self.MAX_EVENTS:
            return None, "FIFO_REPLAY_INPUT_LIMIT"
        if any(not isinstance(item, FifoDatedAllocationEvent) for item in events):
            return None, "FIFO_EVENT_INVALID"
        ids = []
        sale_digests = []
        normalized = []
        for item in events:
            event = item.event
            event_id = getattr(event, "event_id", None)
            if not isinstance(event_id, str) or not event_id or len(event_id) > 160:
                return None, "FIFO_EVENT_INVALID"
            ids.append(event_id)
            position = self._effective_position(item.effective_at, item.effective_date)
            if position is None:
                return None, "EVENT_ORDER_UNRESOLVED"
            if position[1] <= anchor_cutoff_date:
                return None, "INVENTORY_CUTOFF_UNRECONCILED"
            if isinstance(event, FifoSaleEvent):
                if not self._valid_digest(item.source_identity_digest):
                    return None, "PHYSICAL_SALE_IDENTITY_UNCONFIRMED"
                if item.physical_time_confirmed is not True:
                    return None, "PHYSICAL_SALE_TIME_UNCONFIRMED"
                if item.cutoff_bridge_confirmed is not True:
                    return None, "INVENTORY_CUTOFF_UNRECONCILED"
                sale_digests.append(item.source_identity_digest)
            elif isinstance(event, FifoRestockEvent):
                if item.source_identity_digest is not None:
                    return None, "FIFO_SOURCE_IDENTITY_INVALID"
            else:
                return None, "FIFO_EVENT_INVALID"
            normalized.append((position, event_id, item))

        if len(set(ids)) != len(ids):
            return None, "FIFO_EVENT_ID_DUPLICATE"
        if len(set(sale_digests)) != len(sale_digests):
            return None, "FIFO_SALE_IDENTITY_DUPLICATE"

        # Date-only evidence cannot order multiple events on the same date.
        # Equal instants are also ambiguous for per-sale layer attribution.
        positions_by_day = {}
        positions = set()
        for position, _, item in normalized:
            instant_key, day_key, is_date_only = position
            positions_by_day.setdefault(day_key, []).append(is_date_only)
            if instant_key in positions:
                return None, "EVENT_ORDER_UNRESOLVED"
            positions.add(instant_key)
        if any(len(flags) > 1 and any(flags) for flags in positions_by_day.values()):
            return None, "EVENT_ORDER_UNRESOLVED"
        return [item for _, _, item in sorted(normalized, key=lambda row: row[:2])], None

    @staticmethod
    def _effective_position(effective_at, effective_date):
        if effective_at is not None:
            if not isinstance(effective_at, str):
                return None
            try:
                parsed = datetime.fromisoformat(effective_at.replace("Z", "+00:00"))
            except ValueError:
                return None
            if parsed.tzinfo is None or parsed.utcoffset() is None:
                return None
            parsed = parsed.astimezone(timezone.utc)
            source_day = parsed.date().isoformat()
            if effective_date is not None:
                if not isinstance(effective_date, str):
                    return None
                try:
                    if date.fromisoformat(effective_date).isoformat() != source_day:
                        return None
                except ValueError:
                    return None
            return (
                parsed.isoformat(timespec="microseconds"),
                effective_date or source_day,
                False,
            )
        if not isinstance(effective_date, str):
            return None
        try:
            parsed_date = date.fromisoformat(effective_date)
        except ValueError:
            return None
        if parsed_date.isoformat() != effective_date:
            return None
        return (effective_date + "T00:00:00+00:00", effective_date, True)

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
    def _event_day(cls, item):
        if item.effective_date is not None:
            return item.effective_date
        position = cls._effective_position(item.effective_at, None)
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
            "FIFO_RATE_EFFECTIVE_DATE_UNAVAILABLE",
            "FIFO_RATE_TRANSITION_ORDER_UNRESOLVED",
        }:
            return "SOURCE_BLOCKED"
        return "CONFLICT"

    @staticmethod
    def _allocation_line(line, open_rate):
        is_open_rate = open_rate is not None and line.layer_id == open_rate.layer_id
        return {
            "layer_id": None if is_open_rate else line.layer_id,
            "rate_change_id": line.layer_id if is_open_rate else None,
            "quantity": line.quantity,
            "unit_cost_rub": format(line.unit_cost_rub, ".2f"),
            "total_cost_rub": format(line.total_cost_rub, ".2f"),
            "origin_sale_event_id": line.origin_sale_event_id,
        }

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
