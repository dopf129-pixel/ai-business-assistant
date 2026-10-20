"""Bounded read-only Seller API collection for cross-docking unit evidence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
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


class OzonCrossDockingSupplySource:
    """Read a bounded window from existing read-only Ozon supply/act methods.

    This source intentionally does not persist payloads or state. A later
    checkpoint layer can resume it; until then, any exhausted budget returns
    evidence with incomplete coverage and no publishable unit total.
    """

    MAX_REQUESTS = 64
    MAX_ELAPSED_SECONDS = 60.0
    LIST_PAGE_SIZE = 100
    DETAILS_BATCH_SIZE = 50
    MAX_REQUEST_TIMEOUT_SECONDS = 8.0
    MAX_REQUEST_TOTAL_TIMEOUT_SECONDS = 10.0

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
    ) -> CrossDockingSupplyCollection:
        """Collect candidate orders and matching accepted act item rows."""

        started_at = self._monotonic()
        deadline = started_at + self._deadline_seconds
        request_count = 0
        actual_attempt_count = 0
        stopped_reason = None
        list_complete = False
        details_complete = True
        all_order_ids: list[str] = []
        all_orders: list[dict] = []
        summary_by_order_id: dict[str, object] = {}
        products_by_supply_id: dict[str, object] = {}
        cursor = None
        seen_cursors: set[str] = set()

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
            return self._collection(evidence, 0, started_at, "INVALID_DATE_WINDOW")

        def call(method_name: str, *args, **kwargs):
            nonlocal request_count, stopped_reason
            remaining = deadline - self._monotonic()
            if request_count >= self._max_requests:
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
            return self._collection(evidence, 0, started_at, None)

        while True:
            page = call(
                "get_supply_orders_list",
                ["COMPLETED"],
                last_id=cursor,
                limit=self.LIST_PAGE_SIZE,
                sort_by="ORDER_STATE_UPDATED_AT",
                sort_dir="DESC",
            )
            if page is None:
                break
            if not self._successful(page):
                list_complete = False
                stopped_reason = stopped_reason or "SUPPLY_LIST_UNAVAILABLE"
                break
            order_ids = page.get("order_ids")
            if not isinstance(order_ids, list):
                list_complete = False
                stopped_reason = "SUPPLY_LIST_INVALID"
                break
            if not order_ids:
                list_complete = True
                break

            valid_ids = [self._identifier(value) for value in order_ids]
            if any(value is None for value in valid_ids):
                list_complete = False
                stopped_reason = "SUPPLY_LIST_ID_INVALID"
                break
            all_order_ids.extend(valid_ids)

            page_orders: list[dict] = []
            for start in range(0, len(valid_ids), self.DETAILS_BATCH_SIZE):
                batch = valid_ids[start : start + self.DETAILS_BATCH_SIZE]
                details = call("get_supply_orders_details", batch)
                if details is None:
                    details_complete = False
                    break
                if not self._successful(details) or not isinstance(
                    details.get("orders"), list
                ):
                    details_complete = False
                    stopped_reason = stopped_reason or "SUPPLY_DETAILS_UNAVAILABLE"
                    continue
                records = [item for item in details["orders"] if isinstance(item, dict)]
                page_orders.extend(records)
                all_orders.extend(records)
            if len(page_orders) < len(valid_ids):
                details_complete = False

            next_cursor, cursor_valid = self._cursor(page.get("last_id"))
            if not cursor_valid:
                list_complete = False
                stopped_reason = "SUPPLY_LIST_CURSOR_INVALID"
                break
            page_is_older_than_window = (
                len(page_orders) == len(valid_ids)
                and bool(page_orders)
                and all(
                    self._order_local_date(order, timezone_info) is not None
                    and self._order_local_date(order, timezone_info) < date_from
                    for order in page_orders
                )
            )
            if page_is_older_than_window:
                # The API documents ORDER_STATE_UPDATED_AT DESC. Once a full
                # cursor page is older than the lower date bound, later pages
                # cannot contribute to this window.
                list_complete = True
                break

            if next_cursor is None:
                if len(valid_ids) < self.LIST_PAGE_SIZE:
                    list_complete = True
                else:
                    list_complete = False
                    stopped_reason = "SUPPLY_LIST_CURSOR_MISSING"
                break
            if next_cursor in seen_cursors or next_cursor == cursor:
                list_complete = False
                stopped_reason = "SUPPLY_LIST_CURSOR_NOT_ADVANCING"
                break
            seen_cursors.add(next_cursor)
            cursor = next_cursor

        if list_complete and details_complete:
            candidate_supplies = self._in_window_single_crossdock_supplies(
                all_orders,
                date_from=date_from,
                date_to=date_to,
                timezone_info=timezone_info,
            )
            for order_id, supply_id in candidate_supplies:
                summary = call("get_supply_act_summary", order_id)
                if summary is None:
                    break
                summary_by_order_id[order_id] = summary
                if not self._successful(summary):
                    continue
                product = call("get_supply_act_products", supply_id)
                if product is None:
                    break
                products_by_supply_id[supply_id] = product

        evidence = self._evidence_service.normalize_window(
            orders=all_orders,
            summaries_by_order_id=summary_by_order_id,
            products_by_supply_id=products_by_supply_id,
            date_from=date_from,
            date_to=date_to,
            list_complete=list_complete,
            details_complete=details_complete,
            expected_order_ids=all_order_ids,
        )
        return self._collection(
            evidence,
            actual_attempt_count,
            started_at,
            stopped_reason,
        )

    def _collection(
        self,
        evidence: CrossDockingSupplyEvidence,
        request_count: int,
        started_at: float,
        stopped_reason: str | None,
    ) -> CrossDockingSupplyCollection:
        return CrossDockingSupplyCollection(
            evidence=evidence,
            request_count=request_count,
            elapsed_seconds=max(0.0, self._monotonic() - started_at),
            stopped_reason=stopped_reason,
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
