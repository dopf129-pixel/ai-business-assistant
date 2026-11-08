"""Pure, deterministic FIFO allocation for confirmed SKU cost layers.

This module intentionally has no database, Ozon, Telegram, tenant, or planning
dependencies. Source completeness and the inventory cutoff must be established
by callers before an allocation can be treated as factual.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Iterable


_CENT = Decimal("0.01")
_MAX_UNITS_PER_EVENT = 100_000
_MAX_UNITS_IN_STREAM = 1_000_000
_MAX_IDENTIFIER_LENGTH = 160
_MAX_EVENTS_PER_REPLAY = 100_000
_MAX_LAYERS_PER_STREAM = 100_000
_MAX_REPLAY_ALLOCATION_LINES = 250_000


def _is_digest(value):
    return (
        isinstance(value, str) and len(value) == 64
        and all(char in "0123456789abcdef" for char in value)
    )


@dataclass(frozen=True)
class FifoCostLayer:
    """A finite, confirmed cost layer in FIFO order."""

    layer_id: str
    unit_cost_rub: Decimal | str | int
    quantity: int
    currency: str = "RUB"


@dataclass(frozen=True)
class FifoOpenCostRate:
    """A unit rate whose purchase quantity is unknown; never an inventory count."""

    layer_id: str
    unit_cost_rub: Decimal | str | int
    currency: str = "RUB"


@dataclass(frozen=True)
class FifoSaleEvent:
    event_id: str
    quantity: int


@dataclass(frozen=True)
class FifoRestoreSlice:
    """Exact return basis referring to one prior sale allocation layer."""

    sale_event_id: str
    layer_id: str
    quantity: int


@dataclass(frozen=True)
class FifoRestockEvent:
    event_id: str
    quantity: int
    restores: tuple[FifoRestoreSlice, ...]


@dataclass(frozen=True)
class FifoOutflowEvent:
    """A confirmed non-sale quantity loss, valued separately from sales COGS."""

    event_id: str
    quantity: int
    reason_code: str


@dataclass(frozen=True)
class FifoRateBoundaryEvent:
    """Proof-bound switch from one unknown-quantity unit rate to another.

    The event itself does not add inventory. Later boundaries carry exact
    balances established by an independent stock/physical-sale reconciliation.
    """

    event_id: str
    new_rate_change_id: str
    new_unit_cost_rub: Decimal | str | int
    previous_rate_change_id: str | None
    previous_rate_remaining_units: int | None
    expected_older_finite_units: int | None
    reconciliation_evidence_fingerprint: str

    def __post_init__(self):
        for field_name in ("event_id", "new_rate_change_id"):
            value = getattr(self, field_name)
            if (
                not isinstance(value, str) or not value.strip()
                or len(value.strip()) > _MAX_IDENTIFIER_LENGTH
            ):
                raise ValueError("FIFO_RATE_CHAIN_CONFLICT")
            object.__setattr__(self, field_name, value.strip())
        if self.previous_rate_change_id is not None:
            value = self.previous_rate_change_id
            if (
                not isinstance(value, str) or not value.strip()
                or len(value.strip()) > _MAX_IDENTIFIER_LENGTH
            ):
                raise ValueError("FIFO_RATE_CHAIN_CONFLICT")
            object.__setattr__(self, "previous_rate_change_id", value.strip())
            if value.strip() == self.new_rate_change_id:
                raise ValueError("FIFO_RATE_CHAIN_CONFLICT")
        if isinstance(self.new_unit_cost_rub, (bool, float)) or not isinstance(
            self.new_unit_cost_rub, (Decimal, str, int),
        ):
            raise ValueError("FIFO_RATE_BOUNDARY_UNPROVEN")
        try:
            cost = Decimal(self.new_unit_cost_rub).quantize(
                _CENT, rounding=ROUND_HALF_UP,
            )
        except (InvalidOperation, TypeError, ValueError, OverflowError):
            raise ValueError("FIFO_RATE_BOUNDARY_UNPROVEN") from None
        if not cost.is_finite() or cost < 0 or cost > Decimal("1000000000.00"):
            raise ValueError("FIFO_RATE_BOUNDARY_UNPROVEN")
        object.__setattr__(self, "new_unit_cost_rub", cost)
        if not _is_digest(self.reconciliation_evidence_fingerprint):
            raise ValueError("FIFO_RATE_BOUNDARY_UNPROVEN")

        first_boundary = self.previous_rate_change_id is None
        previous_units = self.previous_rate_remaining_units
        finite_units = self.expected_older_finite_units
        if first_boundary:
            if previous_units is not None or finite_units is not None:
                raise ValueError("FIFO_RATE_CHAIN_CONFLICT")
            return
        if (
            isinstance(previous_units, bool) or not isinstance(previous_units, int)
            or previous_units < 0
            or isinstance(finite_units, bool) or not isinstance(finite_units, int)
            or finite_units < 0
        ):
            raise ValueError("FIFO_RATE_BOUNDARY_UNPROVEN")


@dataclass(frozen=True)
class FifoAllocationLine:
    layer_id: str
    quantity: int
    unit_cost_rub: Decimal
    total_cost_rub: Decimal
    origin_sale_event_id: str | None = None


@dataclass(frozen=True)
class FifoSaleAllocation:
    event_id: str
    quantity: int
    total_cost_rub: Decimal
    lines: tuple[FifoAllocationLine, ...]


@dataclass(frozen=True)
class FifoOutflowAllocation:
    event_id: str
    quantity: int
    reason_code: str
    estimated_value_rub: Decimal
    lines: tuple[FifoAllocationLine, ...]


@dataclass(frozen=True)
class FifoAllocationResult:
    status: str
    complete: bool
    reason_code: str | None
    sale_allocations: tuple[FifoSaleAllocation, ...]
    outflow_allocations: tuple[FifoOutflowAllocation, ...]
    total_cogs_rub: Decimal | None
    non_sale_outflow_value_rub: Decimal | None
    inventory_restored_value_rub: Decimal | None
    restored_units: int | None
    remaining_confirmed_units: int | None
    total_available_units: int | None
    next_unit_cost_rub: Decimal | None
    next_unit_cost_status: str


class FifoCostAllocationService:
    """Allocate observed sale quantities over cost layers without side effects."""

    MAX_UNITS_PER_EVENT = _MAX_UNITS_PER_EVENT
    MAX_UNITS_IN_STREAM = _MAX_UNITS_IN_STREAM
    ANCHOR_CONFIRMED = "CONFIRMED"
    ANCHOR_CONFIRMED_ZERO = "CONFIRMED_ZERO"
    _ALLOWED_ANCHORS = frozenset({ANCHOR_CONFIRMED, ANCHOR_CONFIRMED_ZERO})

    def allocate(
        self,
        *,
        layers: Iterable[FifoCostLayer],
        events: Iterable[FifoSaleEvent | FifoRestockEvent | FifoOutflowEvent],
        anchor_status: str = "UNKNOWN",
        cutoff_status: str = "UNRECONCILED",
        event_order_status: str = "UNKNOWN",
        source_completeness: str = "UNKNOWN",
        open_rate: FifoOpenCostRate | None = None,
    ) -> FifoAllocationResult:
        """Replay events in the caller's already-proven causal order.

        ``open_rate`` can cost only the portion of an observed sale that remains
        after all finite layers are exhausted. It never contributes to either
        ``remaining_confirmed_units`` or ``total_available_units``.
        """

        if anchor_status not in self._ALLOWED_ANCHORS:
            return self._incomplete("ANCHOR_UNCONFIRMED")
        if cutoff_status != "RECONCILED":
            return self._incomplete("INVENTORY_CUTOFF_UNRECONCILED")
        if event_order_status != "PROVEN":
            return self._incomplete("EVENT_ORDER_UNRESOLVED")
        if source_completeness != "COMPLETE":
            return self._incomplete("FIFO_SOURCE_INCOMPLETE")

        normalized_layers = self._normalize_layers(layers)
        if isinstance(normalized_layers, str):
            return self._incomplete(normalized_layers)
        layer_state, layer_costs, layer_origins = normalized_layers

        normalized_rate = None
        if open_rate is not None:
            normalized_rate = self._normalize_open_rate(open_rate)
            if isinstance(normalized_rate, str):
                return self._incomplete(normalized_rate)
            rate_id, rate_cost = normalized_rate
            if rate_id in layer_state:
                return self._incomplete("FIFO_LAYER_ID_DUPLICATE")
            layer_costs[rate_id] = rate_cost
            layer_origins[rate_id] = None

        normalized_events = self._normalize_events(events)
        if isinstance(normalized_events, str):
            return self._incomplete(normalized_events)
        if len(set(event.event_id for event in normalized_events)) != len(normalized_events):
            return self._incomplete("FIFO_EVENT_ID_DUPLICATE")
        replay_work_used = sum(
            len(event.restores)
            for event in normalized_events
            if isinstance(event, FifoRestockEvent)
        )
        if replay_work_used > _MAX_REPLAY_ALLOCATION_LINES:
            return self._incomplete("FIFO_REPLAY_WORK_LIMIT")

        initial_known = sum(layer_state.values())
        if initial_known > self.MAX_UNITS_IN_STREAM:
            return self._incomplete("FIFO_STREAM_QUANTITY_LIMIT")
        if initial_known == 0 and anchor_status == self.ANCHOR_CONFIRMED:
            # A confirmed positive anchor must have finite layer rows. A
            # confirmed zero has its own explicit status.
            return self._incomplete("FIFO_ANCHOR_LAYER_MISSING")
        if initial_known > 0 and anchor_status == self.ANCHOR_CONFIRMED_ZERO:
            return self._incomplete("FIFO_ZERO_ANCHOR_HAS_LAYERS")

        restored_by_sale_layer: dict[tuple[str, str], int] = {}
        allocation_by_sale: dict[str, FifoSaleAllocation] = {}
        allocation_line_by_sale_layer: dict[tuple[str, str], FifoAllocationLine] = {}
        sale_allocations: list[FifoSaleAllocation] = []
        outflow_allocations: list[FifoOutflowAllocation] = []
        total_cogs = Decimal("0.00")
        outflow_value = Decimal("0.00")
        restored_value = Decimal("0.00")
        restored_units = 0
        source_sequence = list(layer_state)
        if normalized_rate is not None:
            source_sequence.append(normalized_rate[0])

        for event in normalized_events:
            if isinstance(event, FifoSaleEvent):
                remaining = event.quantity
                lines: list[FifoAllocationLine] = []
                for layer_id in source_sequence:
                    if remaining <= 0:
                        break
                    if layer_id == (normalized_rate[0] if normalized_rate else None):
                        replay_work_used += 1
                        if replay_work_used > _MAX_REPLAY_ALLOCATION_LINES:
                            return self._incomplete("FIFO_REPLAY_WORK_LIMIT")
                        lines.append(
                            FifoAllocationLine(
                                layer_id=layer_id,
                                quantity=remaining,
                                unit_cost_rub=layer_costs[layer_id],
                                total_cost_rub=(layer_costs[layer_id] * remaining).quantize(
                                    _CENT, rounding=ROUND_HALF_UP
                                ),
                            )
                        )
                        remaining = 0
                        break
                    available = layer_state.get(layer_id, 0)
                    taken = min(available, remaining)
                    if taken <= 0:
                        continue
                    replay_work_used += 1
                    if replay_work_used > _MAX_REPLAY_ALLOCATION_LINES:
                        return self._incomplete("FIFO_REPLAY_WORK_LIMIT")
                    unit_cost = layer_costs[layer_id]
                    lines.append(
                        FifoAllocationLine(
                            layer_id=layer_id,
                            quantity=taken,
                            unit_cost_rub=unit_cost,
                            total_cost_rub=(unit_cost * taken).quantize(
                                _CENT, rounding=ROUND_HALF_UP
                            ),
                            origin_sale_event_id=(
                                layer_origins[layer_id][0]
                                if layer_origins.get(layer_id) is not None
                                else None
                            ),
                        )
                    )
                    layer_state[layer_id] -= taken
                    remaining -= taken

                if remaining:
                    return self._incomplete("FIFO_CONFIRMED_QUANTITY_EXHAUSTED")

                allocation = FifoSaleAllocation(
                    event_id=event.event_id,
                    quantity=event.quantity,
                    total_cost_rub=sum(
                        (line.total_cost_rub for line in lines), Decimal("0.00")
                    ).quantize(_CENT, rounding=ROUND_HALF_UP),
                    lines=tuple(lines),
                )
                allocation_by_sale[event.event_id] = allocation
                for line in allocation.lines:
                    allocation_line_by_sale_layer[(event.event_id, line.layer_id)] = line
                sale_allocations.append(allocation)
                total_cogs += allocation.total_cost_rub
                continue

            if isinstance(event, FifoOutflowEvent):
                remaining = event.quantity
                lines: list[FifoAllocationLine] = []
                for layer_id in source_sequence:
                    if remaining <= 0:
                        break
                    # An open rate has unknown physical quantity. Never use it
                    # to value a confirmed outflow or silently consume it.
                    if layer_id == (normalized_rate[0] if normalized_rate else None):
                        continue
                    available = layer_state.get(layer_id, 0)
                    taken = min(available, remaining)
                    if taken <= 0:
                        continue
                    replay_work_used += 1
                    if replay_work_used > _MAX_REPLAY_ALLOCATION_LINES:
                        return self._incomplete("FIFO_REPLAY_WORK_LIMIT")
                    unit_cost = layer_costs[layer_id]
                    lines.append(FifoAllocationLine(
                        layer_id=layer_id,
                        quantity=taken,
                        unit_cost_rub=unit_cost,
                        total_cost_rub=(unit_cost * taken).quantize(
                            _CENT, rounding=ROUND_HALF_UP,
                        ),
                        origin_sale_event_id=(
                            layer_origins[layer_id][0]
                            if layer_origins.get(layer_id) is not None else None
                        ),
                    ))
                    layer_state[layer_id] -= taken
                    remaining -= taken
                if remaining:
                    return self._incomplete("FIFO_OUTFLOW_FINITE_BASIS_UNAVAILABLE")
                estimated_value = sum(
                    (line.total_cost_rub for line in lines), Decimal("0.00"),
                ).quantize(_CENT, rounding=ROUND_HALF_UP)
                outflow_allocations.append(FifoOutflowAllocation(
                    event_id=event.event_id,
                    quantity=event.quantity,
                    reason_code=event.reason_code,
                    estimated_value_rub=estimated_value,
                    lines=tuple(lines),
                ))
                outflow_value += estimated_value
                continue

            if not event.restores:
                return self._incomplete("FIFO_RETURN_BASIS_MISSING")
            if sum(item.quantity for item in event.restores) != event.quantity:
                return self._incomplete("FIFO_RETURN_BASIS_QUANTITY_MISMATCH")

            for restore_index, restore in enumerate(event.restores):
                sale = allocation_by_sale.get(restore.sale_event_id)
                if sale is None:
                    return self._incomplete("FIFO_RETURN_ORIGIN_SALE_MISSING")
                line = allocation_line_by_sale_layer.get(
                    (restore.sale_event_id, restore.layer_id)
                )
                if line is None:
                    return self._incomplete("FIFO_RETURN_ORIGIN_LAYER_MISSING")
                key = (restore.sale_event_id, restore.layer_id)
                restored_before = restored_by_sale_layer.get(key, 0)
                # The prior sale allocation line is the exact quantity basis,
                # including units priced by the open current rate.
                if restored_before + restore.quantity > line.quantity:
                    return self._incomplete("FIFO_RETURN_QUANTITY_EXCEEDS_ORIGIN")

                restored_by_sale_layer[key] = restored_before + restore.quantity
                origin_is_open_rate = normalized_rate is not None and restore.layer_id == normalized_rate[0]
                if origin_is_open_rate:
                    # Keep restored units as a known, finite layer with the
                    # original confirmed rate. It is placed at return time.
                    restored_layer_id = f"{event.event_id}~return~{restore_index}"
                    if restored_layer_id in layer_state or restored_layer_id in layer_costs:
                        return self._incomplete("FIFO_RESTORED_LAYER_ID_CONFLICT")
                    layer_state[restored_layer_id] = restore.quantity
                    layer_costs[restored_layer_id] = line.unit_cost_rub
                    layer_origins[restored_layer_id] = (
                        restore.sale_event_id,
                        restore.layer_id,
                    )
                    source_sequence.insert(source_sequence.index(normalized_rate[0]), restored_layer_id)
                else:
                    if restore.layer_id not in layer_state:
                        return self._incomplete("FIFO_RETURN_ORIGIN_LAYER_MISSING")
                    if layer_state[restore.layer_id] + restore.quantity > self.MAX_UNITS_IN_STREAM:
                        return self._incomplete("FIFO_STREAM_QUANTITY_LIMIT")
                    layer_state[restore.layer_id] += restore.quantity
                restored_amount = (line.unit_cost_rub * restore.quantity).quantize(
                    _CENT, rounding=ROUND_HALF_UP
                )
                restored_value += restored_amount
                restored_units += restore.quantity
                if sum(layer_state.values()) > self.MAX_UNITS_IN_STREAM:
                    return self._incomplete("FIFO_STREAM_QUANTITY_LIMIT")

        remaining_known = sum(layer_state.values())
        total_available = None if normalized_rate is not None else remaining_known
        available_sequence = [
            layer_id for layer_id in source_sequence
            if layer_id != (normalized_rate[0] if normalized_rate else None)
            and layer_state.get(layer_id, 0) > 0
        ]
        if available_sequence:
            next_unit_cost = layer_costs[available_sequence[0]]
            next_unit_status = "CONFIRMED_FINITE_LAYER"
        elif normalized_rate is not None:
            next_unit_cost = layer_costs[normalized_rate[0]]
            next_unit_status = "RATE_ONLY_QUANTITY_UNKNOWN"
        else:
            next_unit_cost = None
            next_unit_status = "NO_CONFIRMED_UNIT"

        return FifoAllocationResult(
            status="FIFO_ALLOCATION_READY",
            complete=True,
            reason_code=None,
            sale_allocations=tuple(sale_allocations),
            outflow_allocations=tuple(outflow_allocations),
            total_cogs_rub=total_cogs.quantize(_CENT, rounding=ROUND_HALF_UP),
            non_sale_outflow_value_rub=outflow_value.quantize(
                _CENT, rounding=ROUND_HALF_UP,
            ),
            inventory_restored_value_rub=restored_value.quantize(
                _CENT, rounding=ROUND_HALF_UP
            ),
            restored_units=restored_units,
            remaining_confirmed_units=remaining_known,
            total_available_units=total_available,
            next_unit_cost_rub=next_unit_cost,
            next_unit_cost_status=next_unit_status,
        )

    def _normalize_layers(self, layers):
        rows = self._bounded_rows(layers, _MAX_LAYERS_PER_STREAM)
        if rows is None:
            return "FIFO_LAYER_INPUT_INVALID"
        if len(rows) > _MAX_LAYERS_PER_STREAM:
            return "FIFO_LAYER_INPUT_LIMIT"
        state: dict[str, int] = {}
        costs: dict[str, Decimal] = {}
        origins: dict[str, tuple[str, str] | None] = {}
        total = 0
        for layer in rows:
            if not isinstance(layer, FifoCostLayer):
                return "FIFO_LAYER_INPUT_INVALID"
            layer_id = self._identifier(layer.layer_id)
            quantity = self._stream_quantity(layer.quantity)
            unit_cost = self._money(layer.unit_cost_rub)
            if layer_id is None or quantity is None or unit_cost is None:
                return "FIFO_LAYER_INPUT_INVALID"
            if layer.currency != "RUB":
                return "FIFO_CURRENCY_UNSUPPORTED"
            if layer_id in state:
                return "FIFO_LAYER_ID_DUPLICATE"
            total += quantity
            if total > self.MAX_UNITS_IN_STREAM:
                return "FIFO_STREAM_QUANTITY_LIMIT"
            state[layer_id] = quantity
            costs[layer_id] = unit_cost
            origins[layer_id] = None
        return state, costs, origins

    def _normalize_open_rate(self, rate):
        if not isinstance(rate, FifoOpenCostRate):
            return "FIFO_OPEN_RATE_INPUT_INVALID"
        layer_id = self._identifier(rate.layer_id)
        unit_cost = self._money(rate.unit_cost_rub)
        if layer_id is None or unit_cost is None:
            return "FIFO_OPEN_RATE_INPUT_INVALID"
        if rate.currency != "RUB":
            return "FIFO_CURRENCY_UNSUPPORTED"
        return layer_id, unit_cost

    def _normalize_events(self, events):
        rows = self._bounded_rows(events, _MAX_EVENTS_PER_REPLAY)
        if rows is None:
            return "FIFO_EVENT_INPUT_INVALID"
        if len(rows) > _MAX_EVENTS_PER_REPLAY:
            return "FIFO_REPLAY_EVENT_LIMIT"
        normalized = []
        restore_slice_count = 0
        for event in rows:
            if not isinstance(event, (FifoSaleEvent, FifoRestockEvent, FifoOutflowEvent)):
                return "FIFO_EVENT_INPUT_INVALID"
            event_id = self._identifier(event.event_id)
            quantity = self._quantity(event.quantity)
            if event_id is None or quantity is None:
                return "FIFO_EVENT_INPUT_INVALID"
            if quantity > self.MAX_UNITS_PER_EVENT:
                return "FIFO_EVENT_QUANTITY_LIMIT"
            if isinstance(event, FifoOutflowEvent):
                reason = event.reason_code
                if reason not in {
                    "HOME_SHORTAGE", "OZON_DISPOSAL", "SUPPLIER_RETURN",
                    "INVENTORY_WRITE_OFF",
                }:
                    return "FIFO_OUTFLOW_REASON_INVALID"
                normalized.append(FifoOutflowEvent(event_id, quantity, reason))
            elif isinstance(event, FifoRestockEvent):
                if not isinstance(event.restores, tuple) or not event.restores:
                    return "FIFO_RETURN_BASIS_MISSING"
                restore_slice_count += len(event.restores)
                if restore_slice_count > _MAX_REPLAY_ALLOCATION_LINES:
                    return "FIFO_REPLAY_WORK_LIMIT"
                slices = []
                for item in event.restores:
                    if not isinstance(item, FifoRestoreSlice):
                        return "FIFO_EVENT_INPUT_INVALID"
                    sale_id = self._identifier(item.sale_event_id)
                    layer_id = self._identifier(item.layer_id)
                    restore_quantity = self._quantity(item.quantity)
                    if sale_id is None or layer_id is None or restore_quantity is None:
                        return "FIFO_EVENT_INPUT_INVALID"
                    slices.append(FifoRestoreSlice(sale_id, layer_id, restore_quantity))
                if sum(item.quantity for item in slices) != quantity:
                    return "FIFO_RETURN_BASIS_QUANTITY_MISMATCH"
                normalized.append(FifoRestockEvent(event_id, quantity, tuple(slices)))
            else:
                normalized.append(FifoSaleEvent(event_id, quantity))
        return tuple(normalized)

    @staticmethod
    def _bounded_rows(values, limit):
        try:
            iterator = iter(values)
        except MemoryError:
            raise
        except Exception:
            return None
        rows = []
        for _ in range(limit + 1):
            try:
                rows.append(next(iterator))
            except StopIteration:
                break
            except MemoryError:
                raise
            except Exception:
                return None
        return tuple(rows)

    @staticmethod
    def _identifier(value):
        if not isinstance(value, str):
            return None
        normalized = value.strip()
        if not normalized or len(normalized) > _MAX_IDENTIFIER_LENGTH:
            return None
        return normalized

    @classmethod
    def _quantity(cls, value):
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            return None
        if value > cls.MAX_UNITS_PER_EVENT:
            return None
        return value

    @classmethod
    def _stream_quantity(cls, value):
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            return None
        if value > cls.MAX_UNITS_IN_STREAM:
            return None
        return value

    @staticmethod
    def _money(value):
        if isinstance(value, bool) or isinstance(value, float):
            return None
        if not isinstance(value, (Decimal, str, int)):
            return None
        try:
            amount = Decimal(value).quantize(_CENT, rounding=ROUND_HALF_UP)
        except (InvalidOperation, TypeError, ValueError, OverflowError):
            return None
        if not amount.is_finite() or amount < 0:
            return None
        if amount > Decimal("1000000000.00"):
            return None
        return amount

    @staticmethod
    def _incomplete(reason_code):
        return FifoAllocationResult(
            status="FIFO_ALLOCATION_INCOMPLETE",
            complete=False,
            reason_code=reason_code,
            sale_allocations=(),
            outflow_allocations=(),
            total_cogs_rub=None,
            non_sale_outflow_value_rub=None,
            inventory_restored_value_rub=None,
            restored_units=None,
            remaining_confirmed_units=None,
            total_available_units=None,
            next_unit_cost_rub=None,
            next_unit_cost_status="UNAVAILABLE",
        )
