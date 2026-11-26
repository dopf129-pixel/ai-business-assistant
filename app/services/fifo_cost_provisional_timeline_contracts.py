"""Typed contracts for non-authoritative provisional FIFO timeline inputs."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from enum import Enum
import re
from types import MappingProxyType

from services.fifo_cost_transition_contracts import (
    ScopeIdentity,
    normalize_digest,
    normalize_quantity,
    normalize_store_timezone,
    source_fingerprint,
)


class ProvisionalTimelineEventKind(str, Enum):
    SUPPLY_RECEIVED = "SUPPLY_RECEIVED"
    OPENING_TRANSIT_LINK = "OPENING_TRANSIT_LINK"
    BUYER_DISPATCH = "BUYER_DISPATCH"
    BUYOUT = "BUYOUT"
    NON_BUYOUT_RESTOCK = "NON_BUYOUT_RESTOCK"
    SALE_RETURN_RESTOCK = "SALE_RETURN_RESTOCK"
    RELEASE_HOLD = "RELEASE_HOLD"
    NON_SALE_REMOVE = "NON_SALE_REMOVE"


class ProvisionalStockZone(str, Enum):
    AVAILABLE = "available"
    EXPIRING = "expiring"
    DEFECTIVE = "defective"
    CHECKING = "checking"
    INTERNAL_TRANSFER = "internal_transfer"
    SELLER_WITHDRAWAL = "seller_withdrawal"
    BUYER_RETURN_TRANSIT = "buyer_return_transit"
    BUYER_DELIVERY = "buyer_delivery"


class ProvisionalEventSource(str, Enum):
    FBO_CSV = "FBO_CSV"
    OWNER_MOVEMENTS_CSV = "OWNER_MOVEMENTS_CSV"
    SAVED_TYPED_EVIDENCE = "SAVED_TYPED_EVIDENCE"


class ProvisionalTimelineIssue(str, Enum):
    FBO_SCOPE_MISMATCH = "FBO_SCOPE_MISMATCH"
    MOVEMENT_SCOPE_MISMATCH = "MOVEMENT_SCOPE_MISMATCH"
    SAVED_EVIDENCE_UNAVAILABLE = "SAVED_EVIDENCE_UNAVAILABLE"
    SAVED_REPORT_VERSION_CONFLICT = "SAVED_REPORT_VERSION_CONFLICT"
    REPORTS_ARE_AGGREGATE_ONLY = "REPORTS_ARE_AGGREGATE_ONLY"
    FBO_DISPATCH_TIME_MISSING = "FBO_DISPATCH_TIME_MISSING"
    FBO_DELIVERY_TIME_MISSING = "FBO_DELIVERY_TIME_MISSING"
    FBO_CANCELLED_UNRESOLVED = "FBO_CANCELLED_UNRESOLVED"
    FBO_UNKNOWN_STATUS = "FBO_UNKNOWN_STATUS"
    FBO_OPENING_LINK_REQUIRED = "FBO_OPENING_LINK_REQUIRED"
    EVENT_REFERENCE_UNMATCHED = "EVENT_REFERENCE_UNMATCHED"
    EVENT_QUANTITY_EXCEEDS_POSTING = "EVENT_QUANTITY_EXCEEDS_POSTING"
    EVENT_STATUS_MISMATCH = "EVENT_STATUS_MISMATCH"
    EVENT_ORDER_CONFLICT = "EVENT_ORDER_CONFLICT"
    EVENT_DUPLICATE_CONFLICT = "EVENT_DUPLICATE_CONFLICT"
    TIMESTAMP_PRECISION_INSUFFICIENT = "TIMESTAMP_PRECISION_INSUFFICIENT"
    TIMELINE_SCOPE_MISMATCH = "TIMELINE_SCOPE_MISMATCH"
    TIMELINE_COST_INVALID = "TIMELINE_COST_INVALID"
    TIMELINE_QUANTITY_LIMIT = "TIMELINE_QUANTITY_LIMIT"
    TIMELINE_EVENT_OUTSIDE_WINDOW = "TIMELINE_EVENT_OUTSIDE_WINDOW"
    TIMELINE_EVENT_ORDER_AMBIGUOUS = "TIMELINE_EVENT_ORDER_AMBIGUOUS"
    TIMELINE_NEGATIVE_AVAILABLE_STOCK = "TIMELINE_NEGATIVE_AVAILABLE_STOCK"
    TIMELINE_OPENING_LINK_INVALID = "TIMELINE_OPENING_LINK_INVALID"
    TIMELINE_DUPLICATE_POSTING = "TIMELINE_DUPLICATE_POSTING"
    TIMELINE_UNSUPPORTED_EVENT = "TIMELINE_UNSUPPORTED_EVENT"
    TIMELINE_BUYOUT_UNMATCHED = "TIMELINE_BUYOUT_UNMATCHED"
    TIMELINE_BUYOUT_QUANTITY_MISMATCH = "TIMELINE_BUYOUT_QUANTITY_MISMATCH"
    TIMELINE_BUYOUT_DUPLICATE = "TIMELINE_BUYOUT_DUPLICATE"
    TIMELINE_RESTOCK_UNMATCHED = "TIMELINE_RESTOCK_UNMATCHED"
    TIMELINE_RESTOCK_QUANTITY_EXCEEDS_RESERVE = "TIMELINE_RESTOCK_QUANTITY_EXCEEDS_RESERVE"
    TIMELINE_RESTOCK_AFTER_BUYOUT = "TIMELINE_RESTOCK_AFTER_BUYOUT"
    TIMELINE_RETURN_ALLOCATION_AMBIGUOUS = "TIMELINE_RETURN_ALLOCATION_AMBIGUOUS"
    TIMELINE_SALE_RETURN_UNMATCHED = "TIMELINE_SALE_RETURN_UNMATCHED"
    TIMELINE_SALE_RETURN_EXCEEDS_BUYOUT = "TIMELINE_SALE_RETURN_EXCEEDS_BUYOUT"
    TIMELINE_ORIGIN_LAYER_MISSING = "TIMELINE_ORIGIN_LAYER_MISSING"
    TIMELINE_OPENING_HELD_INVALID = "TIMELINE_OPENING_HELD_INVALID"
    TIMELINE_HELD_STOCK_INSUFFICIENT = "TIMELINE_HELD_STOCK_INSUFFICIENT"
    TIMELINE_HELD_RELEASE_AMBIGUOUS = "TIMELINE_HELD_RELEASE_AMBIGUOUS"
    TIMELINE_NON_SALE_REMOVE_AMBIGUOUS = "TIMELINE_NON_SALE_REMOVE_AMBIGUOUS"


def scope_fingerprint(scope: ScopeIdentity, timezone_name: str) -> str:
    if not isinstance(scope, ScopeIdentity):
        raise ValueError("FIFO_PROVISIONAL_SCOPE_INVALID")
    timezone_name = normalize_store_timezone(timezone_name)
    return source_fingerprint({
        "owner_id": scope.owner_id,
        "store_id": scope.store_id,
        "product_id": scope.product_id,
        "offer_id": scope.offer_id,
        "sku": scope.sku,
        "timezone": timezone_name,
    })


@dataclass(frozen=True, slots=True)
class ProvisionalTimelineEvent:
    """One redacted model event. Raw references and posting numbers are absent."""

    event_key: str
    source_key: str
    scope_fingerprint: str
    event_kind: ProvisionalTimelineEventKind
    finance_sku: str
    quantity: int
    local_date: date
    effective_at_utc: datetime | None
    time_precision: str
    source: ProvisionalEventSource
    posting_key: str | None = None
    stock_zone: ProvisionalStockZone | None = None
    resellable: bool | None = None

    def __post_init__(self):
        object.__setattr__(self, "event_key", normalize_digest(self.event_key))
        object.__setattr__(self, "source_key", normalize_digest(self.source_key))
        object.__setattr__(self, "scope_fingerprint", normalize_digest(self.scope_fingerprint))
        if not isinstance(self.event_kind, ProvisionalTimelineEventKind):
            raise ValueError("FIFO_PROVISIONAL_TIMELINE_EVENT_INVALID")
        if not isinstance(self.source, ProvisionalEventSource):
            raise ValueError("FIFO_PROVISIONAL_TIMELINE_EVENT_INVALID")
        if not isinstance(self.finance_sku, str) or not re.fullmatch(r"[0-9]{1,40}", self.finance_sku):
            raise ValueError("FIFO_PROVISIONAL_TIMELINE_SKU_INVALID")
        object.__setattr__(self, "quantity", normalize_quantity(self.quantity))
        if self.quantity <= 0 or self.quantity > 1_000_000:
            raise ValueError("FIFO_PROVISIONAL_TIMELINE_QUANTITY_INVALID")
        if not isinstance(self.local_date, date) or isinstance(self.local_date, datetime):
            raise ValueError("FIFO_PROVISIONAL_TIMELINE_TIME_INVALID")
        if self.time_precision not in {"DAY", "INSTANT"}:
            raise ValueError("FIFO_PROVISIONAL_TIMELINE_TIME_INVALID")
        if self.time_precision == "DAY" and self.effective_at_utc is not None:
            raise ValueError("FIFO_PROVISIONAL_TIMELINE_TIME_INVALID")
        if self.time_precision == "INSTANT":
            value = self.effective_at_utc
            if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
                raise ValueError("FIFO_PROVISIONAL_TIMELINE_TIME_INVALID")
            object.__setattr__(self, "effective_at_utc", value.astimezone(timezone.utc))
        if self.posting_key is not None:
            object.__setattr__(self, "posting_key", normalize_digest(self.posting_key))
        if self.stock_zone is not None and not isinstance(self.stock_zone, ProvisionalStockZone):
            raise ValueError("FIFO_PROVISIONAL_TIMELINE_ZONE_INVALID")
        if self.resellable is not None and type(self.resellable) is not bool:
            raise ValueError("FIFO_PROVISIONAL_TIMELINE_RESELLABLE_INVALID")
        kind = self.event_kind
        if kind in {
            ProvisionalTimelineEventKind.OPENING_TRANSIT_LINK,
            ProvisionalTimelineEventKind.NON_BUYOUT_RESTOCK,
            ProvisionalTimelineEventKind.SALE_RETURN_RESTOCK,
            ProvisionalTimelineEventKind.BUYER_DISPATCH,
            ProvisionalTimelineEventKind.BUYOUT,
        } and self.posting_key is None:
            raise ValueError("FIFO_PROVISIONAL_TIMELINE_POSTING_REQUIRED")
        if kind in {ProvisionalTimelineEventKind.RELEASE_HOLD,
                    ProvisionalTimelineEventKind.NON_SALE_REMOVE,
                    ProvisionalTimelineEventKind.SUPPLY_RECEIVED} and self.stock_zone is None:
            raise ValueError("FIFO_PROVISIONAL_TIMELINE_ZONE_REQUIRED")
        if (kind is ProvisionalTimelineEventKind.SUPPLY_RECEIVED
                and self.stock_zone is ProvisionalStockZone.BUYER_DELIVERY):
            raise ValueError("FIFO_PROVISIONAL_TIMELINE_ZONE_INVALID")
        if kind in {ProvisionalTimelineEventKind.NON_BUYOUT_RESTOCK,
                    ProvisionalTimelineEventKind.SALE_RETURN_RESTOCK}:
            if type(self.resellable) is not bool:
                raise ValueError("FIFO_PROVISIONAL_TIMELINE_RESELLABLE_REQUIRED")
        elif self.resellable is not None:
            raise ValueError("FIFO_PROVISIONAL_TIMELINE_RESELLABLE_NOT_ALLOWED")

    def safe_payload(self):
        return {
            "event_key": self.event_key,
            "source_key": self.source_key,
            "scope_fingerprint": self.scope_fingerprint,
            "kind": self.event_kind.value,
            "sku": self.finance_sku,
            "quantity": self.quantity,
            "local_date": self.local_date.isoformat(),
            "effective_at_utc": self.effective_at_utc.isoformat() if self.effective_at_utc else None,
            "time_precision": self.time_precision,
            "source": self.source.value,
            "posting_key": self.posting_key,
            "stock_zone": self.stock_zone.value if self.stock_zone else None,
            "resellable": self.resellable,
        }


@dataclass(frozen=True, slots=True)
class ProvisionalTimelineAnchor:
    """Saved typed evidence used only as an aggregate control, never an event."""

    report_type: str
    file_fingerprint: str
    period_from: str
    period_to: str
    scope_fingerprint: str
    aggregate_fields: object

    def __post_init__(self):
        if self.report_type not in {"TURNOVER", "STOCK_MANAGEMENT"}:
            raise ValueError("FIFO_PROVISIONAL_TIMELINE_ANCHOR_INVALID")
        object.__setattr__(self, "file_fingerprint", normalize_digest(self.file_fingerprint))
        object.__setattr__(self, "scope_fingerprint", normalize_digest(self.scope_fingerprint))
        if not isinstance(self.period_from, str) or not isinstance(self.period_to, str):
            raise ValueError("FIFO_PROVISIONAL_TIMELINE_ANCHOR_INVALID")
        if date.fromisoformat(self.period_to) < date.fromisoformat(self.period_from):
            raise ValueError("FIFO_PROVISIONAL_TIMELINE_ANCHOR_INVALID")
        if not isinstance(self.aggregate_fields, dict):
            raise ValueError("FIFO_PROVISIONAL_TIMELINE_ANCHOR_INVALID")
        object.__setattr__(self, "aggregate_fields", MappingProxyType(dict(self.aggregate_fields)))
