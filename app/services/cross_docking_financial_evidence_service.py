"""Pure financial evidence and weighted unit-rate calculation for cross-docking."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import hashlib
from typing import Mapping

from services.ozon_accrual_fee_classifier import (
    FEE_LABEL_MATCHERS,
    matches_fee_category,
)


CENT = Decimal("0.01")
ZERO = Decimal("0")


@dataclass(frozen=True)
class CrossDockingFinancialEvidence:
    """Validated cross-docking fee totals for one fully-read date window."""

    status: str
    date_from: date
    date_to: date
    days_expected: int
    days_complete: int
    expense_total: Decimal | None
    expense_by_sku: tuple[tuple[str, Decimal], ...] | None
    shared_expense_total: Decimal | None
    has_unattributed_expense: bool
    signed_accrual_total: Decimal | None
    matched_leaf_count: int
    positive_accrual_count: int
    issue_codes: tuple[str, ...]

    @property
    def complete(self) -> bool:
        return self.status == "COMPLETE"


@dataclass(frozen=True)
class CrossDockingUnitRate:
    """Chosen read-only per-unit rate and its calculation provenance."""

    status: str
    amount_per_unit: Decimal | None
    method: str | None
    reason: str | None
    sku: str
    applicable_to_sku: bool
    date_from: date
    date_to: date
    expense_total: Decimal | None
    expense_by_sku: Decimal | None
    shared_expense_total: Decimal | None
    supplied_units_sku: int | None
    supplied_units_store: int | None
    raw_rate: Decimal | None
    rounding_residual: Decimal | None
    days_expected: int
    days_complete: int
    matched_leaf_count: int
    positive_accrual_count: int


class CrossDockingFinancialEvidenceService:
    """Classify leaf charges, reconcile a complete period, then choose its rate.

    The input is the complete raw response for each daily finance page set, not
    the seller payout total. Leaf nodes retain their signed amount and optional
    SKU attribution. Only the existing shared cross-docking label classifier
    can admit a fee to this cost calculation.
    """

    MAX_ACCRUAL_ID = 9_223_372_036_854_775_807
    MAX_MONEY = Decimal("999999999999999999")

    def collect_window(
        self,
        *,
        daily_responses: Mapping[object, object],
        accrual_types: Mapping[object, object],
        date_from: date,
        date_to: date,
    ) -> CrossDockingFinancialEvidence:
        issues: list[str] = []
        issue_set: set[str] = set()

        def add_issue(code: str) -> None:
            if code not in issue_set:
                issues.append(code)
                issue_set.add(code)

        if not self._valid_window(date_from, date_to):
            add_issue("INVALID_DATE_WINDOW")
            safe_from = date_from if isinstance(date_from, date) else date.min
            safe_to = date_to if isinstance(date_to, date) else safe_from
            return self._unavailable(safe_from, safe_to, 0, 0, issues)
        expected_dates = tuple(
            (date_from + timedelta(days=offset)).isoformat()
            for offset in range((date_to - date_from).days + 1)
        )
        if not isinstance(daily_responses, Mapping):
            add_issue("FINANCE_DAILY_RESPONSES_INVALID")
            return self._unavailable(
                date_from, date_to, len(expected_dates), 0, issues
            )
        if not isinstance(accrual_types, Mapping) or not accrual_types:
            add_issue("ACCRUAL_TYPE_DICTIONARY_UNAVAILABLE")

        normalized_types = self._normalize_types(accrual_types)
        if normalized_types is None:
            add_issue("ACCRUAL_TYPE_DICTIONARY_INVALID")
            normalized_types = {}

        present_dates: set[str] = set()
        accrual_rows: dict[tuple[str, str], tuple[object, tuple[dict, ...]]] = {}
        for raw_day, response in daily_responses.items():
            day = self._day_key(raw_day)
            if day is None:
                add_issue("FINANCE_DAY_INVALID")
                continue
            if day not in expected_dates:
                add_issue("FINANCE_DAY_OUTSIDE_WINDOW")
                continue
            present_dates.add(day)
            if not isinstance(response, dict) or response.get("error") is True:
                add_issue("FINANCE_DAY_UNAVAILABLE")
                continue
            accruals = response.get("accruals")
            if not isinstance(accruals, list):
                add_issue("FINANCE_DAY_ACCRUALS_INVALID")
                continue
            for row in accruals:
                if not isinstance(row, dict):
                    add_issue("ACCRUAL_ROW_INVALID")
                    continue
                row_id = self._accrual_identity(row.get("accrual_id"))
                if row_id is None:
                    add_issue("ACCRUAL_ID_MISSING_OR_INVALID")
                    continue
                signature = self._freeze(row)
                identity = (day, row_id)
                previous = accrual_rows.get(identity)
                if previous is not None:
                    if previous[0] != signature:
                        add_issue("CONFLICTING_DUPLICATE_ACCRUAL")
                    # Repeated pagination rows do not add their leaf fees twice.
                    continue
                leaves, extraction_issues = self._fee_leaves(row)
                for code in extraction_issues:
                    add_issue(code)
                accrual_rows[identity] = (signature, tuple(leaves))

        missing_days = set(expected_dates) - present_dates
        if missing_days:
            add_issue("FINANCE_DAYS_INCOMPLETE")

        signed_total = ZERO
        signed_by_sku: dict[str, Decimal] = {}
        signed_shared = ZERO
        unattributed = False
        matched_leaf_count = 0
        positive_accrual_count = 0
        for _, leaves in accrual_rows.values():
            for leaf in leaves:
                type_info = normalized_types.get(leaf["type_id"])
                if type_info is None:
                    add_issue("ACCRUAL_TYPE_UNKNOWN")
                    continue
                labels = [type_info.get("description"), type_info.get("name")]
                labels = [value for value in labels if value]
                if not labels:
                    add_issue("ACCRUAL_TYPE_LABEL_MISSING")
                    continue
                if not matches_fee_category(
                    labels,
                    "cross_docking",
                    FEE_LABEL_MATCHERS["cross_docking"],
                ):
                    continue
                amount = leaf["amount"]
                signed_total += amount
                if abs(signed_total) > self.MAX_MONEY:
                    add_issue("FINANCE_AMOUNT_OVERFLOW")
                    continue
                matched_leaf_count += 1
                if amount > ZERO:
                    positive_accrual_count += 1
                sku = leaf["sku"]
                if sku is None:
                    unattributed = True
                    signed_shared += amount
                else:
                    signed_by_sku[sku] = signed_by_sku.get(sku, ZERO) + amount
                    if abs(signed_by_sku[sku]) > self.MAX_MONEY:
                        add_issue("FINANCE_AMOUNT_OVERFLOW")
                if abs(signed_shared) > self.MAX_MONEY:
                    add_issue("FINANCE_AMOUNT_OVERFLOW")

        if issues:
            return self._unavailable(
                date_from,
                date_to,
                len(expected_dates),
                len(present_dates),
                issues,
                matched_leaf_count=matched_leaf_count,
                positive_accrual_count=positive_accrual_count,
            )
        return CrossDockingFinancialEvidence(
            status="COMPLETE",
            date_from=date_from,
            date_to=date_to,
            days_expected=len(expected_dates),
            days_complete=len(present_dates),
            expense_total=-signed_total,
            expense_by_sku=tuple(
                sorted((sku, -amount) for sku, amount in signed_by_sku.items())
            ),
            shared_expense_total=-signed_shared,
            has_unattributed_expense=unattributed,
            signed_accrual_total=signed_total,
            matched_leaf_count=matched_leaf_count,
            positive_accrual_count=positive_accrual_count,
            issue_codes=(),
        )

    def calculate_rate(
        self,
        *,
        financial: CrossDockingFinancialEvidence,
        supplies,
        sku: object,
    ) -> CrossDockingUnitRate:
        target_sku = self._sku(sku)
        if target_sku is None:
            return self._rate_unavailable(
                financial, "", "SKU_IDENTITY_INVALID", None, None
            )
        units_by_sku = self._supply_units(supplies)
        if units_by_sku is None:
            return self._rate_unavailable(
                financial, target_sku, "SUPPLY_EVIDENCE_INCOMPLETE", None, None
            )
        if not units_by_sku:
            return self._rate_unavailable(
                financial,
                target_sku,
                "NO_CROSSDOCK_SUPPLIES",
                0,
                0,
                status="NO_CROSSDOCK_SUPPLIES",
            )
        sku_units = units_by_sku.get(target_sku, 0)
        store_units = sum(units_by_sku.values())
        if target_sku not in units_by_sku:
            return self._rate_unavailable(
                financial,
                target_sku,
                "SKU_NOT_IN_CROSSDOCK_WINDOW",
                0,
                store_units,
            )
        if not financial.complete or financial.expense_total is None:
            reason = financial.issue_codes[0] if financial.issue_codes else "FINANCE_EVIDENCE_INCOMPLETE"
            return self._rate_unavailable(
                financial, target_sku, reason, sku_units, store_units
            )

        expense_by_sku = dict(financial.expense_by_sku or ()).get(target_sku, ZERO)
        if financial.has_unattributed_expense:
            cost = financial.expense_total
            denominator = store_units
            method = "store_accrual_cost_per_delivered_crossdock_unit"
            status = "STORE_CROSSDOCK_SUPPLY_ESTIMATE"
        else:
            cost = expense_by_sku
            denominator = sku_units
            method = "sku_accrual_cost_per_delivered_crossdock_unit"
            status = "SKU_SUPPLY_PERIOD_AVERAGE"
        if cost < ZERO or financial.expense_total < ZERO:
            return self._rate_unavailable(
                financial,
                target_sku,
                "NET_REFUND_PERIOD",
                sku_units,
                store_units,
                status="UNAVAILABLE",
                expense_by_sku=expense_by_sku,
            )
        if denominator <= 0:
            return self._rate_unavailable(
                financial,
                target_sku,
                "CROSSDOCK_DENOMINATOR_ZERO",
                sku_units,
                store_units,
                expense_by_sku=expense_by_sku,
            )
        try:
            raw_rate = cost / Decimal(denominator)
            amount = raw_rate.quantize(CENT, rounding=ROUND_HALF_UP)
        except (InvalidOperation, ArithmeticError, ValueError):
            return self._rate_unavailable(
                financial,
                target_sku,
                "RATE_ARITHMETIC_OVERFLOW",
                sku_units,
                store_units,
                expense_by_sku=expense_by_sku,
            )
        if not raw_rate.is_finite() or not amount.is_finite():
            return self._rate_unavailable(
                financial,
                target_sku,
                "RATE_ARITHMETIC_OVERFLOW",
                sku_units,
                store_units,
                expense_by_sku=expense_by_sku,
            )
        residual = cost - amount * Decimal(denominator)
        result = self._rate_base(financial, target_sku, sku_units, store_units)
        return CrossDockingUnitRate(
            **result,
            status=("OBSERVED_ZERO" if cost == ZERO else status),
            amount_per_unit=amount,
            method=method,
            reason=None,
            applicable_to_sku=True,
            expense_by_sku=expense_by_sku,
            raw_rate=raw_rate,
            rounding_residual=residual,
        )

    def _fee_leaves(self, accrual: dict) -> tuple[list[dict], list[str]]:
        leaves: list[dict] = []
        issues: list[str] = []

        def add_leaf(node, sku, path):
            if not isinstance(node, dict):
                issues.append("FEE_LEAF_INVALID")
                return
            type_id = self._type_id(node.get("type_id"))
            accrued = node.get("accrued")
            amount = self._amount(accrued.get("amount")) if isinstance(accrued, dict) else None
            if type_id is None:
                issues.append("FEE_TYPE_ID_MISSING_OR_INVALID")
                return
            if amount is None:
                issues.append("FEE_AMOUNT_INVALID")
                return
            leaves.append({"type_id": type_id, "amount": amount, "sku": sku, "path": path})

        posting = accrual.get("posting")
        if posting is not None:
            if not isinstance(posting, dict):
                issues.append("POSTING_NODE_INVALID")
            else:
                products = posting.get("products", [])
                if not isinstance(products, list):
                    issues.append("POSTING_PRODUCTS_INVALID")
                else:
                    for product_index, product in enumerate(products):
                        if not isinstance(product, dict):
                            issues.append("POSTING_PRODUCT_INVALID")
                            continue
                        sku = self._sku(product.get("sku"))
                        delivery = product.get("delivery")
                        if delivery is None:
                            continue
                        if not isinstance(delivery, dict):
                            issues.append("DELIVERY_NODE_INVALID")
                            continue
                        services = delivery.get("services", [])
                        if not isinstance(services, list):
                            issues.append("DELIVERY_SERVICES_INVALID")
                            continue
                        for service_index, service in enumerate(services):
                            add_leaf(
                                service,
                                sku,
                                f"posting.products[{product_index}].delivery.services[{service_index}]",
                            )

        item_fees = accrual.get("item_fees")
        if item_fees is not None:
            if not isinstance(item_fees, dict) or not isinstance(item_fees.get("fees"), list):
                issues.append("ITEM_FEES_INVALID")
            else:
                for group_index, group in enumerate(item_fees["fees"]):
                    if not isinstance(group, dict) or not isinstance(group.get("fees"), list):
                        issues.append("ITEM_FEE_GROUP_INVALID")
                        continue
                    sku = self._sku(group.get("sku"))
                    for fee_index, fee in enumerate(group["fees"]):
                        add_leaf(fee, sku, f"item_fees[{group_index}].fees[{fee_index}]")

        for container_key in ("non_item_fee", "container_fees"):
            if container_key not in accrual:
                continue
            self._walk_fee_nodes(
                accrual[container_key],
                path=container_key,
                add_leaf=add_leaf,
                issues=issues,
            )
        return leaves, issues

    def _walk_fee_nodes(self, node, *, path, add_leaf, issues):
        if isinstance(node, list):
            for index, value in enumerate(node):
                self._walk_fee_nodes(
                    value,
                    path=f"{path}[{index}]",
                    add_leaf=add_leaf,
                    issues=issues,
                )
            return
        if isinstance(node, dict):
            if "type_id" in node or "accrued" in node:
                add_leaf(node, None, path)
                return
            for key, value in node.items():
                if isinstance(value, (dict, list)):
                    self._walk_fee_nodes(
                        value,
                        path=f"{path}.{key}",
                        add_leaf=add_leaf,
                        issues=issues,
                    )

    @classmethod
    def _normalize_types(cls, accrual_types):
        if not isinstance(accrual_types, Mapping):
            return None
        result = {}
        for raw_id, raw_info in accrual_types.items():
            type_id = cls._type_id(raw_id)
            if type_id is None or not isinstance(raw_info, dict):
                return None
            result[type_id] = {
                "name": cls._label(raw_info.get("name")),
                "description": cls._label(raw_info.get("description")),
            }
        return result

    @classmethod
    def _supply_units(cls, supplies):
        if supplies is None or getattr(supplies, "complete", False) is not True:
            return None
        units = getattr(supplies, "units_by_sku", None)
        if not isinstance(units, tuple):
            return None
        result = {}
        for sku, quantity in units:
            normalized_sku = cls._sku(sku)
            if normalized_sku is None or type(quantity) is not int or quantity < 0:
                return None
            if normalized_sku in result:
                return None
            result[normalized_sku] = quantity
        return result

    @classmethod
    def _rate_unavailable(
        cls,
        financial,
        sku,
        reason,
        sku_units,
        store_units,
        *,
        status="UNAVAILABLE",
        expense_by_sku=None,
    ):
        base = cls._rate_base(financial, sku, sku_units, store_units)
        return CrossDockingUnitRate(
            **base,
            status=status,
            amount_per_unit=None,
            method=None,
            reason=reason,
            applicable_to_sku=False,
            expense_by_sku=expense_by_sku,
            raw_rate=None,
            rounding_residual=None,
        )

    @staticmethod
    def _rate_base(financial, sku, sku_units, store_units):
        return {
            "sku": sku,
            "date_from": financial.date_from,
            "date_to": financial.date_to,
            "expense_total": financial.expense_total,
            "shared_expense_total": financial.shared_expense_total,
            "supplied_units_sku": sku_units,
            "supplied_units_store": store_units,
            "days_expected": financial.days_expected,
            "days_complete": financial.days_complete,
            "matched_leaf_count": financial.matched_leaf_count,
            "positive_accrual_count": financial.positive_accrual_count,
        }

    @staticmethod
    def _unavailable(date_from, date_to, expected, complete, issues, **kwargs):
        return CrossDockingFinancialEvidence(
            status="UNAVAILABLE",
            date_from=date_from,
            date_to=date_to,
            days_expected=expected,
            days_complete=complete,
            expense_total=None,
            expense_by_sku=None,
            shared_expense_total=None,
            has_unattributed_expense=False,
            signed_accrual_total=None,
            matched_leaf_count=kwargs.get("matched_leaf_count", 0),
            positive_accrual_count=kwargs.get("positive_accrual_count", 0),
            issue_codes=tuple(issues),
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
    def _day_key(value):
        if isinstance(value, date) and not isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, str):
            try:
                return date.fromisoformat(value).isoformat()
            except ValueError:
                return None
        return None

    @classmethod
    def _accrual_identity(cls, value):
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            return str(value) if 0 <= value <= cls.MAX_ACCRUAL_ID else None
        if isinstance(value, str) and value.strip() and len(value.strip()) <= 128:
            return value.strip()
        return None

    @staticmethod
    def _type_id(value):
        if isinstance(value, bool):
            return None
        try:
            normalized = int(value)
        except (TypeError, ValueError, OverflowError):
            return None
        return normalized if normalized >= 0 else None

    @staticmethod
    def _amount(value):
        if isinstance(value, bool) or value is None:
            return None
        try:
            amount = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError, OverflowError):
            return None
        if (
            not amount.is_finite()
            or abs(amount) > CrossDockingFinancialEvidenceService.MAX_MONEY
            or amount.as_tuple().exponent < -12
        ):
            return None
        return amount

    @staticmethod
    def _sku(value):
        if isinstance(value, bool) or value is None:
            return None
        normalized = str(value).strip()
        return normalized if normalized and len(normalized) <= 128 else None

    @staticmethod
    def _label(value):
        return str(value).strip() if value is not None else ""

    @staticmethod
    def _freeze(value):
        if isinstance(value, dict):
            return tuple(sorted((str(key), CrossDockingFinancialEvidenceService._freeze(item)) for key, item in value.items()))
        if isinstance(value, list):
            return tuple(CrossDockingFinancialEvidenceService._freeze(item) for item in value)
        if isinstance(value, (str, int, float, bool, type(None), Decimal)):
            return value
        return (type(value).__name__, repr(value))
