import json
import logging
import sys
import threading
import time
import traceback
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


_CURRENT_TRACE = ContextVar("period_profit_operation_trace", default=None)


class PeriodProfitOperationTrace:
    """Request-local, secret-free observability for long Period Profit work."""

    DEFAULT_TIME_BUDGET_SECONDS = 600
    DEFAULT_OZON_REQUEST_BUDGET = 300
    MAX_EVENTS = 256

    def __init__(
        self,
        operation="period_profit",
        time_budget_seconds=DEFAULT_TIME_BUDGET_SECONDS,
        ozon_request_budget=DEFAULT_OZON_REQUEST_BUDGET,
        clock=None,
        parent=None,
        utc_clock=None,
    ):
        if parent is not None and not isinstance(parent, PeriodProfitOperationTrace):
            raise TypeError("parent must be a PeriodProfitOperationTrace")
        self.clock = clock or (parent.clock if parent is not None else time.monotonic)
        self.operation = str(operation)
        self.started_at = self.clock()
        self.started_at_utc = self._utc_timestamp(
            utc_clock() if callable(utc_clock) else datetime.now(timezone.utc)
        )
        self.operation_id = uuid4().hex
        self.time_budget_seconds = max(0.0, float(time_budget_seconds))
        self.ozon_request_budget = max(0, int(ozon_request_budget))
        self.ozon_requests_reserved = 0
        self.parent = parent
        self._budget_lock = (
            parent._budget_lock if parent is not None else threading.RLock()
        )
        self._one_time_claims = set() if parent is None else None
        self._cancelled = False
        self.worker_thread_id = None
        self.stage = "created"
        self.ozon_api_calls = 0
        self.posting_numbers_processed = 0
        self.rows_attempted = 0
        self.rows_completed = 0
        self.rows_unknown = 0
        self.budget_reason_code = "NONE"
        self.finance_sku = ""
        self.catalog_sku = ""
        self.identity_cache = {}
        self.identity_diagnostics = {}
        self.posting_response_cache = {}
        self.events = []
        self.total_events = 0
        self.dropped_events = 0
        self._lock = threading.Lock()

    def bind_worker(self):
        self.worker_thread_id = threading.get_ident()

    def update(self, stage, **fields):
        safe = {
            key: value for key, value in fields.items()
            if key in {
                "service", "method", "endpoint", "duration_seconds",
                "cache", "finance_sku", "catalog_sku", "posting_number",
                "posting_numbers_processed", "ozon_api_calls", "status",
            }
        }
        with self._lock:
            self.stage = str(stage)
            if "finance_sku" in safe:
                self.finance_sku = str(safe["finance_sku"] or "")
            if "catalog_sku" in safe:
                self.catalog_sku = str(safe["catalog_sku"] or "")
            event = {
                "stage": self.stage,
                "elapsed_seconds": round(self.clock() - self.started_at, 3),
                **safe,
            }
        for trace in self._trace_chain():
            with trace._lock:
                trace.stage = str(stage)
                trace._append_event_locked(event)
        logging.getLogger("period_profit.diagnostics").info(
            "period_profit_stage %s", json.dumps(event, ensure_ascii=False, sort_keys=True)
        )

    def record_ozon_call(self, endpoint, duration_seconds, status):
        for trace in self._trace_chain():
            with trace._lock:
                trace.ozon_api_calls += 1
        with self._lock:
            count = self.ozon_api_calls
        self.update(
            "ozon_api_call",
            endpoint=str(endpoint),
            duration_seconds=round(float(duration_seconds), 3),
            status=str(status),
            ozon_api_calls=count,
        )

    def reserve_ozon_request(self, endpoint):
        """Reserve one bounded outbound request or return a fail-closed budget error."""
        del endpoint  # Endpoint values belong in request diagnostics, never in the budget key.
        chain = []
        current = self
        while current is not None:
            chain.append(current)
            current = current.parent

        with self._budget_lock:
            if any(trace._cancelled for trace in chain):
                self._set_budget_reason("OPERATION_CANCELLED", chain)
                return {
                    "error": True,
                    "code": "OZON_OPERATION_CANCELLED",
                    "remaining_seconds": self.remaining_seconds(),
                }
            remaining = self.remaining_seconds()
            if remaining <= 0:
                self._set_budget_reason("TIME_BUDGET_EXHAUSTED", chain)
                return {
                    "error": True,
                    "code": "OZON_OPERATION_TIME_BUDGET_EXHAUSTED",
                    "remaining_seconds": 0.0,
                }
            if any(
                trace.ozon_requests_reserved >= trace.ozon_request_budget
                for trace in chain
            ):
                self._set_budget_reason("HTTP_ATTEMPT_BUDGET_EXHAUSTED", chain)
                return {
                    "error": True,
                    "code": "OZON_OPERATION_API_CALL_BUDGET_EXHAUSTED",
                    "remaining_seconds": remaining,
                }
            for trace in chain:
                trace.ozon_requests_reserved += 1
            return {
                "error": False,
                "remaining_seconds": remaining,
                "ozon_requests_reserved": self.ozon_requests_reserved,
                "operation_ozon_requests_reserved": chain[-1].ozon_requests_reserved,
            }

    def claim_once(self, scope, key):
        """Claim a small in-memory marker once for this root operation."""
        try:
            marker = (str(scope), key)
            hash(marker)
        except (TypeError, ValueError):
            return False
        root = self
        while root.parent is not None:
            root = root.parent
        with root._budget_lock:
            if marker in root._one_time_claims:
                return False
            root._one_time_claims.add(marker)
            return True

    def remaining_seconds(self):
        remaining = float("inf")
        current = self
        while current is not None:
            elapsed = max(0.0, current.clock() - current.started_at)
            remaining = min(
                remaining,
                max(0.0, current.time_budget_seconds - elapsed),
            )
            current = current.parent
        return remaining

    def cancel(self):
        """Cooperatively stop this operation and descendants before further work."""
        with self._budget_lock:
            self._cancelled = True

    def is_cancelled(self):
        current = self
        with self._budget_lock:
            while current is not None:
                if current._cancelled:
                    return True
                current = current.parent
        return False

    def is_budget_exhausted(self):
        """Return whether this operation cannot safely start more row work."""
        chain = []
        current = self
        while current is not None:
            chain.append(current)
            current = current.parent
        with self._budget_lock:
            if any(trace._cancelled for trace in chain):
                return True
            if self.remaining_seconds() <= 0:
                return True
            return any(
                trace.ozon_requests_reserved >= trace.ozon_request_budget
                for trace in chain
            )

    def record_posting(self, posting_number):
        count = 0
        for trace in self._trace_chain():
            with trace._lock:
                trace.posting_numbers_processed += 1
                trace.rows_attempted += 1
                count = trace.posting_numbers_processed
        self.update(
            "posting_identity_probe",
            posting_number=str(posting_number),
            posting_numbers_processed=count,
        )

    def record_posting_result(self, status):
        normalized = "completed" if status == "completed" else "unknown"
        for trace in self._trace_chain():
            with trace._lock:
                if normalized == "completed":
                    trace.rows_completed += 1
                else:
                    trace.rows_unknown += 1
        self.update("posting_identity_result", status=normalized)

    def public_summary(self):
        """Return bounded aggregate counters only; never include trace event values."""
        root = self
        while root.parent is not None:
            root = root.parent
        with root._budget_lock:
            with root._lock:
                elapsed = max(0.0, root.clock() - root.started_at)
                return {
                    "operation_id": root.operation_id,
                    "operation_type": self._safe_code(root.operation),
                    "started_at_utc": root.started_at_utc,
                    "elapsed_seconds": min(86400, int(elapsed)),
                    "stage_code": self._safe_code(root.stage),
                    "events_total": root.total_events,
                    "events_dropped": root.dropped_events,
                    "http_attempts": root.ozon_requests_reserved,
                    "http_attempt_cap": root.ozon_request_budget,
                    "rows_attempted": root.rows_attempted,
                    "rows_completed": root.rows_completed,
                    "rows_unknown": root.rows_unknown,
                    "budget_reason_code": self._safe_code(
                        root.budget_reason_code, default="NONE"
                    ),
                }

    def _support_export_context(self):
        """Private input for the allowlisted support exporter; never return it directly."""
        root = self
        while root.parent is not None:
            root = root.parent
        summary = root.public_summary()
        with root._lock:
            summary["_identifier_values"] = [
                {"field": "finance_sku", "kind": "SKU", "value": root.finance_sku},
                {"field": "catalog_sku", "kind": "SKU", "value": root.catalog_sku},
            ]
        return summary

    @staticmethod
    def _utc_timestamp(value):
        if not isinstance(value, datetime):
            return "unknown"
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

    @staticmethod
    def _safe_code(value, default="UNKNOWN"):
        import re

        code = str(value or "").strip().upper()
        if not re.fullmatch(r"[A-Z0-9_.-]{1,64}", code):
            return default
        return code

    def _trace_chain(self):
        chain = []
        current = self
        while current is not None:
            chain.append(current)
            current = current.parent
        return chain

    def _append_event_locked(self, event):
        self.total_events += 1
        self.events.append(dict(event))
        if len(self.events) > self.MAX_EVENTS:
            overflow = len(self.events) - self.MAX_EVENTS
            del self.events[:overflow]
            self.dropped_events += overflow

    @staticmethod
    def _set_budget_reason(reason, chain):
        for trace in chain:
            with trace._lock:
                if trace.budget_reason_code == "NONE":
                    trace.budget_reason_code = reason

    def record_identity_stage(self, name, **fields):
        allowed = {
            "finance_sku_count", "candidate_count", "row_count",
            "sample_count", "record_count", "related_item_count",
            "discovery_call_count", "status",
        }
        safe = {
            key: value for key, value in fields.items()
            if key in allowed and isinstance(value, (str, int, float, bool))
        }
        with self._lock:
            self.identity_diagnostics[str(name)] = dict(safe)
        self.update("selected_identity_" + str(name), **safe)

    def dump_worker_stack(self, reason="operation_over_90_seconds", log_path=None):
        frame = sys._current_frames().get(self.worker_thread_id)
        stack = traceback.format_stack(frame) if frame is not None else []
        with self._lock:
            snapshot = {
                "event": "period_profit_long_running_worker",
                "reason": str(reason),
                "operation": self.operation,
                "elapsed_seconds": round(self.clock() - self.started_at, 3),
                "stage": self.stage,
                "ozon_api_calls": self.ozon_api_calls,
                "ozon_requests_reserved": self.ozon_requests_reserved,
                "posting_numbers_processed": self.posting_numbers_processed,
                "finance_sku": self.finance_sku,
                "catalog_sku": self.catalog_sku,
                "worker_thread_id": self.worker_thread_id,
                "recent_events": self.events[-25:],
                "identity_diagnostics": dict(self.identity_diagnostics),
                "worker_stack": stack,
            }
        target = Path(log_path or "logs/period_profit_diagnostics.log")
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(snapshot, ensure_ascii=False, sort_keys=True) + "\n")
        return snapshot


def current_period_profit_trace():
    return _CURRENT_TRACE.get()


def activate_period_profit_trace(trace):
    return _CURRENT_TRACE.set(trace)


def reset_period_profit_trace(token):
    _CURRENT_TRACE.reset(token)
