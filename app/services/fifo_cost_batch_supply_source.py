"""Bounded, non-publishing source entry point for automatic FIFO supply scans.

This stage intentionally reads at most one list page. The raw state profile,
terminal-cursor proof, nested supply mapping, and dispatch-date fields remain
unverified, so a successful transport can only produce PARTIAL coverage.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
import threading
from time import monotonic
from uuid import uuid4

from services.fifo_cost_batch_rule_service import FifoCostBatchRuleService
from services.fifo_cost_source_collection_service import FifoCostSourceCollectionService
from services.fifo_cost_source_normalizer import FifoCostSourceNormalizer
from services.fifo_cost_transition_contracts import ScopeIdentity
from services.period_profit_operation_diagnostics import (
    PeriodProfitOperationTrace,
    activate_period_profit_trace,
    current_period_profit_trace,
    reset_period_profit_trace,
)


@dataclass(frozen=True, slots=True)
class FifoCostBatchSupplyCollectionResult:
    status: str
    source_status: str
    read_only: bool
    actual_http_attempts: int
    http_attempt_cap: int
    elapsed_seconds: float
    case_revision: int | None
    rule_revision: int | None
    issue_codes: tuple[str, ...]
    continuation_token: str | None = None
    orders_observed: int = 0
    supplies_observed: int = 0
    pagination_complete: bool = False
    details_complete: bool = False


@dataclass(frozen=True, slots=True)
class _BatchScanCheckpoint:
    scope_fingerprint: str
    cursor: str | None
    seen_cursors: tuple[str, ...]
    seen_order_ids: tuple[str, ...]
    seen_supply_ids: tuple[str, ...]
    pages_scanned: int
    expires_at: float


class FifoCostBatchSupplySourceService:
    """Validate scope and collect bounded order-list/details evidence.

    No source response is returned or persisted. FB12+ owns strict response
    SKU composition, normalization, durable checkpoints, and publication.
    """

    TIME_BUDGET_SECONDS = 20.0
    HTTP_ATTEMPT_BUDGET = 10
    REQUEST_TIMEOUT_SECONDS = 8.0
    PAGE_SIZE = 100
    DETAILS_BATCH_SIZE = 50
    MAX_SCAN_ORDERS = 2_000
    MAX_SCAN_SUPPLIES = 5_000
    MAX_SCAN_PAGES = 100
    CHECKPOINT_TTL_SECONDS = 30 * 60
    MAX_CHECKPOINTS = 64
    REQUEST_ALLOWLIST = {
        "get_supply_orders_list": "SUPPLY_ORDER_LIST_V3",
        "get_supply_orders_details": "SUPPLY_ORDER_DETAILS_V3",
    }
    _ID = re.compile(r"^[0-9]{1,19}$")
    _CURSOR = re.compile(r"^[A-Za-z0-9._:-]{1,256}$")

    def __init__(
        self, *, rule_service: FifoCostBatchRuleService, ozon_client,
        monotonic_clock=monotonic,
    ):
        if not isinstance(rule_service, FifoCostBatchRuleService):
            raise TypeError("FIFO_BATCH_RULE_SERVICE_INVALID")
        self.rule_service = rule_service
        self.ozon_client = ozon_client
        self.monotonic_clock = monotonic_clock
        self._checkpoints: dict[str, _BatchScanCheckpoint] = {}
        self._checkpoint_lock = threading.RLock()

    def collect_supplies(
        self, scope: ScopeIdentity, case_id: str, expected_case_revision: int,
        rule_revision: int, continuation_token=None, operation_trace=None,
    ) -> FifoCostBatchSupplyCollectionResult:
        started = self.monotonic_clock()
        parent = operation_trace or current_period_profit_trace()
        if parent is not None and not isinstance(parent, PeriodProfitOperationTrace):
            return self._result(
                started=started, status="INVALID", source_status="CONFLICT",
                issue_codes=("FIFO_BATCH_OPERATION_TRACE_INVALID",),
                case_revision=None, rule_revision=None,
            )
        trace = PeriodProfitOperationTrace(
            operation="fifo_batch_supply_collection",
            time_budget_seconds=self.TIME_BUDGET_SECONDS,
            ozon_request_budget=self.HTTP_ATTEMPT_BUDGET,
            clock=self.monotonic_clock,
            parent=parent,
        )

        # This tenant-scoped read verifies owner/store/SKU, case revision,
        # AUTO_FROM_SUPPLIES, and active rule revision before any HTTP attempt.
        basis = self.rule_service.read_collection_basis(
            scope, case_id, expected_case_revision, rule_revision,
        )
        if basis.get("error"):
            code = str(basis.get("code") or "")
            conflict_codes = {
                "FIFO_BATCH_CASE_REVISION_CONFLICT",
                "FIFO_BATCH_RULE_REVISION_CONFLICT",
                "FIFO_BATCH_RULE_SCOPE_MISMATCH",
            }
            return self._result(
                started=started,
                status="CONFLICT" if code in conflict_codes else "BLOCKED",
                source_status="CONFLICT" if code in conflict_codes else "UNAVAILABLE",
                issue_codes=(code if code.startswith("FIFO_") else
                             "FIFO_BATCH_COLLECTION_BASIS_UNAVAILABLE",),
                case_revision=(expected_case_revision
                               if type(expected_case_revision) is int else None),
                rule_revision=(rule_revision if type(rule_revision) is int else None),
            )

        scope_fingerprint = self._fingerprint({
            "owner": scope.owner_id,
            "store": scope.store_id,
            "product": scope.product_id,
            "offer": scope.offer_id,
            "sku": scope.sku,
            "case_id": case_id,
            "case_revision": basis["case_revision"],
            "rule_id": basis["rule_id"],
            "rule_revision": basis["rule_revision"],
            "rule_fingerprint": basis["rule_fingerprint"],
            "source_profile": "FIFO_BATCH_ORDER_LIST_V1",
        })
        state, checkpoint_error = self._take_checkpoint(
            continuation_token, scope_fingerprint=scope_fingerprint,
        )
        if checkpoint_error:
            return self._result(
                started=started, status="CONFLICT", source_status="CONFLICT",
                issue_codes=(checkpoint_error,),
                case_revision=basis["case_revision"],
                rule_revision=basis["rule_revision"],
            )
        if state is None:
            state = {
                "cursor": None,
                "seen_cursors": [],
                "seen_order_ids": [],
                "seen_supply_ids": [],
                "pages_scanned": 0,
            }

        trace_token = activate_period_profit_trace(trace)
        actual_attempts = 0
        result_status = "PARTIAL"
        source_status = "PARTIAL"
        issues: list[str] = []
        pagination_complete = False
        details_complete = False
        resumable = False
        stop = False
        try:
            while not stop:
                if state["pages_scanned"] >= self.MAX_SCAN_PAGES:
                    issues.append("FIFO_BATCH_SUPPLY_PAGE_LIMIT_REACHED")
                    break
                if self._remaining_attempts(trace) < 3:
                    issues.append("FIFO_BATCH_SOURCE_BUDGET_EXHAUSTED")
                    resumable = True
                    break
                page, used = self._request(
                    trace, "get_supply_orders_list", actual_attempts,
                    list(FifoCostSourceCollectionService.ACTIVE_SUPPLY_STATES),
                    last_id=state["cursor"], limit=self.PAGE_SIZE,
                    sort_by="ORDER_CREATION", sort_dir="ASC",
                )
                actual_attempts += used
                if self._failed(page):
                    issues.append("FIFO_BATCH_SUPPLY_LIST_UNAVAILABLE")
                    resumable = bool(state["cursor"] is not None)
                    break
                order_ids = self._order_ids(page.get("order_ids"))
                cursor, cursor_valid = self._cursor(page.get("last_id"))
                if order_ids is None:
                    result_status = source_status = "CONFLICT"
                    issues.append("FIFO_BATCH_SUPPLY_LIST_INVALID")
                    break
                if not cursor_valid:
                    result_status = source_status = "CONFLICT"
                    issues.append("FIFO_BATCH_SUPPLY_CURSOR_INVALID")
                    break
                if not order_ids:
                    if cursor is not None:
                        result_status = source_status = "CONFLICT"
                        issues.append("FIFO_BATCH_SUPPLY_CURSOR_WITH_EMPTY_PAGE")
                    else:
                        pagination_complete = True
                        details_complete = True
                    break
                if cursor is not None and cursor in state["seen_cursors"]:
                    result_status = source_status = "CONFLICT"
                    issues.append("FIFO_BATCH_SUPPLY_CURSOR_NOT_ADVANCING")
                    break
                if cursor is None and len(order_ids) == self.PAGE_SIZE:
                    issues.append("FIFO_BATCH_SUPPLY_CURSOR_PROOF_MISSING")
                unique_order_ids = list(dict.fromkeys(order_ids))
                if len(unique_order_ids) != len(order_ids) or any(
                    item in state["seen_order_ids"] for item in unique_order_ids
                ):
                    issues.append("FIFO_BATCH_SUPPLY_LIST_MUTATED_DURING_SCAN")
                    unique_order_ids = [
                        item for item in unique_order_ids
                        if item not in state["seen_order_ids"]
                    ]
                if len(state["seen_order_ids"]) + len(unique_order_ids) > self.MAX_SCAN_ORDERS:
                    issues.append("FIFO_BATCH_SUPPLY_ORDER_LIMIT_REACHED")
                    break

                details, used, detail_issue = self._load_order_details(
                    trace, unique_order_ids, actual_attempts,
                )
                actual_attempts += used
                if detail_issue:
                    issues.append(detail_issue)
                    resumable = bool(state["cursor"] is not None or cursor is not None)
                    break
                supplies, state_issues, structure_issue = self._extract_supply_ids(details)
                issues.extend(state_issues)
                if structure_issue:
                    result_status = source_status = "CONFLICT"
                    issues.append(structure_issue)
                    break
                known_supply_ids = set(state["seen_supply_ids"])
                new_supply_ids = []
                for supply_id in supplies:
                    if supply_id not in known_supply_ids:
                        new_supply_ids.append(supply_id)
                        known_supply_ids.add(supply_id)
                if len(state["seen_supply_ids"]) + len(new_supply_ids) > self.MAX_SCAN_SUPPLIES:
                    issues.append("FIFO_BATCH_SUPPLY_ROW_LIMIT_REACHED")
                    break
                state["seen_order_ids"].extend(unique_order_ids)
                state["seen_supply_ids"].extend(new_supply_ids)
                state["pages_scanned"] += 1
                if cursor is None:
                    if len(order_ids) < self.PAGE_SIZE:
                        pagination_complete = True
                    details_complete = pagination_complete
                    stop = True
                else:
                    state["seen_cursors"].append(cursor)
                    state["cursor"] = cursor
                    if self._remaining_attempts(trace) < 3:
                        issues.append("FIFO_BATCH_SOURCE_BUDGET_EXHAUSTED")
                        resumable = True
                        break
        finally:
            reset_period_profit_trace(trace_token)

        if not result_status == "CONFLICT" and not result_status == "UNAVAILABLE":
            issues.append("FIFO_BATCH_SUPPLY_STATE_PROFILE_UNVERIFIED")
            if (
                actual_attempts == 0
                and not pagination_complete
                and "FIFO_BATCH_SOURCE_BUDGET_EXHAUSTED" not in issues
            ):
                result_status = "UNAVAILABLE"
                source_status = "UNAVAILABLE"
        continuation = None
        if resumable and not pagination_complete:
            continuation = self._save_checkpoint(
                _BatchScanCheckpoint(
                    scope_fingerprint=scope_fingerprint,
                    cursor=state["cursor"],
                    seen_cursors=tuple(state["seen_cursors"]),
                    seen_order_ids=tuple(state["seen_order_ids"]),
                    seen_supply_ids=tuple(state["seen_supply_ids"]),
                    pages_scanned=state["pages_scanned"],
                    expires_at=self.monotonic_clock() + self.CHECKPOINT_TTL_SECONDS,
                )
            )
            if continuation is None:
                issues.append("FIFO_BATCH_SUPPLY_CHECKPOINT_UNAVAILABLE")

        return self._result(
            started=started, status=result_status, source_status=source_status,
            issue_codes=issues, case_revision=basis["case_revision"],
            rule_revision=basis["rule_revision"], actual_attempts=actual_attempts,
            continuation_token=continuation,
            orders_observed=len(state["seen_order_ids"]),
            supplies_observed=len(state["seen_supply_ids"]),
            pagination_complete=pagination_complete,
            details_complete=details_complete,
        )

    def _request(self, trace, method_name, actual_attempts_before, *args, **kwargs):
        if method_name not in self.REQUEST_ALLOWLIST:
            return None, 0
        method = getattr(self.ozon_client, method_name, None)
        remaining = trace.remaining_seconds()
        if not callable(method) or trace.is_budget_exhausted() or remaining <= 0:
            return None, 0
        if actual_attempts_before >= self.HTTP_ATTEMPT_BUDGET:
            return None, 0
        observed = 0

        def observe_attempt(_endpoint=None):
            nonlocal observed
            observed += 1

        timeout = min(self.REQUEST_TIMEOUT_SECONDS, remaining)
        try:
            response = method(
                *args, timeout=timeout, max_attempts=1,
                total_timeout=timeout,
                request_attempt_observer=observe_attempt,
                **kwargs,
            )
        except Exception:
            return None, observed
        return response, observed

    def _load_order_details(self, trace, order_ids, actual_attempts_before):
        orders_by_id = {}
        attempts = 0
        for offset in range(0, len(order_ids), self.DETAILS_BATCH_SIZE):
            if self._remaining_attempts(trace) < 1:
                return None, attempts, "FIFO_BATCH_SOURCE_BUDGET_EXHAUSTED"
            batch = order_ids[offset:offset + self.DETAILS_BATCH_SIZE]
            response, used = self._request(
                trace, "get_supply_orders_details", actual_attempts_before + attempts,
                batch,
            )
            attempts += used
            if self._failed(response):
                return None, attempts, "FIFO_BATCH_SUPPLY_DETAILS_UNAVAILABLE"
            records = response.get("orders")
            if not isinstance(records, list) or len(records) != len(batch):
                return None, attempts, "FIFO_BATCH_SUPPLY_DETAILS_COVERAGE_INVALID"
            expected = set(batch)
            for record in records:
                if not isinstance(record, dict):
                    return None, attempts, "FIFO_BATCH_SUPPLY_ORDER_INVALID"
                order_id = self._identifier(record.get("order_id"))
                if order_id not in expected or order_id in orders_by_id:
                    return None, attempts, "FIFO_BATCH_SUPPLY_DETAILS_IDENTITY_MISMATCH"
                orders_by_id[order_id] = record
        if set(orders_by_id) != set(order_ids):
            return None, attempts, "FIFO_BATCH_SUPPLY_DETAILS_COVERAGE_INVALID"
        return [orders_by_id[order_id] for order_id in order_ids], attempts, None

    def _take_checkpoint(self, token, *, scope_fingerprint):
        if token is None:
            return None, None
        if not isinstance(token, str) or not re.fullmatch(r"[0-9a-f]{32}", token):
            return None, "FIFO_BATCH_SUPPLY_CONTINUATION_INVALID"
        with self._checkpoint_lock:
            now = self.monotonic_clock()
            for key, checkpoint in list(self._checkpoints.items()):
                if checkpoint.expires_at <= now:
                    self._checkpoints.pop(key, None)
            checkpoint = self._checkpoints.get(token)
            if checkpoint is None:
                return None, "FIFO_BATCH_SUPPLY_CONTINUATION_STALE"
            if checkpoint.scope_fingerprint != scope_fingerprint:
                return None, "FIFO_BATCH_SUPPLY_CONTINUATION_SCOPE_MISMATCH"
            self._checkpoints.pop(token, None)
        return {
            "cursor": checkpoint.cursor,
            "seen_cursors": list(checkpoint.seen_cursors),
            "seen_order_ids": list(checkpoint.seen_order_ids),
            "seen_supply_ids": list(checkpoint.seen_supply_ids),
            "pages_scanned": checkpoint.pages_scanned,
        }, None

    def _save_checkpoint(self, checkpoint):
        with self._checkpoint_lock:
            now = self.monotonic_clock()
            for key, existing in list(self._checkpoints.items()):
                if existing.expires_at <= now:
                    self._checkpoints.pop(key, None)
            if len(self._checkpoints) >= self.MAX_CHECKPOINTS:
                return None
            token = uuid4().hex
            self._checkpoints[token] = checkpoint
        return token

    @staticmethod
    def _remaining_attempts(trace):
        remaining = trace.ozon_request_budget
        current = trace
        while current is not None:
            remaining = min(
                remaining,
                max(0, current.ozon_request_budget - current.ozon_requests_reserved),
            )
            current = current.parent
        return remaining

    @classmethod
    def _order_ids(cls, value):
        if not isinstance(value, list) or len(value) > cls.PAGE_SIZE:
            return None
        ids = [cls._identifier(item) for item in value]
        return None if any(item is None for item in ids) else ids

    @classmethod
    def _cursor(cls, value):
        if value is None or value == "":
            return None, True
        if isinstance(value, bool):
            return None, False
        cursor = str(value).strip()
        if not cls._CURSOR.fullmatch(cursor):
            return None, False
        return cursor, True

    @classmethod
    def _extract_supply_ids(cls, orders):
        supply_ids = []
        issues = []
        for order in orders:
            state = order.get("state")
            normalized_order_state = (
                state.strip().upper() if isinstance(state, str) else ""
            )
            if (
                not cls._safe_enum(state)
                or normalized_order_state not in
                FifoCostSourceCollectionService.ACTIVE_SUPPLY_STATES
            ):
                issues.append("FIFO_BATCH_SUPPLY_ORDER_STATE_UNSUPPORTED")
            nested = order.get("supplies")
            if not isinstance(nested, list):
                return (), tuple(issues), "FIFO_BATCH_SUPPLY_NESTED_LIST_UNAVAILABLE"
            for supply in nested:
                if not isinstance(supply, dict):
                    return (), tuple(issues), "FIFO_BATCH_SUPPLY_NESTED_RECORD_INVALID"
                supply_id = cls._identifier(supply.get("supply_id"))
                if supply_id is None:
                    return (), tuple(issues), "FIFO_BATCH_SUPPLY_ID_INVALID"
                supply_state = supply.get("state")
                normalized_supply_state = (
                    supply_state.strip().upper()
                    if isinstance(supply_state, str) else ""
                )
                if (
                    not cls._safe_enum(supply_state)
                    or normalized_supply_state not in
                    FifoCostSourceNormalizer._ACTIVE_SUPPLY_STATUS_MAP
                ):
                    issues.append("FIFO_BATCH_SUPPLY_STATE_UNSUPPORTED")
                is_crossdock = supply.get("is_crossdock")
                if is_crossdock is not None and type(is_crossdock) is not bool:
                    return (), tuple(issues), "FIFO_BATCH_SUPPLY_CROSSDOCK_FLAG_INVALID"
                supply_ids.append(supply_id)
        return tuple(supply_ids), tuple(dict.fromkeys(issues)), None

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
    def _safe_enum(value):
        return isinstance(value, str) and bool(re.fullmatch(r"[A-Z0-9_]{1,48}", value.strip()))

    @staticmethod
    def _failed(response):
        return not isinstance(response, dict) or response.get("error") is True

    @staticmethod
    def _fingerprint(value):
        payload = json.dumps(
            value, ensure_ascii=True, sort_keys=True,
            separators=(",", ":"), allow_nan=False,
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def _result(
        self, *, started, status, source_status, issue_codes, case_revision,
        rule_revision, actual_attempts=0, continuation_token=None,
        orders_observed=0, supplies_observed=0, pagination_complete=False,
        details_complete=False,
    ) -> FifoCostBatchSupplyCollectionResult:
        return FifoCostBatchSupplyCollectionResult(
            status=status,
            source_status=source_status,
            read_only=True,
            actual_http_attempts=max(0, int(actual_attempts)),
            http_attempt_cap=self.HTTP_ATTEMPT_BUDGET,
            elapsed_seconds=round(max(0.0, self.monotonic_clock() - started), 3),
            case_revision=case_revision,
            rule_revision=rule_revision,
            issue_codes=tuple(dict.fromkeys(issue_codes)),
            continuation_token=continuation_token,
            orders_observed=orders_observed,
            supplies_observed=supplies_observed,
            pagination_complete=pagination_complete,
            details_complete=details_complete,
        )
