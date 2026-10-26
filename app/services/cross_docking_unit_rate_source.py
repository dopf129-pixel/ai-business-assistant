"""Coordinate bounded cross-docking finance and receipt evidence reads."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, is_dataclass
from datetime import date, datetime, timedelta, timezone
import json
from threading import Event, RLock
from time import monotonic
from typing import Callable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from services.cross_docking_finance_source import OzonCrossDockingFinanceSource
from services.cross_docking_financial_evidence_service import (
    CrossDockingFinancialEvidenceService,
)
from services.cross_docking_supply_source import OzonCrossDockingSupplySource


class CrossDockingUnitRateSource:
    """Build one per-store 56-day evidence snapshot and project it by SKU.

    Incomplete reads keep only bounded, process-local continuation state. No
    raw response is persisted or returned. All APIs remain lazy until
    ``get_rate`` is called from an explicit economics calculation.
    """

    WINDOW_DAYS = 56
    TIMEZONE_NAME = "Europe/Moscow"
    MODEL_VERSION = "cross_docking_unit_cost_v1"
    CACHE_TTL_SECONDS = 600
    MAX_CACHE_ENTRIES = 4
    MAX_CACHE_ENTRY_BYTES = 16 * 1024 * 1024
    MAX_CACHE_BYTES = 24 * 1024 * 1024
    MAX_REQUESTS = 64
    MAX_ELAPSED_SECONDS = 60.0
    MAX_REQUEST_TIMEOUT_SECONDS = 8.0
    MAX_REQUEST_TOTAL_TIMEOUT_SECONDS = 10.0

    def __init__(
        self,
        *,
        ozon_client,
        finance_service,
        financial_evidence_service=None,
        max_requests=MAX_REQUESTS,
        deadline_seconds=MAX_ELAPSED_SECONDS,
        clock=None,
        monotonic_clock: Callable[[], float] = monotonic,
        cache_clock: Callable[[], float] = monotonic,
    ):
        self.ozon_client = ozon_client
        self.finance_service = finance_service
        self.financial_evidence_service = (
            financial_evidence_service
            or CrossDockingFinancialEvidenceService()
        )
        self.finance_source = OzonCrossDockingFinanceSource(
            getattr(finance_service, "ozon", ozon_client),
            max_requests=max_requests,
            deadline_seconds=deadline_seconds,
            monotonic=monotonic_clock,
        )
        self.supply_source = OzonCrossDockingSupplySource(
            ozon_client,
            max_requests=max_requests,
            deadline_seconds=deadline_seconds,
            monotonic=monotonic_clock,
        )
        self.max_requests = min(self.MAX_REQUESTS, max(0, int(max_requests)))
        self.deadline_seconds = min(
            self.MAX_ELAPSED_SECONDS,
            max(0.0, float(deadline_seconds)),
        )
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.monotonic_clock = monotonic_clock
        self.cache_clock = cache_clock
        self._cache = {}
        self._cache_order = []
        self._inflight = {}
        self._lock = RLock()

    def get_rate(
        self,
        *,
        sku,
        tenant_scope,
        operation_trace=None,
        force_refresh=False,
    ):
        target_sku = self._identity(sku)
        target_scope = str(tenant_scope or "").strip()
        if target_sku is None or not target_scope:
            return self._unavailable("CROSSDOCK_IDENTITY_REQUIRED")
        if operation_trace is not None and (
            not callable(getattr(operation_trace, "remaining_seconds", None))
            or not hasattr(operation_trace, "ozon_request_budget")
            or not hasattr(operation_trace, "ozon_requests_reserved")
        ):
            return self._unavailable("CROSSDOCK_OPERATION_CONTEXT_INVALID")

        window = self._window()
        if window is None:
            return self._unavailable("CROSSDOCK_TIMEZONE_UNAVAILABLE")
        date_from, date_to = window
        key = (
            target_scope,
            date_from.isoformat(),
            date_to.isoformat(),
            self.MODEL_VERSION,
        )
        reset_requested = bool(force_refresh)

        while True:
            now = self.cache_clock()
            with self._lock:
                entry = self._cache.get(key)
                if entry is not None and self._expired(entry, now):
                    self._remove_locked(key)
                    entry = None
                pending = self._inflight.get(key)
                if pending is not None:
                    leader = False
                else:
                    if reset_requested:
                        claim_once = getattr(operation_trace, "claim_once", None)
                        if callable(claim_once):
                            try:
                                reset_requested = claim_once(
                                    "cross_docking_force_refresh", key,
                                )
                            except Exception:
                                return self._unavailable(
                                    "CROSSDOCK_OPERATION_CONTEXT_INVALID",
                                    date_from=date_from,
                                    date_to=date_to,
                                )
                        if reset_requested:
                            self._remove_locked(key)
                            entry = None
                        reset_requested = False
                    if entry is not None and self._is_complete(entry):
                        self._touch_locked(key)
                        return self._project(
                            entry,
                            target_sku,
                            date_from,
                            date_to,
                        )
                    pending = Event()
                    self._inflight[key] = pending
                    leader = True

            if leader:
                try:
                    return self._advance(
                        key=key,
                        entry=entry,
                        sku=target_sku,
                        date_from=date_from,
                        date_to=date_to,
                        operation_trace=operation_trace,
                    )
                except Exception:
                    return self._unavailable(
                        "CROSSDOCK_SOURCE_UNAVAILABLE",
                        date_from=date_from,
                        date_to=date_to,
                    )
                finally:
                    with self._lock:
                        current = self._inflight.pop(key, None)
                        if current is not None:
                            current.set()

            wait_seconds = self._wait_seconds(operation_trace)
            if wait_seconds <= 0 or not pending.wait(timeout=min(2.0, wait_seconds)):
                return self._unavailable(
                    "CROSSDOCK_REFRESH_IN_PROGRESS",
                    date_from=date_from,
                    date_to=date_to,
                )

    def _advance(
        self,
        *,
        key,
        entry,
        sku,
        date_from,
        date_to,
        operation_trace,
    ):
        started = self.monotonic_clock()
        if entry is None:
            state = {
                "started_at": self.cache_clock(),
                "finance_checkpoint": None,
                "supply_checkpoint": None,
                "financial_evidence": None,
                "supply_evidence": None,
                "last_reason": None,
            }
        else:
            state = deepcopy(entry)

        used_attempts = 0
        deadline = started + self._remaining_seconds(operation_trace)
        accrual_types = getattr(self.finance_service, "accrual_types", None)
        if state["financial_evidence"] is None and (
            not isinstance(accrual_types, dict) or not accrual_types
        ):
            response, request_attempts, reason = self._load_accrual_types(
                deadline=deadline,
                operation_trace=operation_trace,
                used_attempts=used_attempts,
            )
            used_attempts += request_attempts
            if response is not None:
                accrual_types = response
            else:
                state["last_reason"] = reason

        if (
            state["financial_evidence"] is None
            and isinstance(accrual_types, dict)
            and accrual_types
        ):
            cached_days = self._cached_daily_responses(date_from, date_to)
            remaining_requests = self._remaining_requests(
                operation_trace,
                used_attempts,
            )
            finance_result = self.finance_source.collect_window(
                date_from=date_from,
                date_to=date_to,
                cached_responses=cached_days,
                checkpoint=state["finance_checkpoint"],
                max_requests=remaining_requests,
                deadline_seconds=self._remaining_seconds_for_deadline(deadline),
            )
            used_attempts += finance_result.request_count
            if finance_result.complete:
                state["financial_evidence"] = (
                    self.financial_evidence_service.collect_window(
                        daily_responses=finance_result.responses_by_day(),
                        accrual_types=accrual_types,
                        date_from=date_from,
                        date_to=date_to,
                    )
                )
                state["finance_checkpoint"] = None
                if not state["financial_evidence"].complete:
                    state["financial_evidence"] = None
                    state["last_reason"] = "FINANCE_EVIDENCE_INVALID"
            else:
                state["finance_checkpoint"] = finance_result.checkpoint
                state["last_reason"] = (
                    finance_result.stopped_reason
                    or "FINANCE_WINDOW_INCOMPLETE"
                )

        if state["supply_evidence"] is None:
            remaining_requests = self._remaining_requests(
                operation_trace,
                used_attempts,
            )
            supply_result = self.supply_source.collect_window(
                date_from=date_from,
                date_to=date_to,
                checkpoint=state["supply_checkpoint"],
                max_requests=remaining_requests,
                deadline_seconds=self._remaining_seconds_for_deadline(deadline),
            )
            used_attempts += supply_result.request_count
            if supply_result.evidence.complete:
                state["supply_evidence"] = supply_result.evidence
                state["supply_checkpoint"] = None
            else:
                state["supply_checkpoint"] = supply_result.checkpoint
                state["last_reason"] = (
                    supply_result.stopped_reason
                    or (supply_result.evidence.issue_codes or ("SUPPLY_WINDOW_INCOMPLETE",))[0]
                )

        state["stored_at"] = self.cache_clock()
        with self._lock:
            if not self._store_locked(key, state):
                self._remove_locked(key)
                state = {
                    "started_at": state["started_at"],
                    "stored_at": state["stored_at"],
                    "financial_evidence": None,
                    "supply_evidence": None,
                    "finance_checkpoint": None,
                    "supply_checkpoint": None,
                    "last_reason": "CROSSDOCK_CACHE_SIZE_LIMIT",
                }

        if self._is_complete(state):
            return self._project(state, sku, date_from, date_to)
        return self._unavailable(
            state.get("last_reason") or "CROSSDOCK_WINDOW_INCOMPLETE",
            date_from=date_from,
            date_to=date_to,
            finance_checkpointed=state.get("finance_checkpoint") is not None,
            supply_checkpointed=state.get("supply_checkpoint") is not None,
            http_attempts=used_attempts,
            elapsed_seconds=max(0.0, self.monotonic_clock() - started),
        )

    def _load_accrual_types(self, *, deadline, operation_trace, used_attempts):
        if self._remaining_requests(operation_trace, used_attempts) <= 0:
            return None, 0, "CROSSDOCK_HTTP_BUDGET_EXHAUSTED"
        remaining = self._remaining_seconds_for_deadline(deadline)
        if remaining <= 0:
            return None, 0, "CROSSDOCK_TIME_BUDGET_EXHAUSTED"
        client = getattr(self.finance_service, "ozon", self.ozon_client)
        getter = getattr(client, "get_accrual_types", None)
        if not callable(getter):
            return None, 0, "ACCRUAL_TYPE_DICTIONARY_UNAVAILABLE"
        attempts = 0

        def observe_attempt(_endpoint=None):
            nonlocal attempts
            attempts += 1

        try:
            response = getter(
                timeout=max(0.1, min(self.MAX_REQUEST_TIMEOUT_SECONDS, remaining)),
                max_attempts=1,
                total_timeout=max(
                    0.1,
                    min(self.MAX_REQUEST_TOTAL_TIMEOUT_SECONDS, remaining),
                ),
                request_attempt_observer=observe_attempt,
            )
        except TypeError:
            return None, max(1, attempts), "ACCRUAL_TYPE_DICTIONARY_UNAVAILABLE"
        except Exception:
            return None, max(1, attempts), "ACCRUAL_TYPE_DICTIONARY_UNAVAILABLE"
        if attempts == 0:
            attempts = 1
        if not isinstance(response, dict) or response.get("error") is True:
            return None, attempts, self._safe_code(
                response.get("code") if isinstance(response, dict) else None,
                "ACCRUAL_TYPE_DICTIONARY_UNAVAILABLE",
            )
        rows = response.get("accrual_types")
        if not isinstance(rows, list):
            return None, attempts, "ACCRUAL_TYPE_DICTIONARY_INVALID"
        types = {}
        for row in rows:
            if not isinstance(row, dict):
                return None, attempts, "ACCRUAL_TYPE_DICTIONARY_INVALID"
            type_id = row.get("id")
            if isinstance(type_id, bool):
                return None, attempts, "ACCRUAL_TYPE_DICTIONARY_INVALID"
            try:
                normalized_id = int(type_id)
            except (TypeError, ValueError, OverflowError):
                return None, attempts, "ACCRUAL_TYPE_DICTIONARY_INVALID"
            if normalized_id <= 0:
                return None, attempts, "ACCRUAL_TYPE_DICTIONARY_INVALID"
            types[normalized_id] = {
                "name": row.get("name"),
                "description": row.get("description"),
            }
        if not types:
            return None, attempts, "ACCRUAL_TYPE_DICTIONARY_INVALID"
        self.finance_service.accrual_types = types
        return types, attempts, None

    def _cached_daily_responses(self, date_from, date_to):
        getter = getattr(self.finance_service, "get_cached_daily_accruals", None)
        if not callable(getter):
            return {}
        try:
            result = getter(date_from, date_to)
        except Exception:
            return {}
        return result if isinstance(result, dict) else {}

    def _project(self, entry, sku, date_from, date_to):
        financial = entry.get("financial_evidence")
        supplies = entry.get("supply_evidence")
        if financial is None or supplies is None:
            return self._unavailable(
                entry.get("last_reason") or "CROSSDOCK_WINDOW_INCOMPLETE",
                date_from=date_from,
                date_to=date_to,
            )
        rate = self.financial_evidence_service.calculate_rate(
            financial=financial,
            supplies=supplies,
            sku=sku,
        )
        return {
            "error": False,
            "status": rate.status,
            "cross_docking_per_unit": (
                str(rate.amount_per_unit)
                if rate.amount_per_unit is not None
                else None
            ),
            "method": rate.method,
            "reason": rate.reason,
            "sku": rate.sku,
            "applicable_to_sku": rate.applicable_to_sku,
            "date_from": rate.date_from.isoformat(),
            "date_to": rate.date_to.isoformat(),
            "timezone": self.TIMEZONE_NAME,
            "financial_date_basis": "ACCRUAL_DATE",
            "supply_date_basis": "COMPLETED_SINGLE_CROSSDOCK_ORDER_STATE_UPDATED_DATE",
            "denominator_kind": "DELIVERED_CROSSDOCK_UNITS",
            "supplied_units_sku": rate.supplied_units_sku,
            "supplied_units_store": rate.supplied_units_store,
            "expense_total": self._decimal_string(rate.expense_total),
            "expense_by_sku": self._decimal_string(rate.expense_by_sku),
            "shared_expense_total": self._decimal_string(rate.shared_expense_total),
            "raw_rate": self._decimal_string(rate.raw_rate),
            "rounding_residual": self._decimal_string(rate.rounding_residual),
            "days_expected": rate.days_expected,
            "days_complete": rate.days_complete,
            "matched_leaf_count": rate.matched_leaf_count,
            "positive_accrual_count": rate.positive_accrual_count,
            "supply_status": supplies.status,
            "evidence_complete": True,
            "supply_orders_scanned": supplies.orders_scanned,
            "crossdock_supplies_seen": supplies.crossdock_supplies_seen,
            "as_of": self._now().isoformat(),
            "model_version": self.MODEL_VERSION,
            "read_only": True,
            "executed": False,
        }

    def _window(self):
        try:
            now = self.clock()
            if not isinstance(now, datetime):
                return None
            if now.tzinfo is None:
                now = now.astimezone()
            local_now = now.astimezone(ZoneInfo(self.TIMEZONE_NAME))
            end = local_now.date() - timedelta(days=1)
            return end - timedelta(days=self.WINDOW_DAYS - 1), end
        except (TypeError, ValueError, OverflowError, ZoneInfoNotFoundError):
            return None

    def _remaining_requests(self, operation_trace, used_attempts):
        local_remaining = max(0, self.max_requests - int(used_attempts))
        if operation_trace is None:
            return local_remaining
        try:
            parent_remaining = max(
                0,
                int(operation_trace.ozon_request_budget)
                - int(operation_trace.ozon_requests_reserved),
            )
        except (TypeError, ValueError, OverflowError):
            return 0
        return min(local_remaining, parent_remaining)

    def _remaining_seconds(self, operation_trace):
        remaining = self.deadline_seconds
        if operation_trace is not None:
            try:
                remaining = min(remaining, float(operation_trace.remaining_seconds()))
            except (TypeError, ValueError, OverflowError):
                return 0.0
        return max(0.0, remaining)

    def _remaining_seconds_for_deadline(self, deadline):
        return max(0.0, min(deadline - self.monotonic_clock(), self.deadline_seconds))

    def _wait_seconds(self, operation_trace):
        return self._remaining_seconds(operation_trace)

    def _expired(self, entry, now):
        anchor = entry.get(
            "stored_at"
            if self._is_complete(entry)
            else "started_at"
        )
        try:
            return now - float(anchor) >= self.CACHE_TTL_SECONDS
        except (TypeError, ValueError, OverflowError):
            return True

    @staticmethod
    def _is_complete(entry):
        return (
            isinstance(entry, dict)
            and entry.get("financial_evidence") is not None
            and entry.get("supply_evidence") is not None
        )

    def _store_locked(self, key, entry):
        size = self._entry_size(entry)
        if size > self.MAX_CACHE_ENTRY_BYTES:
            return False
        self._cache[key] = deepcopy(entry)
        self._touch_locked(key)
        while len(self._cache_order) > self.MAX_CACHE_ENTRIES:
            self._remove_locked(self._cache_order[0])
        while self._cache and self._cache_total_size_locked() > self.MAX_CACHE_BYTES:
            self._remove_locked(self._cache_order[0])
        return key in self._cache

    def _entry_size(self, entry):
        try:
            payload = {}
            for key in (
                "finance_checkpoint",
                "supply_checkpoint",
                "financial_evidence",
                "supply_evidence",
            ):
                value = entry.get(key)
                payload[key] = asdict(value) if is_dataclass(value) else value
            return len(
                json.dumps(
                    payload,
                    ensure_ascii=False,
                    allow_nan=False,
                    default=str,
                    separators=(",", ":"),
                ).encode("utf-8")
            )
        except (TypeError, ValueError, OverflowError):
            return self.MAX_CACHE_ENTRY_BYTES + 1

    def _cache_total_size_locked(self):
        return sum(self._entry_size(entry) for entry in self._cache.values())

    def _touch_locked(self, key):
        if key in self._cache_order:
            self._cache_order.remove(key)
        self._cache_order.append(key)

    def _remove_locked(self, key):
        self._cache.pop(key, None)
        try:
            self._cache_order.remove(key)
        except ValueError:
            pass

    def _unavailable(
        self,
        reason,
        *,
        date_from=None,
        date_to=None,
        finance_checkpointed=False,
        supply_checkpointed=False,
        http_attempts=0,
        elapsed_seconds=0.0,
    ):
        return {
            "error": False,
            "status": "UNAVAILABLE",
            "evidence_complete": False,
            "cross_docking_per_unit": None,
            "method": None,
            "reason": self._safe_code(reason, "CROSSDOCK_SOURCE_UNAVAILABLE"),
            "applicable_to_sku": False,
            "date_from": date_from.isoformat() if isinstance(date_from, date) else None,
            "date_to": date_to.isoformat() if isinstance(date_to, date) else None,
            "timezone": self.TIMEZONE_NAME,
            "denominator_kind": "DELIVERED_CROSSDOCK_UNITS",
            "days_expected": self.WINDOW_DAYS,
            "days_complete": 0,
            "finance_checkpointed": bool(finance_checkpointed),
            "supply_checkpointed": bool(supply_checkpointed),
            "http_attempts": max(0, int(http_attempts)),
            "elapsed_seconds": round(max(0.0, float(elapsed_seconds)), 3),
            "model_version": self.MODEL_VERSION,
            "read_only": True,
            "executed": False,
        }

    def _now(self):
        value = self.clock()
        if not isinstance(value, datetime):
            raise ValueError("clock must return datetime")
        if value.tzinfo is None:
            value = value.astimezone()
        return value.astimezone(timezone.utc)

    @staticmethod
    def _identity(value):
        if isinstance(value, bool) or value is None:
            return None
        normalized = str(value).strip()
        return normalized if normalized else None

    @staticmethod
    def _decimal_string(value):
        return str(value) if value is not None else None

    @staticmethod
    def _safe_code(value, default):
        text = str(value or default).strip()
        if not text or len(text) > 80 or not text.replace("_", "").isalnum():
            return default
        return text.upper()
