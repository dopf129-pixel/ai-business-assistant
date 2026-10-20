"""Normalize completed Ozon cross-docking receipts into per-SKU unit facts.

The service is deliberately pure: it consumes already-read Seller API payloads,
does not call the network, does not persist source payloads, and only publishes
an aggregate denominator when every relevant input is complete and unambiguous.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
import hashlib
from typing import Mapping, Sequence
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


@dataclass(frozen=True)
class CrossDockingSupplyUnit:
    """An accepted SKU quantity with no raw order or supply identifier."""

    identity_fingerprint: str
    sku: str
    units: int
    completed_at_utc: datetime
    completed_date: date


@dataclass(frozen=True)
class CrossDockingSupplyEvidence:
    """Fail-closed projection of supply facts for one date window."""

    status: str
    supplies: tuple[CrossDockingSupplyUnit, ...]
    total_units: int | None
    units_by_sku: tuple[tuple[str, int], ...] | None
    issue_codes: tuple[str, ...]
    orders_scanned: int
    crossdock_supplies_seen: int
    excluded_direct_supplies: int
    excluded_outside_window: int

    @property
    def complete(self) -> bool:
        return self.status in {"COMPLETE", "NO_CROSSDOCK_SUPPLIES"}


class CrossDockingSupplyEvidenceService:
    """Convert accepted act item facts into actual cross-docking units."""

    TIMEZONE_NAME = "Europe/Moscow"
    ORDER_COMPLETED = "COMPLETED"
    SUPPLY_COMPLETED = "COMPLETED"
    CROSSDOCK_ACT_TYPE = "ACCEPTANCE"
    CROSSDOCK_ACT_STATE = "ACCEPTED"
    MAX_ID = 9_223_372_036_854_775_807

    def normalize_window(
        self,
        *,
        orders: Sequence[object],
        summaries_by_order_id: Mapping[object, object],
        products_by_supply_id: Mapping[object, object],
        date_from: date,
        date_to: date,
        list_complete: bool = True,
        details_complete: bool = True,
        expected_order_ids: Sequence[object] | None = None,
    ) -> CrossDockingSupplyEvidence:
        """Normalize one fully-read candidate set; incomplete inputs never yield totals."""

        issues: list[str] = []
        issue_set: set[str] = set()

        def add_issue(code: str) -> None:
            if code not in issue_set:
                issues.append(code)
                issue_set.add(code)

        if not isinstance(date_from, date) or isinstance(date_from, datetime):
            add_issue("INVALID_DATE_WINDOW")
        if not isinstance(date_to, date) or isinstance(date_to, datetime):
            add_issue("INVALID_DATE_WINDOW")
        if (
            isinstance(date_from, date)
            and not isinstance(date_from, datetime)
            and isinstance(date_to, date)
            and not isinstance(date_to, datetime)
            and date_from > date_to
        ):
            add_issue("INVALID_DATE_WINDOW")
        if list_complete is not True:
            add_issue("SUPPLY_LIST_INCOMPLETE")
        if details_complete is not True:
            add_issue("SUPPLY_DETAILS_INCOMPLETE")

        if not isinstance(orders, (list, tuple)):
            add_issue("SUPPLY_ORDERS_INVALID")
        if expected_order_ids is not None:
            if not isinstance(expected_order_ids, (list, tuple)):
                add_issue("EXPECTED_ORDER_IDS_INVALID")
            elif any(self._identifier(value) is None for value in expected_order_ids):
                add_issue("EXPECTED_ORDER_ID_INVALID")

        if issues:
            return self._result(
                supplies=(),
                issues=issues,
                orders_scanned=0,
                crossdock_supplies_seen=0,
                excluded_direct_supplies=0,
                excluded_outside_window=0,
            )

        timezone_info = self.resolve_timezone()
        if timezone_info is None:
            return self._result(
                supplies=(),
                issues=["TIMEZONE_DATA_UNAVAILABLE"],
                orders_scanned=0,
                crossdock_supplies_seen=0,
                excluded_direct_supplies=0,
                excluded_outside_window=0,
            )
        issue_candidates: list[tuple[str, str, object, object, datetime]] = []
        excluded_direct = 0
        excluded_outside = 0
        crossdock_seen = 0
        order_snapshots: dict[str, tuple[object, ...]] = {}
        seen_supply_ids: dict[str, CrossDockingSupplyUnit] = {}

        expected_ids = None
        if expected_order_ids is not None:
            expected_ids = {
                normalized
                for value in expected_order_ids
                if (normalized := self._identifier(value)) is not None
            }

        scanned_orders = 0
        for order in orders if isinstance(orders, (list, tuple)) else ():
            scanned_orders += 1
            if not isinstance(order, dict):
                add_issue("INVALID_ORDER_RECORD")
                continue
            order_id = self._identifier(order.get("order_id"))
            if order_id is None:
                add_issue("ORDER_ID_MISSING_OR_INVALID")
                continue

            supplies = order.get("supplies")
            supply_signature = self._supply_signature(supplies)
            signature = (
                order.get("state"),
                order.get("state_updated_date"),
                supply_signature,
            )
            if order_id in order_snapshots:
                if order_snapshots[order_id] != signature:
                    add_issue("CONFLICTING_DUPLICATE_ORDER")
                continue
            order_snapshots[order_id] = signature

            if expected_ids is not None and order_id not in expected_ids:
                add_issue("UNEXPECTED_ORDER_DETAIL")
            if order.get("state") != self.ORDER_COMPLETED:
                # List requests are explicitly filtered to completed orders;
                # non-completed records are never denominator candidates.
                continue
            if not isinstance(supplies, list):
                add_issue("ORDER_SUPPLIES_MISSING")
                continue
            if not supplies:
                add_issue("ORDER_SUPPLIES_EMPTY")
                continue

            crossdock_in_order = [
                supply
                for supply in supplies
                if isinstance(supply, dict) and supply.get("is_crossdock") is True
            ]
            unknown_flag_in_order = any(
                not isinstance(supply, dict)
                or type(supply.get("is_crossdock")) is not bool
                for supply in supplies
            )
            direct_count = sum(
                1
                for supply in supplies
                if isinstance(supply, dict)
                and supply.get("is_crossdock") is False
            )
            excluded_direct += direct_count
            if unknown_flag_in_order:
                add_issue("CROSSDOCK_FLAG_UNKNOWN")

            if not crossdock_in_order:
                continue

            # The UI/API evidence proves the parent completion timestamp only
            # for an order with one nested supply. Avoid assigning one order
            # timestamp to several independently completed supplies.
            if len(supplies) != 1:
                completed_at = self.parse_datetime(order.get("state_updated_date"))
                if completed_at is None:
                    add_issue("COMPLETION_TIMESTAMP_MISSING")
                    continue
                completed_date = completed_at.astimezone(timezone_info).date()
                if completed_date < date_from:
                    # A completed parent order cannot have a child supply
                    # completed after its own completion date. Old orders are
                    # outside the requested window even when per-supply time
                    # is unavailable.
                    excluded_outside += len(crossdock_in_order)
                    continue
                add_issue("MULTI_SUPPLY_COMPLETION_DATE_UNVERIFIED")
                crossdock_seen += len(crossdock_in_order)
                continue

            supply = supplies[0]
            if not isinstance(supply, dict):
                add_issue("INVALID_SUPPLY_RECORD")
                continue
            if supply.get("is_crossdock") is not True:
                continue
            supply_state = supply.get("state")
            if not isinstance(supply_state, str) or not supply_state.strip():
                add_issue("SUPPLY_STATE_MISSING")
                continue
            if supply_state != self.SUPPLY_COMPLETED:
                # This order cannot contribute units until the nested supply
                # state is confirmed complete. Do not infer from parent state.
                add_issue("CROSSDOCK_SUPPLY_NOT_COMPLETED")
                continue

            completed_at = self.parse_datetime(order.get("state_updated_date"))
            if completed_at is None:
                add_issue("COMPLETION_TIMESTAMP_MISSING")
                continue
            completed_date = completed_at.astimezone(timezone_info).date()
            if not date_from <= completed_date <= date_to:
                excluded_outside += 1
                continue

            crossdock_seen += 1
            supply_id = self._identifier(supply.get("supply_id"))
            if supply_id is None:
                add_issue("SUPPLY_ID_MISSING_OR_INVALID")
                continue

            summary = self._mapping_get(summaries_by_order_id, order_id)
            product = self._mapping_get(products_by_supply_id, supply_id)
            evidence = self._accepted_supply_fact(
                order_id=order_id,
                supply_id=supply_id,
                summary_response=summary,
                product_response=product,
                completed_at=completed_at,
                completed_date=completed_date,
            )
            if isinstance(evidence, str):
                add_issue(evidence)
                continue

            previous = seen_supply_ids.get(supply_id)
            if previous is not None:
                if previous != evidence:
                    add_issue("CONFLICTING_DUPLICATE_SUPPLY")
                continue
            seen_supply_ids[supply_id] = evidence

        if expected_ids is not None:
            observed_ids = set(order_snapshots)
            missing_ids = expected_ids - observed_ids
            if missing_ids:
                add_issue("SUPPLY_DETAILS_MISSING_ORDER")

        supplies_sorted = tuple(
            sorted(
                seen_supply_ids.values(),
                key=lambda item: (item.completed_date, item.sku, item.identity_fingerprint),
            )
        )
        return self._result(
            supplies=supplies_sorted,
            issues=issues,
            orders_scanned=scanned_orders,
            crossdock_supplies_seen=crossdock_seen,
            excluded_direct_supplies=excluded_direct,
            excluded_outside_window=excluded_outside,
        )

    def _accepted_supply_fact(
        self,
        *,
        order_id: str,
        supply_id: str,
        summary_response: object,
        product_response: object,
        completed_at: datetime,
        completed_date: date,
    ) -> CrossDockingSupplyUnit | str:
        if not self._successful_response(summary_response):
            return "ACT_SUMMARY_UNAVAILABLE"
        groups = summary_response.get("supplies_acts")
        if not isinstance(groups, list):
            return "ACT_SUMMARY_INVALID"
        matching_groups = [
            group
            for group in groups
            if isinstance(group, dict)
            and self._identifier(group.get("supply_id")) == supply_id
        ]
        if len(matching_groups) != 1:
            return "SUPPLY_ACT_GROUP_MISSING_OR_AMBIGUOUS"
        group = matching_groups[0]
        if group.get("is_agreement_completed") is not True:
            return "SUPPLY_ACCEPTANCE_AGREEMENT_INCOMPLETE"
        acts = group.get("supply_acts")
        if not isinstance(acts, list):
            return "SUPPLY_ACCEPTANCE_ACTS_MISSING"
        accepted_acts = [
            act
            for act in acts
            if isinstance(act, dict)
            and act.get("type") == self.CROSSDOCK_ACT_TYPE
            and act.get("act_state") == self.CROSSDOCK_ACT_STATE
        ]
        if len(accepted_acts) != 1:
            return "ACCEPTED_ACT_MISSING_OR_AMBIGUOUS"
        accepted_act = accepted_acts[0]
        act_id = self._identifier(accepted_act.get("act_id"))
        if act_id is None:
            return "ACCEPTED_ACT_ID_MISSING"
        act_summary = accepted_act.get("summary")
        if not isinstance(act_summary, dict):
            return "ACCEPTED_ACT_SUMMARY_MISSING"
        unidentified = self._quantity(act_summary.get("unidentified_quantity"))
        if unidentified is None:
            return "UNIDENTIFIED_QUANTITY_UNKNOWN"
        if unidentified != 0:
            return "UNIDENTIFIED_QUANTITY_PRESENT"

        if not self._successful_response(product_response):
            return "ACT_PRODUCT_UNAVAILABLE"
        product_acts = product_response.get("supply_acts")
        if not isinstance(product_acts, list):
            return "ACT_PRODUCT_INVALID"
        matching_acts = [
            act
            for act in product_acts
            if isinstance(act, dict)
            and act.get("type") == self.CROSSDOCK_ACT_TYPE
            and self._identifier(act.get("act_id")) == act_id
        ]
        if len(matching_acts) != 1:
            return "ACT_PRODUCT_ID_MISMATCH_OR_AMBIGUOUS"
        items = matching_acts[0].get("items")
        if not isinstance(items, list) or not items:
            return "ACT_PRODUCT_ITEMS_MISSING"

        quantities_by_sku: dict[str, int] = {}
        for item in items:
            if not isinstance(item, dict):
                return "ACT_PRODUCT_ITEM_INVALID"
            sku_info = item.get("sku_info")
            sku = self._sku(sku_info.get("sku") if isinstance(sku_info, dict) else None)
            if sku is None:
                return "SKU_MISSING_OR_INVALID"
            quantity = self._quantity(item.get("fact_quantity"))
            if quantity is None:
                return "FACT_QUANTITY_MISSING_OR_INVALID"
            if "unidentified_quantity" in item:
                item_unidentified = self._quantity(item.get("unidentified_quantity"))
                if item_unidentified is None:
                    return "UNIDENTIFIED_QUANTITY_UNKNOWN"
                if item_unidentified != 0:
                    return "UNIDENTIFIED_QUANTITY_PRESENT"
            quantities_by_sku[sku] = quantities_by_sku.get(sku, 0) + quantity

        if len(quantities_by_sku) != 1:
            return "SUPPLY_PRODUCT_IDENTITY_AMBIGUOUS"

        summary_quantity = self._quantity(act_summary.get("fact_quantity"))
        line_quantity = sum(quantities_by_sku.values())
        if summary_quantity is None:
            return "ACT_SUMMARY_FACT_QUANTITY_UNKNOWN"
        if summary_quantity != line_quantity:
            return "ACT_SUMMARY_PRODUCT_QUANTITY_MISMATCH"

        sku, units = next(iter(quantities_by_sku.items()))
        fingerprint = hashlib.sha256(
            f"{order_id}:{supply_id}".encode("ascii")
        ).hexdigest()
        return CrossDockingSupplyUnit(
            identity_fingerprint=fingerprint,
            sku=sku,
            units=units,
            completed_at_utc=completed_at.astimezone(timezone.utc),
            completed_date=completed_date,
        )

    @classmethod
    def _result(
        cls,
        *,
        supplies: tuple[CrossDockingSupplyUnit, ...],
        issues: list[str],
        orders_scanned: int,
        crossdock_supplies_seen: int,
        excluded_direct_supplies: int,
        excluded_outside_window: int,
    ) -> CrossDockingSupplyEvidence:
        complete = not issues
        if not complete:
            status = "INCOMPLETE"
            total_units = None
            units_by_sku = None
        elif not supplies:
            status = "NO_CROSSDOCK_SUPPLIES"
            total_units = 0
            units_by_sku = ()
        else:
            status = "COMPLETE"
            totals: dict[str, int] = {}
            for supply in supplies:
                totals[supply.sku] = totals.get(supply.sku, 0) + supply.units
            total_units = sum(totals.values())
            units_by_sku = tuple(sorted(totals.items()))
        return CrossDockingSupplyEvidence(
            status=status,
            supplies=supplies,
            total_units=total_units,
            units_by_sku=units_by_sku,
            issue_codes=tuple(issues),
            orders_scanned=orders_scanned,
            crossdock_supplies_seen=crossdock_supplies_seen,
            excluded_direct_supplies=excluded_direct_supplies,
            excluded_outside_window=excluded_outside_window,
        )

    @classmethod
    def _identifier(cls, value: object) -> str | None:
        if isinstance(value, bool) or value is None:
            return None
        raw = str(value).strip()
        if not raw.isascii() or not raw.isdigit():
            return None
        try:
            parsed = int(raw)
        except (TypeError, ValueError, OverflowError):
            return None
        if parsed <= 0 or parsed > cls.MAX_ID:
            return None
        return str(parsed)

    @classmethod
    def resolve_timezone(cls):
        try:
            return ZoneInfo(cls.TIMEZONE_NAME)
        except (ZoneInfoNotFoundError, OSError, ValueError):
            return None

    @classmethod
    def _sku(cls, value: object) -> str | None:
        return cls._identifier(value)

    @staticmethod
    def _quantity(value: object) -> int | None:
        if type(value) is not int or value < 0:
            return None
        return value

    @staticmethod
    def parse_datetime(value: object) -> datetime | None:
        if not isinstance(value, str) or not value.strip():
            return None
        raw = value.strip()
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(raw)
        except (TypeError, ValueError, OverflowError):
            return None
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return None
        return parsed.astimezone(timezone.utc)

    @classmethod
    def _mapping_get(cls, mapping: Mapping[object, object], key: str) -> object:
        if not isinstance(mapping, Mapping):
            return None
        if key in mapping:
            return mapping[key]
        for candidate, value in mapping.items():
            if cls._identifier(candidate) == key:
                return value
        return None

    @staticmethod
    def _successful_response(response: object) -> bool:
        return isinstance(response, dict) and response.get("error") is not True

    @classmethod
    def _supply_signature(cls, supplies: object) -> tuple[object, ...] | None:
        if not isinstance(supplies, list):
            return None
        return tuple(
            (
                cls._identifier(supply.get("supply_id")),
                supply.get("state"),
                supply.get("is_crossdock"),
            )
            if isinstance(supply, dict)
            else None
            for supply in supplies
        )
