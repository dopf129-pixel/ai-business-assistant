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
    COST_INPUT_INVALID = "COST_INPUT_INVALID"
    STATE_INVALID = "STATE_INVALID"
    REPORT_EVIDENCE_INVALID = "REPORT_EVIDENCE_INVALID"


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


class AcceptedQuantityKind(str, Enum):
    CUMULATIVE = "CUMULATIVE"
    DOCUMENT_LINES = "DOCUMENT_LINES"


class SupplyReferenceKind(str, Enum):
    ORDER = "ORDER"
    SUPPLY = "SUPPLY"


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
        if set(unknown) - {"declared_shipped_units"}:
            _fail(TransitionReasonCode.CONTRACT_INVALID)
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
        if self.presence is EvidencePresence.MISSING:
            if self.declared_quantity is not None or self.accepted_quantity is not None:
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


def _fail(reason_code: TransitionReasonCode) -> None:
    raise TransitionContractError(reason_code)
