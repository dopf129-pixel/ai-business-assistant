"""Typed, fail-closed contracts for late FIFO transitions.

This module owns value validation only.  It performs no API calls, database
access, accounting, migration, or evidence approval.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from enum import Enum
import hashlib
import json
import re
from types import MappingProxyType
from typing import Callable, Mapping
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


CONTRACT_SCHEMA_VERSION = 1
MAX_TRANSITION_QUANTITY = 1_000_000
MAX_TRANSITION_MONEY = Decimal("1000000000")
MONEY_QUANTUM = Decimal("0.01")
DEFAULT_STORE_TIMEZONE = "Europe/Moscow"
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_SAFE_TOKEN_RE = re.compile(r"^[A-Z0-9_./-]{1,64}$")
_OPAQUE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{8,96}$")
_CELL_REFERENCE_RE = re.compile(r"^[A-Z]{1,3}[1-9][0-9]{0,6}$")
_FIELD_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


class TransitionReasonCode(str, Enum):
    CASE_NOT_READY = "CASE_NOT_READY"
    SUPPLY_OBSERVATION_MISSING = "SUPPLY_OBSERVATION_MISSING"
    SUPPLY_IDENTITY_CONFLICT = "SUPPLY_IDENTITY_CONFLICT"
    RECEIPT_CONFLICT = "RECEIPT_CONFLICT"
    STOCK_SCOPE_UNPROVEN = "STOCK_SCOPE_UNPROVEN"
    INVENTORY_CUTOFF_UNRECONCILED = "INVENTORY_CUTOFF_UNRECONCILED"
    EVENT_COVERAGE_INCOMPLETE = "EVENT_COVERAGE_INCOMPLETE"
    PREVIEW_STALE = "PREVIEW_STALE"
    IDEMPOTENCY_CONFLICT = "IDEMPOTENCY_CONFLICT"
    REPORT_FORMAT_UNSUPPORTED = "REPORT_FORMAT_UNSUPPORTED"
    CONTRACT_INVALID = "CONTRACT_INVALID"
    SCOPE_INVALID = "SCOPE_INVALID"
    MONEY_INVALID = "MONEY_INVALID"
    QUANTITY_INVALID = "QUANTITY_INVALID"
    DATE_INVALID = "DATE_INVALID"
    TIMESTAMP_INVALID = "TIMESTAMP_INVALID"
    TIMEZONE_INVALID = "TIMEZONE_INVALID"
    FINGERPRINT_INVALID = "FINGERPRINT_INVALID"
    SOURCE_PROOF_UNAVAILABLE = "SOURCE_PROOF_UNAVAILABLE"
    LOOKUP_REFERENCE_UNAVAILABLE = "LOOKUP_REFERENCE_UNAVAILABLE"
    COST_INPUT_INVALID = "COST_INPUT_INVALID"
    STATE_INVALID = "STATE_INVALID"
    REPORT_EVIDENCE_INVALID = "REPORT_EVIDENCE_INVALID"
    FIFO_RATE_BOUNDARY_UNPROVEN = "FIFO_RATE_BOUNDARY_UNPROVEN"
    FIFO_RATE_CHAIN_CONFLICT = "FIFO_RATE_CHAIN_CONFLICT"
    FIFO_RATE_BALANCE_MISMATCH = "FIFO_RATE_BALANCE_MISMATCH"
    FIFO_RATE_REPLAY_REQUIRED = "FIFO_RATE_REPLAY_REQUIRED"
    FIFO_TRANSITION_EVIDENCE_MISSING = "FIFO_TRANSITION_EVIDENCE_MISSING"
    FIFO_TRANSITION_EVIDENCE_CONFLICT = "FIFO_TRANSITION_EVIDENCE_CONFLICT"
    FIFO_TRANSITION_EVIDENCE_QUOTA_EXCEEDED = "FIFO_TRANSITION_EVIDENCE_QUOTA_EXCEEDED"
    FIFO_PHYSICAL_SALES_DOCUMENT_INVALID = "FIFO_PHYSICAL_SALES_DOCUMENT_INVALID"
    FIFO_TRANSITION_PREVIEW_STALE = "FIFO_TRANSITION_PREVIEW_STALE"
    FIFO_TRANSITION_CONFIRMATION_EXPIRED = "FIFO_TRANSITION_CONFIRMATION_EXPIRED"


class TransitionContractError(ValueError):
    """Validation error with a stable, non-sensitive reason code."""

    def __init__(self, reason_code: TransitionReasonCode):
        self.reason_code = reason_code
        super().__init__(reason_code.value)


class TransitionState(str, Enum):
    DRAFT = "DRAFT"
    AWAITING_EVIDENCE = "AWAITING_EVIDENCE"
    READY_TO_CONFIRM = "READY_TO_CONFIRM"
    APPLIED = "APPLIED"
    CANCELLED = "CANCELLED"


class CostInputMode(str, Enum):
    TOTAL_LANDED = "TOTAL_LANDED"
    COMPONENTS = "COMPONENTS"


class EvidenceSourceKind(str, Enum):
    OWNER_INPUT = "OWNER_INPUT"
    OWNER_IMPORTED = "OWNER_IMPORTED"
    OZON_API = "OZON_API"
    LOCAL_DERIVED = "LOCAL_DERIVED"


class EvidenceCompleteness(str, Enum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    UNKNOWN = "UNKNOWN"


class NormalizedSupplyStatus(str, Enum):
    DECLARED = "DECLARED"
    AT_DROPOFF = "AT_DROPOFF"
    IN_TRANSIT = "IN_TRANSIT"
    RECEIVING = "RECEIVING"
    PARTIALLY_ACCEPTED = "PARTIALLY_ACCEPTED"
    ACCEPTED = "ACCEPTED"
    CANCELLED = "CANCELLED"
    UNKNOWN = "UNKNOWN"


class EvidencePresence(str, Enum):
    PRESENT = "PRESENT"
    MISSING = "MISSING"


class TransitionBridgeEvidenceKind(str, Enum):
    PHYSICAL_SALES_DOCUMENT = "PHYSICAL_SALES_DOCUMENT"
    FINANCE_IDENTITY_SNAPSHOT = "FINANCE_IDENTITY_SNAPSHOT"
    MOVEMENT_COVERAGE = "MOVEMENT_COVERAGE"
    CUTOFF_SELECTION = "CUTOFF_SELECTION"
    OPENING_COMPOSITION = "OPENING_COMPOSITION"
    RATE_BOUNDARY_PROOF = "RATE_BOUNDARY_PROOF"
    PERIOD_SUMMARY_SNAPSHOT = "PERIOD_SUMMARY_SNAPSHOT"
    TAX_POLICY_SNAPSHOT = "TAX_POLICY_SNAPSHOT"


class TransitionEvidenceConfirmationKind(str, Enum):
    SOURCE_SELECTION = "SOURCE_SELECTION"
    PERIOD = "PERIOD"
    PHYSICAL_SALES = "PHYSICAL_SALES"
    MOVEMENT_COVERAGE = "MOVEMENT_COVERAGE"
    CUTOFF_SELECTION = "CUTOFF_SELECTION"
    OPENING_COMPOSITION = "OPENING_COMPOSITION"
    RATE_BOUNDARY = "RATE_BOUNDARY"
    TAX_POLICY = "TAX_POLICY"
    EVIDENCE_REVIEW = "EVIDENCE_REVIEW"


_BRIDGE_PAYLOAD_KEYS = {
    TransitionBridgeEvidenceKind.PHYSICAL_SALES_DOCUMENT: frozenset({
        "document_fingerprint", "row_count", "period_from", "period_to",
        "timezone", "semantics", "identity_fingerprint",
    }),
    TransitionBridgeEvidenceKind.FINANCE_IDENTITY_SNAPSHOT: frozenset({
        "snapshot_fingerprint", "identity_fingerprint", "row_count",
        "matched_rows", "page_count", "scope_complete", "pagination_complete",
    }),
    TransitionBridgeEvidenceKind.MOVEMENT_COVERAGE: frozenset({
        "snapshot_fingerprint", "identity_fingerprint", "event_count",
        "period_from", "complete_through", "page_count", "scope_complete",
        "pagination_complete",
    }),
    TransitionBridgeEvidenceKind.CUTOFF_SELECTION: frozenset({
        "cutoff_date", "complete_through", "bridge_fingerprint",
        "selected_event_count", "identity_fingerprint",
    }),
    TransitionBridgeEvidenceKind.OPENING_COMPOSITION: frozenset({
        "opening_date", "total_units", "component_count",
        "composition_fingerprint", "identity_fingerprint",
    }),
    TransitionBridgeEvidenceKind.RATE_BOUNDARY_PROOF: frozenset({
        "effective_date", "rate_fingerprint", "predecessor_fingerprint",
        "reconciliation_fingerprint", "replay_fingerprint", "identity_fingerprint",
    }),
    TransitionBridgeEvidenceKind.PERIOD_SUMMARY_SNAPSHOT: frozenset({
        "report_type", "period_from", "period_to", "row_count",
        "summary_fingerprint", "identity_fingerprint",
    }),
    TransitionBridgeEvidenceKind.TAX_POLICY_SNAPSHOT: frozenset({
        "tax_policy_fingerprint", "policy_code", "rate_percent",
        "effective_from", "calculation_basis", "identity_fingerprint",
    }),
}


_CONFIRMATION_PAYLOAD_KEYS = {
    TransitionEvidenceConfirmationKind.SOURCE_SELECTION: frozenset({
        "selected_source_fingerprint", "selection_reason",
    }),
    TransitionEvidenceConfirmationKind.PERIOD: frozenset({
        "period_from", "period_to", "timezone",
    }),
    TransitionEvidenceConfirmationKind.PHYSICAL_SALES: frozenset({
        "document_fingerprint", "row_count", "rows_fingerprint",
        "period_from", "period_to", "timezone", "semantics",
    }),
    TransitionEvidenceConfirmationKind.MOVEMENT_COVERAGE: frozenset({
        "coverage_fingerprint", "complete_through", "event_count",
    }),
    TransitionEvidenceConfirmationKind.CUTOFF_SELECTION: frozenset({
        "cutoff_date", "bridge_fingerprint", "stock_semantics",
    }),
    TransitionEvidenceConfirmationKind.OPENING_COMPOSITION: frozenset({
        "composition_fingerprint", "opening_date", "total_units",
    }),
    TransitionEvidenceConfirmationKind.RATE_BOUNDARY: frozenset({
        "rate_fingerprint", "effective_date", "reconciliation_fingerprint",
    }),
    TransitionEvidenceConfirmationKind.TAX_POLICY: frozenset({
        "tax_policy_fingerprint", "effective_from", "calculation_basis",
    }),
    TransitionEvidenceConfirmationKind.EVIDENCE_REVIEW: frozenset({
        "reviewed_fingerprint", "review_outcome",
    }),
}


@dataclass(frozen=True, slots=True)
class FifoFinancialPeriodSummary:
    """Frozen Period Profit values bound to exact financial sale identities.

    ``current_sku_product_cost_rub`` is the proven before-COGS for the exact
    transition sales listed here. ``current_total_product_cost_rub`` remains the
    canonical whole-store Period Profit cost, so all unaffected SKU and sale
    costs stay in the unchanged portion of the impact calculation.
    """

    period_from: str
    period_to: str
    source_fingerprint: str
    reconstruction_fingerprint: str
    tax_policy_fingerprint: str
    sale_identity_digests: tuple[str, ...]
    revenue_rub: Decimal
    discount_points_rub: Decimal
    net_accrual_rub: Decimal
    current_total_product_cost_rub: Decimal
    current_sku_product_cost_rub: Decimal
    complete: bool = True

    def __post_init__(self) -> None:
        start = normalize_date_only(self.period_from)
        end = normalize_date_only(self.period_to)
        if start > end or start[:7] != end[:7]:
            _fail(TransitionReasonCode.DATE_INVALID)
        object.__setattr__(self, "period_from", start)
        object.__setattr__(self, "period_to", end)
        for name in (
            "source_fingerprint", "reconstruction_fingerprint",
            "tax_policy_fingerprint",
        ):
            object.__setattr__(self, name, normalize_digest(getattr(self, name)))
        if type(self.complete) is not bool or self.complete is not True:
            _fail(TransitionReasonCode.EVENT_COVERAGE_INCOMPLETE)
        identities = self.sale_identity_digests
        if (
            not isinstance(identities, tuple)
            or not identities
            or len(identities) > 100_000
        ):
            _fail(TransitionReasonCode.EVENT_COVERAGE_INCOMPLETE)
        normalized_identities = tuple(normalize_digest(value) for value in identities)
        if len(normalized_identities) != len(set(normalized_identities)):
            _fail(TransitionReasonCode.FINGERPRINT_INVALID)
        object.__setattr__(self, "sale_identity_digests", normalized_identities)
        for name in (
            "revenue_rub", "discount_points_rub",
            "current_total_product_cost_rub", "current_sku_product_cost_rub",
        ):
            object.__setattr__(self, name, normalize_money(getattr(self, name)))
        net = self.net_accrual_rub
        if isinstance(net, bool) or not isinstance(net, (Decimal, int, str)):
            _fail(TransitionReasonCode.MONEY_INVALID)
        try:
            net = Decimal(str(net))
        except (InvalidOperation, ValueError):
            _fail(TransitionReasonCode.MONEY_INVALID)
        if not net.is_finite() or abs(net) > MAX_TRANSITION_MONEY:
            _fail(TransitionReasonCode.MONEY_INVALID)
        object.__setattr__(
            self, "net_accrual_rub",
            net.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP),
        )
        if self.current_sku_product_cost_rub > self.current_total_product_cost_rub:
            _fail(TransitionReasonCode.FIFO_RATE_BALANCE_MISMATCH)

    @property
    def period(self) -> str:
        return self.period_from[:7]

    def as_impact_summary(self) -> dict[str, object]:
        """Return the existing late-entry impact service input contract."""
        return {
            "period": self.period,
            "complete": self.complete,
            "source_fingerprint": self.source_fingerprint,
            "sale_identity_digests": list(self.sale_identity_digests),
            "revenue": format(self.revenue_rub, ".2f"),
            "discount_points": format(self.discount_points_rub, ".2f"),
            "net_accrual": format(self.net_accrual_rub, ".2f"),
            "current_total_product_cost": format(
                self.current_total_product_cost_rub, ".2f",
            ),
            "current_sku_product_cost": format(
                self.current_sku_product_cost_rub, ".2f",
            ),
            "period_from": self.period_from,
            "period_to": self.period_to,
            "reconstruction_fingerprint": self.reconstruction_fingerprint,
            "tax_policy_fingerprint": self.tax_policy_fingerprint,
        }


@dataclass(frozen=True, slots=True)
class TransitionBridgeEvidence:
    """Typed, bounded evidence envelope; sensitive source bytes remain separate."""

    metadata: TransitionMetadata
    evidence_kind: TransitionBridgeEvidenceKind
    captured_at: str
    payload: Mapping[str, object]
    sensitive_payload: str
    period_from: str | None = None
    period_to: str | None = None
    as_of: str | None = None
    complete_through: str | None = None
    row_count: int | None = None
    schema_version: int = 1

    def __post_init__(self) -> None:
        _require_metadata(self.metadata)
        if not isinstance(self.evidence_kind, TransitionBridgeEvidenceKind):
            _fail(TransitionReasonCode.CONTRACT_INVALID)
        if type(self.schema_version) is not int or self.schema_version != 1:
            _fail(TransitionReasonCode.CONTRACT_INVALID)
        if (self.period_from is None) != (self.period_to is None):
            _fail(TransitionReasonCode.DATE_INVALID)
        if self.period_from is not None:
            start = normalize_date_only(self.period_from)
            end = normalize_date_only(self.period_to)
            if end < start:
                _fail(TransitionReasonCode.DATE_INVALID)
            object.__setattr__(self, "period_from", start)
            object.__setattr__(self, "period_to", end)
        if self.as_of is not None:
            if self.period_from is not None:
                _fail(TransitionReasonCode.CONTRACT_INVALID)
            object.__setattr__(self, "as_of", normalize_utc_timestamp(self.as_of))
        if self.complete_through is not None:
            object.__setattr__(
                self, "complete_through", normalize_date_only(self.complete_through),
            )
        object.__setattr__(self, "captured_at", normalize_utc_timestamp(self.captured_at))
        if self.row_count is not None:
            count = normalize_quantity(self.row_count)
            if count < 1 or count > 50_000:
                _fail(TransitionReasonCode.FIFO_TRANSITION_EVIDENCE_QUOTA_EXCEEDED)
            object.__setattr__(self, "row_count", count)
        if self.evidence_kind is TransitionBridgeEvidenceKind.PHYSICAL_SALES_DOCUMENT:
            if self.metadata.source_kind is not EvidenceSourceKind.OWNER_IMPORTED:
                _fail(TransitionReasonCode.CONTRACT_INVALID)
            if self.row_count is None or self.period_from is None:
                _fail(TransitionReasonCode.FIFO_PHYSICAL_SALES_DOCUMENT_INVALID)
        if not isinstance(self.sensitive_payload, str) or not self.sensitive_payload:
            _fail(TransitionReasonCode.CONTRACT_INVALID)
        raw_size = len(self.sensitive_payload.encode("utf-8"))
        raw_limit = (
            12 * 1024 * 1024
            if self.evidence_kind is TransitionBridgeEvidenceKind.PHYSICAL_SALES_DOCUMENT
            else 48 * 1024 * 1024
        )
        if raw_size > raw_limit:
            _fail(TransitionReasonCode.FIFO_TRANSITION_EVIDENCE_QUOTA_EXCEEDED)
        _validate_bridge_source(self.evidence_kind, self.metadata.source_kind)
        normalized = _validate_transition_bridge_payload(self.evidence_kind, self.payload)
        _validate_bridge_completeness(self)
        object.__setattr__(self, "payload", MappingProxyType(normalized))


@dataclass(frozen=True, slots=True)
class TransitionEvidenceConfirmation:
    """Typed owner confirmation bound by the repository to one evidence hash."""

    confirmation_kind: TransitionEvidenceConfirmationKind
    confirmed_fields: Mapping[str, object]

    def __post_init__(self) -> None:
        if not isinstance(self.confirmation_kind, TransitionEvidenceConfirmationKind):
            _fail(TransitionReasonCode.CONTRACT_INVALID)
        normalized = _validate_transition_confirmation_fields(
            self.confirmation_kind, self.confirmed_fields,
        )
        object.__setattr__(self, "confirmed_fields", MappingProxyType(normalized))


@dataclass(frozen=True, slots=True)
class SupplyActEvidence:
    """Allowlisted acceptance-act facts; references are opaque digests only."""

    act_ref: str
    act_type: str
    act_state: str
    created_date: str | None
    declared_quantity: int | None
    approved_quantity: int | None
    fact_quantity: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "act_ref", normalize_digest(self.act_ref))
        if self.act_type != "ACCEPTANCE" or self.act_state != "ACCEPTED":
            _fail(TransitionReasonCode.CONTRACT_INVALID)
        if self.created_date is not None:
            object.__setattr__(self, "created_date", normalize_date_only(self.created_date))
        if self.fact_quantity is None:
            _fail(TransitionReasonCode.QUANTITY_INVALID)
        for name in ("declared_quantity", "approved_quantity", "fact_quantity"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, normalize_quantity(value))


class AcceptedQuantityKind(str, Enum):
    CUMULATIVE = "CUMULATIVE"
    DOCUMENT_LINES = "DOCUMENT_LINES"


class SupplyReferenceKind(str, Enum):
    ORDER = "ORDER"
    SUPPLY = "SUPPLY"


def supply_reference_digest(*, owner_id, store_id, reference_kind, reference_id):
    """Build the stable owner/store/type-scoped digest for a numeric lookup ID."""
    if not isinstance(owner_id, str) or not owner_id.strip() or len(owner_id.strip()) > 128:
        return None
    if not isinstance(store_id, str) or not store_id.strip() or len(store_id.strip()) > 128:
        return None
    try:
        kind = (
            reference_kind if isinstance(reference_kind, SupplyReferenceKind)
            else SupplyReferenceKind(str(reference_kind).strip().upper())
        )
    except (TypeError, ValueError):
        return None
    if isinstance(reference_id, bool) or not isinstance(reference_id, (str, int)):
        return None
    raw = str(reference_id).strip()
    if not raw.isascii() or not raw.isdigit() or len(raw) > 40:
        return None
    normalized_id = str(int(raw))
    if normalized_id == "0":
        return None
    material = "\0".join((
        "fifo-transition-reference:v1",
        owner_id.strip(),
        store_id.strip(),
        kind.value,
        normalized_id,
    ))
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


class ReportType(str, Enum):
    STOCK_MANAGEMENT = "STOCK_MANAGEMENT"
    TURNOVER = "TURNOVER"


class PeriodProvenance(str, Enum):
    FILENAME_CANDIDATE = "FILENAME_CANDIDATE"
    OWNER_CONFIRMED = "OWNER_CONFIRMED"
    API_AS_OF = "API_AS_OF"
    UNKNOWN = "UNKNOWN"


class StockBucket(str, Enum):
    AVAILABLE = "available"
    RESERVED = "reserved"
    PREPARING = "preparing"
    CHECKING = "checking"
    SUPPLIER_PLANNED = "supplier_planned"
    SUPPLIER_TRANSIT = "supplier_transit"
    SUPPLIER_RECEIVING = "supplier_receiving"
    BUYER_DELIVERY = "buyer_delivery"
    BUYER_RETURN_TRANSIT = "buyer_return_transit"
    INTERNAL_TRANSFER = "internal_transfer"
    DEFECTIVE = "defective"
    REMOVED_FROM_SALE = "removed_from_sale"
    SELLER_WITHDRAWAL = "seller_withdrawal"


@dataclass(frozen=True, slots=True)
class ScopeIdentity:
    owner_id: str
    store_id: str
    sku: str
    product_id: str | None = None
    offer_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "owner_id", _required_text(self.owner_id, 128))
        object.__setattr__(self, "store_id", _required_text(self.store_id, 128))
        object.__setattr__(self, "sku", _required_text(self.sku, 64))
        object.__setattr__(self, "product_id", _optional_text(self.product_id, 128))
        object.__setattr__(self, "offer_id", _optional_text(self.offer_id, 128))
        if self.product_id is None and self.offer_id is None:
            _fail(TransitionReasonCode.SCOPE_INVALID)


@dataclass(frozen=True, slots=True)
class TransitionMetadata:
    scope: ScopeIdentity
    source_kind: EvidenceSourceKind
    completeness: EvidenceCompleteness
    source_fingerprint: str
    schema_version: int = CONTRACT_SCHEMA_VERSION
    store_timezone: str = DEFAULT_STORE_TIMEZONE

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != CONTRACT_SCHEMA_VERSION:
            _fail(TransitionReasonCode.CONTRACT_INVALID)
        if not isinstance(self.scope, ScopeIdentity):
            _fail(TransitionReasonCode.SCOPE_INVALID)
        if not isinstance(self.source_kind, EvidenceSourceKind):
            _fail(TransitionReasonCode.CONTRACT_INVALID)
        if not isinstance(self.completeness, EvidenceCompleteness):
            _fail(TransitionReasonCode.CONTRACT_INVALID)
        object.__setattr__(
            self, "source_fingerprint", normalize_digest(self.source_fingerprint),
        )
        object.__setattr__(
            self, "store_timezone", normalize_store_timezone(self.store_timezone),
        )


@dataclass(frozen=True, slots=True)
class UnknownValue:
    reason_code: TransitionReasonCode
    source_kind: EvidenceSourceKind

    def __post_init__(self) -> None:
        if not isinstance(self.reason_code, TransitionReasonCode):
            _fail(TransitionReasonCode.CONTRACT_INVALID)
        if not isinstance(self.source_kind, EvidenceSourceKind):
            _fail(TransitionReasonCode.CONTRACT_INVALID)


@dataclass(frozen=True, slots=True)
class CostComponents:
    purchase_cost_rub: Decimal
    delivery_cost_rub: Decimal
    packaging_cost_rub: Decimal

    def __post_init__(self) -> None:
        for name in (
            "purchase_cost_rub", "delivery_cost_rub", "packaging_cost_rub",
        ):
            object.__setattr__(self, name, normalize_money(getattr(self, name)))

    @property
    def total_rub(self) -> Decimal:
        return normalize_money(
            self.purchase_cost_rub + self.delivery_cost_rub + self.packaging_cost_rub,
        )


@dataclass(frozen=True, slots=True)
class TransitionCase:
    metadata: TransitionMetadata
    case_id: str
    case_revision: int
    state: TransitionState
    created_at: str
    updated_at: str
    dispatch_date: str | None
    old_unit_cost_rub: Decimal | None
    new_unit_cost_rub: Decimal | None
    cost_input_mode: CostInputMode
    cost_components: CostComponents | None
    owner_old_home_units: int | None
    owner_old_transit_units: int | None
    new_home_quantity: int | None
    declared_shipped_units: int | None
    opening_evidence_ref: str | None = None
    source_watermark: str | None = None
    reason_codes: tuple[TransitionReasonCode, ...] = ()
    supersedes_case_id: str | None = None
    unknown_values: Mapping[str, UnknownValue] = field(default_factory=dict)

    _OPTIONAL_FIELDS = frozenset({
        "dispatch_date", "old_unit_cost_rub", "new_unit_cost_rub",
        "owner_old_home_units", "owner_old_transit_units", "new_home_quantity",
        "declared_shipped_units",
    })

    def __post_init__(self) -> None:
        if not isinstance(self.metadata, TransitionMetadata):
            _fail(TransitionReasonCode.CONTRACT_INVALID)
        if self.metadata.source_kind is not EvidenceSourceKind.OWNER_INPUT:
            _fail(TransitionReasonCode.CONTRACT_INVALID)
        object.__setattr__(self, "case_id", _opaque_id(self.case_id))
        if type(self.case_revision) is not int or self.case_revision < 1:
            _fail(TransitionReasonCode.CONTRACT_INVALID)
        if not isinstance(self.state, TransitionState):
            _fail(TransitionReasonCode.STATE_INVALID)
        if not isinstance(self.cost_input_mode, CostInputMode):
            _fail(TransitionReasonCode.COST_INPUT_INVALID)
        object.__setattr__(self, "created_at", normalize_utc_timestamp(self.created_at))
        object.__setattr__(self, "updated_at", normalize_utc_timestamp(self.updated_at))
        if self.updated_at < self.created_at:
            _fail(TransitionReasonCode.TIMESTAMP_INVALID)
        if self.dispatch_date is not None:
            object.__setattr__(self, "dispatch_date", normalize_date_only(self.dispatch_date))

        for name in ("old_unit_cost_rub", "new_unit_cost_rub"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, normalize_money(value))
        for name in (
            "owner_old_home_units", "owner_old_transit_units", "new_home_quantity",
            "declared_shipped_units",
        ):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, normalize_quantity(value))

        unknown = dict(self.unknown_values)
        if set(unknown) - self._OPTIONAL_FIELDS:
            _fail(TransitionReasonCode.CONTRACT_INVALID)
        for name in self._OPTIONAL_FIELDS:
            value = getattr(self, name)
            if value is None:
                if name not in unknown:
                    _fail(TransitionReasonCode.CONTRACT_INVALID)
                if not isinstance(unknown[name], UnknownValue):
                    _fail(TransitionReasonCode.CONTRACT_INVALID)
            elif name in unknown:
                _fail(TransitionReasonCode.CONTRACT_INVALID)
        object.__setattr__(self, "unknown_values", MappingProxyType(unknown))

        if self.cost_input_mode is CostInputMode.TOTAL_LANDED:
            if self.cost_components is not None:
                _fail(TransitionReasonCode.COST_INPUT_INVALID)
        elif self.cost_input_mode is CostInputMode.COMPONENTS:
            if self.new_unit_cost_rub is None:
                if self.cost_components is not None:
                    _fail(TransitionReasonCode.COST_INPUT_INVALID)
            elif (
                not isinstance(self.cost_components, CostComponents)
                or self.cost_components.total_rub != self.new_unit_cost_rub
            ):
                _fail(TransitionReasonCode.COST_INPUT_INVALID)

        if not isinstance(self.reason_codes, tuple) or any(
            not isinstance(code, TransitionReasonCode) for code in self.reason_codes
        ):
            _fail(TransitionReasonCode.CONTRACT_INVALID)
        object.__setattr__(self, "opening_evidence_ref", _optional_opaque_id(self.opening_evidence_ref))
        object.__setattr__(self, "supersedes_case_id", _optional_opaque_id(self.supersedes_case_id))
        object.__setattr__(self, "source_watermark", _optional_text(self.source_watermark, 256))


@dataclass(frozen=True, slots=True)
class SupplyDeclaration:
    metadata: TransitionMetadata
    case_id: str
    declaration_id: str
    revision: int
    reference_kind: SupplyReferenceKind
    reference_digest: str
    encrypted_lookup_reference: str | None
    declared_shipped_units: int | None
    dispatch_date: str | None
    provenance: EvidenceSourceKind
    unknown_values: Mapping[str, UnknownValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_metadata(self.metadata)
        if self.metadata.source_kind is not EvidenceSourceKind.OWNER_INPUT:
            _fail(TransitionReasonCode.CONTRACT_INVALID)
        object.__setattr__(self, "case_id", _opaque_id(self.case_id))
        object.__setattr__(self, "declaration_id", _opaque_id(self.declaration_id))
        if type(self.revision) is not int or self.revision < 1:
            _fail(TransitionReasonCode.CONTRACT_INVALID)
        if not isinstance(self.reference_kind, SupplyReferenceKind):
            _fail(TransitionReasonCode.CONTRACT_INVALID)
        object.__setattr__(self, "reference_digest", normalize_digest(self.reference_digest))
        object.__setattr__(
            self, "encrypted_lookup_reference",
            _optional_ciphertext(self.encrypted_lookup_reference),
        )
        unknown = dict(self.unknown_values)
        if set(unknown) - {"declared_shipped_units", "lookup_reference"}:
            _fail(TransitionReasonCode.CONTRACT_INVALID)
        if self.encrypted_lookup_reference is None:
            _require_unknown(unknown, "lookup_reference")
            if (
                unknown["lookup_reference"].reason_code
                is not TransitionReasonCode.LOOKUP_REFERENCE_UNAVAILABLE
                or unknown["lookup_reference"].source_kind
                is not EvidenceSourceKind.OWNER_INPUT
            ):
                _fail(TransitionReasonCode.CONTRACT_INVALID)
        else:
            _reject_unknown(unknown, "lookup_reference")
        if self.declared_shipped_units is None:
            _require_unknown(unknown, "declared_shipped_units")
        else:
            object.__setattr__(self, "declared_shipped_units", normalize_quantity(self.declared_shipped_units))
            _reject_unknown(unknown, "declared_shipped_units")
        if self.dispatch_date is not None:
            object.__setattr__(self, "dispatch_date", normalize_date_only(self.dispatch_date))
        if not isinstance(self.provenance, EvidenceSourceKind):
            _fail(TransitionReasonCode.CONTRACT_INVALID)
        if self.provenance is not EvidenceSourceKind.OWNER_INPUT:
            _fail(TransitionReasonCode.CONTRACT_INVALID)
        object.__setattr__(self, "unknown_values", MappingProxyType(unknown))


@dataclass(frozen=True, slots=True)
class SupplyObservation:
    metadata: TransitionMetadata
    declaration_id: str
    captured_at: str
    source_as_of: str | None
    raw_status: str | None
    normalized_status: NormalizedSupplyStatus
    declared_quantity: int | None
    accepted_quantity: int | None
    accepted_quantity_kind: AcceptedQuantityKind | None
    act_reference_digest: str | None
    act_version_digest: str | None
    scope_complete: bool
    pagination_complete: bool
    presence: EvidencePresence
    unknown_values: Mapping[str, UnknownValue] = field(default_factory=dict)
    act_captured_at: str | None = None
    act_source_fingerprint: str | None = None
    act_source_supply_reference_digest: str | None = None
    act_order_reference_digest: str | None = None
    act_evidence: tuple[SupplyActEvidence, ...] = ()

    def __post_init__(self) -> None:
        _require_metadata(self.metadata)
        if self.metadata.source_kind is not EvidenceSourceKind.OZON_API:
            _fail(TransitionReasonCode.CONTRACT_INVALID)
        object.__setattr__(self, "declaration_id", _opaque_id(self.declaration_id))
        object.__setattr__(self, "captured_at", normalize_utc_timestamp(self.captured_at))
        if self.source_as_of is not None:
            object.__setattr__(self, "source_as_of", normalize_utc_timestamp(self.source_as_of))
        if self.raw_status is not None:
            if not isinstance(self.raw_status, str):
                _fail(TransitionReasonCode.CONTRACT_INVALID)
            raw = self.raw_status.strip().upper()
            if not _SAFE_TOKEN_RE.fullmatch(raw):
                _fail(TransitionReasonCode.CONTRACT_INVALID)
            object.__setattr__(self, "raw_status", raw)
        if not isinstance(self.normalized_status, NormalizedSupplyStatus):
            _fail(TransitionReasonCode.CONTRACT_INVALID)
        if not isinstance(self.presence, EvidencePresence):
            _fail(TransitionReasonCode.CONTRACT_INVALID)
        for name in ("scope_complete", "pagination_complete"):
            if type(getattr(self, name)) is not bool:
                _fail(TransitionReasonCode.CONTRACT_INVALID)
        unknown = dict(self.unknown_values)
        if set(unknown) - {"declared_quantity", "accepted_quantity"}:
            _fail(TransitionReasonCode.CONTRACT_INVALID)
        for name in ("declared_quantity", "accepted_quantity"):
            value = getattr(self, name)
            if value is None:
                _require_unknown(unknown, name)
            else:
                object.__setattr__(self, name, normalize_quantity(value))
                _reject_unknown(unknown, name)
        if self.accepted_quantity is None:
            if self.accepted_quantity_kind is not None:
                _fail(TransitionReasonCode.CONTRACT_INVALID)
        elif not isinstance(self.accepted_quantity_kind, AcceptedQuantityKind):
            _fail(TransitionReasonCode.CONTRACT_INVALID)
        for name in ("act_reference_digest", "act_version_digest"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, normalize_digest(value))
        for name in (
            "act_source_fingerprint", "act_source_supply_reference_digest",
            "act_order_reference_digest",
        ):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, normalize_digest(value))
        if self.act_captured_at is not None:
            object.__setattr__(self, "act_captured_at", normalize_utc_timestamp(self.act_captured_at))
        if not isinstance(self.act_evidence, tuple) or len(self.act_evidence) > 100:
            _fail(TransitionReasonCode.CONTRACT_INVALID)
        if any(not isinstance(item, SupplyActEvidence) for item in self.act_evidence):
            _fail(TransitionReasonCode.CONTRACT_INVALID)
        if self.act_evidence:
            references = tuple(sorted(item.act_ref for item in self.act_evidence))
            reference_digest = hashlib.sha256(
                json.dumps(
                    list(references), sort_keys=True, separators=(",", ":"),
                    ensure_ascii=True,
                ).encode("utf-8")
            ).hexdigest()
            if (
                self.accepted_quantity is None
                or self.accepted_quantity_kind is not AcceptedQuantityKind.DOCUMENT_LINES
                or len(set(references)) != len(references)
                or sum(item.fact_quantity for item in self.act_evidence) != self.accepted_quantity
                or self.act_reference_digest != reference_digest
                or self.act_version_digest is None
                or self.act_source_fingerprint is None
                or self.act_source_supply_reference_digest is None
                or self.act_order_reference_digest is None
                or self.act_captured_at is None
            ):
                _fail(TransitionReasonCode.CONTRACT_INVALID)
        elif self.accepted_quantity_kind is AcceptedQuantityKind.DOCUMENT_LINES:
            _fail(TransitionReasonCode.CONTRACT_INVALID)
        elif any((
            self.act_captured_at is not None,
            self.act_source_fingerprint is not None,
            self.act_source_supply_reference_digest is not None,
            self.act_order_reference_digest is not None,
        )):
            _fail(TransitionReasonCode.CONTRACT_INVALID)
        if self.presence is EvidencePresence.MISSING:
            if (
                self.declared_quantity is not None
                or self.accepted_quantity is not None
                or self.act_evidence
            ):
                _fail(TransitionReasonCode.CONTRACT_INVALID)
            if not unknown:
                _fail(TransitionReasonCode.CONTRACT_INVALID)
        object.__setattr__(self, "unknown_values", MappingProxyType(unknown))


@dataclass(frozen=True, slots=True)
class BucketSnapshot:
    metadata: TransitionMetadata
    captured_at: str
    source_as_of: str | None
    quantities: Mapping[StockBucket, int | None]
    unknown_values: Mapping[str, UnknownValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_metadata(self.metadata)
        if self.metadata.source_kind not in (
            EvidenceSourceKind.OZON_API, EvidenceSourceKind.OWNER_IMPORTED,
        ):
            _fail(TransitionReasonCode.CONTRACT_INVALID)
        object.__setattr__(self, "captured_at", normalize_utc_timestamp(self.captured_at))
        if self.source_as_of is not None:
            object.__setattr__(self, "source_as_of", normalize_utc_timestamp(self.source_as_of))
        normalized: dict[StockBucket, int | None] = {}
        unknown = dict(self.unknown_values)
        for bucket, value in self.quantities.items():
            if not isinstance(bucket, StockBucket):
                _fail(TransitionReasonCode.CONTRACT_INVALID)
            name = bucket.value
            if value is None:
                _require_unknown(unknown, name)
                normalized[bucket] = None
            else:
                normalized[bucket] = normalize_quantity(value)
                _reject_unknown(unknown, name)
        if not normalized or set(unknown) - {bucket.value for bucket in normalized}:
            _fail(TransitionReasonCode.CONTRACT_INVALID)
        object.__setattr__(self, "quantities", MappingProxyType(normalized))
        object.__setattr__(self, "unknown_values", MappingProxyType(unknown))


@dataclass(frozen=True, slots=True)
class ReportEvidence:
    metadata: TransitionMetadata
    report_type: ReportType
    period_from: str | None
    period_to: str | None
    period_provenance: PeriodProvenance
    captured_at: str
    file_sha256: str
    parser_version: str
    cell_references: tuple[str, ...]
    normalized_fields: Mapping[str, object]

    def __post_init__(self) -> None:
        _require_metadata(self.metadata)
        if self.metadata.source_kind not in (
            EvidenceSourceKind.OZON_API, EvidenceSourceKind.OWNER_IMPORTED,
        ):
            _fail(TransitionReasonCode.REPORT_EVIDENCE_INVALID)
        if not isinstance(self.report_type, ReportType):
            _fail(TransitionReasonCode.REPORT_EVIDENCE_INVALID)
        if not isinstance(self.period_provenance, PeriodProvenance):
            _fail(TransitionReasonCode.REPORT_EVIDENCE_INVALID)
        if (self.period_from is None) != (self.period_to is None):
            _fail(TransitionReasonCode.REPORT_EVIDENCE_INVALID)
        if self.period_from is not None:
            start = normalize_date_only(self.period_from)
            end = normalize_date_only(self.period_to)
            if end < start:
                _fail(TransitionReasonCode.REPORT_EVIDENCE_INVALID)
            object.__setattr__(self, "period_from", start)
            object.__setattr__(self, "period_to", end)
        object.__setattr__(self, "captured_at", normalize_utc_timestamp(self.captured_at))
        object.__setattr__(self, "file_sha256", normalize_digest(self.file_sha256))
        parser_version = _required_text(self.parser_version, 64)
        if not re.fullmatch(r"[A-Za-z0-9._+-]{1,64}", parser_version):
            _fail(TransitionReasonCode.REPORT_EVIDENCE_INVALID)
        object.__setattr__(self, "parser_version", parser_version)
        if not isinstance(self.cell_references, tuple) or any(
            not isinstance(ref, str) or not _CELL_REFERENCE_RE.fullmatch(ref)
            for ref in self.cell_references
        ):
            _fail(TransitionReasonCode.REPORT_EVIDENCE_INVALID)
        if len(self.cell_references) > 100_000:
            _fail(TransitionReasonCode.REPORT_EVIDENCE_INVALID)
        fields = dict(self.normalized_fields)
        if len(fields) > 100 or any(
            not isinstance(key, str) or not _FIELD_NAME_RE.fullmatch(key)
            for key in fields
        ):
            _fail(TransitionReasonCode.REPORT_EVIDENCE_INVALID)
        for value in fields.values():
            _validate_json_value(value)
        object.__setattr__(
            self, "normalized_fields",
            MappingProxyType({key: _freeze_json(value) for key, value in fields.items()}),
        )


@dataclass(frozen=True, slots=True)
class SourceProof:
    """Coverage proof for a read, never proof of physical-time semantics."""

    metadata: TransitionMetadata
    scope_complete: bool
    pagination_complete: bool
    source_as_of: str | None = None

    def __post_init__(self) -> None:
        _require_metadata(self.metadata)
        if type(self.scope_complete) is not bool or type(self.pagination_complete) is not bool:
            _fail(TransitionReasonCode.CONTRACT_INVALID)
        if self.source_as_of is not None:
            object.__setattr__(self, "source_as_of", normalize_utc_timestamp(self.source_as_of))

    @property
    def api_read_complete(self) -> bool:
        return (
            self.metadata.source_kind is EvidenceSourceKind.OZON_API
            and self.metadata.completeness is EvidenceCompleteness.COMPLETE
            and self.scope_complete is True
            and self.pagination_complete is True
        )

    def require_api_read_complete(self) -> None:
        if not self.api_read_complete:
            _fail(TransitionReasonCode.EVENT_COVERAGE_INCOMPLETE)


@dataclass(frozen=True, slots=True)
class FinancialPreviewBinding:
    metadata: TransitionMetadata
    fifo_revision: int
    case_revision: int
    evidence_set_fingerprint: str
    allocation_revision: int
    tax_policy_fingerprint: str

    def __post_init__(self) -> None:
        _require_metadata(self.metadata)
        for name in ("fifo_revision", "case_revision", "allocation_revision"):
            value = getattr(self, name)
            if type(value) is not int or value < 1:
                _fail(TransitionReasonCode.CONTRACT_INVALID)
        for name in ("evidence_set_fingerprint", "tax_policy_fingerprint"):
            object.__setattr__(self, name, normalize_digest(getattr(self, name)))


ClockProvider = Callable[[], datetime]


def utc_now(clock: ClockProvider) -> str:
    """Read an injected aware clock and return its canonical UTC timestamp."""
    if not callable(clock):
        _fail(TransitionReasonCode.TIMESTAMP_INVALID)
    return normalize_utc_timestamp(clock())


def normalize_money(value: object) -> Decimal:
    if isinstance(value, (bool, float)) or value is None:
        _fail(TransitionReasonCode.MONEY_INVALID)
    if not isinstance(value, (Decimal, int, str)):
        _fail(TransitionReasonCode.MONEY_INVALID)
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        _fail(TransitionReasonCode.MONEY_INVALID)
    if not amount.is_finite() or amount < 0 or amount > MAX_TRANSITION_MONEY:
        _fail(TransitionReasonCode.MONEY_INVALID)
    try:
        return amount.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)
    except InvalidOperation:
        _fail(TransitionReasonCode.MONEY_INVALID)


def normalize_quantity(value: object) -> int:
    if type(value) is not int or not 0 <= value <= MAX_TRANSITION_QUANTITY:
        _fail(TransitionReasonCode.QUANTITY_INVALID)
    return value


def normalize_date_only(value: object) -> str:
    if isinstance(value, datetime):
        _fail(TransitionReasonCode.DATE_INVALID)
    if isinstance(value, date):
        return value.isoformat()
    if not isinstance(value, str):
        _fail(TransitionReasonCode.DATE_INVALID)
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        _fail(TransitionReasonCode.DATE_INVALID)
    if parsed.isoformat() != value:
        _fail(TransitionReasonCode.DATE_INVALID)
    return parsed.isoformat()


def normalize_utc_timestamp(value: object) -> str:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        if "T" not in value:
            _fail(TransitionReasonCode.TIMESTAMP_INVALID)
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            _fail(TransitionReasonCode.TIMESTAMP_INVALID)
    else:
        _fail(TransitionReasonCode.TIMESTAMP_INVALID)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        _fail(TransitionReasonCode.TIMESTAMP_INVALID)
    utc = parsed.astimezone(timezone.utc)
    return utc.isoformat(timespec="microseconds").replace("+00:00", "Z")


def normalize_store_timezone(value: object = DEFAULT_STORE_TIMEZONE) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 64:
        _fail(TransitionReasonCode.TIMEZONE_INVALID)
    name = value.strip()
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        _fail(TransitionReasonCode.TIMEZONE_INVALID)
    return name


def normalize_digest(value: object) -> str:
    if not isinstance(value, str) or not _DIGEST_RE.fullmatch(value.lower()):
        _fail(TransitionReasonCode.FINGERPRINT_INVALID)
    return value.lower()


def source_fingerprint(payload: object) -> str:
    """Stable SHA-256 for already-normalized, allowlisted contract data."""
    encoded = json.dumps(
        _json_safe(payload), sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _require_unknown(
    values: Mapping[str, UnknownValue], field_name: str,
) -> None:
    if not isinstance(values, Mapping) or not isinstance(values.get(field_name), UnknownValue):
        _fail(TransitionReasonCode.CONTRACT_INVALID)


def _reject_unknown(values: Mapping[str, UnknownValue], field_name: str) -> None:
    if field_name in values:
        _fail(TransitionReasonCode.CONTRACT_INVALID)


def _require_metadata(metadata: object) -> None:
    if not isinstance(metadata, TransitionMetadata):
        _fail(TransitionReasonCode.CONTRACT_INVALID)


def _required_text(value: object, max_length: int) -> str:
    if not isinstance(value, str):
        _fail(TransitionReasonCode.CONTRACT_INVALID)
    normalized = value.strip()
    if (
        not normalized or len(normalized) > max_length
        or any(ord(char) < 32 or ord(char) == 127 for char in normalized)
    ):
        _fail(TransitionReasonCode.CONTRACT_INVALID)
    return normalized


def _optional_text(value: object, max_length: int) -> str | None:
    if value is None:
        return None
    return _required_text(value, max_length)


def _opaque_id(value: object) -> str:
    if not isinstance(value, str) or not _OPAQUE_ID_RE.fullmatch(value):
        _fail(TransitionReasonCode.CONTRACT_INVALID)
    return value


def _optional_opaque_id(value: object) -> str | None:
    return None if value is None else _opaque_id(value)


def _optional_ciphertext(value: object) -> str | None:
    if value is None:
        return None
    if (
        not isinstance(value, str) or len(value) < 80 or len(value) > 4096
        or not value.startswith("gAAAA")
        or not re.fullmatch(r"gAAAA[A-Za-z0-9_-]+={0,2}", value)
    ):
        _fail(TransitionReasonCode.CONTRACT_INVALID)
    return value


def _validate_json_value(value: object, depth: int = 0) -> None:
    if depth > 6:
        _fail(TransitionReasonCode.REPORT_EVIDENCE_INVALID)
    if value is None or type(value) in (bool, int) or isinstance(value, Decimal):
        if isinstance(value, Decimal) and not value.is_finite():
            _fail(TransitionReasonCode.REPORT_EVIDENCE_INVALID)
        if type(value) is int and abs(value) > MAX_TRANSITION_QUANTITY:
            _fail(TransitionReasonCode.REPORT_EVIDENCE_INVALID)
        return
    if isinstance(value, str):
        if len(value) > 4096 or any(ord(char) < 32 and char not in "\t\n\r" for char in value):
            _fail(TransitionReasonCode.REPORT_EVIDENCE_INVALID)
        return
    if isinstance(value, (list, tuple)) and len(value) <= 10_000:
        for item in value:
            _validate_json_value(item, depth + 1)
        return
    if isinstance(value, Mapping) and len(value) <= 10_000:
        for key, item in value.items():
            if not isinstance(key, str) or len(key) > 128:
                _fail(TransitionReasonCode.REPORT_EVIDENCE_INVALID)
            _validate_json_value(item, depth + 1)
        return
    _fail(TransitionReasonCode.REPORT_EVIDENCE_INVALID)


def _json_safe(value: object) -> object:
    if isinstance(value, Decimal):
        if not value.is_finite():
            _fail(TransitionReasonCode.CONTRACT_INVALID)
        return format(value, "f")
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return normalize_utc_timestamp(value)
    if isinstance(value, date):
        return normalize_date_only(value)
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            _fail(TransitionReasonCode.CONTRACT_INVALID)
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if value is None or type(value) in (bool, int, str):
        return value
    _fail(TransitionReasonCode.CONTRACT_INVALID)


def _freeze_json(value: object) -> object:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze_json(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_json(item) for item in value)
    return value


def _validate_transition_bridge_payload(
    kind: TransitionBridgeEvidenceKind, value: Mapping[str, object],
) -> dict[str, object]:
    if not isinstance(value, Mapping) or set(value) != _BRIDGE_PAYLOAD_KEYS[kind]:
        _fail(TransitionReasonCode.FIFO_TRANSITION_EVIDENCE_MISSING)
    result = dict(value)
    digest_fields = {
        "document_fingerprint", "snapshot_fingerprint", "identity_fingerprint",
        "bridge_fingerprint", "composition_fingerprint", "rate_fingerprint",
        "predecessor_fingerprint", "reconciliation_fingerprint",
        "replay_fingerprint", "summary_fingerprint", "tax_policy_fingerprint",
    }
    date_fields = {
        "period_from", "period_to", "complete_through", "cutoff_date",
        "opening_date", "effective_date", "as_of", "effective_from",
    }
    count_fields = {
        "row_count", "matched_rows", "page_count", "event_count",
        "selected_event_count", "total_units", "component_count",
    }
    boolean_fields = {"scope_complete", "pagination_complete"}
    for key in digest_fields & result.keys():
        if result[key] is None and key == "predecessor_fingerprint":
            continue
        result[key] = normalize_digest(result[key])
    for key in date_fields & result.keys():
        result[key] = normalize_date_only(result[key])
    for key in count_fields & result.keys():
        if key == "selected_event_count" and result[key] is None:
            continue
        if type(result[key]) is not int or not 0 <= result[key] <= MAX_TRANSITION_QUANTITY:
            _fail(TransitionReasonCode.QUANTITY_INVALID)
    for key in ("event_count", "selected_event_count"):
        if key in result and result[key] is not None and result[key] > 100_000:
            _fail(TransitionReasonCode.FIFO_TRANSITION_EVIDENCE_QUOTA_EXCEEDED)
    if "page_count" in result and result["page_count"] < 1:
        _fail(TransitionReasonCode.EVENT_COVERAGE_INCOMPLETE)
    for key in boolean_fields & result.keys():
        if type(result[key]) is not bool:
            _fail(TransitionReasonCode.CONTRACT_INVALID)
    for key in ("timezone",):
        if key in result:
            result[key] = normalize_store_timezone(result[key])
    for key in ("semantics", "report_type", "policy_code", "calculation_basis"):
        if key in result:
            token = _required_text(result[key], 64)
            if not re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}", token):
                _fail(TransitionReasonCode.CONTRACT_INVALID)
            result[key] = token
    if "rate_percent" in result:
        raw_rate = result["rate_percent"]
        if not isinstance(raw_rate, (str, Decimal)) or isinstance(raw_rate, bool):
            _fail(TransitionReasonCode.CONTRACT_INVALID)
        try:
            rate = Decimal(str(raw_rate))
        except InvalidOperation:
            _fail(TransitionReasonCode.CONTRACT_INVALID)
        if not rate.is_finite() or rate < 0 or rate > Decimal("100"):
            _fail(TransitionReasonCode.CONTRACT_INVALID)
        result["rate_percent"] = format(rate, "f")
    if kind is TransitionBridgeEvidenceKind.PHYSICAL_SALES_DOCUMENT:
        if result["semantics"] != "PHYSICAL_OUTFLOW":
            _fail(TransitionReasonCode.FIFO_PHYSICAL_SALES_DOCUMENT_INVALID)
        if result["row_count"] < 1:
            _fail(TransitionReasonCode.FIFO_PHYSICAL_SALES_DOCUMENT_INVALID)
        if result["period_to"] < result["period_from"]:
            _fail(TransitionReasonCode.DATE_INVALID)
    if kind is TransitionBridgeEvidenceKind.FINANCE_IDENTITY_SNAPSHOT:
        if result["matched_rows"] > result["row_count"]:
            _fail(TransitionReasonCode.CONTRACT_INVALID)
    if kind is TransitionBridgeEvidenceKind.MOVEMENT_COVERAGE:
        if result["period_from"] > result["complete_through"]:
            _fail(TransitionReasonCode.DATE_INVALID)
    if kind is TransitionBridgeEvidenceKind.PERIOD_SUMMARY_SNAPSHOT:
        if result["period_to"] < result["period_from"]:
            _fail(TransitionReasonCode.DATE_INVALID)
    return {key: _freeze_json(item) for key, item in result.items()}


def _validate_bridge_completeness(evidence: TransitionBridgeEvidence) -> None:
    completeness = evidence.metadata.completeness
    if completeness is not EvidenceCompleteness.COMPLETE:
        return
    payload = evidence.payload
    kind = evidence.evidence_kind
    if kind is TransitionBridgeEvidenceKind.FINANCE_IDENTITY_SNAPSHOT:
        complete = payload["scope_complete"] is True and payload["pagination_complete"] is True
    elif kind is TransitionBridgeEvidenceKind.MOVEMENT_COVERAGE:
        complete = (
            payload["scope_complete"] is True
            and payload["pagination_complete"] is True
            and evidence.complete_through == payload["complete_through"]
        )
    elif kind is TransitionBridgeEvidenceKind.CUTOFF_SELECTION:
        complete = (
            evidence.metadata.source_kind is EvidenceSourceKind.LOCAL_DERIVED
            and evidence.complete_through == payload["complete_through"]
            and type(payload["selected_event_count"]) is int
            and payload["selected_event_count"] <= 100_000
        )
    elif kind is TransitionBridgeEvidenceKind.OPENING_COMPOSITION:
        complete = evidence.metadata.source_kind is EvidenceSourceKind.LOCAL_DERIVED
    elif kind is TransitionBridgeEvidenceKind.RATE_BOUNDARY_PROOF:
        complete = evidence.metadata.source_kind is EvidenceSourceKind.LOCAL_DERIVED
    elif kind is TransitionBridgeEvidenceKind.TAX_POLICY_SNAPSHOT:
        complete = evidence.metadata.source_kind in {
            EvidenceSourceKind.OZON_API, EvidenceSourceKind.LOCAL_DERIVED,
        }
    elif kind is TransitionBridgeEvidenceKind.PHYSICAL_SALES_DOCUMENT:
        complete = (
            evidence.row_count == payload["row_count"]
            and evidence.period_from == payload["period_from"]
            and evidence.period_to == payload["period_to"]
        )
    elif kind is TransitionBridgeEvidenceKind.PERIOD_SUMMARY_SNAPSHOT:
        complete = (
            evidence.period_from == payload["period_from"]
            and evidence.period_to == payload["period_to"]
            and evidence.row_count == payload["row_count"]
        )
    else:
        complete = True
    if not complete:
        _fail(TransitionReasonCode.EVENT_COVERAGE_INCOMPLETE)


def _validate_bridge_source(
    kind: TransitionBridgeEvidenceKind, source: EvidenceSourceKind,
) -> None:
    allowed = {
        TransitionBridgeEvidenceKind.PHYSICAL_SALES_DOCUMENT: {
            EvidenceSourceKind.OWNER_IMPORTED,
        },
        TransitionBridgeEvidenceKind.FINANCE_IDENTITY_SNAPSHOT: {
            EvidenceSourceKind.OZON_API, EvidenceSourceKind.OWNER_IMPORTED,
        },
        TransitionBridgeEvidenceKind.MOVEMENT_COVERAGE: {
            EvidenceSourceKind.OZON_API, EvidenceSourceKind.OWNER_IMPORTED,
        },
        TransitionBridgeEvidenceKind.CUTOFF_SELECTION: {
            EvidenceSourceKind.OWNER_INPUT, EvidenceSourceKind.LOCAL_DERIVED,
        },
        TransitionBridgeEvidenceKind.OPENING_COMPOSITION: {
            EvidenceSourceKind.OWNER_INPUT, EvidenceSourceKind.LOCAL_DERIVED,
        },
        TransitionBridgeEvidenceKind.RATE_BOUNDARY_PROOF: {
            EvidenceSourceKind.OWNER_INPUT, EvidenceSourceKind.OZON_API,
            EvidenceSourceKind.LOCAL_DERIVED,
        },
        TransitionBridgeEvidenceKind.PERIOD_SUMMARY_SNAPSHOT: {
            EvidenceSourceKind.OZON_API, EvidenceSourceKind.OWNER_IMPORTED,
            EvidenceSourceKind.LOCAL_DERIVED,
        },
        TransitionBridgeEvidenceKind.TAX_POLICY_SNAPSHOT: {
            EvidenceSourceKind.OWNER_INPUT, EvidenceSourceKind.OZON_API,
            EvidenceSourceKind.LOCAL_DERIVED,
        },
    }
    if source not in allowed[kind]:
        _fail(TransitionReasonCode.CONTRACT_INVALID)


def _validate_transition_confirmation_fields(
    kind: TransitionEvidenceConfirmationKind, value: Mapping[str, object],
) -> dict[str, object]:
    if not isinstance(value, Mapping) or set(value) != _CONFIRMATION_PAYLOAD_KEYS[kind]:
        _fail(TransitionReasonCode.CONTRACT_INVALID)
    result = dict(value)
    digest_fields = {
        "selected_source_fingerprint", "document_fingerprint", "rows_fingerprint",
        "coverage_fingerprint", "bridge_fingerprint", "composition_fingerprint",
        "rate_fingerprint", "reconciliation_fingerprint", "tax_policy_fingerprint",
        "reviewed_fingerprint",
    }
    for key in digest_fields & result.keys():
        result[key] = normalize_digest(result[key])
    for key in ("period_from", "period_to", "complete_through", "cutoff_date",
                "opening_date", "effective_date", "effective_from"):
        if key in result:
            result[key] = normalize_date_only(result[key])
    for key in ("row_count", "event_count", "total_units"):
        if key in result:
            if type(result[key]) is not int or not 0 <= result[key] <= MAX_TRANSITION_QUANTITY:
                _fail(TransitionReasonCode.QUANTITY_INVALID)
    if "timezone" in result:
        result["timezone"] = normalize_store_timezone(result["timezone"])
    for key in ("selection_reason", "semantics", "stock_semantics",
                "calculation_basis", "review_outcome"):
        if key in result:
            token = _required_text(result[key], 64)
            if not re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}", token):
                _fail(TransitionReasonCode.CONTRACT_INVALID)
            result[key] = token
    if "period_from" in result and "period_to" in result:
        if result["period_to"] < result["period_from"]:
            _fail(TransitionReasonCode.DATE_INVALID)
    if "semantics" in result and result["semantics"] != "PHYSICAL_OUTFLOW":
        _fail(TransitionReasonCode.CONTRACT_INVALID)
    if "review_outcome" in result and result["review_outcome"] not in {
        "CONFIRMED", "REJECTED",
    }:
        _fail(TransitionReasonCode.CONTRACT_INVALID)
    return {key: _freeze_json(item) for key, item in result.items()}


def _fail(reason_code: TransitionReasonCode) -> None:
    raise TransitionContractError(reason_code)
