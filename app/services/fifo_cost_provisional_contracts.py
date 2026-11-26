"""Typed, non-authoritative contracts for provisional FIFO estimates."""
from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from types import MappingProxyType
from collections.abc import Mapping
from services.fifo_cost_transition_contracts import ReportEvidence, ScopeIdentity, normalize_money, normalize_quantity, normalize_store_timezone

class ProvisionalStatus(str, Enum):
    NEED_INPUT = "NEED_INPUT"
    SOURCE_CONFLICT = "SOURCE_CONFLICT"
    SUMMARY_RANGE = "SUMMARY_RANGE"
    TIMELINE_MODEL = "TIMELINE_MODEL"
    TIMELINE_GAP = "TIMELINE_GAP"
    STALE = "STALE"

class ProvisionalIssueCode(str, Enum):
    SNAPSHOT_REQUIRED = "SNAPSHOT_REQUIRED"
    MOVEMENT_REPORT_REQUIRED = "MOVEMENT_REPORT_REQUIRED"
    REPORT_PERIOD_UNCONFIRMED = "REPORT_PERIOD_UNCONFIRMED"
    REPORT_SCOPE_MISMATCH = "REPORT_SCOPE_MISMATCH"
    REPORT_INCOMPLETE = "REPORT_INCOMPLETE"
    REPORT_WINDOW_MISMATCH = "REPORT_WINDOW_MISMATCH"
    REPORT_CONTROL_INVALID = "REPORT_CONTROL_INVALID"
    BUCKET_BOUNDARY_MISMATCH = "BUCKET_BOUNDARY_MISMATCH"
    UNSUPPORTED_RECEIPTS = "UNSUPPORTED_RECEIPTS"
    UNSUPPORTED_EXPENSES = "UNSUPPORTED_EXPENSES"
    OWNER_OPENING_COMPOSITION_REQUIRED = "OWNER_OPENING_COMPOSITION_REQUIRED"
    OWNER_RECEIPT_PARTY_REQUIRED = "OWNER_RECEIPT_PARTY_REQUIRED"
    CLOSING_OLD_STOCK_RANGE_INVALID = "CLOSING_OLD_STOCK_RANGE_INVALID"
    QUANTITY_DISTRIBUTION_EMPTY = "QUANTITY_DISTRIBUTION_EMPTY"
    MONEY_INPUT_INVALID = "MONEY_INPUT_INVALID"
    END_OLD_STOCK_UNESTABLISHED = "END_OLD_STOCK_UNESTABLISHED"

OPENING_BUCKETS = (
    "available", "expiring", "defective", "checking", "internal_transfer",
    "seller_withdrawal", "buyer_return_transit", "buyer_delivery",
)
RECEIPT_COLUMNS = tuple("LMNOPQR")
NON_SALE_EXPENSE_COLUMNS = tuple("UVWXYZ")
SUPPORTED_RECEIPT_COLUMNS = frozenset({"L", "M"})
SUPPORTED_NON_SALE_EXPENSE_COLUMNS = frozenset({"V", "W", "X"})

@dataclass(frozen=True, slots=True)
class ProvisionalRangeAssumptions:
    opening_all_old: bool | None = None
    all_period_supply_receipts_new: bool | None = None
    closing_old_min: int | None = None
    closing_old_max: int | None = None
    def __post_init__(self):
        for name in ("opening_all_old", "all_period_supply_receipts_new"):
            value = getattr(self, name)
            if value is not None and type(value) is not bool:
                raise ValueError("FIFO_PROVISIONAL_ASSUMPTION_INVALID")
        low, high = self.closing_old_min, self.closing_old_max
        if (low is None) != (high is None):
            raise ValueError("FIFO_PROVISIONAL_CLOSING_RANGE_INVALID")
        if low is not None:
            normalize_quantity(low)
            normalize_quantity(high)
            if low > high:
                raise ValueError("FIFO_PROVISIONAL_CLOSING_RANGE_INVALID")

@dataclass(frozen=True, slots=True)
class ProvisionalSummaryRequest:
    scope: ScopeIdentity
    store_timezone: str
    snapshot: ReportEvidence | None
    movement_report: ReportEvidence | None
    old_unit_cost_rub: Decimal
    new_unit_cost_rub: Decimal
    assumptions: ProvisionalRangeAssumptions
    def __post_init__(self):
        if not isinstance(self.scope, ScopeIdentity):
            raise ValueError("FIFO_PROVISIONAL_SCOPE_INVALID")
        object.__setattr__(self, "store_timezone", normalize_store_timezone(self.store_timezone))
        if self.snapshot is not None and not isinstance(self.snapshot, ReportEvidence):
            raise ValueError("FIFO_PROVISIONAL_REPORT_INVALID")
        if self.movement_report is not None and not isinstance(self.movement_report, ReportEvidence):
            raise ValueError("FIFO_PROVISIONAL_REPORT_INVALID")
        if not isinstance(self.assumptions, ProvisionalRangeAssumptions):
            raise ValueError("FIFO_PROVISIONAL_ASSUMPTIONS_INVALID")
        object.__setattr__(self, "old_unit_cost_rub", normalize_money(self.old_unit_cost_rub))
        object.__setattr__(self, "new_unit_cost_rub", normalize_money(self.new_unit_cost_rub))

@dataclass(frozen=True, slots=True)
class ProvisionalSummaryResult:
    status: ProvisionalStatus
    issue_codes: tuple[ProvisionalIssueCode, ...] = ()
    period_from: str | None = None
    period_to: str | None = None
    opening_total: int | None = None
    opening_buckets: Mapping[str, int] | None = None
    closing_total: int | None = None
    closing_buckets: Mapping[str, int] | None = None
    supply_receipts: int | None = None
    buyer_return_receipts: int | None = None
    redeemed_units: int | None = None
    other_supported_expenses: int | None = None
    excluded_compensation_receipt: int | None = None
    excluded_compensation_expense: int | None = None
    old_sold_min: int | None = None
    old_sold_max: int | None = None
    new_sold_min: int | None = None
    new_sold_max: int | None = None
    gross_cogs_low_rub: Decimal | None = None
    gross_cogs_high_rub: Decimal | None = None
    old_cost_rub: Decimal | None = None
    new_cost_rub: Decimal | None = None
    snapshot_fingerprint: str | None = None
    movement_fingerprint: str | None = None
    result_fingerprint: str | None = None
    def __post_init__(self):
        if not isinstance(self.status, ProvisionalStatus):
            raise ValueError("FIFO_PROVISIONAL_STATUS_INVALID")
        if not isinstance(self.issue_codes, tuple) or any(not isinstance(x, ProvisionalIssueCode) for x in self.issue_codes):
            raise ValueError("FIFO_PROVISIONAL_ISSUES_INVALID")
        for name in ("opening_buckets", "closing_buckets"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, MappingProxyType(dict(value)))
