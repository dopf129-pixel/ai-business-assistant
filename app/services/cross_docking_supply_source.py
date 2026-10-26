"""Bounded read-only Seller API collection for cross-docking unit evidence."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import date, datetime
import json
import time
from typing import Callable

from services.cross_docking_supply_evidence_service import (
    CrossDockingSupplyEvidence,
    CrossDockingSupplyEvidenceService,
)


@dataclass(frozen=True)
class CrossDockingSupplyCollection:
    evidence: CrossDockingSupplyEvidence
    request_count: int
    elapsed_seconds: float
    stopped_reason: str | None
    checkpoint: "CrossDockingSupplyCheckpoint | None" = None


@dataclass(frozen=True)
class CrossDockingSupplyCheckpoint:
    """Ephemeral continuation state; never serialize or show it to the seller."""

    date_from: str
    date_to: str
    cursor: str | None
    seen_cursors: tuple[str, ...]
    order_ids: tuple[str, ...]
    orders: tuple[dict, ...]
    list_complete: bool
    pending_order_ids: tuple[str, ...] | None
    pending_next_cursor: str | None
    pending_is_last_page: bool
    pending_details_offset: int
    pending_orders: tuple[dict, ...]
    summaries_by_order_id: tuple[tuple[str, object], ...]
    products_by_supply_id: tuple[tuple[str, object], ...]
    candidates: tuple[tuple[str, str], ...] | None
    candidate_index: int
    terminal_issue: str | None = None


class OzonCrossDockingSupplySource:
    """Read a bounded window from existing read-only Ozon supply/act methods.

    Checkpoints are process-local and date-scoped. An exhausted bounded read
    can resume on the next explicit calculation, but never publishes a
    partial unit denominator.
    """

    MAX_REQUESTS = 64
    MAX_ELAPSED_SECONDS = 60.0
    LIST_PAGE_SIZE = 100
    DETAILS_BATCH_SIZE = 50
    MAX_REQUEST_TIMEOUT_SECONDS = 8.0
    MAX_REQUEST_TOTAL_TIMEOUT_SECONDS = 10.0
    MAX_CHECKPOINT_ORDERS = 5_000
    MAX_CHECKPOINT_BYTES = 8 * 1024 * 1024

    def __init__(
        self,
        client,
        *,
        evidence_service: CrossDockingSupplyEvidenceService | None = None,
        max_requests: int = MAX_REQUESTS,
        deadline_seconds: float = MAX_ELAPSED_SECONDS,
        monotonic: Callable[[], float] = time.monotonic,
    ):
        self._client = client
        self._evidence_service = evidence_service or CrossDockingSupplyEvidenceService()
        self._max_requests = min(self.MAX_REQUESTS, max(1, int(max_requests)))
        self._deadline_seconds = min(
            self.MAX_ELAPSED_SECONDS,
            max(0.01, float(deadline_seconds)),
        )
        self._monotonic = monotonic

    def collect_window(
        self,
        *,
        date_from: date,
        date_to: date,
        checkpoint: CrossDockingSupplyCheckpoint | None = None,
        max_requests: int | None = None,
        deadline_seconds: float | None = None,
    ) -> CrossDockingSupplyCollection:
        """Collect or resume a bounded read of orders and accepted act rows."""

        started_at = self._monotonic()
        effective_deadline = min(
            self._deadline_seconds,
            max(0.01, float(deadline_seconds))
            if deadline_seconds is not None
            else self._deadline_seconds,
        )
        deadline = started_at + effective_deadline
        request_budget = min(
            self._max_requests,
            max(0, int(max_requests)) if max_requests is not None else self._max_requests,
        )
        request_count = 0
        actual_attempt_count = 0
        stopped_reason = None
        details_complete = True

        if (
            not isinstance(date_from, date)
            or isinstance(date_from, datetime)
            or not isinstance(date_to, date)
            or isinstance(date_to, datetime)
            or date_from > date_to
        ):
            evidence = self._evidence_service.normalize_window(
                orders=[],
                summaries_by_order_id={},
                products_by_supply_id={},
                date_from=date_from,
                date_to=date_to,
            )
            return self._collection(
                evidence, 0, started_at, "INVALID_DATE_WINDOW", None
            )

        if checkpoint is not None and (
            not isinstance(checkpoint, CrossDockingSupplyCheckpoint)
            or checkpoint.date_from != date_from.isoformat()
            or checkpoint.date_to != date_to.isoformat()
        ):
            evidence = self._incomplete_evidence(date_from, date_to, "CHECKPOINT_SCOPE_MISMATCH")
            return self._collection(
                evidence, 0, started_at, "CHECKPOINT_SCOPE_MISMATCH", None
            )

        state = self._state_from_checkpoint(checkpoint, date_from, date_to)
        if state["terminal_issue"]:
            evidence = self._incomplete_evidence(
                date_from, date_to, state["terminal_issue"]
            )
            return self._collection(
                evidence, 0, started_at, state["terminal_issue"], checkpoint
            )

        def call(method_name: str, *args, **kwargs):
            nonlocal request_count, stopped_reason
            remaining = deadline - self._monotonic()
            if request_count >= request_budget:
                stopped_reason = "REQUEST_BUDGET_EXHAUSTED"
                return None
            if remaining <= 0:
                stopped_reason = "TIME_BUDGET_EXHAUSTED"
                return None
            method = getattr(self._client, method_name, None)
            if not callable(method):
                stopped_reason = "SOURCE_METHOD_UNAVAILABLE"
                return {"error": True, "code": "SOURCE_METHOD_UNAVAILABLE"}
            timeout = max(0.1, min(self.MAX_REQUEST_TIMEOUT_SECONDS, remaining))
            total_timeout = max(
                0.1,
                min(self.MAX_REQUEST_TOTAL_TIMEOUT_SECONDS, remaining),
            )
            request_count += 1

            def observe_attempt(_endpoint=None):
                nonlocal actual_attempt_count
                actual_attempt_count += 1

            try:
                return method(
                    *args,
                    timeout=timeout,
                    max_attempts=1,
                    total_timeout=total_timeout,
                    request_attempt_observer=observe_attempt,
                    **kwargs,
                )
            except Exception:
                stopped_reason = "SOURCE_REQUEST_FAILED"
                return {"error": True, "code": "SOURCE_REQUEST_FAILED"}

        timezone_info = self._evidence_service.resolve_timezone()
        if timezone_info is None:
            evidence = self._evidence_service.normalize_window(
                orders=[],
                summaries_by_order_id={},
                products_by_supply_id={},
                date_from=date_from,
                date_to=date_to,
            )
            return self._collection(evidence, 0, started_at, None, checkpoint)

        while not state["list_complete"] and not state["terminal_issue"]:
            if state["pending_order_ids"] is None:
                page = call(
                    "get_supply_orders_list",
                    ["COMPLETED"],
                    last_id=state["cursor"],
                    limit=self.LIST_PAGE_SIZE,
                    sort_by="ORDER_STATE_UPDATED_AT",
                    sort_dir="DESC",
                )
                if page is None:
                    break
                if not self._successful(page):
                    stopped_reason = stopped_reason or "SUPPLY_LIST_UNAVAILABLE"
                    break
                order_ids = page.get("order_ids")
                if not isinstance(order_ids, list):
                    state["terminal_issue"] = "SUPPLY_LIST_INVALID"
                    stopped_reason = state["terminal_issue"]
                    break
                if not order_ids:
                    state["list_complete"] = True
                    break
                valid_ids = [self._identifier(value) for value in order_ids]
                if any(value is None for value in valid_ids):
                    state["terminal_issue"] = "SUPPLY_LIST_ID_INVALID"
                    stopped_reason = state["terminal_issue"]
                    break
                next_cursor, cursor_valid = self._cursor(page.get("last_id"))
                page_is_last = next_cursor is None and len(valid_ids) < self.LIST_PAGE_SIZE
                if not cursor_valid:
                    state["terminal_issue"] = "SUPPLY_LIST_CURSOR_INVALID"
                    stopped_reason = state["terminal_issue"]
                    break
                if next_cursor is None and not page_is_last:
                    state["terminal_issue"] = "SUPPLY_LIST_CURSOR_MISSING"
                    stopped_reason = state["terminal_issue"]
                    break
                if next_cursor is not None and (
                    next_cursor == state["cursor"]
                    or next_cursor in state["seen_cursors"]
                ):
                    state["terminal_issue"] = "SUPPLY_LIST_CURSOR_NOT_ADVANCING"
                    stopped_reason = state["terminal_issue"]
                    break
                state["pending_order_ids"] = list(valid_ids)
                state["pending_next_cursor"] = next_cursor
                state["pending_is_last_page"] = page_is_last
                state["pending_details_offset"] = 0
                state["pending_orders"] = []

            pending_ids = state["pending_order_ids"]
            while state["pending_details_offset"] < len(pending_ids):
                start = state["pending_details_offset"]
                batch = pending_ids[start : start + self.DETAILS_BATCH_SIZE]
                details = call("get_supply_orders_details", batch)
                if details is None:
                    break
                if not self._successful(details):
                    stopped_reason = stopped_reason or "SUPPLY_DETAILS_UNAVAILABLE"
                    break
                records = details.get("orders")
                if not isinstance(records, list) or any(
                    not isinstance(item, dict) for item in records
                ):
                    state["terminal_issue"] = "SUPPLY_DETAILS_INVALID"
                    stopped_reason = state["terminal_issue"]
                    break
                if len(records) != len(batch):
                    state["terminal_issue"] = "SUPPLY_DETAILS_COVERAGE_INCOMPLETE"
                    stopped_reason = state["terminal_issue"]
                    break
                state["pending_orders"].extend(deepcopy(records))
                state["pending_details_offset"] += len(batch)
            if state["terminal_issue"] or state["pending_details_offset"] < len(pending_ids):
                break

            state["order_ids"].extend(pending_ids)
            state["orders"].extend(state["pending_orders"])
            page_orders = state["pending_orders"]
            next_cursor = state["pending_next_cursor"]
            page_is_last = state["pending_is_last_page"]
            state["pending_order_ids"] = None
            state["pending_next_cursor"] = None
            state["pending_is_last_page"] = False
            state["pending_details_offset"] = 0
            state["pending_orders"] = []

            page_is_older_than_window = (
                len(page_orders) == len(pending_ids)
                and bool(page_orders)
                and all(
                    self._order_local_date(order, timezone_info) is not None
                    and self._order_local_date(order, timezone_info) < date_from
                    for order in page_orders
                )
            )
            if page_is_older_than_window:
                state["list_complete"] = True
                break
            if page_is_last:
                state["list_complete"] = True
                break
            if next_cursor is None:
                state["terminal_issue"] = "SUPPLY_LIST_CURSOR_MISSING"
                stopped_reason = state["terminal_issue"]
                break
            state["seen_cursors"].add(next_cursor)
            state["cursor"] = next_cursor

        if state["list_complete"] and not state["terminal_issue"]:
            if state["candidates"] is None:
                state["candidates"] = self._in_window_single_crossdock_supplies(
                    state["orders"],
                    date_from=date_from,
                    date_to=date_to,
                    timezone_info=timezone_info,
                )
            while state["candidate_index"] < len(state["candidates"]):
                order_id, supply_id = state["candidates"][state["candidate_index"]]
                summary = state["summaries_by_order_id"].get(order_id)
                if summary is None:
                    summary = call("get_supply_act_summary", order_id)
                    if summary is None:
                        break
                    if not self._successful(summary):
                        stopped_reason = stopped_reason or "SUPPLY_ACT_SUMMARY_UNAVAILABLE"
                        break
                    state["summaries_by_order_id"][order_id] = deepcopy(summary)
                if not isinstance(summary.get("supplies_acts"), list):
                    state["terminal_issue"] = "SUPPLY_ACT_SUMMARY_INVALID"
                    stopped_reason = state["terminal_issue"]
                    break
                product = state["products_by_supply_id"].get(supply_id)
                if product is None:
                    product = call("get_supply_act_products", supply_id)
                    if product is None:
                        break
                    if not self._successful(product):
                        stopped_reason = stopped_reason or "SUPPLY_ACT_PRODUCT_UNAVAILABLE"
                        break
                    state["products_by_supply_id"][supply_id] = deepcopy(product)
                if not isinstance(product.get("supply_acts"), list):
                    state["terminal_issue"] = "SUPPLY_ACT_PRODUCT_INVALID"
                    stopped_reason = state["terminal_issue"]
                    break
                state["candidate_index"] += 1

        evidence = self._evidence_service.normalize_window(
            orders=state["orders"],
            summaries_by_order_id=state["summaries_by_order_id"],
            products_by_supply_id=state["products_by_supply_id"],
            date_from=date_from,
            date_to=date_to,
            list_complete=state["list_complete"] and not state["terminal_issue"],
            details_complete=details_complete and not state["terminal_issue"],
            expected_order_ids=state["order_ids"],
        )
        next_checkpoint = None
        if evidence.complete is not True:
            next_checkpoint = self._checkpoint_from_state(
                date_from, date_to, state
            )
            if next_checkpoint is None and state["terminal_issue"] is None:
                stopped_reason = stopped_reason or "CHECKPOINT_SIZE_LIMIT"
        return self._collection(
            evidence,
            actual_attempt_count,
            started_at,
            stopped_reason or state["terminal_issue"],
            next_checkpoint,
        )

    def _collection(
        self,
        evidence: CrossDockingSupplyEvidence,
        request_count: int,
        started_at: float,
        stopped_reason: str | None,
        checkpoint: CrossDockingSupplyCheckpoint | None,
    ) -> CrossDockingSupplyCollection:
        return CrossDockingSupplyCollection(
            evidence=evidence,
            request_count=request_count,
            elapsed_seconds=max(0.0, self._monotonic() - started_at),
            stopped_reason=stopped_reason,
            checkpoint=checkpoint,
        )

    def _state_from_checkpoint(self, checkpoint, date_from, date_to):
        if checkpoint is None:
            return {
                "cursor": None,
                "seen_cursors": set(),
                "order_ids": [],
                "orders": [],
                "list_complete": False,
                "pending_order_ids": None,
                "pending_next_cursor": None,
                "pending_is_last_page": False,
                "pending_details_offset": 0,
                "pending_orders": [],
                "summaries_by_order_id": {},
                "products_by_supply_id": {},
                "candidates": None,
                "candidate_index": 0,
                "terminal_issue": None,
            }
        try:
            return {
                "cursor": checkpoint.cursor,
                "seen_cursors": set(checkpoint.seen_cursors),
                "order_ids": list(checkpoint.order_ids),
                "orders": deepcopy(list(checkpoint.orders)),
                "list_complete": checkpoint.list_complete,
                "pending_order_ids": (
                    list(checkpoint.pending_order_ids)
                    if checkpoint.pending_order_ids is not None
                    else None
                ),
                "pending_next_cursor": checkpoint.pending_next_cursor,
                "pending_is_last_page": checkpoint.pending_is_last_page,
                "pending_details_offset": checkpoint.pending_details_offset,
                "pending_orders": deepcopy(list(checkpoint.pending_orders)),
                "summaries_by_order_id": dict(checkpoint.summaries_by_order_id),
                "products_by_supply_id": dict(checkpoint.products_by_supply_id),
                "candidates": (
                    list(checkpoint.candidates)
                    if checkpoint.candidates is not None
                    else None
                ),
                "candidate_index": checkpoint.candidate_index,
                "terminal_issue": checkpoint.terminal_issue,
            }
        except (TypeError, ValueError):
            return {
                "cursor": None,
                "seen_cursors": set(),
                "order_ids": [],
                "orders": [],
                "list_complete": False,
                "pending_order_ids": None,
                "pending_next_cursor": None,
                "pending_is_last_page": False,
                "pending_details_offset": 0,
                "pending_orders": [],
                "summaries_by_order_id": {},
                "products_by_supply_id": {},
                "candidates": None,
                "candidate_index": 0,
                "terminal_issue": "CHECKPOINT_INVALID",
            }

    @staticmethod
    def _checkpoint_from_state(date_from, date_to, state):
        checkpoint = CrossDockingSupplyCheckpoint(
            date_from=date_from.isoformat(),
            date_to=date_to.isoformat(),
            cursor=state["cursor"],
            seen_cursors=tuple(sorted(state["seen_cursors"])),
            order_ids=tuple(state["order_ids"]),
            orders=tuple(deepcopy(state["orders"])),
            list_complete=state["list_complete"],
            pending_order_ids=(
                tuple(state["pending_order_ids"])
                if state["pending_order_ids"] is not None
                else None
            ),
            pending_next_cursor=state["pending_next_cursor"],
            pending_is_last_page=state["pending_is_last_page"],
            pending_details_offset=state["pending_details_offset"],
            pending_orders=tuple(deepcopy(state["pending_orders"])),
            summaries_by_order_id=tuple(
                (key, deepcopy(value))
                for key, value in sorted(state["summaries_by_order_id"].items())
            ),
            products_by_supply_id=tuple(
                (key, deepcopy(value))
                for key, value in sorted(state["products_by_supply_id"].items())
            ),
            candidates=(tuple(state["candidates"]) if state["candidates"] is not None else None),
            candidate_index=state["candidate_index"],
            terminal_issue=state["terminal_issue"],
        )
        if len(checkpoint.order_ids) > OzonCrossDockingSupplySource.MAX_CHECKPOINT_ORDERS:
            return None
        try:
            encoded = json.dumps(
                {
                    "orders": checkpoint.orders,
                    "pending_orders": checkpoint.pending_orders,
                    "summaries": checkpoint.summaries_by_order_id,
                    "products": checkpoint.products_by_supply_id,
                },
                allow_nan=False,
                separators=(",", ":"),
            ).encode("utf-8")
        except (TypeError, ValueError, OverflowError):
            return None
        if len(encoded) > OzonCrossDockingSupplySource.MAX_CHECKPOINT_BYTES:
            return None
        return checkpoint

    def _incomplete_evidence(self, date_from, date_to, issue):
        return CrossDockingSupplyEvidence(
            status="INCOMPLETE",
            supplies=(),
            total_units=None,
            units_by_sku=None,
            issue_codes=(issue,),
            orders_scanned=0,
            crossdock_supplies_seen=0,
            excluded_direct_supplies=0,
            excluded_outside_window=0,
        )

    def _in_window_single_crossdock_supplies(
        self,
        orders: list[dict],
        *,
        date_from: date,
        date_to: date,
        timezone_info,
    ) -> list[tuple[str, str]]:
        candidates = []
        seen = set()
        for order in orders:
            if order.get("state") != "COMPLETED":
                continue
            supplies = order.get("supplies")
            if not isinstance(supplies, list) or len(supplies) != 1:
                continue
            supply = supplies[0]
            if (
                not isinstance(supply, dict)
                or supply.get("state") != "COMPLETED"
                or supply.get("is_crossdock") is not True
            ):
                continue
            order_id = self._identifier(order.get("order_id"))
            supply_id = self._identifier(supply.get("supply_id"))
            completed_on = self._order_local_date(order, timezone_info)
            if (
                order_id is None
                or supply_id is None
                or completed_on is None
                or completed_on < date_from
                or completed_on > date_to
                or supply_id in seen
            ):
                continue
            seen.add(supply_id)
            candidates.append((order_id, supply_id))
        return candidates

    @staticmethod
    def _successful(response: object) -> bool:
        return isinstance(response, dict) and response.get("error") is not True

    @staticmethod
    def _identifier(value: object) -> str | None:
        if isinstance(value, bool) or value is None:
            return None
        raw = str(value).strip()
        if not raw.isascii() or not raw.isdigit():
            return None
        try:
            parsed = int(raw)
        except (TypeError, ValueError, OverflowError):
            return None
        if parsed <= 0 or parsed > 9_223_372_036_854_775_807:
            return None
        return str(parsed)

    @staticmethod
    def _cursor(value: object) -> tuple[str | None, bool]:
        if value is None:
            return None, True
        if isinstance(value, bool) or not isinstance(value, (str, int)):
            return None, False
        cursor = str(value).strip()
        if not cursor:
            return None, True
        if len(cursor) > 256:
            return None, False
        return cursor, True

    @classmethod
    def _order_local_date(cls, order: dict, timezone_info) -> date | None:
        completed_at = CrossDockingSupplyEvidenceService.parse_datetime(
            order.get("state_updated_date")
        )
        if completed_at is None:
            return None
        return completed_at.astimezone(timezone_info).date()
