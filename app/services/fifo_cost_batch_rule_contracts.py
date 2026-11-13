"""Immutable contracts for FIFO batch rules and supply observations.

This module validates normalized values only. It performs no API requests,
database operations, FIFO accounting, or owner approval.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time
from decimal import Decimal
from enum import Enum
import re
from types import MappingProxyType
from typing import Mapping

from services.fifo_cost_transition_contracts import (
    EvidenceCompleteness,
    EvidenceSourceKind,
    NormalizedSupplyStatus,
    ScopeIdentity,
    SupplyTotalMode,
    TransitionContractError,
    TransitionReasonCode,
    normalize_date_only,
    normalize_digest,
    normalize_money,
    normalize_quantity,
    normalize_store_timezone,
    normalize_utc_timestamp,
    source_fingerprint,
)


MAX_BATCH_OBSERVATIONS = 20_000
MAX_SCAN_ORDERS = 2_000
MAX_SCAN_SUPPLIES = 5_000
MAX_SCAN_SKU_ROWS = 10_000
MAX_RULE_REVISIONS = 100
MAX_BATCH_TOTAL = MAX_SCAN_SUPPLIES * 1_000_000
MAX_DECISION_ROWS = 50
_SAFE_ENUM = re.compile(r"^[A-Z0-9_]{1,64}$")
_OPAQUE_ID = re.compile(r"^[A-Za-z0-9_-]{8,96}$")
_FERNET_TOKEN = re.compile(r"^gAAAA[A-Za-z0-9_-]+={0,2}$")


class BatchStartDayPolicy(str, Enum):
    ALL_OWNER_CONFIRMED = "ALL_OWNER_CONFIRMED"
    EXPLICIT_SUPPLY_SET = "EXPLICIT_SUPPLY_SET"


class BatchRuleEventKind(str, Enum):
    CONFIRM = "CONFIRM"
    REPLACE = "REPLACE"
    CLOSE = "CLOSE"
    CANCEL = "CANCEL"


class DispatchTimeStatus(str, Enum):
    CONFIRMED = "CONFIRMED"
    UNKNOWN = "UNKNOWN"


class SupplyMembership(str, Enum):
    ELIGIBLE = "ELIGIBLE"
    NEEDS_CONFIRMATION = "NEEDS_CONFIRMATION"
    OUTSIDE_RULE = "OUTSIDE_RULE"
    EXCLUDED = "EXCLUDED"
    CONFLICT = "CONFLICT"


class MembershipDecisionKind(str, Enum):
    INCLUDED = "INCLUDED"
    EXCLUDED = "EXCLUDED"


class MembershipDecisionSource(str, Enum):
    RULE_WITH_CONFIRMED_DISPATCH = "RULE_WITH_CONFIRMED_DISPATCH"
    OWNER_SELECTED_SET = "OWNER_SELECTED_SET"


class ManifestFreshness(str, Enum):
    CURRENT = "CURRENT"
    STALE = "STALE"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class BatchRuleRevision:
    scope: ScopeIdentity
    case_id: str
    rule_id: str
    rule_revision: int
    policy_version: int
    start_local_date: str
    store_timezone: str
    start_day_policy: BatchStartDayPolicy
    new_unit_cost_rub: Decimal
    cost_input_fingerprint: str
    old_home_confirmed_zero: bool
    old_transit_confirmed_zero: bool
    boundary_supply_digests: tuple[str, ...]
    predecessor_rule_id: str | None
    predecessor_rule_revision: int | None
    event_kind: BatchRuleEventKind
    end_local_date_exclusive: str | None
    owner_confirmation_fingerprint: str
    confirmed_at_utc: str
    rule_fingerprint: str
    applied_rate_reference: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.scope, ScopeIdentity):
            _invalid(TransitionReasonCode.SCOPE_INVALID)
        _opaque(self.case_id)
        _opaque(self.rule_id)
        if type(self.rule_revision) is not int or not 1 <= self.rule_revision <= MAX_RULE_REVISIONS:
            _invalid(TransitionReasonCode.CONTRACT_INVALID)
        if type(self.policy_version) is not int or self.policy_version != 1:
            _invalid(TransitionReasonCode.CONTRACT_INVALID)
        object.__setattr__(self, "start_local_date", normalize_date_only(self.start_local_date))
        object.__setattr__(self, "store_timezone", normalize_store_timezone(self.store_timezone))
        if not isinstance(self.start_day_policy, BatchStartDayPolicy):
            _invalid(TransitionReasonCode.CONTRACT_INVALID)
        cost = normalize_money(self.new_unit_cost_rub)
        if cost <= Decimal("0.00"):
            _invalid(TransitionReasonCode.MONEY_INVALID)
        object.__setattr__(self, "new_unit_cost_rub", cost)
        object.__setattr__(self, "cost_input_fingerprint", normalize_digest(self.cost_input_fingerprint))
        if type(self.old_home_confirmed_zero) is not bool or not self.old_home_confirmed_zero:
            _invalid(TransitionReasonCode.CONTRACT_INVALID)
        if type(self.old_transit_confirmed_zero) is not bool or not self.old_transit_confirmed_zero:
            _invalid(TransitionReasonCode.CONTRACT_INVALID)
        boundary = _digest_tuple(self.boundary_supply_digests, max_items=MAX_SCAN_SUPPLIES)
        object.__setattr__(self, "boundary_supply_digests", boundary)
        predecessor_id = self.predecessor_rule_id
        predecessor_revision = self.predecessor_rule_revision
        if (predecessor_id is None) != (predecessor_revision is None):
            _invalid(TransitionReasonCode.CONTRACT_INVALID)
        if predecessor_id is not None:
            _opaque(predecessor_id)
            if type(predecessor_revision) is not int or predecessor_revision < 1:
                _invalid(TransitionReasonCode.CONTRACT_INVALID)
        if not isinstance(self.event_kind, BatchRuleEventKind):
            _invalid(TransitionReasonCode.CONTRACT_INVALID)
        end = self.end_local_date_exclusive
        if end is not None:
            end = normalize_date_only(end)
            if end <= self.start_local_date:
                _invalid(TransitionReasonCode.DATE_INVALID)
            object.__setattr__(self, "end_local_date_exclusive", end)
        if self.event_kind in {BatchRuleEventKind.CLOSE, BatchRuleEventKind.CANCEL} and end is None:
            _invalid(TransitionReasonCode.DATE_INVALID)
        object.__setattr__(
            self, "owner_confirmation_fingerprint",
            normalize_digest(self.owner_confirmation_fingerprint),
        )
        object.__setattr__(self, "confirmed_at_utc", normalize_utc_timestamp(self.confirmed_at_utc))
        object.__setattr__(self, "rule_fingerprint", normalize_digest(self.rule_fingerprint))
        if self.applied_rate_reference is not None:
            _opaque(self.applied_rate_reference)


@dataclass(frozen=True, slots=True)
class BatchRuleInput:
    start_local_date: str
    start_day_policy: BatchStartDayPolicy
    boundary_supply_digests: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "start_local_date", normalize_date_only(self.start_local_date))
        if not isinstance(self.start_day_policy, BatchStartDayPolicy):
            _invalid(TransitionReasonCode.CONTRACT_INVALID)
        boundary = _digest_tuple(self.boundary_supply_digests, max_items=MAX_SCAN_SUPPLIES)
        if self.start_day_policy is BatchStartDayPolicy.EXPLICIT_SUPPLY_SET and not boundary:
            _invalid(TransitionReasonCode.CONTRACT_INVALID)
        object.__setattr__(self, "boundary_supply_digests", boundary)


@dataclass(frozen=True, slots=True)
class BatchRulePreview:
    preview_id: str
    scope: ScopeIdentity
    case_id: str
    expected_case_revision: int
    rule_id: str
    rule_revision: int
    expected_rule_head_revision: int
    close_active_rule_revision: int | None
    predecessor_rule_id: str | None
    predecessor_rule_revision: int | None
    start_local_date: str
    store_timezone: str
    start_day_policy: BatchStartDayPolicy
    new_unit_cost_rub: Decimal
    cost_input_fingerprint: str
    old_home_confirmed_zero: bool
    old_transit_confirmed_zero: bool
    boundary_supply_digests: tuple[str, ...]
    rule_head_fingerprint: str
    preview_fingerprint: str
    created_at_utc: str
    expires_at_utc: str

    def __post_init__(self) -> None:
        _opaque(self.preview_id)
        if not isinstance(self.scope, ScopeIdentity):
            _invalid(TransitionReasonCode.SCOPE_INVALID)
        _opaque(self.case_id)
        if type(self.expected_case_revision) is not int or self.expected_case_revision < 1:
            _invalid(TransitionReasonCode.CONTRACT_INVALID)
        _opaque(self.rule_id)
        for name in ("rule_revision", "expected_rule_head_revision"):
            value = getattr(self, name)
            if type(value) is not int or not 0 <= value <= MAX_RULE_REVISIONS:
                _invalid(TransitionReasonCode.CONTRACT_INVALID)
        if self.rule_revision < 1:
            _invalid(TransitionReasonCode.CONTRACT_INVALID)
        if self.close_active_rule_revision is not None and (
            type(self.close_active_rule_revision) is not int
            or self.close_active_rule_revision < 1
        ):
            _invalid(TransitionReasonCode.CONTRACT_INVALID)
        if (self.predecessor_rule_id is None) != (self.predecessor_rule_revision is None):
            _invalid(TransitionReasonCode.CONTRACT_INVALID)
        if self.predecessor_rule_id is not None:
            _opaque(self.predecessor_rule_id)
            if type(self.predecessor_rule_revision) is not int or self.predecessor_rule_revision < 1:
                _invalid(TransitionReasonCode.CONTRACT_INVALID)
        object.__setattr__(self, "start_local_date", normalize_date_only(self.start_local_date))
        object.__setattr__(self, "store_timezone", normalize_store_timezone(self.store_timezone))
        if not isinstance(self.start_day_policy, BatchStartDayPolicy):
            _invalid(TransitionReasonCode.CONTRACT_INVALID)
        cost = normalize_money(self.new_unit_cost_rub)
        if cost <= Decimal("0.00"):
            _invalid(TransitionReasonCode.MONEY_INVALID)
        object.__setattr__(self, "new_unit_cost_rub", cost)
        object.__setattr__(self, "cost_input_fingerprint", normalize_digest(self.cost_input_fingerprint))
        if type(self.old_home_confirmed_zero) is not bool or not self.old_home_confirmed_zero:
            _invalid(TransitionReasonCode.CONTRACT_INVALID)
        if type(self.old_transit_confirmed_zero) is not bool or not self.old_transit_confirmed_zero:
            _invalid(TransitionReasonCode.CONTRACT_INVALID)
        object.__setattr__(
            self, "boundary_supply_digests",
            _digest_tuple(self.boundary_supply_digests, max_items=MAX_SCAN_SUPPLIES),
        )
        object.__setattr__(self, "rule_head_fingerprint", normalize_digest(self.rule_head_fingerprint))
        object.__setattr__(self, "preview_fingerprint", normalize_digest(self.preview_fingerprint))
        created = normalize_utc_timestamp(self.created_at_utc)
        expires = normalize_utc_timestamp(self.expires_at_utc)
        if expires <= created:
            _invalid(TransitionReasonCode.TIMESTAMP_INVALID)
        object.__setattr__(self, "created_at_utc", created)
        object.__setattr__(self, "expires_at_utc", expires)


@dataclass(frozen=True, slots=True)
class SupplySkuObservation:
    scope: ScopeIdentity
    record_key: str
    order_ref_digest: str
    supply_ref_digest: str
    encrypted_lookup_payload: str
    source_profile_version: str
    source_fingerprint: str
    captured_at: str
    source_as_of: str | None
    source_status: str | None
    normalized_status: NormalizedSupplyStatus
    is_crossdock: bool | None
    dispatch_local_date: str | None
    dispatch_local_time: str | None
    dispatch_time_status: DispatchTimeStatus
    planned_declared_quantity: int | None
    shipped_composition_quantity: int | None
    accepted_quantity: int | None
    quantity_source_kind: EvidenceSourceKind
    quantity_coverage: EvidenceCompleteness
    acceptance_fingerprint: str | None
    acceptance_version: int | None
    explicit_zero_fields: tuple[str, ...]
    membership: SupplyMembership
    issues: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.scope, ScopeIdentity):
            _invalid(TransitionReasonCode.SCOPE_INVALID)
        for name in ("record_key", "order_ref_digest", "supply_ref_digest", "source_fingerprint"):
            object.__setattr__(self, name, normalize_digest(getattr(self, name)))
        ciphertext = self.encrypted_lookup_payload
        if (
            not isinstance(ciphertext, str) or not 80 <= len(ciphertext) <= 4096
            or not _FERNET_TOKEN.fullmatch(ciphertext)
        ):
            _invalid(TransitionReasonCode.CONTRACT_INVALID)
        object.__setattr__(self, "source_profile_version", _safe_text(self.source_profile_version, 64))
        object.__setattr__(self, "captured_at", normalize_utc_timestamp(self.captured_at))
        if self.source_as_of is not None:
            object.__setattr__(self, "source_as_of", normalize_utc_timestamp(self.source_as_of))
        if self.source_status is not None:
            object.__setattr__(self, "source_status", _safe_enum_text(self.source_status))
        if not isinstance(self.normalized_status, NormalizedSupplyStatus):
            _invalid(TransitionReasonCode.CONTRACT_INVALID)
        if self.is_crossdock is not None and type(self.is_crossdock) is not bool:
            _invalid(TransitionReasonCode.CONTRACT_INVALID)
        if self.dispatch_local_date is not None:
            object.__setattr__(self, "dispatch_local_date", normalize_date_only(self.dispatch_local_date))
        if self.dispatch_local_time is not None:
            if not isinstance(self.dispatch_local_time, str):
                _invalid(TransitionReasonCode.TIMESTAMP_INVALID)
            try:
                parsed_time = time.fromisoformat(self.dispatch_local_time)
            except ValueError:
                _invalid(TransitionReasonCode.TIMESTAMP_INVALID)
            if parsed_time.tzinfo is not None:
                _invalid(TransitionReasonCode.TIMESTAMP_INVALID)
            normalized_time = parsed_time.isoformat()
            object.__setattr__(self, "dispatch_local_time", normalized_time)
        if not isinstance(self.dispatch_time_status, DispatchTimeStatus):
            _invalid(TransitionReasonCode.CONTRACT_INVALID)
        if self.dispatch_time_status is DispatchTimeStatus.CONFIRMED and self.dispatch_local_date is None:
            _invalid(TransitionReasonCode.DATE_INVALID)
        for name in ("planned_declared_quantity", "shipped_composition_quantity", "accepted_quantity"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, normalize_quantity(value))
        if not isinstance(self.quantity_source_kind, EvidenceSourceKind):
            _invalid(TransitionReasonCode.CONTRACT_INVALID)
        if not isinstance(self.quantity_coverage, EvidenceCompleteness):
            _invalid(TransitionReasonCode.CONTRACT_INVALID)
        if self.acceptance_fingerprint is not None:
            object.__setattr__(self, "acceptance_fingerprint", normalize_digest(self.acceptance_fingerprint))
        if (self.acceptance_fingerprint is None) != (self.acceptance_version is None):
            _invalid(TransitionReasonCode.CONTRACT_INVALID)
        if self.acceptance_version is not None and (
            type(self.acceptance_version) is not int or self.acceptance_version < 1
        ):
            _invalid(TransitionReasonCode.CONTRACT_INVALID)
        if self.accepted_quantity is not None and self.acceptance_fingerprint is None:
            _invalid(TransitionReasonCode.CONTRACT_INVALID)
        zero_fields = _safe_field_tuple(
            self.explicit_zero_fields,
            allowed={"planned_declared_quantity", "shipped_composition_quantity", "accepted_quantity"},
        )
        for field_name in zero_fields:
            if getattr(self, field_name) != 0:
                _invalid(TransitionReasonCode.CONTRACT_INVALID)
        object.__setattr__(self, "explicit_zero_fields", zero_fields)
        if not isinstance(self.membership, SupplyMembership):
            _invalid(TransitionReasonCode.CONTRACT_INVALID)
        object.__setattr__(self, "issues", _safe_issue_tuple(self.issues))


@dataclass(frozen=True, slots=True)
class BatchMembershipDecision:
    decision_id: str
    revision: int
    scope: ScopeIdentity
    case_id: str
    rule_id: str
    rule_revision: int
    decision: MembershipDecisionKind
    source: MembershipDecisionSource
    record_keys: tuple[str, ...]
    relevant_source_fingerprints: tuple[tuple[str, str], ...]
    candidate_set_fingerprint: str
    membership_binding_fingerprint: str
    idempotency_key: str
    confirmed_at: str
    previous_decision_ref: str | None = None

    def __post_init__(self) -> None:
        _opaque(self.decision_id)
        if type(self.revision) is not int or self.revision < 1:
            _invalid(TransitionReasonCode.CONTRACT_INVALID)
        if not isinstance(self.scope, ScopeIdentity):
            _invalid(TransitionReasonCode.SCOPE_INVALID)
        _opaque(self.case_id)
        _opaque(self.rule_id)
        if type(self.rule_revision) is not int or self.rule_revision < 1:
            _invalid(TransitionReasonCode.CONTRACT_INVALID)
        if not isinstance(self.decision, MembershipDecisionKind) or not isinstance(
            self.source, MembershipDecisionSource,
        ):
            _invalid(TransitionReasonCode.CONTRACT_INVALID)
        keys = _digest_tuple(self.record_keys, max_items=MAX_DECISION_ROWS)
        if not keys:
            _invalid(TransitionReasonCode.CONTRACT_INVALID)
        object.__setattr__(self, "record_keys", keys)
        pairs = self.relevant_source_fingerprints
        if not isinstance(pairs, tuple) or len(pairs) != len(keys):
            _invalid(TransitionReasonCode.FINGERPRINT_INVALID)
        normalized_pairs = []
        for pair in pairs:
            if not isinstance(pair, tuple) or len(pair) != 2:
                _invalid(TransitionReasonCode.FINGERPRINT_INVALID)
            normalized_pairs.append((normalize_digest(pair[0]), normalize_digest(pair[1])))
        normalized_pairs = tuple(sorted(normalized_pairs))
        if tuple(key for key, _ in normalized_pairs) != keys:
            _invalid(TransitionReasonCode.FINGERPRINT_INVALID)
        object.__setattr__(self, "relevant_source_fingerprints", normalized_pairs)
        object.__setattr__(self, "candidate_set_fingerprint", normalize_digest(self.candidate_set_fingerprint))
        object.__setattr__(
            self, "membership_binding_fingerprint",
            normalize_digest(self.membership_binding_fingerprint),
        )
        _opaque(self.idempotency_key)
        object.__setattr__(self, "confirmed_at", normalize_utc_timestamp(self.confirmed_at))
        if self.previous_decision_ref is not None:
            _opaque(self.previous_decision_ref)


@dataclass(frozen=True, slots=True)
class SupplyScanCoverage:
    scan_id: str
    revision: int
    scope: ScopeIdentity
    case_id: str
    rule_revision: int
    requested_from: str | None
    requested_through: str | None
    captured_at: str
    source_as_of: str | None
    supported_state_profile: tuple[str, ...]
    list_pagination_complete: bool
    details_complete: bool
    sku_composition_complete: bool
    historical_window_proven: bool
    membership_complete: bool
    quantity_complete: bool
    physical_receipt_timing_complete: bool
    observation_set_fingerprint: str
    source_contract_version: str
    orders_seen: int
    supplies_seen: int
    sku_rows_seen: int
    unknown_order_count: int
    unknown_supply_count: int
    unknown_quantity_supply_count: int
    issue_codes: tuple[str, ...]
    resumable_token: str | None = None

    def __post_init__(self) -> None:
        _opaque(self.scan_id)
        if type(self.revision) is not int or self.revision < 1:
            _invalid(TransitionReasonCode.CONTRACT_INVALID)
        if not isinstance(self.scope, ScopeIdentity):
            _invalid(TransitionReasonCode.SCOPE_INVALID)
        _opaque(self.case_id)
        if type(self.rule_revision) is not int or self.rule_revision < 1:
            _invalid(TransitionReasonCode.CONTRACT_INVALID)
        if (self.requested_from is None) != (self.requested_through is None):
            _invalid(TransitionReasonCode.DATE_INVALID)
        if self.requested_from is not None:
            start = normalize_date_only(self.requested_from)
            end = normalize_date_only(self.requested_through)
            if start > end:
                _invalid(TransitionReasonCode.DATE_INVALID)
            object.__setattr__(self, "requested_from", start)
            object.__setattr__(self, "requested_through", end)
        object.__setattr__(self, "captured_at", normalize_utc_timestamp(self.captured_at))
        if self.source_as_of is not None:
            object.__setattr__(self, "source_as_of", normalize_utc_timestamp(self.source_as_of))
        states = _safe_token_tuple(self.supported_state_profile)
        object.__setattr__(self, "supported_state_profile", states)
        for name in (
            "list_pagination_complete", "details_complete", "sku_composition_complete",
            "historical_window_proven", "membership_complete", "quantity_complete",
            "physical_receipt_timing_complete",
        ):
            if type(getattr(self, name)) is not bool:
                _invalid(TransitionReasonCode.CONTRACT_INVALID)
        object.__setattr__(
            self, "observation_set_fingerprint",
            normalize_digest(self.observation_set_fingerprint),
        )
        object.__setattr__(self, "source_contract_version", _safe_text(self.source_contract_version, 64))
        for name, cap in (
            ("orders_seen", MAX_SCAN_ORDERS),
            ("supplies_seen", MAX_SCAN_SUPPLIES),
            ("sku_rows_seen", MAX_SCAN_SKU_ROWS),
            ("unknown_order_count", MAX_SCAN_ORDERS),
            ("unknown_supply_count", MAX_SCAN_SUPPLIES),
            ("unknown_quantity_supply_count", MAX_SCAN_SUPPLIES),
        ):
            value = getattr(self, name)
            if type(value) is not int or not 0 <= value <= cap:
                _invalid(TransitionReasonCode.QUANTITY_INVALID)
        object.__setattr__(self, "issue_codes", _safe_issue_tuple(self.issue_codes))
        if self.resumable_token is not None:
            _opaque(self.resumable_token)


@dataclass(frozen=True, slots=True)
class AutomaticBatchManifest:
    rule_id: str
    rule_revision: int
    rule_fingerprint: str
    scan_id: str
    observation_record_keys: tuple[str, ...]
    membership_decision_refs: tuple[str, ...]
    owner_control_total: int | None
    owner_control_from: str | None
    owner_control_through: str | None
    owner_control_kind: str | None
    owner_control_status: str | None
    declared_in_found_supplies: int | None
    declared_in_shipped_supplies: int | None
    accepted_units: int | None
    pending_units: int | None
    planned_units: int | None
    known_subtotal: int
    unknown_quantity_supply_count: int
    found_supply_count: int
    included_supply_count: int
    undecided_supply_count: int
    coverage: SupplyScanCoverage
    current_through: str | None
    freshness: ManifestFreshness
    issues: tuple[str, ...]
    manifest_fingerprint: str | None = None
    read_only: bool = True

    def __post_init__(self) -> None:
        _opaque(self.rule_id)
        if type(self.rule_revision) is not int or self.rule_revision < 1:
            _invalid(TransitionReasonCode.CONTRACT_INVALID)
        object.__setattr__(self, "rule_fingerprint", normalize_digest(self.rule_fingerprint))
        _opaque(self.scan_id)
        object.__setattr__(
            self, "observation_record_keys",
            _digest_tuple(self.observation_record_keys, max_items=MAX_BATCH_OBSERVATIONS),
        )
        object.__setattr__(self, "membership_decision_refs", _opaque_tuple(self.membership_decision_refs, 20_000))
        self._validate_control()
        for name in (
            "declared_in_found_supplies", "declared_in_shipped_supplies",
            "accepted_units", "pending_units", "planned_units",
        ):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, _aggregate_quantity(value))
        object.__setattr__(self, "known_subtotal", _aggregate_quantity(self.known_subtotal))
        for name, cap in (
            ("unknown_quantity_supply_count", MAX_SCAN_SUPPLIES),
            ("found_supply_count", MAX_SCAN_SUPPLIES),
            ("included_supply_count", MAX_SCAN_SUPPLIES),
            ("undecided_supply_count", MAX_SCAN_SUPPLIES),
        ):
            value = getattr(self, name)
            if type(value) is not int or not 0 <= value <= cap:
                _invalid(TransitionReasonCode.QUANTITY_INVALID)
        if self.included_supply_count > self.found_supply_count or self.undecided_supply_count > self.found_supply_count:
            _invalid(TransitionReasonCode.CONTRACT_INVALID)
        if not isinstance(self.coverage, SupplyScanCoverage):
            _invalid(TransitionReasonCode.CONTRACT_INVALID)
        if self.current_through is not None:
            object.__setattr__(self, "current_through", normalize_utc_timestamp(self.current_through))
        if not isinstance(self.freshness, ManifestFreshness):
            _invalid(TransitionReasonCode.CONTRACT_INVALID)
        object.__setattr__(self, "issues", _safe_issue_tuple(self.issues))
        if type(self.read_only) is not bool or self.read_only is not True:
            _invalid(TransitionReasonCode.CONTRACT_INVALID)
        calculated = source_fingerprint(self.canonical_fingerprint_payload())
        if self.manifest_fingerprint is not None and normalize_digest(self.manifest_fingerprint) != calculated:
            _invalid(TransitionReasonCode.FINGERPRINT_INVALID)
        object.__setattr__(self, "manifest_fingerprint", calculated)

    def _validate_control(self) -> None:
        fields = (self.owner_control_from, self.owner_control_through, self.owner_control_kind, self.owner_control_status)
        if self.owner_control_total is None:
            if any(value is not None for value in fields):
                _invalid(TransitionReasonCode.CONTRACT_INVALID)
            return
        object.__setattr__(self, "owner_control_total", _aggregate_quantity(self.owner_control_total))
        if any(value is None for value in fields):
            _invalid(TransitionReasonCode.CONTRACT_INVALID)
        start = normalize_date_only(self.owner_control_from)
        end = normalize_date_only(self.owner_control_through)
        if start > end:
            _invalid(TransitionReasonCode.DATE_INVALID)
        object.__setattr__(self, "owner_control_from", start)
        object.__setattr__(self, "owner_control_through", end)
        object.__setattr__(self, "owner_control_kind", _safe_enum_text(self.owner_control_kind))
        object.__setattr__(self, "owner_control_status", _safe_enum_text(self.owner_control_status))

    def canonical_fingerprint_payload(self) -> Mapping[str, object]:
        """Stable business content; deliberately excludes capture timestamps."""
        return MappingProxyType({
            "rule_id": self.rule_id,
            "rule_revision": self.rule_revision,
            "rule_fingerprint": self.rule_fingerprint,
            "observation_record_keys": tuple(sorted(self.observation_record_keys)),
            "membership_decision_refs": tuple(sorted(self.membership_decision_refs)),
            "owner_control_total": self.owner_control_total,
            "owner_control_from": self.owner_control_from,
            "owner_control_through": self.owner_control_through,
            "owner_control_kind": self.owner_control_kind,
            "owner_control_status": self.owner_control_status,
            "declared_in_found_supplies": self.declared_in_found_supplies,
            "declared_in_shipped_supplies": self.declared_in_shipped_supplies,
            "accepted_units": self.accepted_units,
            "pending_units": self.pending_units,
            "planned_units": self.planned_units,
            "known_subtotal": self.known_subtotal,
            "unknown_quantity_supply_count": self.unknown_quantity_supply_count,
            "found_supply_count": self.found_supply_count,
            "included_supply_count": self.included_supply_count,
            "undecided_supply_count": self.undecided_supply_count,
            "observation_set_fingerprint": self.coverage.observation_set_fingerprint,
            "coverage": {
                "list_pagination_complete": self.coverage.list_pagination_complete,
                "details_complete": self.coverage.details_complete,
                "sku_composition_complete": self.coverage.sku_composition_complete,
                "historical_window_proven": self.coverage.historical_window_proven,
                "membership_complete": self.coverage.membership_complete,
                "quantity_complete": self.coverage.quantity_complete,
                "physical_receipt_timing_complete": self.coverage.physical_receipt_timing_complete,
            },
            "freshness": self.freshness.value,
            "issues": tuple(sorted(self.issues)),
        })


def canonical_membership_binding_fingerprint(
    *,
    scope: ScopeIdentity,
    supply_ref_digest: str,
    rule_id: str,
    rule_revision: int,
    rule_fingerprint: str,
    dispatch_local_date: str | None,
    owner_selected: bool,
) -> str:
    """Hash stable membership proof, excluding transport status and timestamps."""
    if not isinstance(scope, ScopeIdentity):
        _invalid(TransitionReasonCode.SCOPE_INVALID)
    if type(owner_selected) is not bool:
        _invalid(TransitionReasonCode.CONTRACT_INVALID)
    if type(rule_revision) is not int or rule_revision < 1:
        _invalid(TransitionReasonCode.CONTRACT_INVALID)
    return source_fingerprint({
        "scope": {
            "owner_id": scope.owner_id,
            "store_id": scope.store_id,
            "product_id": scope.product_id,
            "offer_id": scope.offer_id,
            "sku": scope.sku,
        },
        "supply_ref_digest": normalize_digest(supply_ref_digest),
        "rule_id": _opaque(rule_id),
        "rule_revision": rule_revision,
        "rule_fingerprint": normalize_digest(rule_fingerprint),
        "dispatch_local_date": (
            normalize_date_only(dispatch_local_date)
            if dispatch_local_date is not None else None
        ),
        "owner_selected": owner_selected,
    })


def _opaque(value: object) -> str:
    if not isinstance(value, str) or not _OPAQUE_ID.fullmatch(value):
        _invalid(TransitionReasonCode.CONTRACT_INVALID)
    return value


def _opaque_tuple(values: object, max_items: int) -> tuple[str, ...]:
    if not isinstance(values, tuple) or len(values) > max_items:
        _invalid(TransitionReasonCode.CONTRACT_INVALID)
    normalized = tuple(_opaque(value) for value in values)
    if len(normalized) != len(set(normalized)):
        _invalid(TransitionReasonCode.CONTRACT_INVALID)
    return tuple(sorted(normalized))


def _digest_tuple(values: object, max_items: int) -> tuple[str, ...]:
    if not isinstance(values, tuple) or len(values) > max_items:
        _invalid(TransitionReasonCode.FINGERPRINT_INVALID)
    normalized = tuple(normalize_digest(value) for value in values)
    if len(normalized) != len(set(normalized)):
        _invalid(TransitionReasonCode.FINGERPRINT_INVALID)
    return tuple(sorted(normalized))


def _safe_text(value: object, maximum: int) -> str:
    if not isinstance(value, str):
        _invalid(TransitionReasonCode.CONTRACT_INVALID)
    value = value.strip()
    if not value or len(value) > maximum or any(ord(char) < 32 for char in value):
        _invalid(TransitionReasonCode.CONTRACT_INVALID)
    return value


def _safe_enum_text(value: object) -> str:
    if not isinstance(value, str) or not _SAFE_ENUM.fullmatch(value):
        _invalid(TransitionReasonCode.CONTRACT_INVALID)
    return value


def _safe_token_tuple(values: object, allowed: set[str] | None = None) -> tuple[str, ...]:
    if not isinstance(values, tuple) or len(values) > 256:
        _invalid(TransitionReasonCode.CONTRACT_INVALID)
    normalized = tuple(_safe_enum_text(value) for value in values)
    if len(normalized) != len(set(normalized)):
        _invalid(TransitionReasonCode.CONTRACT_INVALID)
    if allowed is not None and set(normalized) - allowed:
        _invalid(TransitionReasonCode.CONTRACT_INVALID)
    return tuple(sorted(normalized))


def _safe_field_tuple(values: object, allowed: set[str]) -> tuple[str, ...]:
    if not isinstance(values, tuple) or len(values) > len(allowed):
        _invalid(TransitionReasonCode.CONTRACT_INVALID)
    if any(not isinstance(value, str) or value not in allowed for value in values):
        _invalid(TransitionReasonCode.CONTRACT_INVALID)
    if len(values) != len(set(values)):
        _invalid(TransitionReasonCode.CONTRACT_INVALID)
    return tuple(sorted(values))


def _aggregate_quantity(value: object) -> int:
    if type(value) is not int or not 0 <= value <= MAX_BATCH_TOTAL:
        _invalid(TransitionReasonCode.QUANTITY_INVALID)
    return value


def _safe_issue_tuple(values: object) -> tuple[str, ...]:
    if not isinstance(values, tuple) or len(values) > 128:
        _invalid(TransitionReasonCode.CONTRACT_INVALID)
    return tuple(sorted({_safe_enum_text(value) for value in values}))


def _invalid(reason: TransitionReasonCode) -> None:
    raise TransitionContractError(reason)
