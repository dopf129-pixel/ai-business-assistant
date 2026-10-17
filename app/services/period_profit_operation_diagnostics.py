import json
import logging
import sys
import threading
import time
import traceback
from contextvars import ContextVar
from pathlib import Path


_CURRENT_TRACE = ContextVar("period_profit_operation_trace", default=None)


class PeriodProfitOperationTrace:
    """Request-local, secret-free observability for long Period Profit work."""

    DEFAULT_TIME_BUDGET_SECONDS = 600
    DEFAULT_OZON_REQUEST_BUDGET = 300

    def __init__(
        self,
        operation="period_profit",
        time_budget_seconds=DEFAULT_TIME_BUDGET_SECONDS,
        ozon_request_budget=DEFAULT_OZON_REQUEST_BUDGET,
        clock=None,
        parent=None,
    ):
        if parent is not None and not isinstance(parent, PeriodProfitOperationTrace):
            raise TypeError("parent must be a PeriodProfitOperationTrace")
        self.clock = clock or (parent.clock if parent is not None else time.monotonic)
        self.operation = str(operation)
        self.started_at = self.clock()
        self.time_budget_seconds = max(0.0, float(time_budget_seconds))
        self.ozon_request_budget = max(0, int(ozon_request_budget))
        self.ozon_requests_reserved = 0
        self.parent = parent
        self._budget_lock = (
            parent._budget_lock if parent is not None else threading.RLock()
        )
        self._cancelled = False
        self.worker_thread_id = None
        self.stage = "created"
        self.ozon_api_calls = 0
        self.posting_numbers_processed = 0
        self.finance_sku = ""
        self.catalog_sku = ""
        self.identity_cache = {}
        self.identity_diagnostics = {}
        self.posting_response_cache = {}
        self.events = []
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
            self.events.append(event)
        logging.getLogger("period_profit.diagnostics").info(
            "period_profit_stage %s", json.dumps(event, ensure_ascii=False, sort_keys=True)
        )

    def record_ozon_call(self, endpoint, duration_seconds, status):
        with self._lock:
            self.ozon_api_calls += 1
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
                return {
                    "error": True,
                    "code": "OZON_OPERATION_CANCELLED",
                    "remaining_seconds": self.remaining_seconds(),
                }
            remaining = self.remaining_seconds()
            if remaining <= 0:
                return {
                    "error": True,
                    "code": "OZON_OPERATION_TIME_BUDGET_EXHAUSTED",
                    "remaining_seconds": 0.0,
                }
            if any(
                trace.ozon_requests_reserved >= trace.ozon_request_budget
                for trace in chain
            ):
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
        with self._lock:
            self.posting_numbers_processed += 1
            count = self.posting_numbers_processed
        self.update(
            "posting_identity_probe",
            posting_number=str(posting_number),
            posting_numbers_processed=count,
        )

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
