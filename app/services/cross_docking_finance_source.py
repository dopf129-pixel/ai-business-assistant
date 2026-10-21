"""Bounded resumable daily finance pages for the cross-docking window."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import date, datetime, timedelta
import json
import time
from typing import Callable, Mapping


@dataclass(frozen=True)
class CrossDockingFinanceCheckpoint:
    """Ephemeral continuation state; raw finance rows stay process-local."""

    date_from: str
    date_to: str
    current_day: str
    last_id: str
    seen_cursors: tuple[str, ...]
    current_accruals: tuple[dict, ...]
    daily_responses: tuple[tuple[str, dict], ...]
    terminal_issue: str | None = None


@dataclass(frozen=True)
class CrossDockingFinanceCollection:
    status: str
    daily_responses: tuple[tuple[str, dict], ...]
    days_expected: int
    days_complete: int
    request_count: int
    elapsed_seconds: float
    stopped_reason: str | None
    checkpoint: CrossDockingFinanceCheckpoint | None

    @property
    def complete(self) -> bool:
        return self.status == "COMPLETE"

    def responses_by_day(self) -> dict[str, dict]:
        return {day: deepcopy(response) for day, response in self.daily_responses}


class OzonCrossDockingFinanceSource:
    """Load complete inclusive day responses without resetting progress."""

    MAX_REQUESTS = 64
    MAX_ELAPSED_SECONDS = 60.0
    MAX_REQUEST_TIMEOUT_SECONDS = 8.0
    MAX_REQUEST_TOTAL_TIMEOUT_SECONDS = 10.0
    MAX_CHECKPOINT_BYTES = 8 * 1024 * 1024
    MAX_ACCRUAL_ROWS = 100_000

    def __init__(
        self,
        client,
        *,
        max_requests: int = MAX_REQUESTS,
        deadline_seconds: float = MAX_ELAPSED_SECONDS,
        monotonic: Callable[[], float] = time.monotonic,
    ):
        self._client = client
        self._max_requests = min(self.MAX_REQUESTS, max(0, int(max_requests)))
        self._deadline_seconds = min(
            self.MAX_ELAPSED_SECONDS,
            max(0.0, float(deadline_seconds)),
        )
        self._monotonic = monotonic

    def collect_window(
        self,
        *,
        date_from: date,
        date_to: date,
        cached_responses: Mapping[object, object] | None = None,
        checkpoint: CrossDockingFinanceCheckpoint | None = None,
        max_requests: int | None = None,
        deadline_seconds: float | None = None,
    ) -> CrossDockingFinanceCollection:
        started_at = self._monotonic()
        request_budget = min(
            self._max_requests,
            max(0, int(max_requests)) if max_requests is not None else self._max_requests,
        )
        allowed_seconds = min(
            self._deadline_seconds,
            max(0.0, float(deadline_seconds))
            if deadline_seconds is not None
            else self._deadline_seconds,
        )
        deadline = started_at + allowed_seconds
        stopped_reason = None
        request_count = 0
        attempt_count = 0

        if not self._valid_window(date_from, date_to):
            return self._collection(
                date_from,
                date_to,
                {},
                0,
                request_count,
                started_at,
                "INVALID_DATE_WINDOW",
                None,
            )

        state, state_error = self._state(
            date_from,
            date_to,
            cached_responses or {},
            checkpoint,
        )
        if state_error:
            return self._collection(
                date_from,
                date_to,
                {},
                0,
                request_count,
                started_at,
                state_error,
                None,
            )
        if state["terminal_issue"]:
            return self._collection(
                date_from,
                date_to,
                state["daily_responses"],
                len(state["daily_responses"]),
                request_count,
                started_at,
                state["terminal_issue"],
                self._checkpoint_from_state(date_from, date_to, state),
            )

        def call(day: str):
            nonlocal request_count, attempt_count, stopped_reason
            remaining = deadline - self._monotonic()
            if request_count >= request_budget:
                stopped_reason = "REQUEST_BUDGET_EXHAUSTED"
                return None
            if remaining <= 0:
                stopped_reason = "TIME_BUDGET_EXHAUSTED"
                return None
            method = getattr(self._client, "get_accruals_by_day_page", None)
            if not callable(method):
                stopped_reason = "FINANCE_PAGE_METHOD_UNAVAILABLE"
                return {"error": True, "code": stopped_reason}
            timeout = max(0.1, min(self.MAX_REQUEST_TIMEOUT_SECONDS, remaining))
            total_timeout = max(
                0.1,
                min(self.MAX_REQUEST_TOTAL_TIMEOUT_SECONDS, remaining),
            )
            request_count += 1

            def observe_attempt(_endpoint=None):
                nonlocal attempt_count
                attempt_count += 1

            try:
                return method(
                    day,
                    last_id=state["last_id"],
                    timeout=timeout,
                    max_attempts=1,
                    total_timeout=total_timeout,
                    request_attempt_observer=observe_attempt,
                )
            except Exception:
                stopped_reason = "FINANCE_PAGE_REQUEST_FAILED"
                return {"error": True, "code": stopped_reason}

        while state["current_day"] <= date_to.isoformat():
            day = state["current_day"]
            if day in state["daily_responses"]:
                state["current_accruals"] = []
                state["last_id"] = ""
                state["seen_cursors"] = set()
                state["current_day"] = (
                    date.fromisoformat(day) + timedelta(days=1)
                ).isoformat()
                continue
            page = call(day)
            if page is None:
                break
            if not isinstance(page, dict) or page.get("error") is True:
                stopped_reason = stopped_reason or "FINANCE_DAY_PAGE_UNAVAILABLE"
                break
            accruals = page.get("accruals")
            if not isinstance(accruals, list) or any(
                not isinstance(row, dict) for row in accruals
            ):
                state["terminal_issue"] = "FINANCE_DAY_PAGE_INVALID"
                stopped_reason = state["terminal_issue"]
                break
            state["current_accruals"].extend(deepcopy(accruals))
            if sum(len(rows.get("accruals", [])) for rows in state["daily_responses"].values()) + len(
                state["current_accruals"]
            ) > self.MAX_ACCRUAL_ROWS:
                state["terminal_issue"] = "FINANCE_WINDOW_ROW_LIMIT"
                stopped_reason = state["terminal_issue"]
                break
            next_cursor, valid_cursor = self._cursor(page.get("last_id"))
            if not valid_cursor:
                state["terminal_issue"] = "FINANCE_CURSOR_INVALID"
                stopped_reason = state["terminal_issue"]
                break
            if next_cursor is None:
                state["daily_responses"][day] = {
                    "error": False,
                    "accruals": state["current_accruals"],
                }
                state["current_accruals"] = []
                state["last_id"] = ""
                state["seen_cursors"] = set()
                state["current_day"] = (
                    date.fromisoformat(day) + timedelta(days=1)
                ).isoformat()
                continue
            if next_cursor == state["last_id"] or next_cursor in state["seen_cursors"]:
                state["terminal_issue"] = "FINANCE_CURSOR_NOT_ADVANCING"
                stopped_reason = state["terminal_issue"]
                break
            state["seen_cursors"].add(next_cursor)
            state["last_id"] = next_cursor

        checkpoint_out = None
        if state["current_day"] <= date_to.isoformat() or state["terminal_issue"]:
            checkpoint_out = self._checkpoint_from_state(
                date_from, date_to, state
            )
            if checkpoint_out is None and state["terminal_issue"] is None:
                stopped_reason = stopped_reason or "FINANCE_CHECKPOINT_SIZE_LIMIT"
        return self._collection(
            date_from,
            date_to,
            state["daily_responses"],
            len(state["daily_responses"]),
            attempt_count if attempt_count else request_count,
            started_at,
            stopped_reason or state["terminal_issue"],
            checkpoint_out,
        )

    def _state(self, date_from, date_to, cached_responses, checkpoint):
        daily = {}
        try:
            for raw_day, response in cached_responses.items():
                day = self._day(raw_day)
                if day is None:
                    continue
                if not date_from <= date.fromisoformat(day) <= date_to:
                    continue
                if (
                    isinstance(response, dict)
                    and response.get("error") is not True
                    and isinstance(response.get("accruals"), list)
                    and response.get("last_id") in (None, "")
                    and isinstance(response.get("pages_loaded"), int)
                    and not isinstance(response.get("pages_loaded"), bool)
                    and response.get("pages_loaded") >= 1
                    and all(isinstance(row, dict) for row in response["accruals"])
                ):
                    daily[day] = {
                        "error": False,
                        "accruals": deepcopy(response["accruals"]),
                    }
        except Exception:
            return None, "FINANCE_CACHE_INVALID"

        if checkpoint is None:
            current_day = date_from.isoformat()
            while current_day in daily and current_day <= date_to.isoformat():
                current_day = (date.fromisoformat(current_day) + timedelta(days=1)).isoformat()
            return {
                "current_day": current_day,
                "last_id": "",
                "seen_cursors": set(),
                "current_accruals": [],
                "daily_responses": daily,
                "terminal_issue": None,
            }, None
        if (
            not isinstance(checkpoint, CrossDockingFinanceCheckpoint)
            or checkpoint.date_from != date_from.isoformat()
            or checkpoint.date_to != date_to.isoformat()
        ):
            return None, "FINANCE_CHECKPOINT_SCOPE_MISMATCH"
        try:
            daily.update(
                {
                    day: {"error": False, "accruals": deepcopy(response["accruals"])}
                    for day, response in checkpoint.daily_responses
                }
            )
            return {
                "current_day": checkpoint.current_day,
                "last_id": checkpoint.last_id,
                "seen_cursors": set(checkpoint.seen_cursors),
                "current_accruals": deepcopy(list(checkpoint.current_accruals)),
                "daily_responses": daily,
                "terminal_issue": checkpoint.terminal_issue,
            }, None
        except Exception:
            return None, "FINANCE_CHECKPOINT_INVALID"

    def _checkpoint_from_state(self, date_from, date_to, state):
        checkpoint = CrossDockingFinanceCheckpoint(
            date_from=date_from.isoformat(),
            date_to=date_to.isoformat(),
            current_day=state["current_day"],
            last_id=state["last_id"],
            seen_cursors=tuple(sorted(state["seen_cursors"])),
            current_accruals=tuple(deepcopy(state["current_accruals"])),
            daily_responses=tuple(
                (day, deepcopy(response))
                for day, response in sorted(state["daily_responses"].items())
            ),
            terminal_issue=state["terminal_issue"],
        )
        try:
            encoded = json.dumps(
                {
                    "current_accruals": checkpoint.current_accruals,
                    "daily_responses": checkpoint.daily_responses,
                },
                allow_nan=False,
                separators=(",", ":"),
            ).encode("utf-8")
        except (TypeError, ValueError, OverflowError):
            return None
        return checkpoint if len(encoded) <= self.MAX_CHECKPOINT_BYTES else None

    def _collection(
        self,
        date_from,
        date_to,
        daily_responses,
        days_complete,
        request_count,
        started_at,
        stopped_reason,
        checkpoint,
    ):
        expected = (
            (date_to - date_from).days + 1
            if self._valid_window(date_from, date_to)
            else 0
        )
        return CrossDockingFinanceCollection(
            status="COMPLETE" if expected and days_complete == expected else "INCOMPLETE",
            daily_responses=tuple(
                (day, deepcopy(response))
                for day, response in sorted(daily_responses.items())
            ),
            days_expected=expected,
            days_complete=days_complete,
            request_count=request_count,
            elapsed_seconds=max(0.0, self._monotonic() - started_at),
            stopped_reason=stopped_reason,
            checkpoint=checkpoint,
        )

    @staticmethod
    def _valid_window(date_from, date_to):
        return (
            isinstance(date_from, date)
            and not isinstance(date_from, datetime)
            and isinstance(date_to, date)
            and not isinstance(date_to, datetime)
            and date_from <= date_to
        )

    @staticmethod
    def _day(value):
        if isinstance(value, date) and not isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, str):
            try:
                return date.fromisoformat(value).isoformat()
            except ValueError:
                return None
        return None

    @staticmethod
    def _cursor(value):
        if value in (None, ""):
            return None, True
        if isinstance(value, bool) or not isinstance(value, (str, int)):
            return None, False
        cursor = str(value).strip()
        if not cursor or len(cursor) > 256:
            return None, False
        return cursor, True
