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

    def __init__(self, operation="period_profit"):
        self.operation = str(operation)
        self.started_at = time.monotonic()
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
                "elapsed_seconds": round(time.monotonic() - self.started_at, 3),
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
                "elapsed_seconds": round(time.monotonic() - self.started_at, 3),
                "stage": self.stage,
                "ozon_api_calls": self.ozon_api_calls,
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
