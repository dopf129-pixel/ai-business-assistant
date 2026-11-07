"""Owner-triggered, read-only FIFO inventory and supply source collection."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from functools import wraps
import hashlib
import inspect
import json
import re
import threading
from time import monotonic
from typing import Callable
from uuid import uuid4

from services.fifo_cost_source_normalizer import FifoCostSourceNormalizer
from services.fifo_cost_transition_contracts import (
    SupplyReferenceKind,
    supply_reference_digest,
)
from services.period_profit_operation_diagnostics import (
    PeriodProfitOperationTrace,
    activate_period_profit_trace,
    current_period_profit_trace,
    reset_period_profit_trace,
)


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
            store_id = self._text(values.get("store_id"), 128)
            tenant_scope = self._text(values.get("tenant_scope"), 128)
            resource = action
            if action == "supply":
                supply_id = self._identifier(values.get("supply_id"))
                if supply_id is None:
                    return method(self, *args, **kwargs)
                resource = self._digest("SUPPLY", supply_id)
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
    MAX_PAGE_SIZE = 100
    MAX_DETAILS_BATCH_SIZE = 50
    MAX_REQUEST_TIMEOUT_SECONDS = 8.0
    MAX_REQUEST_TOTAL_TIMEOUT_SECONDS = 10.0
    MAX_ACTIVE_SUPPLY_TIME_BUDGET_SECONDS = 20.0
    CHECKPOINT_TTL_SECONDS = 600.0
    MAX_CHECKPOINTS = 256
    MAX_INFLIGHT_COLLECTIONS = 64
    MAX_SEEN_ROWS = 10_000
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
        self._inflight_keys: set[str] = set()
        self._checkpoint_lock = threading.RLock()

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
