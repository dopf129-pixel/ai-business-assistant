"""Owner-triggered, read-only FIFO inventory and supply source collection."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from functools import wraps
import hashlib
import inspect
import json
import re
import threading
from time import monotonic
from types import MappingProxyType
from typing import Callable, Mapping
from uuid import uuid4
from zoneinfo import ZoneInfo

from services.fifo_cost_source_normalizer import FifoCostSourceNormalizer
from services.fifo_cost_cutoff_bridge_service import FifoCutoffBridgeSourceAdapter
from services.fifo_cost_transition_contracts import (
    EvidenceCompleteness,
    EvidenceSourceKind,
    ScopeIdentity,
    SourceProof,
    SupplyReferenceKind,
    TransitionMetadata,
    normalize_store_timezone,
    supply_reference_digest,
)
from services.ozon_account_repository import split_store_tenant_scope
from services.period_profit_return_evidence_service import PeriodProfitReturnEvidenceService
from services.period_profit_operation_diagnostics import (
    PeriodProfitOperationTrace,
    activate_period_profit_trace,
    current_period_profit_trace,
    reset_period_profit_trace,
)
from services.tenant_context import get_current_tenant_user_id


_MAX_RETURN_SNAPSHOT_RECORDS = 100_000
_MAX_RETURN_SNAPSHOT_BYTES = 16 * 1024 * 1024
_RETURN_SNAPSHOT_RECORD_KEYS = frozenset({
    "id", "return_id", "posting_number", "offer_id", "sku", "quantity",
    "type", "schema", "visual_status_sys_name",
    "visual_status_change_moment", "source",
})
_RETURN_SNAPSHOT_OPTIONAL_KEYS = frozenset({
    "status", "visual_status", "return_reason_name", "return_date",
    "logistic_return_date", "technical_return_moment", "return_final_moment",
    "cancelled_with_compensation_moment", "compensation_status_sys_name",
    "compensation_status_change_moment",
})


@dataclass(frozen=True)
class FifoSourceCollectionResult:
    status: str
    source_status: str
    read_only: bool
    actual_http_attempts: int
    http_attempt_cap: int
    elapsed_seconds: float
    source_fingerprint: str | None
    issue_codes: tuple[str, ...]
    stock_snapshot: object = None
    supply_snapshot: object = None
    continuation_token: str | None = None
    finance_identity_snapshots: tuple[object, ...] = field(default=(), repr=False)
    return_snapshot: object = field(default=None, repr=False)


@dataclass(frozen=True)
class FifoReturnStatusSnapshot:
    """Exact Returns API observations; never a physical-movement proof."""

    status: str
    source_status: str
    store_id: str = field(repr=False)
    offer_id: str = field(repr=False)
    sku: str = field(repr=False)
    return_schema: str
    period_from: str
    period_to: str
    filter_basis: str
    filter_timezone: str
    store_timezone: str
    captured_at: str
    page_count: int
    record_count: int
    records: tuple[object, ...] = field(repr=False)
    source_fingerprint: str
    issue_codes: tuple[str, ...] = ()
    movement_coverage_complete: bool = False

    def __post_init__(self):
        if self.status not in {"COMPLETE", "PARTIAL"}:
            raise ValueError("FIFO_RETURN_SNAPSHOT_STATUS_INVALID")
        if self.source_status != self.status:
            raise ValueError("FIFO_RETURN_SNAPSHOT_STATUS_INVALID")
        if self.return_schema not in {"FBO", "FBS"}:
            raise ValueError("FIFO_RETURN_SNAPSHOT_SCHEMA_INVALID")
        if (
            self.filter_basis != "VISUAL_STATUS_CHANGE_MOMENT_UTC"
            or self.filter_timezone != "UTC"
        ):
            raise ValueError("FIFO_RETURN_SNAPSHOT_DATE_BASIS_INVALID")
        if self.movement_coverage_complete is not False:
            raise ValueError("FIFO_RETURN_SNAPSHOT_COVERAGE_INVALID")
        for name, value, maximum in (
            ("store_id", self.store_id, 128),
            ("offer_id", self.offer_id, 256),
            ("sku", self.sku, 64),
        ):
            if not isinstance(value, str) or not value.strip() or len(value) > maximum:
                raise ValueError("FIFO_RETURN_SNAPSHOT_SCOPE_INVALID")
        try:
            normalized_timezone = normalize_store_timezone(self.store_timezone)
            captured_at = datetime.fromisoformat(
                self.captured_at.strip().replace("Z", "+00:00"),
            )
        except (TypeError, ValueError, AttributeError):
            raise ValueError("FIFO_RETURN_SNAPSHOT_TIME_INVALID") from None
        if (
            normalized_timezone != self.store_timezone
            or captured_at.tzinfo is None or captured_at.utcoffset() is None
            or captured_at.utcoffset().total_seconds() != 0
        ):
            raise ValueError("FIFO_RETURN_SNAPSHOT_TIME_INVALID")
        for value in (self.period_from, self.period_to):
            try:
                parsed = date.fromisoformat(value)
            except (TypeError, ValueError):
                raise ValueError("FIFO_RETURN_SNAPSHOT_PERIOD_INVALID") from None
            if parsed.isoformat() != value:
                raise ValueError("FIFO_RETURN_SNAPSHOT_PERIOD_INVALID")
        if (
            date.fromisoformat(self.period_to) < date.fromisoformat(self.period_from)
            or type(self.page_count) is not int or self.page_count < 1
            or self.page_count > 100
            or type(self.record_count) is not int or self.record_count < 0
            or self.record_count > _MAX_RETURN_SNAPSHOT_RECORDS
            or not isinstance(self.captured_at, str) or not self.captured_at
            or not isinstance(self.source_fingerprint, str)
            or not re.fullmatch(r"[0-9a-f]{64}", self.source_fingerprint)
        ):
            raise ValueError("FIFO_RETURN_SNAPSHOT_INVALID")
        normalized_records = []
        seen_ids = set()
        for item in self.records:
            if (
                not isinstance(item, Mapping)
                or not _RETURN_SNAPSHOT_RECORD_KEYS.issubset(item)
                or set(item) - _RETURN_SNAPSHOT_RECORD_KEYS - _RETURN_SNAPSHOT_OPTIONAL_KEYS
            ):
                raise ValueError("FIFO_RETURN_SNAPSHOT_RECORDS_INVALID")
            record = dict(item)
            record_id = record.get("return_id")
            if (
                not isinstance(record_id, str)
                or not re.fullmatch(r"[1-9][0-9]{0,18}", record_id)
                or record.get("id") != record_id or record_id in seen_ids
                or not isinstance(record.get("posting_number"), str)
                or not 1 <= len(record["posting_number"]) <= 256
                or record.get("offer_id") != self.offer_id
                or record.get("sku") != self.sku
                or not 1 <= len(record["sku"]) <= 64
                or type(record.get("quantity")) is not int
                or not 1 <= record["quantity"] <= FifoCostSourceNormalizer.MAX_UNITS
                or not isinstance(record.get("type"), str)
                or not re.fullmatch(r"[A-Za-z0-9_]{1,64}", record["type"])
                or record.get("schema") != self.return_schema
                or not isinstance(record.get("visual_status_sys_name"), str)
                or not re.fullmatch(
                    r"[A-Za-z0-9_]{1,64}", record["visual_status_sys_name"],
                )
                or record.get("source") != "OZON_RETURNS_API"
            ):
                raise ValueError("FIFO_RETURN_SNAPSHOT_RECORDS_INVALID")
            for name in _RETURN_SNAPSHOT_OPTIONAL_KEYS:
                if name not in record:
                    continue
                value = record[name]
                maximum = 256 if name == "return_reason_name" else 128
                if not isinstance(value, str) or not 1 <= len(value) <= maximum:
                    raise ValueError("FIFO_RETURN_SNAPSHOT_RECORDS_INVALID")
                if name in {"visual_status", "compensation_status_sys_name"} and not re.fullmatch(
                    r"[A-Za-z0-9_]{1,64}", value,
                ):
                    raise ValueError("FIFO_RETURN_SNAPSHOT_RECORDS_INVALID")
            try:
                moment = datetime.fromisoformat(
                    record["visual_status_change_moment"].replace("Z", "+00:00"),
                )
            except (AttributeError, TypeError, ValueError):
                raise ValueError("FIFO_RETURN_SNAPSHOT_RECORDS_INVALID") from None
            if (
                moment.tzinfo is None or moment.utcoffset() is None
                or moment.utcoffset().total_seconds() != 0
                or not date.fromisoformat(self.period_from)
                <= moment.astimezone(timezone.utc).date()
                <= date.fromisoformat(self.period_to)
            ):
                raise ValueError("FIFO_RETURN_SNAPSHOT_RECORDS_INVALID")
            seen_ids.add(record_id)
            normalized_records.append(MappingProxyType(record))
        records = tuple(normalized_records)
        if len(records) != self.record_count:
            raise ValueError("FIFO_RETURN_SNAPSHOT_RECORDS_INVALID")
        try:
            payload_size = len(json.dumps(
                [dict(item) for item in records], sort_keys=True,
                separators=(",", ":"), ensure_ascii=False, allow_nan=False,
            ).encode("utf-8"))
        except (TypeError, ValueError, OverflowError):
            raise ValueError("FIFO_RETURN_SNAPSHOT_RECORDS_INVALID") from None
        if payload_size > _MAX_RETURN_SNAPSHOT_BYTES:
            raise ValueError("FIFO_RETURN_SNAPSHOT_BYTE_LIMIT")
        if not isinstance(self.issue_codes, tuple) or any(
            not isinstance(code, str) or not re.fullmatch(r"[A-Z0-9_]{1,96}", code)
            for code in self.issue_codes
        ):
            raise ValueError("FIFO_RETURN_SNAPSHOT_ISSUES_INVALID")
        object.__setattr__(self, "records", records)

    def to_payload(self):
        """Return normalized records for the existing tenant-encrypted evidence API."""
        return {
            "status": self.status,
            "source_status": self.source_status,
            "store_id": self.store_id,
            "offer_id": self.offer_id,
            "sku": self.sku,
            "return_schema": self.return_schema,
            "period_from": self.period_from,
            "period_to": self.period_to,
            "filter_basis": self.filter_basis,
            "filter_timezone": self.filter_timezone,
            "store_timezone": self.store_timezone,
            "captured_at": self.captured_at,
            "page_count": self.page_count,
            "record_count": self.record_count,
            "records": [dict(item) for item in self.records],
            "source_fingerprint": self.source_fingerprint,
            "issue_codes": list(self.issue_codes),
            "movement_coverage_complete": False,
        }


@dataclass(frozen=True)
class _FinanceIdentityCheckpoint:
    scope_fingerprint: str
    months: tuple[tuple[int, int, str, str], ...]
    next_month_index: int
    batches: tuple[object, ...]
    seen_identity_fingerprints: tuple[str, ...]
    normalized_bytes: int
    source_fingerprint: str
    expires_at: float


@dataclass(frozen=True)
class _ReturnStatusCheckpoint:
    scope_fingerprint: str
    last_id: int
    seen_cursor_ids: tuple[int, ...]
    seen_return_ids: tuple[str, ...]
    pages_checked: int
    records: tuple[dict, ...]
    normalized_bytes: int
    source_fingerprint: str
    expires_at: float


@dataclass(frozen=True)
class _SupplySearchCheckpoint:
    scope_fingerprint: str
    cursor: str | None
    seen_cursor_fingerprints: tuple[str, ...]
    seen_order_fingerprints: tuple[str, ...]
    pages_checked: int
    source_fingerprint: str
    matched_supply: tuple[str, str] | None
    expires_at: float


def _singleflight_collection(action):
    """Prevent duplicate concurrent reads for one exact owner/store/SKU scope."""

    def decorate(method):
        signature = inspect.signature(method)

        @wraps(method)
        def guarded(self, *args, **kwargs):
            bound = signature.bind(self, *args, **kwargs)
            bound.apply_defaults()
            values = bound.arguments
            identity = self._identity(values.get("identity"))
            scope = values.get("scope")
            if identity is None and isinstance(scope, ScopeIdentity):
                identity = (scope.product_id, scope.offer_id, scope.sku)
            store_id = self._text(
                values.get("store_id") or getattr(scope, "store_id", None), 128,
            )
            tenant_scope = self._text(
                values.get("tenant_scope") or get_current_tenant_user_id(), 128,
            )
            resource = action
            if action == "supply":
                supply_id = self._identifier(values.get("supply_id"))
                if supply_id is None:
                    return method(self, *args, **kwargs)
                resource = self._digest("SUPPLY", supply_id)
            if action in {"finance_identity", "return_status"}:
                resource = self._fingerprint({
                    "action": action,
                    "period_from": values.get("period_from"),
                    "period_to": values.get("period_to"),
                    "return_schema": values.get("return_schema"),
                })
            if identity is None or store_id is None or tenant_scope is None:
                return method(self, *args, **kwargs)
            key = self._fingerprint({
                "action": action,
                "tenant": tenant_scope,
                "store": store_id,
                "identity": list(identity),
                "resource": resource,
                "transition_case_id": values.get("transition_case_id"),
                "transition_case_revision": values.get("transition_case_revision"),
            })
            if key is None:
                return method(self, *args, **kwargs)
            started = self.monotonic_clock()
            with self._checkpoint_lock:
                if key in self._inflight_keys:
                    return self._result(
                        status="PARTIAL", source_status="PARTIAL",
                        attempts=0, cap=0, started=started,
                        issues=("FIFO_SOURCE_ALREADY_IN_PROGRESS",),
                    )
                if len(self._inflight_keys) >= self.MAX_INFLIGHT_COLLECTIONS:
                    return self._result(
                        status="UNAVAILABLE", source_status="UNAVAILABLE",
                        attempts=0, cap=0, started=started,
                        issues=("FIFO_SOURCE_CONCURRENCY_LIMIT",),
                    )
                self._inflight_keys.add(key)
            try:
                return method(self, *args, **kwargs)
            finally:
                with self._checkpoint_lock:
                    self._inflight_keys.discard(key)

        return guarded

    return decorate


class FifoCostSourceCollectionService:
    """Collect bounded Ozon evidence only when a caller explicitly requests it.

    Continuations are opaque, single-use and process-local. No API response or
    raw Ozon identifier is written to disk or returned by the collector.
    """

    MAX_ELAPSED_SECONDS = 60.0
    MAX_HTTP_ATTEMPTS = 64
    MAX_DIAGNOSTIC_HTTP_ATTEMPTS = 10
    MAX_DIAGNOSTIC_PAGES_PER_CALL = 2
    MAX_TOTAL_SUPPLY_PAGES = 100
    MAX_TOTAL_FINANCE_MONTHS = 100
    MAX_TOTAL_FINANCE_IDENTITIES = 100_000
    MAX_FINANCE_IDENTITY_SNAPSHOT_BYTES = 16 * 1024 * 1024
    MAX_TOTAL_RETURN_PAGES = 100
    MAX_RETURN_SNAPSHOT_RECORDS = _MAX_RETURN_SNAPSHOT_RECORDS
    MAX_RETURN_SNAPSHOT_BYTES = _MAX_RETURN_SNAPSHOT_BYTES
    MAX_SCOPED_SOURCE_CHECKPOINTS = 4
    MAX_SCOPED_SOURCE_CHECKPOINT_BYTES = 64 * 1024 * 1024
    MAX_PAGE_SIZE = 100
    MAX_DETAILS_BATCH_SIZE = 50
    MAX_REQUEST_TIMEOUT_SECONDS = 8.0
    MAX_REQUEST_TOTAL_TIMEOUT_SECONDS = 10.0
    MAX_ACTIVE_SUPPLY_TIME_BUDGET_SECONDS = 20.0
    CHECKPOINT_TTL_SECONDS = 600.0
    MAX_CHECKPOINTS = 256
    MAX_INFLIGHT_COLLECTIONS = 64
    MAX_SEEN_ROWS = 10_000
    RETURN_PAGE_SIZE = PeriodProfitReturnEvidenceService.PAGE_SIZE
    RETURN_PAGE_COUNT_PER_CALL = MAX_DIAGNOSTIC_PAGES_PER_CALL
    ACTIVE_SUPPLY_STATES = (
        "DATA_FILLING",
        "READY_TO_SUPPLY",
        "ACCEPTED_AT_SUPPLY_WAREHOUSE",
        "IN_TRANSIT",
        "ACCEPTANCE_AT_STORAGE_WAREHOUSE",
        "REPORTS_CONFIRMATION_AWAITING",
        "REPORT_REJECTED",
        "COMPLETED",
        "REJECTED_AT_SUPPLY_WAREHOUSE",
        "CANCELLED",
        "OVERDUE",
        "UNSPECIFIED",
    )
    _ID = re.compile(r"^[0-9]{1,19}$")
    _CURSOR = re.compile(r"^[A-Za-z0-9._:-]{1,256}$")

    def __init__(
        self,
        *,
        ozon_client,
        normalizer: FifoCostSourceNormalizer | None = None,
        monotonic_clock: Callable[[], float] = monotonic,
        utc_clock: Callable[[], datetime] | None = None,
    ):
        self.ozon_client = ozon_client
        self.normalizer = normalizer or FifoCostSourceNormalizer()
        self.monotonic_clock = monotonic_clock
        self.utc_clock = utc_clock or (lambda: datetime.now(timezone.utc))
        self._checkpoints: dict[str, _SupplySearchCheckpoint] = {}
        self._finance_checkpoints: dict[str, _FinanceIdentityCheckpoint] = {}
        self._return_checkpoints: dict[str, _ReturnStatusCheckpoint] = {}
        self._inflight_keys: set[str] = set()
        self._checkpoint_lock = threading.RLock()
        self.cutoff_bridge_source_adapter = FifoCutoffBridgeSourceAdapter()

    @_singleflight_collection("stock")
    def collect_stock_snapshot(
        self,
        *,
        identity,
        store_id,
        tenant_scope,
        identity_mapping_confirmed=False,
        owner_confirmed_stock_semantics=False,
        owner_confirmed_zero_transit=False,
        operation_trace=None,
        http_attempt_budget=1,
        time_budget_seconds=15.0,
    ) -> FifoSourceCollectionResult:
        """Read one exact-product stock response and normalize it fail-closed."""

        started = self.monotonic_clock()
        normalized_identity = self._identity(identity)
        normalized_store = self._text(store_id, 128)
        normalized_tenant = self._text(tenant_scope, 128)
        attempts_limit, seconds_limit = self._limits(
            http_attempt_budget, time_budget_seconds,
            default_attempts=1, maximum_attempts=self.MAX_DIAGNOSTIC_HTTP_ATTEMPTS,
        )
        if (
            normalized_identity is None
            or normalized_store is None
            or normalized_tenant is None
            or attempts_limit is None
            or seconds_limit is None
            or type(identity_mapping_confirmed) is not bool
            or type(owner_confirmed_stock_semantics) is not bool
            or type(owner_confirmed_zero_transit) is not bool
        ):
            return self._result(
                status="INVALID", source_status="CONFLICT", attempts=0,
                cap=attempts_limit or 0, started=started,
                issues=("FIFO_STOCK_COLLECTION_INPUT_INVALID",),
            )

        trace = self._new_trace(
            "fifo_cost_stock_snapshot",
            seconds_limit,
            attempts_limit,
            operation_trace,
        )
        token = activate_period_profit_trace(trace)
        attempts = 0
        response = None
        reason = None
        try:
            response, attempts, reason = self._call(
                trace,
                "get_product_stocks",
                normalized_identity[0],
                limit=self.MAX_PAGE_SIZE,
                max_http_attempts=attempts_limit,
            )
        finally:
            reset_period_profit_trace(token)

        if response is None:
            response = {"error": True, "code": reason or "FIFO_SOURCE_UNAVAILABLE"}
        captured_at = self._now_utc()
        pagination_complete = self._stock_pages_complete(
            response,
            expected_limit=self.MAX_PAGE_SIZE,
        )
        snapshot = self.normalizer.normalize_stock_snapshot(
            response,
            identity={
                "product_id": normalized_identity[0],
                "offer_id": normalized_identity[1],
                "sku": normalized_identity[2],
            },
            store_id=normalized_store,
            captured_at=captured_at,
            pagination_complete=pagination_complete,
            pages_read=1,
            identity_mapping_confirmed=identity_mapping_confirmed,
            field_semantics_confirmed=owner_confirmed_stock_semantics,
            transit_units=0 if owner_confirmed_zero_transit else None,
            transit_complete=owner_confirmed_zero_transit,
            transit_overlap_confirmed=owner_confirmed_zero_transit,
        )
        issues = list(snapshot.issue_codes)
        if reason:
            issues.append(reason)
        status = snapshot.status
        if trace.is_cancelled():
            status = "UNAVAILABLE"
            snapshot_source_status = "UNAVAILABLE"
            issues.append("FIFO_SOURCE_CANCELLED")
        elif trace.remaining_seconds() <= 0:
            status = "PARTIAL" if attempts else "UNAVAILABLE"
            snapshot_source_status = status
            issues.append("FIFO_SOURCE_TIME_BUDGET_EXHAUSTED")
        elif attempts == 0 and isinstance(response, dict) and response.get("error") is True:
            status = "UNAVAILABLE"
            snapshot_source_status = "UNAVAILABLE"
        else:
            snapshot_source_status = snapshot.source_status
        return self._result(
            status=status,
            source_status=snapshot_source_status,
            attempts=attempts,
            cap=attempts_limit,
            started=started,
            fingerprint=snapshot.source_fingerprint,
            issues=tuple(issues),
            stock_snapshot=snapshot,
        )

    @_singleflight_collection("finance_identity")
    def collect_finance_identity_snapshot(
        self, *, scope, period_from, period_to, transition_case_id,
        transition_case_revision, store_timezone,
        confirmed_finance_sku_mappings=None, continuation_token=None,
        operation_trace=None, max_pages_per_call=MAX_DIAGNOSTIC_PAGES_PER_CALL,
        http_attempt_budget=MAX_DIAGNOSTIC_HTTP_ATTEMPTS,
        time_budget_seconds=20.0,
    ):
        """Read complete monthly realization identity batches through the real adapter.

        ``get_realization_posting`` is monthly and returns the rows for that
        month in one response. Continuation advances across calendar months;
        it never pretends that a partially read month is complete.
        """
        started = self.monotonic_clock()
        valid, issue = self._validate_transition_source_request(
            scope=scope, period_from=period_from, period_to=period_to,
            transition_case_id=transition_case_id,
            transition_case_revision=transition_case_revision,
            store_timezone=store_timezone,
        )
        months = self._calendar_months(period_from, period_to) if valid else ()
        attempts_limit, seconds_limit = self._limits(
            http_attempt_budget, time_budget_seconds,
            default_attempts=self.MAX_DIAGNOSTIC_HTTP_ATTEMPTS,
            maximum_attempts=self.MAX_DIAGNOSTIC_HTTP_ATTEMPTS,
        )
        page_limit = self._bounded_integer(
            max_pages_per_call, minimum=1,
            maximum=self.MAX_DIAGNOSTIC_PAGES_PER_CALL,
        )
        mappings_input = (
            {} if confirmed_finance_sku_mappings is None
            else confirmed_finance_sku_mappings
        )
        if (
            not valid or not months or len(months) > self.MAX_TOTAL_FINANCE_MONTHS
            or attempts_limit is None or seconds_limit is None
            or page_limit is None
            or not isinstance(mappings_input, dict)
        ):
            return self._result(
                status="INVALID", source_status="CONFLICT", attempts=0,
                cap=attempts_limit or 0, started=started,
                issues=(issue or "FIFO_FINANCE_IDENTITY_COLLECTION_INPUT_INVALID",),
            )

        mappings = dict(mappings_input)
        scope_fingerprint = self._fingerprint({
            "source": "FINANCE_IDENTITY",
            "scope": self._scope_material(scope),
            "period_from": period_from,
            "period_to": period_to,
            "case_id": transition_case_id,
            "case_revision": transition_case_revision,
            "store_timezone": store_timezone,
            "confirmed_mappings": mappings,
        })
        if scope_fingerprint is None:
            return self._result(
                status="INVALID", source_status="CONFLICT", attempts=0,
                cap=attempts_limit, started=started,
                issues=("FIFO_FINANCE_IDENTITY_SCOPE_FINGERPRINT_INVALID",),
            )
        checkpoint, checkpoint_error = self._take_scoped_checkpoint(
            self._finance_checkpoints, continuation_token,
            scope_fingerprint=scope_fingerprint,
        )
        if checkpoint_error:
            return self._result(
                status="CONFLICT", source_status="CONFLICT", attempts=0,
                cap=attempts_limit, started=started, issues=(checkpoint_error,),
            )
        state_months = checkpoint.months if checkpoint else tuple(months)
        next_index = checkpoint.next_month_index if checkpoint else 0
        batches = list(checkpoint.batches) if checkpoint else []
        seen = set(checkpoint.seen_identity_fingerprints) if checkpoint else set()
        normalized_bytes = checkpoint.normalized_bytes if checkpoint else 0
        chain_fingerprint = checkpoint.source_fingerprint if checkpoint else self._fingerprint({
            "source": "OZON_FINANCE_REALIZATION_POSTING_V1",
            "scope": self._scope_material(scope),
            "period_from": period_from,
            "period_to": period_to,
        })
        trace = self._new_trace(
            "fifo_finance_identity_snapshot", seconds_limit,
            attempts_limit, operation_trace,
        )
        trace_token = activate_period_profit_trace(trace)
        attempts = 0
        issues = []
        pages_this_call = 0
        try:
            while next_index < len(state_months) and pages_this_call < page_limit:
                if trace.is_cancelled() or trace.remaining_seconds() <= 0 or attempts >= attempts_limit:
                    reason = (
                        "FIFO_SOURCE_CANCELLED" if trace.is_cancelled() else
                        "FIFO_SOURCE_TIME_BUDGET_EXHAUSTED" if trace.remaining_seconds() <= 0 else
                        "FIFO_SOURCE_HTTP_BUDGET_EXHAUSTED"
                    )
                    issues.append(reason)
                    break
                year, month, month_from, month_to = state_months[next_index]
                latest_reportable_month = self._latest_reportable_realization_month(
                    store_timezone,
                )
                if latest_reportable_month is None:
                    issues.append("FIFO_SOURCE_CLOCK_UNAVAILABLE")
                    break
                if (year, month) > latest_reportable_month:
                    issues.append("FIFO_FINANCE_REALIZATION_MONTH_NOT_PUBLISHED")
                    break
                response, call_attempts, request_reason = self._call(
                    trace, "get_realization_posting", year, month,
                    max_http_attempts=attempts_limit - attempts,
                )
                attempts += call_attempts
                if request_reason or not isinstance(response, dict) or response.get("error") is True:
                    issues.append(request_reason or self._safe_error_code(
                        response, "FIFO_FINANCE_IDENTITY_SOURCE_UNAVAILABLE",
                    ))
                    break
                try:
                    if self._realization_has_continuation(response):
                        raise ValueError("FIFO_FINANCE_PAGINATION_UNSUPPORTED")
                    response_rows = self._realization_rows(response)
                    response_complete = isinstance(response_rows, list)
                    if not response_complete:
                        raise ValueError("FIFO_FINANCE_MONTH_ROWS_MISSING")
                    raw_fingerprint = self._fingerprint(response)
                    metadata = TransitionMetadata(
                        scope=scope,
                        source_kind=EvidenceSourceKind.OZON_API,
                        completeness=(
                            EvidenceCompleteness.COMPLETE if response_complete
                            else EvidenceCompleteness.PARTIAL
                        ),
                        source_fingerprint=raw_fingerprint,
                        store_timezone=store_timezone,
                    )
                    proof = SourceProof(
                        metadata=metadata,
                        scope_complete=response_complete,
                        pagination_complete=(
                            response_complete
                            and not self._realization_has_continuation(response)
                        ),
                        source_as_of=None,
                    )
                    batch = self.cutoff_bridge_source_adapter.parse_realization_postings(
                        response=response,
                        scope=scope,
                        proof=proof,
                        period_from=month_from,
                        period_to=month_to,
                        source_as_of=None,
                        confirmed_finance_sku_mappings=mappings,
                    )
                except (TypeError, ValueError) as error:
                    issues.append(self._safe_issue_code(
                        error, "FIFO_FINANCE_IDENTITY_SOURCE_FORMAT_INVALID",
                    ))
                    return self._result(
                        status="CONFLICT", source_status="CONFLICT",
                        attempts=attempts, cap=attempts_limit, started=started,
                        fingerprint=chain_fingerprint, issues=issues,
                        finance_identity_snapshots=tuple(batches),
                    )
                for row in batch.rows:
                    identity_digest = self._fingerprint({
                        "posting_number": row.posting_number,
                        "finance_sku": row.finance_sku,
                        "offer_id": row.offer_id,
                        "product_id": row.product_id,
                    })
                    if identity_digest in seen:
                        return self._result(
                            status="CONFLICT", source_status="CONFLICT",
                            attempts=attempts, cap=attempts_limit, started=started,
                            fingerprint=chain_fingerprint,
                            issues=("FIFO_FINANCE_IDENTITY_DUPLICATE_ACROSS_MONTHS",),
                            finance_identity_snapshots=tuple(batches),
                        )
                    seen.add(identity_digest)
                if len(seen) > self.MAX_TOTAL_FINANCE_IDENTITIES:
                    return self._result(
                        status="PARTIAL", source_status="PARTIAL",
                        attempts=attempts, cap=attempts_limit, started=started,
                        fingerprint=chain_fingerprint,
                        issues=("FIFO_FINANCE_IDENTITY_ROW_LIMIT",),
                        finance_identity_snapshots=tuple(batches),
                    )
                batch_bytes = self._finance_identity_batch_bytes(batch)
                if (
                    batch_bytes is None
                    or normalized_bytes + batch_bytes
                    > self.MAX_FINANCE_IDENTITY_SNAPSHOT_BYTES
                ):
                    return self._result(
                        status="PARTIAL", source_status="PARTIAL",
                        attempts=attempts, cap=attempts_limit, started=started,
                        fingerprint=chain_fingerprint,
                        issues=("FIFO_FINANCE_IDENTITY_SOURCE_BYTE_LIMIT",),
                        finance_identity_snapshots=tuple(batches),
                    )
                normalized_bytes += batch_bytes
                batches.append(batch)
                chain_fingerprint = self._fingerprint({
                    "previous": chain_fingerprint,
                    "month": [year, month],
                    "batch": batch.source_fingerprint,
                })
                next_index += 1
                pages_this_call += 1
        finally:
            reset_period_profit_trace(trace_token)

        if next_index == len(state_months):
            return self._result(
                status="COMPLETE", source_status="COMPLETE", attempts=attempts,
                cap=attempts_limit, started=started, fingerprint=chain_fingerprint,
                issues=issues, finance_identity_snapshots=tuple(batches),
            )
        continuation = self._save_scoped_checkpoint(
            self._finance_checkpoints,
            _FinanceIdentityCheckpoint(
                scope_fingerprint=scope_fingerprint,
                months=state_months,
                next_month_index=next_index,
                batches=tuple(batches),
                seen_identity_fingerprints=tuple(sorted(seen)),
                normalized_bytes=normalized_bytes,
                source_fingerprint=chain_fingerprint,
                expires_at=self.monotonic_clock() + self.CHECKPOINT_TTL_SECONDS,
            ),
        ) if batches else None
        if continuation is None and next_index < len(state_months) and batches:
            issues.append("FIFO_FINANCE_IDENTITY_CONTINUATION_UNAVAILABLE")
        return self._result(
            status="PARTIAL" if batches else "UNAVAILABLE",
            source_status="PARTIAL" if batches else "UNAVAILABLE",
            attempts=attempts, cap=attempts_limit, started=started,
            fingerprint=chain_fingerprint, issues=issues,
            finance_identity_snapshots=tuple(batches),
            continuation=continuation,
        )

    @_singleflight_collection("return_status")
    def collect_return_status_snapshot(
        self, *, scope, period_from, period_to, transition_case_id,
        transition_case_revision, store_timezone, return_schema,
        continuation_token=None, operation_trace=None,
        max_pages_per_call=RETURN_PAGE_COUNT_PER_CALL,
        http_attempt_budget=MAX_DIAGNOSTIC_HTTP_ATTEMPTS,
        time_budget_seconds=20.0,
    ):
        """Collect paginated Returns observations without inventing physical dates.

        ``visual_status_change_moment`` is filtered by UTC date, as the existing
        Seller API client sends `Z` boundaries for this date-only request.
        Even a complete FBO/FBS query is not full physical movement coverage:
        seller withdrawals, damages and other outflows require separate proof.
        """
        started = self.monotonic_clock()
        valid, issue = self._validate_transition_source_request(
            scope=scope, period_from=period_from, period_to=period_to,
            transition_case_id=transition_case_id,
            transition_case_revision=transition_case_revision,
            store_timezone=store_timezone,
        )
        attempts_limit, seconds_limit = self._limits(
            http_attempt_budget, time_budget_seconds,
            default_attempts=self.MAX_DIAGNOSTIC_HTTP_ATTEMPTS,
            maximum_attempts=self.MAX_DIAGNOSTIC_HTTP_ATTEMPTS,
        )
        page_limit = self._bounded_integer(
            max_pages_per_call, minimum=1,
            maximum=self.RETURN_PAGE_COUNT_PER_CALL,
        )
        if (
            not valid or not isinstance(return_schema, str)
            or return_schema not in {"FBO", "FBS"}
            or scope.offer_id is None
            or attempts_limit is None or seconds_limit is None
            or page_limit is None
        ):
            return self._result(
                status="INVALID", source_status="CONFLICT", attempts=0,
                cap=attempts_limit or 0, started=started,
                issues=(issue or (
                    "FIFO_RETURN_OFFER_ID_REQUIRED" if isinstance(scope, ScopeIdentity)
                    and scope.offer_id is None else "FIFO_RETURN_COLLECTION_INPUT_INVALID"
                ),),
            )

        scope_fingerprint = self._fingerprint({
            "source": "RETURN_STATUS_OBSERVATION",
            "scope": self._scope_material(scope),
            "period_from": period_from,
            "period_to": period_to,
            "case_id": transition_case_id,
            "case_revision": transition_case_revision,
            "store_timezone": store_timezone,
            "return_schema": return_schema,
            "filter_basis": "VISUAL_STATUS_CHANGE_MOMENT_UTC",
        })
        if scope_fingerprint is None:
            return self._result(
                status="INVALID", source_status="CONFLICT", attempts=0,
                cap=attempts_limit, started=started,
                issues=("FIFO_RETURN_SCOPE_FINGERPRINT_INVALID",),
            )
        checkpoint, checkpoint_error = self._take_scoped_checkpoint(
            self._return_checkpoints, continuation_token,
            scope_fingerprint=scope_fingerprint,
        )
        if checkpoint_error:
            return self._result(
                status="CONFLICT", source_status="CONFLICT", attempts=0,
                cap=attempts_limit, started=started, issues=(checkpoint_error,),
            )
        last_id = checkpoint.last_id if checkpoint else 0
        seen_cursors = set(checkpoint.seen_cursor_ids) if checkpoint else {0}
        seen_ids = set(checkpoint.seen_return_ids) if checkpoint else set()
        pages_checked = checkpoint.pages_checked if checkpoint else 0
        records = list(checkpoint.records) if checkpoint else []
        normalized_bytes = checkpoint.normalized_bytes if checkpoint else 0
        chain_fingerprint = checkpoint.source_fingerprint if checkpoint else self._fingerprint({
            "source": "OZON_RETURNS_LIST_V1",
            "scope": self._scope_material(scope),
            "period_from": period_from,
            "period_to": period_to,
            "schema": return_schema,
            "filter_basis": "VISUAL_STATUS_CHANGE_MOMENT_UTC",
        })
        trace = self._new_trace(
            "fifo_return_status_snapshot", seconds_limit,
            attempts_limit, operation_trace,
        )
        trace_token = activate_period_profit_trace(trace)
        attempts = 0
        issues = []
        complete = False
        conflict = False
        quota_blocked = False
        try:
            pages_this_call = 0
            while pages_this_call < page_limit and pages_checked < self.MAX_TOTAL_RETURN_PAGES:
                if trace.is_cancelled() or trace.remaining_seconds() <= 0 or attempts >= attempts_limit:
                    issues.append(
                        "FIFO_SOURCE_CANCELLED" if trace.is_cancelled() else
                        "FIFO_SOURCE_TIME_BUDGET_EXHAUSTED" if trace.remaining_seconds() <= 0 else
                        "FIFO_SOURCE_HTTP_BUDGET_EXHAUSTED"
                    )
                    break
                response, call_attempts, request_reason = self._call(
                    trace,
                    "get_returns",
                    offer_id=scope.offer_id,
                    return_schema=return_schema,
                    since=period_from,
                    to=period_to,
                    limit=self.RETURN_PAGE_SIZE,
                    last_id=last_id,
                    max_http_attempts=attempts_limit - attempts,
                )
                attempts += call_attempts
                if request_reason or not isinstance(response, dict) or response.get("error") is True:
                    issues.append(request_reason or self._safe_error_code(
                        response, "FIFO_RETURNS_SOURCE_UNAVAILABLE",
                    ))
                    break
                page_records, has_next, page_error = self._parse_return_page(
                    response, scope=scope, return_schema=return_schema,
                    period_from=period_from, period_to=period_to,
                )
                if page_error:
                    issues.append(page_error)
                    conflict = True
                    break
                if has_next and not page_records:
                    issues.append("FIFO_RETURNS_EMPTY_PAGE_WITH_HAS_NEXT")
                    conflict = True
                    break
                page_ids = [item["return_id"] for item in page_records]
                duplicate_id = next((value for value in page_ids if value in seen_ids), None)
                if duplicate_id is not None or len(page_ids) != len(set(page_ids)):
                    issues.append("FIFO_RETURNS_DUPLICATE_ID")
                    conflict = True
                    break
                normalized_page = [item["record"] for item in page_records]
                if len(records) + len(normalized_page) > self.MAX_RETURN_SNAPSHOT_RECORDS:
                    issues.append("FIFO_RETURNS_RECORD_LIMIT")
                    quota_blocked = True
                    break
                try:
                    page_bytes = len(json.dumps(
                        normalized_page, sort_keys=True, separators=(",", ":"),
                        ensure_ascii=False, allow_nan=False,
                    ).encode("utf-8"))
                except (TypeError, ValueError, OverflowError):
                    issues.append("FIFO_RETURNS_RECORD_SERIALIZATION_INVALID")
                    conflict = True
                    break
                if normalized_bytes + page_bytes > self.MAX_RETURN_SNAPSHOT_BYTES:
                    issues.append("FIFO_RETURNS_SOURCE_BYTE_LIMIT")
                    quota_blocked = True
                    break
                normalized_bytes += page_bytes
                page_fingerprint = self._fingerprint(normalized_page)
                records.extend(normalized_page)
                seen_ids.update(page_ids)
                pages_checked += 1
                pages_this_call += 1
                chain_fingerprint = self._fingerprint({
                    "previous": chain_fingerprint,
                    "page": page_fingerprint,
                    "cursor": last_id,
                })
                if not has_next:
                    complete = True
                    break
                next_id = int(page_ids[-1])
                if next_id == last_id or next_id in seen_cursors:
                    issues.append("FIFO_RETURNS_CURSOR_NOT_ADVANCING")
                    conflict = True
                    break
                seen_cursors.add(next_id)
                last_id = next_id
            if pages_checked >= self.MAX_TOTAL_RETURN_PAGES and not complete and not conflict:
                issues.append("FIFO_RETURNS_PAGE_LIMIT_REACHED")
        finally:
            reset_period_profit_trace(trace_token)

        if conflict:
            return self._result(
                status="CONFLICT", source_status="CONFLICT", attempts=attempts,
                cap=attempts_limit, started=started, fingerprint=chain_fingerprint,
                issues=issues,
            )
        continuation = None
        if (
            not complete and pages_checked > 0
            and pages_checked < self.MAX_TOTAL_RETURN_PAGES
            and not quota_blocked
        ):
            continuation = self._save_scoped_checkpoint(
                self._return_checkpoints,
                _ReturnStatusCheckpoint(
                    scope_fingerprint=scope_fingerprint,
                    last_id=last_id,
                    seen_cursor_ids=tuple(sorted(seen_cursors)),
                    seen_return_ids=tuple(sorted(seen_ids)),
                    pages_checked=pages_checked,
                    records=tuple(records),
                    normalized_bytes=normalized_bytes,
                    source_fingerprint=chain_fingerprint,
                    expires_at=self.monotonic_clock() + self.CHECKPOINT_TTL_SECONDS,
                ),
            )
            if continuation is None:
                issues.append("FIFO_RETURNS_CONTINUATION_UNAVAILABLE")
        if complete:
            status = "COMPLETE"
        elif records or pages_checked or quota_blocked:
            status = "PARTIAL"
        else:
            status = "UNAVAILABLE"
        snapshot = None
        if records or complete:
            snapshot = FifoReturnStatusSnapshot(
                status=status,
                source_status=status,
                store_id=scope.store_id,
                offer_id=scope.offer_id,
                sku=scope.sku,
                return_schema=return_schema,
                period_from=period_from,
                period_to=period_to,
                filter_basis="VISUAL_STATUS_CHANGE_MOMENT_UTC",
                filter_timezone="UTC",
                store_timezone=store_timezone,
                captured_at=self._now_utc().isoformat(
                    timespec="microseconds",
                ).replace("+00:00", "Z"),
                page_count=pages_checked,
                record_count=len(records),
                records=tuple(records),
                source_fingerprint=chain_fingerprint,
                issue_codes=tuple(issues),
            )
        return self._result(
            status=status, source_status=status, attempts=attempts,
            cap=attempts_limit, started=started, fingerprint=chain_fingerprint,
            issues=issues, continuation=continuation,
            return_snapshot=snapshot,
        )

    @_singleflight_collection("active_supply")
    def observe_active_supply_by_id(
        self,
        supply_id,
        *,
        owner_id,
        identity,
        store_id,
        tenant_scope,
        operation_trace=None,
        checkpoint_token=None,
        transition_case_id=None,
        transition_case_revision=None,
        max_pages_per_call=MAX_DIAGNOSTIC_PAGES_PER_CALL,
        http_attempt_budget=MAX_DIAGNOSTIC_HTTP_ATTEMPTS,
        time_budget_seconds=20.0,
    ) -> FifoSourceCollectionResult:
        """Observe one declared supply across active and terminal order states.

        Unlike ``find_supply_by_id`` this method does not require a completed
        order or an accepted act. It returns status only; missing quantities
        remain unknown and a negative result is authoritative only after a
        complete paginated lookup.
        """

        started = self.monotonic_clock()
        normalized_supply_id = self._identifier(supply_id)
        normalized_owner = self._text(owner_id, 128)
        normalized_identity = self._identity(identity)
        normalized_store = self._text(store_id, 128)
        normalized_tenant = self._text(tenant_scope, 128)
        normalized_case_id = self._text(transition_case_id, 128) if transition_case_id is not None else None
        normalized_case_revision = self._bounded_integer(
            transition_case_revision, minimum=1, maximum=1_000_000,
        ) if transition_case_revision is not None else None
        case_scope_valid = (
            (transition_case_id is None and transition_case_revision is None)
            or (normalized_case_id is not None and normalized_case_revision is not None)
        )
        normalized_reference_digest = (
            supply_reference_digest(
                owner_id=normalized_owner,
                store_id=normalized_store,
                reference_kind=SupplyReferenceKind.SUPPLY,
                reference_id=normalized_supply_id,
            )
            if normalized_owner and normalized_store and normalized_supply_id
            else None
        )
        attempts_limit, seconds_limit = self._limits(
            http_attempt_budget, time_budget_seconds,
            default_attempts=self.MAX_DIAGNOSTIC_HTTP_ATTEMPTS,
            maximum_attempts=self.MAX_DIAGNOSTIC_HTTP_ATTEMPTS,
        )
        page_limit = self._bounded_integer(
            max_pages_per_call, minimum=1,
            maximum=self.MAX_DIAGNOSTIC_PAGES_PER_CALL,
        )
        if (
            normalized_supply_id is None
            or normalized_owner is None
            or normalized_reference_digest is None
            or normalized_identity is None
            or normalized_store is None
            or normalized_tenant is None
            or not case_scope_valid
            or attempts_limit is None
            or seconds_limit is None
            or page_limit is None
        ):
            return self._result(
                status="INVALID", source_status="CONFLICT", attempts=0,
                cap=attempts_limit or 0, started=started,
                issues=("FIFO_ACTIVE_SUPPLY_LOOKUP_INPUT_INVALID",),
            )

        scope_fingerprint = self._fingerprint({
            "action": "active_supply_status",
            "tenant": normalized_tenant,
            "store": normalized_store,
            "identity": list(normalized_identity),
            "declaration_reference_digest": normalized_reference_digest,
            "transition_case_id": normalized_case_id,
            "transition_case_revision": normalized_case_revision,
        })
        state, state_error = self._take_checkpoint(
            checkpoint_token, scope_fingerprint=scope_fingerprint,
        )
        if state_error:
            return self._result(
                status="CONFLICT", source_status="CONFLICT", attempts=0,
                cap=attempts_limit, started=started, issues=(state_error,),
            )
        if checkpoint_token is None:
            state["source_fingerprint"] = self._fingerprint({
                "source": "fifo-active-supply-status:v1",
                "scope": scope_fingerprint,
            })
        if state["pages_checked"] >= self.MAX_TOTAL_SUPPLY_PAGES:
            return self._result(
                status="PARTIAL", source_status="PARTIAL", attempts=0,
                cap=attempts_limit, started=started,
                fingerprint=state["source_fingerprint"],
                issues=("FIFO_ACTIVE_SUPPLY_SEARCH_PAGE_LIMIT",),
            )

        trace = self._new_trace(
            "fifo_active_supply_observation",
            min(seconds_limit, self.MAX_ACTIVE_SUPPLY_TIME_BUDGET_SECONDS),
            attempts_limit,
            operation_trace,
        )
        token = activate_period_profit_trace(trace)
        attempts = 0
        pages_this_call = 0
        status = "PARTIAL"
        source_status = "PARTIAL"
        issues: list[str] = []
        final_fingerprint = state["source_fingerprint"]
        snapshot = None
        continuation = None
        found = state.get("matched_supply") is not None
        matched_supply = state.get("matched_supply")
        try:
            while pages_this_call < page_limit:
                if trace.is_cancelled():
                    status = "UNAVAILABLE"
                    source_status = "UNAVAILABLE"
                    issues.append("FIFO_SOURCE_CANCELLED")
                    break
                if trace.remaining_seconds() <= 0:
                    issues.append("FIFO_SOURCE_TIME_BUDGET_EXHAUSTED")
                    break
                if attempts >= attempts_limit:
                    issues.append("FIFO_SOURCE_HTTP_BUDGET_EXHAUSTED")
                    break

                page, used, reason = self._call(
                    trace,
                    "get_supply_orders_list",
                    list(self.ACTIVE_SUPPLY_STATES),
                    last_id=state["cursor"],
                    limit=self.MAX_PAGE_SIZE,
                    sort_by="ORDER_STATE_UPDATED_AT",
                    sort_dir="DESC",
                    max_http_attempts=attempts_limit - attempts,
                )
                attempts += used
                if page is None or self._failed_response(page):
                    issues.append(reason or self._safe_error_code(
                        page, "FIFO_ACTIVE_SUPPLY_LIST_UNAVAILABLE",
                    ))
                    break
                page_ids = self._order_ids(page.get("order_ids"))
                if page_ids is None:
                    status = "CONFLICT"
                    source_status = "CONFLICT"
                    issues.append("FIFO_ACTIVE_SUPPLY_LIST_INVALID")
                    break
                cursor, cursor_valid = self._cursor(page.get("last_id"))
                if not cursor_valid:
                    status = "CONFLICT"
                    source_status = "CONFLICT"
                    issues.append("FIFO_ACTIVE_SUPPLY_CURSOR_INVALID")
                    break
                if not page_ids:
                    if cursor is not None:
                        status = "CONFLICT"
                        source_status = "CONFLICT"
                        issues.append("FIFO_ACTIVE_SUPPLY_CURSOR_WITH_EMPTY_PAGE")
                    else:
                        final_fingerprint = self._fingerprint({
                            "previous": final_fingerprint,
                            "terminal_empty_page": True,
                        })
                        source_status = "COMPLETE"
                        if matched_supply is not None:
                            found = True
                            status = "PRESENT"
                            snapshot = self.normalizer.normalize_active_supply_snapshot(
                                supply_reference_digest=normalized_reference_digest,
                                store_id=normalized_store,
                                captured_at=self._now_utc(),
                                source_fingerprint=final_fingerprint,
                                presence="PRESENT",
                                raw_status=matched_supply[1],
                                order_id=matched_supply[0],
                                scope_complete=True,
                                pagination_complete=True,
                                source_status="COMPLETE",
                                issue_codes=issues,
                            )
                        else:
                            status = "MISSING"
                            snapshot = self.normalizer.normalize_active_supply_snapshot(
                                supply_reference_digest=normalized_reference_digest,
                                store_id=normalized_store,
                                captured_at=self._now_utc(),
                                source_fingerprint=final_fingerprint,
                                presence="MISSING",
                                raw_status=None,
                                order_id=None,
                                scope_complete=True,
                                pagination_complete=True,
                                source_status="COMPLETE",
                            )
                        issues.extend(snapshot.issue_codes)
                    break
                if cursor is None and len(page_ids) >= self.MAX_PAGE_SIZE:
                    status = "CONFLICT"
                    source_status = "CONFLICT"
                    issues.append("FIFO_ACTIVE_SUPPLY_CURSOR_MISSING")
                    break
                cursor_digest = self._digest("CURSOR", cursor) if cursor is not None else None
                if cursor is not None and (
                    cursor == state["cursor"]
                    or cursor_digest in state["seen_cursor_fingerprints"]
                ):
                    status = "CONFLICT"
                    source_status = "CONFLICT"
                    issues.append("FIFO_ACTIVE_SUPPLY_CURSOR_NOT_ADVANCING")
                    break
                page_order_fingerprints = tuple(
                    self._digest("ORDER", order_id) for order_id in page_ids
                )
                if len(set(page_order_fingerprints)) != len(page_order_fingerprints):
                    status = "CONFLICT"
                    source_status = "CONFLICT"
                    issues.append("FIFO_ACTIVE_SUPPLY_DUPLICATE_ORDER_ID")
                    break
                if set(page_order_fingerprints).intersection(state["seen_order_fingerprints"]):
                    status = "CONFLICT"
                    source_status = "CONFLICT"
                    issues.append("FIFO_ACTIVE_SUPPLY_ORDER_REPEATED_ACROSS_PAGES")
                    break
                if len(state["seen_order_fingerprints"]) + len(page_order_fingerprints) > self.MAX_SEEN_ROWS:
                    status = "PARTIAL"
                    source_status = "PARTIAL"
                    issues.append("FIFO_ACTIVE_SUPPLY_SEARCH_ROW_LIMIT")
                    break

                orders, used, reason = self._load_order_details(
                    trace, page_ids,
                    max_http_attempts=attempts_limit - attempts,
                )
                attempts += used
                if orders is None:
                    issues.append(reason or "FIFO_ACTIVE_SUPPLY_DETAILS_UNAVAILABLE")
                    break
                final_fingerprint = self._fingerprint({
                    "previous": final_fingerprint,
                    "page": self._page_fingerprint(page_ids, orders),
                })
                pages_this_call += 1
                state["pages_checked"] += 1
                state["seen_order_fingerprints"].extend(page_order_fingerprints)
                matches = self._matching_supply_orders(orders, normalized_supply_id)
                if matches is None:
                    status = "CONFLICT"
                    source_status = "CONFLICT"
                    issues.append("FIFO_ACTIVE_SUPPLY_ORDER_STRUCTURE_INVALID")
                    break
                if len(matches) > 1:
                    status = "CONFLICT"
                    source_status = "CONFLICT"
                    issues.append("FIFO_ACTIVE_SUPPLY_ID_AMBIGUOUS")
                    break
                if matches:
                    if matched_supply is not None:
                        status = "CONFLICT"
                        source_status = "CONFLICT"
                        issues.append("FIFO_ACTIVE_SUPPLY_ID_AMBIGUOUS")
                        break
                    order, supply = matches[0]
                    order_id = self._identifier(order.get("order_id"))
                    if order_id is None:
                        status = "CONFLICT"
                        source_status = "CONFLICT"
                        issues.append("FIFO_ACTIVE_SUPPLY_ORDER_ID_INVALID")
                        break
                    order_state = self._safe_enum(order.get("state"))
                    if order_state not in self.ACTIVE_SUPPLY_STATES:
                        issues.append("FIFO_ACTIVE_SUPPLY_ORDER_STATE_UNKNOWN")
                    matched_supply = (order_id, supply.get("state"))
                    state["matched_supply"] = matched_supply
                    if cursor is None:
                        found = True
                        snapshot = self.normalizer.normalize_active_supply_snapshot(
                            supply_reference_digest=normalized_reference_digest,
                            store_id=normalized_store,
                            captured_at=self._now_utc(),
                            source_fingerprint=final_fingerprint,
                            presence="PRESENT",
                            raw_status=matched_supply[1],
                            order_id=matched_supply[0],
                            scope_complete=True,
                            pagination_complete=True,
                            source_status="COMPLETE",
                            issue_codes=issues,
                        )
                        issues.extend(snapshot.issue_codes)
                        source_status = snapshot.source_status
                        status = snapshot.status
                        break
                    state["cursor"] = cursor
                    if cursor_digest is not None:
                        state["seen_cursor_fingerprints"].append(cursor_digest)
                    status = "PARTIAL"
                    source_status = "PARTIAL"
                    continue

                state["cursor"] = cursor
                if cursor_digest is not None:
                    state["seen_cursor_fingerprints"].append(cursor_digest)
                if cursor is None:
                    source_status = "COMPLETE"
                    if matched_supply is not None:
                        found = True
                        status = "PRESENT"
                        snapshot = self.normalizer.normalize_active_supply_snapshot(
                            supply_reference_digest=normalized_reference_digest,
                            store_id=normalized_store,
                            captured_at=self._now_utc(),
                            source_fingerprint=final_fingerprint,
                            presence="PRESENT",
                            raw_status=matched_supply[1],
                            order_id=matched_supply[0],
                            scope_complete=True,
                            pagination_complete=True,
                            source_status="COMPLETE",
                            issue_codes=issues,
                        )
                    else:
                        status = "MISSING"
                        snapshot = self.normalizer.normalize_active_supply_snapshot(
                            supply_reference_digest=normalized_reference_digest,
                            store_id=normalized_store,
                            captured_at=self._now_utc(),
                            source_fingerprint=final_fingerprint,
                            presence="MISSING",
                            raw_status=None,
                            order_id=None,
                            scope_complete=True,
                            pagination_complete=True,
                            source_status="COMPLETE",
                        )
                    issues.extend(snapshot.issue_codes)
                    break

            if status == "PARTIAL" and not issues and state["pages_checked"] >= self.MAX_TOTAL_SUPPLY_PAGES:
                issues.append("FIFO_ACTIVE_SUPPLY_SEARCH_PAGE_LIMIT")
        finally:
            reset_period_profit_trace(token)

        if status == "PARTIAL" and attempts == 0 and pages_this_call == 0 and state["pages_checked"] == 0:
            status = "UNAVAILABLE"
            source_status = "UNAVAILABLE"
        if status == "PARTIAL" and not trace.is_cancelled():
            continuation = self._save_checkpoint(
                _SupplySearchCheckpoint(
                    scope_fingerprint=scope_fingerprint,
                    cursor=state["cursor"],
                    seen_cursor_fingerprints=tuple(state["seen_cursor_fingerprints"]),
                    seen_order_fingerprints=tuple(state["seen_order_fingerprints"]),
                    pages_checked=state["pages_checked"],
                    source_fingerprint=final_fingerprint,
                    matched_supply=matched_supply,
                    expires_at=self.monotonic_clock() + self.CHECKPOINT_TTL_SECONDS,
                )
            )
            if continuation is None:
                issues.append("FIFO_ACTIVE_SUPPLY_CHECKPOINT_UNAVAILABLE")
        if trace.is_cancelled():
            continuation = None
            snapshot = None
            status = "UNAVAILABLE"
            source_status = "UNAVAILABLE"
        return self._result(
            status=status,
            source_status=source_status,
            attempts=attempts,
            cap=attempts_limit,
            started=started,
            fingerprint=final_fingerprint,
            issues=tuple(dict.fromkeys(issues)),
            supply_snapshot=snapshot,
            continuation=continuation,
        )

    @_singleflight_collection("supply")
    def find_supply_by_id(
        self,
        supply_id,
        *,
        identity,
        store_id,
        tenant_scope,
        operation_trace=None,
        checkpoint_token=None,
        transition_case_id=None,
        transition_case_revision=None,
        max_pages_per_call=MAX_DIAGNOSTIC_PAGES_PER_CALL,
        http_attempt_budget=MAX_DIAGNOSTIC_HTTP_ATTEMPTS,
        time_budget_seconds=MAX_ELAPSED_SECONDS,
    ) -> FifoSourceCollectionResult:
        """Find one supply through bounded completed-order pages and accepted acts.

        A completed negative lookup is ``NOT_FOUND``; only a matched accepted
        act returns unit facts. Any truncated or interrupted read remains
        ``PARTIAL`` and, where possible, receives a short-lived continuation.
        """

        started = self.monotonic_clock()
        normalized_supply_id = self._identifier(supply_id)
        normalized_identity = self._identity(identity)
        normalized_store = self._text(store_id, 128)
        normalized_tenant = self._text(tenant_scope, 128)
        normalized_case_id = self._text(transition_case_id, 128) if transition_case_id is not None else None
        normalized_case_revision = self._bounded_integer(
            transition_case_revision, minimum=1, maximum=1_000_000,
        ) if transition_case_revision is not None else None
        case_scope_valid = (
            (transition_case_id is None and transition_case_revision is None)
            or (normalized_case_id is not None and normalized_case_revision is not None)
        )
        attempts_limit, seconds_limit = self._limits(
            http_attempt_budget, time_budget_seconds,
            default_attempts=self.MAX_DIAGNOSTIC_HTTP_ATTEMPTS,
            maximum_attempts=self.MAX_HTTP_ATTEMPTS,
        )
        page_limit = self._bounded_integer(
            max_pages_per_call, minimum=1,
            maximum=self.MAX_DIAGNOSTIC_PAGES_PER_CALL,
        )
        if (
            normalized_supply_id is None
            or normalized_identity is None
            or normalized_store is None
            or normalized_tenant is None
            or not case_scope_valid
            or attempts_limit is None
            or seconds_limit is None
            or page_limit is None
        ):
            return self._result(
                status="INVALID", source_status="CONFLICT", attempts=0,
                cap=attempts_limit or 0, started=started,
                issues=("FIFO_SUPPLY_LOOKUP_INPUT_INVALID",),
            )

        scope_fingerprint = self._fingerprint({
            "tenant": normalized_tenant,
            "store": normalized_store,
            "identity": list(normalized_identity),
            "supply_ref": self._digest("SUPPLY", normalized_supply_id),
            "transition_case_id": normalized_case_id,
            "transition_case_revision": normalized_case_revision,
        })
        state, state_error = self._take_checkpoint(
            checkpoint_token,
            scope_fingerprint=scope_fingerprint,
        )
        if state_error:
            return self._result(
                status="CONFLICT", source_status="CONFLICT", attempts=0,
                cap=attempts_limit, started=started, issues=(state_error,),
            )
        if state["pages_checked"] >= self.MAX_TOTAL_SUPPLY_PAGES:
            return self._result(
                status="PARTIAL", source_status="PARTIAL", attempts=0,
                cap=attempts_limit, started=started,
                fingerprint=state["source_fingerprint"],
                issues=("FIFO_SUPPLY_SEARCH_PAGE_LIMIT",),
            )

        trace = self._new_trace(
            "fifo_cost_supply_lookup",
            seconds_limit,
            attempts_limit,
            operation_trace,
        )
        token = activate_period_profit_trace(trace)
        attempts = 0
        pages_this_call = 0
        status = "PARTIAL"
        source_status = "PARTIAL"
        issues: list[str] = []
        final_fingerprint = state["source_fingerprint"]
        snapshot = None
        continuation = None
        candidate_found = False
        try:
            while pages_this_call < page_limit:
                if trace.is_cancelled():
                    status = "UNAVAILABLE"
                    source_status = "UNAVAILABLE"
                    issues.append("FIFO_SOURCE_CANCELLED")
                    break
                if trace.remaining_seconds() <= 0:
                    issues.append("FIFO_SOURCE_TIME_BUDGET_EXHAUSTED")
                    break
                if attempts >= attempts_limit:
                    issues.append("FIFO_SOURCE_HTTP_BUDGET_EXHAUSTED")
                    break

                page, call_attempts, reason = self._call(
                    trace,
                    "get_supply_orders_list",
                    ["COMPLETED"],
                    last_id=state["cursor"],
                    limit=self.MAX_PAGE_SIZE,
                    sort_by="ORDER_STATE_UPDATED_AT",
                    sort_dir="DESC",
                    max_http_attempts=attempts_limit - attempts,
                )
                attempts += call_attempts
                if page is None or self._failed_response(page):
                    issues.append(reason or self._safe_error_code(page, "FIFO_SUPPLY_LIST_UNAVAILABLE"))
                    break
                page_ids = self._order_ids(page.get("order_ids"))
                if page_ids is None:
                    status = "CONFLICT"
                    source_status = "CONFLICT"
                    issues.append("FIFO_SUPPLY_LIST_INVALID")
                    break
                cursor, cursor_valid = self._cursor(page.get("last_id"))
                if not cursor_valid:
                    status = "CONFLICT"
                    source_status = "CONFLICT"
                    issues.append("FIFO_SUPPLY_CURSOR_INVALID")
                    break
                if not page_ids:
                    if cursor is not None:
                        status = "CONFLICT"
                        source_status = "CONFLICT"
                        issues.append("FIFO_SUPPLY_CURSOR_WITH_EMPTY_PAGE")
                    else:
                        final_fingerprint = self._fingerprint({
                            "previous": final_fingerprint,
                            "terminal_empty_page": True,
                        })
                        status = "NOT_FOUND"
                        source_status = "COMPLETE"
                    break
                if cursor is None and len(page_ids) >= self.MAX_PAGE_SIZE:
                    status = "CONFLICT"
                    source_status = "CONFLICT"
                    issues.append("FIFO_SUPPLY_CURSOR_MISSING")
                    break
                cursor_digest = self._digest("CURSOR", cursor) if cursor is not None else None
                if cursor is not None and (
                    cursor == state["cursor"]
                    or cursor_digest in state["seen_cursor_fingerprints"]
                ):
                    status = "CONFLICT"
                    source_status = "CONFLICT"
                    issues.append("FIFO_SUPPLY_CURSOR_NOT_ADVANCING")
                    break
                page_order_fingerprints = tuple(
                    self._digest("ORDER", order_id) for order_id in page_ids
                )
                if len(set(page_order_fingerprints)) != len(page_order_fingerprints):
                    status = "CONFLICT"
                    source_status = "CONFLICT"
                    issues.append("FIFO_SUPPLY_DUPLICATE_ORDER_ID")
                    break
                if set(page_order_fingerprints).intersection(state["seen_order_fingerprints"]):
                    status = "CONFLICT"
                    source_status = "CONFLICT"
                    issues.append("FIFO_SUPPLY_ORDER_REPEATED_ACROSS_PAGES")
                    break
                if len(state["seen_order_fingerprints"]) + len(page_order_fingerprints) > self.MAX_SEEN_ROWS:
                    status = "PARTIAL"
                    source_status = "PARTIAL"
                    issues.append("FIFO_SUPPLY_SEARCH_ROW_LIMIT")
                    break

                orders, call_attempts, reason = self._load_order_details(
                    trace,
                    page_ids,
                    max_http_attempts=attempts_limit - attempts,
                )
                attempts += call_attempts
                if orders is None:
                    issues.append(reason or "FIFO_SUPPLY_DETAILS_UNAVAILABLE")
                    break
                page_digest = self._page_fingerprint(page_ids, orders)
                final_fingerprint = self._fingerprint({
                    "previous": final_fingerprint,
                    "page": page_digest,
                })
                pages_this_call += 1
                state["pages_checked"] += 1
                state["seen_order_fingerprints"].extend(page_order_fingerprints)

                matches = self._matching_supply_orders(orders, normalized_supply_id)
                if matches is None:
                    status = "CONFLICT"
                    source_status = "CONFLICT"
                    issues.append("FIFO_SUPPLY_ORDER_STRUCTURE_INVALID")
                    break
                if len(matches) > 1:
                    status = "CONFLICT"
                    source_status = "CONFLICT"
                    issues.append("FIFO_SUPPLY_ID_AMBIGUOUS")
                    break
                if matches:
                    candidate_found = True
                    order, _matched_supply = matches[0]
                    order_id = self._identifier(order.get("order_id"))
                    if order.get("state") != "COMPLETED" or order_id is None:
                        status = "CONFLICT"
                        source_status = "CONFLICT"
                        issues.append("FIFO_SUPPLY_ORDER_STATE_OR_ID_INVALID")
                        break
                    summary, call_attempts, reason = self._call(
                        trace,
                        "get_supply_act_summary",
                        order_id,
                        max_http_attempts=attempts_limit - attempts,
                    )
                    attempts += call_attempts
                    if summary is None or self._failed_response(summary):
                        issues.append(reason or self._safe_error_code(summary, "FIFO_SUPPLY_SUMMARY_UNAVAILABLE"))
                        break
                    products, call_attempts, reason = self._call(
                        trace,
                        "get_supply_act_products",
                        normalized_supply_id,
                        max_http_attempts=attempts_limit - attempts,
                    )
                    attempts += call_attempts
                    if products is None or self._failed_response(products):
                        issues.append(reason or self._safe_error_code(products, "FIFO_SUPPLY_PRODUCTS_UNAVAILABLE"))
                        break
                    snapshot = self.normalizer.normalize_supply_act_snapshot(
                        products,
                        summary,
                        store_id=normalized_store,
                        expected_supply_id=normalized_supply_id,
                        expected_order_id=order_id,
                        captured_at=self._now_utc(),
                        products_complete=True,
                        summary_complete=True,
                    )
                    if snapshot.status in {"COMPLETE", "CONFIRMED_ZERO"}:
                        if snapshot.units_by_sku is None or tuple(
                            sku for sku, _ in snapshot.units_by_sku
                        ) != (normalized_identity[2],):
                            status = "CONFLICT"
                            source_status = "CONFLICT"
                            issues.append("FIFO_SUPPLY_SKU_IDENTITY_MISMATCH")
                            break
                        status = snapshot.status
                        source_status = snapshot.source_status
                        final_fingerprint = self._fingerprint({
                            "page_chain": final_fingerprint,
                            "normalized_supply": snapshot.source_fingerprint,
                        })
                        break
                    status = snapshot.status
                    source_status = snapshot.source_status
                    issues.extend(snapshot.issue_codes)
                    break

                state["cursor"] = cursor
                if cursor_digest is not None:
                    state["seen_cursor_fingerprints"].append(cursor_digest)
                if cursor is None:
                    status = "NOT_FOUND"
                    source_status = "COMPLETE"
                    break

            if status == "PARTIAL" and not issues and state["pages_checked"] >= self.MAX_TOTAL_SUPPLY_PAGES:
                issues.append("FIFO_SUPPLY_SEARCH_PAGE_LIMIT")
        finally:
            reset_period_profit_trace(token)

        if (
            status == "PARTIAL"
            and attempts == 0
            and pages_this_call == 0
            and state["pages_checked"] == 0
        ):
            status = "UNAVAILABLE"
            source_status = "UNAVAILABLE"
        if status == "PARTIAL" and not trace.is_cancelled() and not candidate_found:
            continuation = self._save_checkpoint(
                _SupplySearchCheckpoint(
                    scope_fingerprint=scope_fingerprint,
                    cursor=state["cursor"],
                    seen_cursor_fingerprints=tuple(state["seen_cursor_fingerprints"]),
                    seen_order_fingerprints=tuple(state["seen_order_fingerprints"]),
                    pages_checked=state["pages_checked"],
                    source_fingerprint=final_fingerprint,
                    matched_supply=None,
                    expires_at=self.monotonic_clock() + self.CHECKPOINT_TTL_SECONDS,
                )
            )
            if continuation is None:
                issues.append("FIFO_SUPPLY_CHECKPOINT_UNAVAILABLE")
        if trace.is_cancelled():
            continuation = None
            status = "UNAVAILABLE"
            source_status = "UNAVAILABLE"
        return self._result(
            status=status,
            source_status=source_status,
            attempts=attempts,
            cap=attempts_limit,
            started=started,
            fingerprint=final_fingerprint,
            issues=tuple(issues),
            supply_snapshot=snapshot,
            continuation=continuation,
        )

    def _load_order_details(self, trace, order_ids, *, max_http_attempts):
        orders_by_id = {}
        attempts = 0
        offset = 0
        while offset < len(order_ids):
            batch = order_ids[offset:offset + self.MAX_DETAILS_BATCH_SIZE]
            response, used, reason = self._call(
                trace,
                "get_supply_orders_details",
                batch,
                max_http_attempts=max_http_attempts - attempts,
            )
            attempts += used
            if response is None or self._failed_response(response):
                return None, attempts, reason or self._safe_error_code(
                    response, "FIFO_SUPPLY_DETAILS_UNAVAILABLE",
                )
            records = response.get("orders") if isinstance(response, dict) else None
            if not isinstance(records, list) or len(records) != len(batch):
                return None, attempts, "FIFO_SUPPLY_DETAILS_COVERAGE_INVALID"
            expected = set(batch)
            for record in records:
                if not isinstance(record, dict):
                    return None, attempts, "FIFO_SUPPLY_ORDER_INVALID"
                order_id = self._identifier(record.get("order_id"))
                if order_id not in expected or order_id in orders_by_id:
                    return None, attempts, "FIFO_SUPPLY_DETAILS_IDENTITY_MISMATCH"
                orders_by_id[order_id] = record
            offset += len(batch)
        if set(orders_by_id) != set(order_ids):
            return None, attempts, "FIFO_SUPPLY_DETAILS_COVERAGE_INVALID"
        return [orders_by_id[order_id] for order_id in order_ids], attempts, None

    def _call(self, trace, method_name, *args, max_http_attempts, **kwargs):
        if trace.is_cancelled():
            return None, 0, "FIFO_SOURCE_CANCELLED"
        if trace.remaining_seconds() <= 0:
            return None, 0, "FIFO_SOURCE_TIME_BUDGET_EXHAUSTED"
        if max_http_attempts <= 0:
            return None, 0, "FIFO_SOURCE_HTTP_BUDGET_EXHAUSTED"
        method = getattr(self.ozon_client, method_name, None)
        if not callable(method):
            return {"error": True, "code": "FIFO_SOURCE_METHOD_UNAVAILABLE"}, 0, "FIFO_SOURCE_METHOD_UNAVAILABLE"
        remaining = trace.remaining_seconds()
        timeout = min(self.MAX_REQUEST_TIMEOUT_SECONDS, remaining)
        total_timeout = min(self.MAX_REQUEST_TOTAL_TIMEOUT_SECONDS, remaining)
        if timeout <= 0 or total_timeout <= 0:
            return None, 0, "FIFO_SOURCE_TIME_BUDGET_EXHAUSTED"
        observed = 0

        def observe_attempt(_endpoint=None):
            nonlocal observed
            observed += 1

        try:
            response = method(
                *args,
                timeout=timeout,
                max_attempts=1,
                total_timeout=total_timeout,
                request_attempt_observer=observe_attempt,
                **kwargs,
            )
        except Exception:
            return {"error": True, "code": "FIFO_SOURCE_REQUEST_FAILED"}, observed, "FIFO_SOURCE_REQUEST_FAILED"
        if observed > max_http_attempts:
            return {"error": True, "code": "FIFO_SOURCE_HTTP_BUDGET_EXCEEDED"}, observed, "FIFO_SOURCE_HTTP_BUDGET_EXCEEDED"
        return response, observed, None

    def _take_checkpoint(self, token, *, scope_fingerprint):
        if token is None:
            return self._empty_state(), None
        if not isinstance(token, str) or not re.fullmatch(r"[0-9a-f]{32}", token):
            return self._empty_state(), "FIFO_SUPPLY_CHECKPOINT_INVALID"
        with self._checkpoint_lock:
            checkpoint = self._checkpoints.get(token)
            if checkpoint is None:
                return self._empty_state(), "FIFO_SUPPLY_CHECKPOINT_STALE"
            if checkpoint.expires_at <= self.monotonic_clock():
                self._checkpoints.pop(token, None)
                return self._empty_state(), "FIFO_SUPPLY_CHECKPOINT_EXPIRED"
            if checkpoint.scope_fingerprint != scope_fingerprint:
                return self._empty_state(), "FIFO_SUPPLY_CHECKPOINT_SCOPE_MISMATCH"
            self._checkpoints.pop(token, None)
        return {
            "cursor": checkpoint.cursor,
            "seen_cursor_fingerprints": list(checkpoint.seen_cursor_fingerprints),
            "seen_order_fingerprints": list(checkpoint.seen_order_fingerprints),
            "pages_checked": checkpoint.pages_checked,
            "source_fingerprint": checkpoint.source_fingerprint,
            "matched_supply": checkpoint.matched_supply,
        }, None

    def _save_checkpoint(self, checkpoint):
        token = uuid4().hex
        with self._checkpoint_lock:
            now = self.monotonic_clock()
            expired = [
                key for key, value in self._checkpoints.items()
                if value.expires_at <= now
            ]
            for key in expired:
                self._checkpoints.pop(key, None)
            while len(self._checkpoints) >= self.MAX_CHECKPOINTS:
                self._checkpoints.pop(next(iter(self._checkpoints)))
            self._checkpoints[token] = checkpoint
        return token

    @staticmethod
    def _empty_state():
        return {
            "cursor": None,
            "seen_cursor_fingerprints": [],
            "seen_order_fingerprints": [],
            "pages_checked": 0,
            "source_fingerprint": hashlib.sha256(b"fifo-supply-search-v1").hexdigest(),
            "matched_supply": None,
        }

    @classmethod
    def _matching_supply_orders(cls, orders, target_supply_id):
        matches = []
        for order in orders:
            if not isinstance(order, dict):
                return None
            supplies = order.get("supplies")
            if not isinstance(supplies, list):
                return None
            for supply in supplies:
                if not isinstance(supply, dict):
                    return None
                supply_id = cls._identifier(supply.get("supply_id"))
                if supply_id is None:
                    return None
                if supply_id == target_supply_id:
                    matches.append((order, supply))
        return matches

    @classmethod
    def _page_fingerprint(cls, order_ids, orders):
        rows = []
        for order_id, order in zip(order_ids, orders):
            supplies = []
            for supply in order.get("supplies", []):
                supplies.append([
                    cls._digest("SUPPLY", cls._identifier(supply.get("supply_id")) or "invalid"),
                    cls._safe_enum(supply.get("state")),
                    supply.get("is_crossdock") if type(supply.get("is_crossdock")) is bool else None,
                ])
            rows.append([
                cls._digest("ORDER", order_id),
                cls._safe_enum(order.get("state")),
                sorted(supplies),
            ])
        return cls._fingerprint(rows)

    @classmethod
    def _order_ids(cls, value):
        if not isinstance(value, list) or len(value) > cls.MAX_PAGE_SIZE:
            return None
        result = [cls._identifier(item) for item in value]
        if any(item is None for item in result):
            return None
        return result

    @classmethod
    def _cursor(cls, value):
        if value is None or value == "":
            return None, True
        if isinstance(value, bool):
            return None, False
        raw = str(value).strip()
        if not cls._CURSOR.fullmatch(raw):
            return None, False
        return raw, True

    @classmethod
    def _stock_pages_complete(cls, response, *, expected_limit):
        if not isinstance(response, dict) or response.get("error") is True:
            return False
        items = response.get("items")
        if not isinstance(items, list) or len(items) > expected_limit:
            return False
        if "total_items" not in response:
            return False
        total = response.get("total_items")
        if type(total) is not int or total < 0 or total > 10_000:
            return False
        return total == len(items)

    @classmethod
    def _validate_transition_source_request(
        cls, *, scope, period_from, period_to, transition_case_id,
        transition_case_revision, store_timezone,
    ):
        if not isinstance(scope, ScopeIdentity):
            return False, "FIFO_TRANSITION_SCOPE_INVALID"
        tenant_scope = str(get_current_tenant_user_id() or "").strip()
        owner_id, store_id = split_store_tenant_scope(tenant_scope)
        if owner_id != scope.owner_id or store_id != scope.store_id:
            return False, "FIFO_TRANSITION_SCOPE_MISMATCH"
        normalized_case_id = cls._text(transition_case_id, 128)
        if (
            normalized_case_id is None or normalized_case_id != transition_case_id
            or cls._bounded_integer(
                transition_case_revision, minimum=1, maximum=1_000_000,
            ) is None
        ):
            return False, "FIFO_TRANSITION_REVISION_INVALID"
        dates = []
        for value in (period_from, period_to):
            if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
                return False, "FIFO_SOURCE_PERIOD_INVALID"
            try:
                parsed = date.fromisoformat(value)
            except ValueError:
                return False, "FIFO_SOURCE_PERIOD_INVALID"
            if parsed.isoformat() != value:
                return False, "FIFO_SOURCE_PERIOD_INVALID"
            dates.append(parsed)
        if dates[1] < dates[0]:
            return False, "FIFO_SOURCE_PERIOD_INVALID"
        try:
            normalize_store_timezone(store_timezone)
        except (TypeError, ValueError):
            return False, "FIFO_SOURCE_TIMEZONE_INVALID"
        return True, None

    @staticmethod
    def _scope_material(scope):
        return {
            "owner_id": scope.owner_id,
            "store_id": scope.store_id,
            "product_id": scope.product_id,
            "offer_id": scope.offer_id,
            "sku": scope.sku,
        }

    @classmethod
    def _calendar_months(cls, period_from, period_to):
        try:
            start = date.fromisoformat(period_from)
            end = date.fromisoformat(period_to)
        except (TypeError, ValueError):
            return ()
        months = []
        year, month = start.year, start.month
        while (year, month) <= (end.year, end.month):
            first = date(year, month, 1)
            if month == 12:
                next_month = date(year + 1, 1, 1)
            else:
                next_month = date(year, month + 1, 1)
            last = date.fromordinal(next_month.toordinal() - 1)
            months.append((year, month, first.isoformat(), last.isoformat()))
            if month == 12:
                year, month = year + 1, 1
            else:
                month += 1
            if len(months) > cls.MAX_TOTAL_FINANCE_MONTHS:
                return tuple(months)
        return tuple(months)

    def _latest_reportable_realization_month(self, store_timezone):
        """Ozon publishes the monthly realization report after day five.

        A current/unpublished month cannot be treated as a complete zero-row
        report, even when the API returns an empty row array.
        """
        now_utc = self._now_utc()
        if now_utc is None:
            return None
        try:
            now = now_utc.astimezone(ZoneInfo(
                normalize_store_timezone(store_timezone),
            ))
        except (TypeError, ValueError):
            return None
        offset = 1 if now.day > 5 else 2
        year, month = now.year, now.month - offset
        while month <= 0:
            year -= 1
            month += 12
        return year, month

    @staticmethod
    def _realization_has_continuation(response):
        containers = [response]
        result = response.get("result")
        if isinstance(result, dict):
            containers.append(result)
        for container in containers:
            if "has_next" in container:
                if type(container["has_next"]) is not bool:
                    raise ValueError("FIFO_FINANCE_PAGINATION_FLAG_INVALID")
                if container["has_next"]:
                    return True
            for name in ("next_page_token", "next_cursor", "cursor"):
                value = container.get(name)
                if value not in (None, "", False):
                    return True
        return False

    @staticmethod
    def _realization_rows(response):
        if not isinstance(response, dict):
            return None
        rows = response.get("rows")
        if rows is None and isinstance(response.get("result"), dict):
            rows = response["result"].get("rows")
        return rows if isinstance(rows, list) else None

    @staticmethod
    def _finance_identity_batch_bytes(batch):
        try:
            material = [
                {
                    "posting_number": row.posting_number,
                    "finance_sku": row.finance_sku,
                    "offer_id": row.offer_id,
                    "product_id": row.product_id,
                }
                for row in batch.rows
            ]
            return len(json.dumps(
                material, sort_keys=True, separators=(",", ":"),
                ensure_ascii=False, allow_nan=False,
            ).encode("utf-8"))
        except (AttributeError, TypeError, ValueError, OverflowError):
            return None

    @classmethod
    def _parse_return_page(cls, response, *, scope, return_schema, period_from, period_to):
        if not isinstance(response, dict) or response.get("error") is True:
            return (), False, "FIFO_RETURNS_SOURCE_UNAVAILABLE"
        containers = [response]
        result = response.get("result")
        if isinstance(result, dict):
            containers.append(result)
        page = None
        has_next = None
        for container in containers:
            for key in ("returns", "items"):
                if key in container:
                    if page is not None or not isinstance(container[key], list):
                        return (), False, "FIFO_RETURNS_PAGE_FORMAT_INVALID"
                    page = container[key]
            if "has_next" in container:
                if has_next is not None or type(container["has_next"]) is not bool:
                    return (), False, "FIFO_RETURNS_PAGINATION_FLAG_INVALID"
                has_next = container["has_next"]
        if page is None:
            return (), False, "FIFO_RETURNS_PAGE_FORMAT_INVALID"
        if len(page) > PeriodProfitReturnEvidenceService.PAGE_SIZE:
            return (), False, "FIFO_RETURNS_PAGE_SIZE_EXCEEDED"
        if has_next is None:
            return (), False, "FIFO_RETURNS_PAGINATION_FLAG_MISSING"

        normalized = []
        for raw in page:
            if not isinstance(raw, dict):
                return (), False, "FIFO_RETURNS_RECORD_INVALID"
            record = PeriodProfitReturnEvidenceService._normalize_record(raw)
            raw_id = record.get("id")
            alt_id = record.get("return_id")
            record_id = cls._identifier(raw_id if raw_id is not None else alt_id)
            if raw_id is not None and alt_id is not None:
                if cls._identifier(raw_id) != cls._identifier(alt_id):
                    return (), False, "FIFO_RETURNS_IDENTITY_CONFLICT"
            posting = cls._text(record.get("posting_number"), 256)
            offer = cls._text(record.get("offer_id"), 256)
            sku = cls._text(str(record.get("sku")) if record.get("sku") is not None else None, 64)
            quantity = record.get("quantity")
            return_type = cls._text(record.get("type"), 64)
            status = cls._text(record.get("visual_status_sys_name"), 64)
            moment = record.get("visual_status_change_moment")
            if offer != scope.offer_id or sku != scope.sku:
                return (), False, "FIFO_RETURNS_IDENTITY_SCOPE_MISMATCH"
            if (
                record_id is None or posting is None or type(quantity) is not int
                or not 1 <= quantity <= FifoCostSourceNormalizer.MAX_UNITS
                or return_type is None or status is None
                or not isinstance(moment, str) or len(moment) > 128
            ):
                return (), False, "FIFO_RETURNS_RECORD_IDENTITY_OR_QUANTITY_INVALID"
            raw_schema = record.get("schema")
            if raw_schema is not None and raw_schema != return_schema:
                return (), False, "FIFO_RETURNS_SCHEMA_MISMATCH"
            try:
                parsed_moment = datetime.fromisoformat(moment.strip().replace("Z", "+00:00"))
            except ValueError:
                return (), False, "FIFO_RETURNS_STATUS_MOMENT_INVALID"
            if parsed_moment.tzinfo is None or parsed_moment.utcoffset() is None:
                return (), False, "FIFO_RETURNS_STATUS_MOMENT_INVALID"
            utc_moment = parsed_moment.astimezone(timezone.utc)
            if not date.fromisoformat(period_from) <= utc_moment.date() <= date.fromisoformat(period_to):
                return (), False, "FIFO_RETURNS_STATUS_MOMENT_OUTSIDE_PERIOD"
            normalized_record = {
                "id": record_id,
                "return_id": record_id,
                "posting_number": posting,
                "offer_id": offer,
                "sku": sku,
                "quantity": quantity,
                "type": return_type,
                "schema": return_schema,
                "visual_status_sys_name": status,
                "visual_status_change_moment": utc_moment.isoformat(
                    timespec="microseconds",
                ).replace("+00:00", "Z"),
                "source": "OZON_RETURNS_API",
            }
            optional_fields = {
                "status": (record.get("status"), 64),
                "visual_status": (record.get("visual_status_sys_name"), 64),
                "return_reason_name": (record.get("return_reason_name"), 256),
                "return_date": (record.get("return_date"), 128),
                "logistic_return_date": (record.get("logistic_return_date"), 128),
                "technical_return_moment": (record.get("technical_return_moment"), 128),
                "return_final_moment": (record.get("return_final_moment"), 128),
                "cancelled_with_compensation_moment": (
                    record.get("cancelled_with_compensation_moment"), 128,
                ),
                "compensation_status_sys_name": (
                    record.get("compensation_status_sys_name"), 64,
                ),
                "compensation_status_change_moment": (
                    record.get("compensation_status_change_moment"), 128,
                ),
            }
            for name, (value, maximum) in optional_fields.items():
                if value is None:
                    continue
                bounded = cls._text(value, maximum)
                if bounded is None:
                    return (), False, "FIFO_RETURNS_OPTIONAL_FIELD_INVALID"
                if name in {"visual_status", "compensation_status_sys_name"} and not re.fullmatch(
                    r"[A-Za-z0-9_]{1,64}", bounded,
                ):
                    return (), False, "FIFO_RETURNS_OPTIONAL_FIELD_INVALID"
                normalized_record[name] = bounded
            normalized.append({"return_id": record_id, "record": normalized_record})
        return tuple(normalized), has_next, None

    def _take_scoped_checkpoint(self, collection, token, *, scope_fingerprint):
        if token is None:
            return None, None
        if not isinstance(token, str) or not re.fullmatch(r"[0-9a-f]{32}", token):
            return None, "FIFO_SOURCE_CONTINUATION_INVALID"
        with self._checkpoint_lock:
            now = self.monotonic_clock()
            for key, value in list(collection.items()):
                if value.expires_at <= now:
                    collection.pop(key, None)
            checkpoint = collection.get(token)
            if checkpoint is None:
                return None, "FIFO_SOURCE_CONTINUATION_STALE"
            if checkpoint.scope_fingerprint != scope_fingerprint:
                return None, "FIFO_SOURCE_CONTINUATION_SCOPE_MISMATCH"
            collection.pop(token, None)
        return checkpoint, None

    def _save_scoped_checkpoint(self, collection, checkpoint):
        size = getattr(checkpoint, "normalized_bytes", None)
        if (
            type(size) is not int or size < 0
            or size > self.MAX_FINANCE_IDENTITY_SNAPSHOT_BYTES
        ):
            return None
        with self._checkpoint_lock:
            now = self.monotonic_clock()
            collections = (self._finance_checkpoints, self._return_checkpoints)
            for scoped_collection in collections:
                for key, value in list(scoped_collection.items()):
                    if value.expires_at <= now:
                        scoped_collection.pop(key, None)
            while (
                sum(len(item) for item in collections)
                >= self.MAX_SCOPED_SOURCE_CHECKPOINTS
                or sum(
                    getattr(value, "normalized_bytes", 0)
                    for scoped_collection in collections
                    for value in scoped_collection.values()
                ) + size > self.MAX_SCOPED_SOURCE_CHECKPOINT_BYTES
            ):
                active = [
                    (value.expires_at, scoped_collection, key)
                    for scoped_collection in collections
                    for key, value in scoped_collection.items()
                ]
                if not active:
                    return None
                _expires_at, oldest_collection, oldest_key = min(active)
                oldest_collection.pop(oldest_key, None)
            token = uuid4().hex
            collection[token] = checkpoint
        return token

    @classmethod
    def _safe_issue_code(cls, error, default):
        candidate = str(error) if error is not None else ""
        return candidate if cls._safe_issue(candidate) else default

    def _new_trace(self, operation, seconds, attempts, parent):
        return PeriodProfitOperationTrace(
            operation=operation,
            time_budget_seconds=min(self.MAX_ELAPSED_SECONDS, seconds),
            ozon_request_budget=attempts,
            parent=parent if parent is not None else current_period_profit_trace(),
        )

    def _result(
        self,
        *,
        status,
        source_status,
        attempts,
        cap,
        started,
        fingerprint=None,
        issues=(),
        stock_snapshot=None,
        supply_snapshot=None,
        continuation=None,
        finance_identity_snapshots=(),
        return_snapshot=None,
    ):
        return FifoSourceCollectionResult(
            status=status,
            source_status=source_status,
            read_only=True,
            actual_http_attempts=max(0, int(attempts)),
            http_attempt_cap=max(0, int(cap)),
            elapsed_seconds=round(max(0.0, self.monotonic_clock() - started), 3),
            source_fingerprint=fingerprint,
            issue_codes=tuple(dict.fromkeys(
                code for code in issues if self._safe_issue(code)
            )),
            stock_snapshot=stock_snapshot,
            supply_snapshot=supply_snapshot,
            continuation_token=continuation,
            finance_identity_snapshots=tuple(finance_identity_snapshots or ()),
            return_snapshot=return_snapshot,
        )

    @classmethod
    def _limits(cls, attempts, seconds, *, default_attempts, maximum_attempts):
        normalized_attempts = cls._bounded_integer(
            attempts, minimum=1, maximum=maximum_attempts,
        )
        if not isinstance(seconds, (int, float)) or isinstance(seconds, bool):
            return normalized_attempts, None
        value = float(seconds)
        if not 0.01 <= value <= cls.MAX_ELAPSED_SECONDS:
            return normalized_attempts, None
        if normalized_attempts is None:
            return None, value
        return min(normalized_attempts, maximum_attempts or default_attempts), value

    @classmethod
    def _identity(cls, value):
        if not isinstance(value, dict):
            return None
        product_id = cls._identifier(value.get("product_id"))
        offer_id = cls._text(value.get("offer_id"), 128)
        sku = cls._identifier(value.get("sku"))
        if product_id is None or sku is None:
            return None
        return product_id, offer_id, sku

    @classmethod
    def _identifier(cls, value):
        if isinstance(value, bool) or value is None:
            return None
        raw = str(value).strip()
        if not cls._ID.fullmatch(raw):
            return None
        parsed = int(raw)
        return str(parsed) if 0 < parsed <= 9_223_372_036_854_775_807 else None

    @staticmethod
    def _bounded_integer(value, *, minimum, maximum):
        if type(value) is not int or not minimum <= value <= maximum:
            return None
        return value

    @staticmethod
    def _text(value, max_length):
        if not isinstance(value, str):
            return None
        normalized = value.strip()
        return normalized if normalized and len(normalized) <= max_length else None

    def _now_utc(self):
        value = self.utc_clock()
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            return None
        return value.astimezone(timezone.utc)

    @classmethod
    def _digest(cls, kind, value):
        return hashlib.sha256(
            f"fifo-source-v1:{kind}:{value}".encode("ascii")
        ).hexdigest()

    @classmethod
    def _fingerprint(cls, value):
        try:
            payload = json.dumps(
                value, sort_keys=True, separators=(",", ":"),
                ensure_ascii=True, allow_nan=False,
            ).encode("utf-8")
        except (TypeError, ValueError, OverflowError):
            return None
        return hashlib.sha256(payload).hexdigest()

    @staticmethod
    def _safe_enum(value):
        if not isinstance(value, str):
            return "UNKNOWN"
        result = value.strip().upper()
        return result if re.fullmatch(r"[A-Z0-9_]{1,48}", result) else "UNKNOWN"

    @classmethod
    def _safe_error_code(cls, response, default):
        if isinstance(response, dict):
            candidate = response.get("code")
            if isinstance(candidate, str) and re.fullmatch(r"[A-Z0-9_.-]{1,64}", candidate):
                return candidate
        return default

    @staticmethod
    def _failed_response(response):
        return not isinstance(response, dict) or response.get("error") is True

    @staticmethod
    def _safe_issue(value):
        return isinstance(value, str) and re.fullmatch(r"[A-Z0-9_.-]{1,64}", value) is not None
