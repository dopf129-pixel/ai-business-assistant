"""Bounded, non-publishing source entry point for automatic FIFO supply scans.

This stage intentionally reads at most one list page. The raw state profile,
terminal-cursor proof, nested supply mapping, and dispatch-date fields remain
unverified, so a successful transport can only produce PARTIAL coverage.
"""

from __future__ import annotations

from dataclasses import dataclass
from time import monotonic

from services.fifo_cost_batch_rule_service import FifoCostBatchRuleService
from services.fifo_cost_source_collection_service import FifoCostSourceCollectionService
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


class FifoCostBatchSupplySourceService:
    """Validate the collection basis and perform one bounded list request.

    No source response is returned or persisted. FB12+ owns strict response
    normalization, pagination, observations, and durable scan publication.
    """

    TIME_BUDGET_SECONDS = 20.0
    HTTP_ATTEMPT_BUDGET = 10
    REQUEST_TIMEOUT_SECONDS = 8.0
    PAGE_SIZE = 100
    REQUEST_ALLOWLIST = {
        "get_supply_orders_list": "SUPPLY_ORDER_LIST_V3",
    }

    def __init__(
        self, *, rule_service: FifoCostBatchRuleService, ozon_client,
        monotonic_clock=monotonic,
    ):
        if not isinstance(rule_service, FifoCostBatchRuleService):
            raise TypeError("FIFO_BATCH_RULE_SERVICE_INVALID")
        self.rule_service = rule_service
        self.ozon_client = ozon_client
        self.monotonic_clock = monotonic_clock

    def collect_supplies(
        self, scope: ScopeIdentity, case_id: str, expected_case_revision: int,
        rule_revision: int, continuation_token=None, operation_trace=None,
    ) -> FifoCostBatchSupplyCollectionResult:
        started = self.monotonic_clock()
        if continuation_token is not None:
            return self._result(
                started=started, status="INVALID", source_status="CONFLICT",
                issue_codes=("FIFO_BATCH_CONTINUATION_NOT_SUPPORTED",),
                case_revision=None, rule_revision=None,
            )

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

        trace_token = activate_period_profit_trace(trace)
        actual_attempts = 0
        result_status = "PARTIAL"
        source_status = "PARTIAL"
        issues: tuple[str, ...]
        try:
            method_name = "get_supply_orders_list"
            if method_name not in self.REQUEST_ALLOWLIST:
                result_status = "BLOCKED"
                source_status = "UNAVAILABLE"
                issues = ("FIFO_BATCH_SOURCE_REQUEST_NOT_ALLOWLISTED",)
            else:
                method = getattr(self.ozon_client, method_name, None)
                remaining = trace.remaining_seconds()
                if not callable(method):
                    result_status = "BLOCKED"
                    source_status = "UNAVAILABLE"
                    issues = ("FIFO_BATCH_SOURCE_METHOD_UNAVAILABLE",)
                elif trace.is_budget_exhausted() or remaining <= 0:
                    result_status = "PARTIAL"
                    source_status = "PARTIAL"
                    issues = ("FIFO_BATCH_SOURCE_BUDGET_EXHAUSTED",)
                else:
                    def observe_attempt(_endpoint=None):
                        nonlocal actual_attempts
                        actual_attempts += 1

                    timeout = min(self.REQUEST_TIMEOUT_SECONDS, remaining)
                    try:
                        response = method(
                            list(FifoCostSourceCollectionService.ACTIVE_SUPPLY_STATES),
                            last_id=None,
                            limit=self.PAGE_SIZE,
                            sort_by="ORDER_CREATION",
                            sort_dir="ASC",
                            timeout=timeout,
                            max_attempts=1,
                            total_timeout=timeout,
                            request_attempt_observer=observe_attempt,
                        )
                    except Exception:
                        response = None
                    if actual_attempts > self.HTTP_ATTEMPT_BUDGET:
                        result_status = "PARTIAL"
                        source_status = "PARTIAL"
                        issues = ("FIFO_BATCH_SOURCE_HTTP_BUDGET_EXCEEDED",)
                    elif response is None or (
                        isinstance(response, dict) and response.get("error") is True
                    ):
                        result_status = "UNAVAILABLE" if actual_attempts == 0 else "PARTIAL"
                        source_status = "UNAVAILABLE" if actual_attempts == 0 else "PARTIAL"
                        issues = ("FIFO_BATCH_SUPPLY_LIST_UNAVAILABLE",)
                    else:
                        # Do not inspect or expose response data until FB12
                        # establishes the normalized source profile.
                        issues = ("FIFO_BATCH_SUPPLY_STATE_PROFILE_UNVERIFIED",)
        finally:
            reset_period_profit_trace(trace_token)

        return self._result(
            started=started, status=result_status, source_status=source_status,
            issue_codes=issues, case_revision=basis["case_revision"],
            rule_revision=basis["rule_revision"], actual_attempts=actual_attempts,
        )

    def _result(
        self, *, started, status, source_status, issue_codes, case_revision,
        rule_revision, actual_attempts=0,
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
            continuation_token=None,
        )
