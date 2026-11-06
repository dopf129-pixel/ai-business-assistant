"""Pure aggregate economics for explicitly planned successful unit sales."""

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import re

from services.fifo_planning_quantity_allocation_service import (
    FifoPlanningQuantityAllocationService,
)


class SalesMixPlanningService:
    MAX_ITEMS = 10
    MAX_QUANTITY_PER_ITEM = 100_000
    MAX_TOTAL_QUANTITY = 1_000_000
    MAX_FIXED_EXPENSES = 20
    MAX_AMOUNT = Decimal("1000000000.00")
    MAX_FIXED_EXPENSE_TOTAL = Decimal("1000000000.00")
    MAX_AGGREGATE_AMOUNT = Decimal("1000000000000.00")
    MONEY_COMPONENTS = (
        "revenue", "cost_of_goods", "discount_points", "commission", "advertising", "fees",
        "profit_before_tax",
    )

    def __init__(self, scenario_service, tax_service=None, fifo_allocator=None):
        self.scenario_service = scenario_service
        self.tax_service = tax_service or getattr(scenario_service, "tax_service", None)
        self.fifo_allocator = fifo_allocator or FifoPlanningQuantityAllocationService()

    def calculate(self, items, *, quantities, period_label, expenses, expenses_confirmed,
                  include_cross_docking=False):
        error = self._validate_scope(items, quantities, period_label, expenses, expenses_confirmed)
        if error:
            return self._error(error)

        quantity_map = quantities
        canonical_rows = []
        excluded = []
        totals = {field: Decimal("0.00") for field in self.MONEY_COMPONENTS}
        after_ad_unknown_components = set()
        pre_ad_profit_before_tax_total = Decimal("0.00")
        pre_ad_revenue_total = Decimal("0.00")
        pre_ad_discount_points_total = Decimal("0.00")
        pre_ad_complete = True
        pre_ad_policy_set = set()
        pre_ad_policy_missing = False
        pre_ad_known_expenses = {}
        pre_ad_included_expense_keys = set()
        pre_ad_confirmed_zero_expense_candidates = set()
        pre_ad_confirmed_zero_expense_intersection = None
        pre_ad_unknown_expense_keys = set()
        pre_ad_excluded_expense_reasons = {}
        additional_expense_total = Decimal("0.00")
        has_extended_expenses = False
        cross_docking_total = Decimal("0.00")
        cross_docking_complete = True
        quantity_known = True
        policy_set = set()
        policy_missing = False
        complete = True

        for index, item in enumerate(items, start=1):
            identity = item.get("identity") or {}
            row_id = str(item.get("row_id") or identity.get("sku") or "")
            quantity = quantity_map.get(row_id)
            label = self._safe_label(identity)
            if quantity is None:
                quantity_known = False
                complete = False
                pre_ad_complete = False
                if include_cross_docking:
                    cross_docking_complete = False
                excluded.append({"row_id": row_id, "label": label, "reason": "QUANTITY_UNKNOWN"})
                continue

            inputs = item.get("inputs") if isinstance(item.get("inputs"), dict) else {}
            extended_scenario = item.get("extended_scenario")
            strict_return_evidence = item.get("strict_return_evidence")
            has_extended_expenses = has_extended_expenses or extended_scenario is not None
            policy = self._tax_policy(inputs)
            if policy is None:
                policy_missing = True
            else:
                policy_set.add(policy)

            if quantity == 0:
                row_components = {field: Decimal("0.00") for field in self.MONEY_COMPONENTS}
                row_components["pre_ad_profit_before_tax"] = Decimal("0.00")
                if extended_scenario is not None:
                    row_components["additional_unit_expenses"] = Decimal("0.00")
                if include_cross_docking:
                    row_components["cross_docking"] = Decimal("0.00")
                unit_price = self._decimal(inputs.get("price"))
                canonical_rows.append(self._row_result(
                    row_id, label, quantity, row_components,
                    unit_price=unit_price.quantize(Decimal("0.01")) if unit_price is not None else None,
                ))
                continue

            projected = self.scenario_service.calculate_components_only(
                inputs,
                extended_scenario=extended_scenario,
                strict_return_evidence=strict_return_evidence,
                identity=identity,
            )
            unit = projected.get("calculated") or {}
            cost_allocation, fifo_cost_delta, fifo_cost_error = self._fifo_quantity_cost(
                item, inputs, quantity, unit,
            )
            if fifo_cost_error is not None:
                complete = False
                pre_ad_complete = False
                if include_cross_docking:
                    cross_docking_complete = False
                excluded.append({
                    "row_id": row_id,
                    "label": label,
                    "reason": "FIFO_QUANTITY_ALLOCATION_INCOMPLETE",
                    "cost_reason": fifo_cost_error,
                })
                continue
            pre_ad_unit_profit = self._decimal(unit.get("pre_ad_profit_before_tax"))
            pre_ad_revenue = self._decimal(unit.get("revenue"))
            pre_ad_discount_points = self._decimal(unit.get("discount_points"))
            ad_fields = set(getattr(
                self.scenario_service, "ADVERTISING_INPUT_FIELDS", (),
            ))
            non_ad_missing = [
                field for field in (projected.get("missing_inputs") or [])
                if field not in ad_fields
            ]
            non_ad_invalid = [
                field for field in (projected.get("invalid_inputs") or [])
                if field not in ad_fields
            ]
            unit_scope = projected.get("pre_ad_expense_scope")
            pre_ad_row_available = (
                not non_ad_missing
                and not non_ad_invalid
                and pre_ad_unit_profit is not None
                and pre_ad_revenue is not None
                and pre_ad_discount_points is not None
                and isinstance(unit_scope, dict)
            )
            if pre_ad_row_available:
                pre_ad_profit_before_tax_total += (
                    (pre_ad_unit_profit * quantity).quantize(Decimal("0.01"))
                    + fifo_cost_delta
                )
                pre_ad_revenue_total += (pre_ad_revenue * quantity).quantize(Decimal("0.01"))
                pre_ad_discount_points_total += (
                    pre_ad_discount_points * quantity
                ).quantize(Decimal("0.01"))
                if abs(pre_ad_profit_before_tax_total) > self.MAX_AGGREGATE_AMOUNT:
                    return self._error("AGGREGATE_AMOUNT_LIMIT_EXCEEDED")
                if abs(pre_ad_revenue_total) > self.MAX_AGGREGATE_AMOUNT:
                    return self._error("AGGREGATE_AMOUNT_LIMIT_EXCEEDED")
                if abs(pre_ad_discount_points_total) > self.MAX_AGGREGATE_AMOUNT:
                    return self._error("AGGREGATE_AMOUNT_LIMIT_EXCEEDED")
                if policy is None:
                    pre_ad_policy_missing = True
                else:
                    pre_ad_policy_set.add(policy)
                scope_known = unit_scope.get("known_non_ad_expenses_rub") or {}
                for key, raw_amount in scope_known.items():
                    amount = self._decimal(raw_amount)
                    if amount is None:
                        pre_ad_complete = False
                        continue
                    pre_ad_known_expenses[key] = pre_ad_known_expenses.get(
                        key, Decimal("0.00"),
                    ) + (amount * quantity).quantize(Decimal("0.01"))
                if fifo_cost_delta and "COGS" in pre_ad_known_expenses:
                    # The unit scenario's COGS is the next-unit reference. Use
                    # the exact layer total for this quantity while retaining
                    # the existing pre-ad rounding adjustment and tax bridge.
                    pre_ad_known_expenses["COGS"] -= fifo_cost_delta
                pre_ad_included_expense_keys.update(
                    unit_scope.get("included_expense_keys") or []
                )
                row_confirmed_zero_keys = set(
                    unit_scope.get("confirmed_zero_expense_keys") or []
                )
                pre_ad_confirmed_zero_expense_candidates.update(
                    row_confirmed_zero_keys
                )
                if pre_ad_confirmed_zero_expense_intersection is None:
                    pre_ad_confirmed_zero_expense_intersection = row_confirmed_zero_keys
                else:
                    pre_ad_confirmed_zero_expense_intersection.intersection_update(
                        row_confirmed_zero_keys
                    )
                pre_ad_unknown_expense_keys.update(
                    unit_scope.get("unknown_non_ad_expense_keys") or []
                )
                pre_ad_excluded_expense_reasons.update(
                    unit_scope.get("excluded_expense_reasons") or {}
                )
            else:
                pre_ad_complete = False
            after_ad_partial_only = (
                projected.get("available") is not True
                and pre_ad_row_available
                and not non_ad_missing
                and not non_ad_invalid
            )
            if projected.get("available") is not True:
                complete = False
                if not after_ad_partial_only:
                    if include_cross_docking:
                        cross_docking_complete = False
                    excluded.append({
                        "row_id": row_id,
                        "label": label,
                        "reason": "UNIT_INPUTS_INCOMPLETE",
                        "missing_inputs": list(projected.get("missing_inputs") or [])[:12],
                        "invalid_inputs": list(projected.get("invalid_inputs") or [])[:12],
                        **({"extended_reason": (projected.get("extended_calculation") or {}).get("reason")}
                           if isinstance(projected.get("extended_calculation"), dict) else {}),
                    })
                    continue

            row_components = {}
            pre_ad_unit_profit = self._decimal(unit.get("pre_ad_profit_before_tax"))
            if pre_ad_unit_profit is None:
                complete = False
                excluded.append({
                    "row_id": row_id,
                    "label": label,
                    "reason": "PRE_AD_COMPONENT_UNKNOWN",
                })
                continue
            pre_ad_row_profit = (
                (pre_ad_unit_profit * quantity).quantize(Decimal("0.01"))
                + fifo_cost_delta
            )
            row_components["pre_ad_profit_before_tax"] = pre_ad_row_profit
            additional_unit_expense = self._decimal(unit.get("additional_unit_expenses"))
            if extended_scenario is not None:
                if additional_unit_expense is None:
                    complete = False
                    excluded.append({
                        "row_id": row_id,
                        "label": label,
                        "reason": "EXTENDED_EXPENSE_COMPONENT_UNKNOWN",
                    })
                    continue
                row_components["additional_unit_expenses"] = (
                    additional_unit_expense * quantity
                ).quantize(Decimal("0.01"))
                additional_expense_total += row_components["additional_unit_expenses"]
                if additional_expense_total > self.MAX_AGGREGATE_AMOUNT:
                    return self._error("AGGREGATE_AMOUNT_LIMIT_EXCEEDED")
            for field in self.MONEY_COMPONENTS:
                source_field = "cost" if field == "cost_of_goods" else field
                value = self._decimal(unit.get(source_field))
                if value is None:
                    if after_ad_partial_only and field in {"advertising", "profit_before_tax"}:
                        row_components[field] = None
                        after_ad_unknown_components.add(field)
                        continue
                    complete = False
                    break
                row_amount = (value * quantity).quantize(Decimal("0.01"))
                if cost_allocation is not None and cost_allocation.get("status") == "COMPLETE":
                    if field == "cost_of_goods":
                        row_amount = Decimal(cost_allocation["total_cost_rub"])
                    elif field == "profit_before_tax":
                        row_amount += fifo_cost_delta
                row_components[field] = row_amount
                totals[field] += row_components[field]
                if abs(totals[field]) > self.MAX_AGGREGATE_AMOUNT:
                    return self._error("AGGREGATE_AMOUNT_LIMIT_EXCEEDED")
            if include_cross_docking:
                evidence = (item.get("sources") or {}).get("cross_docking")
                if (isinstance(evidence, dict)
                        and evidence.get("evidence_complete") is True
                        and evidence.get("rate_available") is True
                        and evidence.get("applicable_to_sku") is True
                        and unit.get("cross_docking") is not None):
                    amount = self._decimal(unit.get("cross_docking"))
                    if amount is None or amount < 0:
                        cross_docking_complete = False
                        complete = False
                        row_components["cross_docking"] = None
                    else:
                        row_amount = (amount * quantity).quantize(Decimal("0.01"))
                        cross_docking_total += row_amount
                        if cross_docking_total > self.MAX_AGGREGATE_AMOUNT:
                            return self._error("AGGREGATE_AMOUNT_LIMIT_EXCEEDED")
                        row_components["cross_docking"] = row_amount
                else:
                    cross_docking_complete = False
                    complete = False
                    row_components["cross_docking"] = None
            if not set(self.MONEY_COMPONENTS).issubset(row_components):
                excluded.append({"row_id": row_id, "label": label, "reason": "UNIT_COMPONENT_UNKNOWN"})
                continue
            row_result = self._row_result(
                row_id, label, quantity, row_components,
                unit_price=self._decimal(unit.get("revenue")),
                cost_allocation=cost_allocation,
            )
            if after_ad_partial_only:
                row_result["after_ad_status"] = "INCOMPLETE_ADVERTISING"
                row_result["after_ad_missing_inputs"] = list(
                    projected.get("missing_inputs") or []
                )[:12]
                row_result["after_ad_invalid_inputs"] = list(
                    projected.get("invalid_inputs") or []
                )[:12]
            canonical_rows.append(row_result)

        fixed_expenses = self._validated_expenses(expenses)
        expense_total = sum(
            (amount for _name, amount, _category in fixed_expenses), Decimal("0.00"),
        )
        fixed_non_ad_expense_total = sum(
            (amount for _name, amount, category in fixed_expenses if category == "OTHER"),
            Decimal("0.00"),
        )
        fixed_advertising_expense_total = sum(
            (amount for _name, amount, category in fixed_expenses if category == "ADVERTISING"),
            Decimal("0.00"),
        )
        fixed_unclassified_expense_total = sum(
            (amount for _name, amount, category in fixed_expenses if category == "UNCLASSIFIED"),
            Decimal("0.00"),
        )
        if expense_total > self.MAX_FIXED_EXPENSE_TOTAL:
            return self._error("FIXED_EXPENSE_TOTAL_LIMIT_EXCEEDED")
        if fixed_non_ad_expense_total:
            pre_ad_known_expenses["FIXED_PLANNING_EXPENSES"] = fixed_non_ad_expense_total
            pre_ad_included_expense_keys.add("FIXED_PLANNING_EXPENSES")
        if fixed_unclassified_expense_total:
            pre_ad_unknown_expense_keys.add("UNCLASSIFIED_FIXED_PLANNING_EXPENSES")
        pre_tax_subtotal = totals["profit_before_tax"] - expense_total
        pre_ad_pre_tax_subtotal = pre_ad_profit_before_tax_total - fixed_non_ad_expense_total
        if abs(pre_tax_subtotal) > self.MAX_AGGREGATE_AMOUNT:
            return self._error("AGGREGATE_AMOUNT_LIMIT_EXCEEDED")
        if abs(pre_ad_pre_tax_subtotal) > self.MAX_AGGREGATE_AMOUNT:
            return self._error("AGGREGATE_AMOUNT_LIMIT_EXCEEDED")
        all_rows_known = quantity_known and complete and not excluded
        same_policy = len(policy_set) == 1 and not policy_missing
        pre_ad_rows_known = quantity_known and pre_ad_complete
        pre_ad_same_policy = len(pre_ad_policy_set) == 1 and not pre_ad_policy_missing
        pre_ad_confirmed_zero_expense_keys = (
            set(pre_ad_confirmed_zero_expense_intersection or ())
            if pre_ad_rows_known and pre_ad_same_policy
            else set()
        )
        # A source may explicitly exclude a category for one SKU while another
        # SKU has evidence for it. The aggregate is only partially covered in
        # that case; do not report the category as globally excluded.
        for key in list(pre_ad_excluded_expense_reasons):
            if key in pre_ad_included_expense_keys or key in pre_ad_unknown_expense_keys:
                pre_ad_excluded_expense_reasons.pop(key, None)
                if key in pre_ad_included_expense_keys:
                    pre_ad_unknown_expense_keys.add(key)
        # A zero confirmed for one SKU is not a zero for the whole mix. If a
        # category is also included by another SKU (or its coverage is partial),
        # retain its amount in the aggregate additional-expense pool and remove
        # the misleading category-specific zero.
        for key in (
            pre_ad_confirmed_zero_expense_candidates
            - pre_ad_confirmed_zero_expense_keys
        ):
            if pre_ad_known_expenses.get(key) == Decimal("0.00"):
                pre_ad_known_expenses.pop(key, None)
        tax = None
        final_profit = None
        margin = None
        pre_ad_tax = None
        pre_ad_profit = None
        pre_ad_margin = None
        pre_ad_status = "UNAVAILABLE"
        pre_ad_reason = "MIX_INPUTS_OR_TAX_POLICY_INCOMPLETE"
        tax_status = (
            "MIXED_TAX_POLICIES" if len(policy_set) > 1
            else "PARTIAL_INPUTS" if not all_rows_known
            else "TAX_POLICY_MISSING"
        )

        if all_rows_known and same_policy:
            mode, rate, minimum_rate = next(iter(policy_set))
            try:
                tax_result = self.tax_service.calculate(
                    mode=mode,
                    revenue=float(totals["revenue"]),
                    gross_profit=float(pre_tax_subtotal),
                    tax_rate=float(rate) if rate is not None else None,
                    minimum_tax_rate=float(minimum_rate) if minimum_rate is not None else None,
                    discount_points=float(totals["discount_points"]),
                    comparison_gross_profit=float(pre_ad_pre_tax_subtotal),
                )
            except (ArithmeticError, OverflowError, TypeError, ValueError):
                tax_result = {"error": True}
            if not isinstance(tax_result, dict) or tax_result.get("error") is True or not tax_result.get("configured"):
                tax_status = "TAX_CALCULATION_UNAVAILABLE"
            else:
                tax = self._decimal(tax_result.get("tax_amount"))
                if tax is not None:
                    tax = tax.quantize(Decimal("0.01"))
                    final_profit = pre_tax_subtotal - tax
                    if totals["revenue"] != 0:
                        margin = (final_profit * Decimal("100") / totals["revenue"]).quantize(Decimal("0.01"))
                    tax_status = "CONFIRMED"
                    comparison = tax_result.get("comparison")
                    if (isinstance(comparison, dict)
                            and comparison.get("status") == "AVAILABLE"):
                        pre_ad_tax = self._decimal(comparison.get("tax_amount"))
                        if pre_ad_tax is not None:
                            pre_ad_tax = pre_ad_tax.quantize(Decimal("0.01"))
                            pre_ad_profit = pre_ad_pre_tax_subtotal - pre_ad_tax
                            if pre_ad_revenue_total != 0:
                                pre_ad_margin = (
                                    pre_ad_profit * Decimal("100") / pre_ad_revenue_total
                                ).quantize(Decimal("0.01"))
                                pre_ad_status = "AVAILABLE"
                                pre_ad_reason = None
                            else:
                                pre_ad_status = "UNDEFINED_ZERO_REVENUE"
                                pre_ad_reason = "ZERO_REVENUE_DENOMINATOR"
                    else:
                        pre_ad_reason = (
                            comparison.get("reason")
                            if isinstance(comparison, dict)
                            else "COMPARISON_TAX_UNAVAILABLE"
                        )
                else:
                    tax_status = "TAX_CALCULATION_UNAVAILABLE"

        elif pre_ad_rows_known and pre_ad_same_policy:
            mode, rate, minimum_rate = next(iter(pre_ad_policy_set))
            try:
                tax_result = self.tax_service.calculate(
                    mode=mode,
                    revenue=float(pre_ad_revenue_total),
                    gross_profit=float(pre_ad_pre_tax_subtotal),
                    tax_rate=float(rate) if rate is not None else None,
                    minimum_tax_rate=float(minimum_rate) if minimum_rate is not None else None,
                    discount_points=float(pre_ad_discount_points_total),
                )
            except (ArithmeticError, OverflowError, TypeError, ValueError):
                tax_result = {"error": True}
            if (
                isinstance(tax_result, dict)
                and tax_result.get("error") is not True
                and tax_result.get("configured")
            ):
                pre_ad_tax = self._decimal(tax_result.get("tax_amount"))
                if pre_ad_tax is not None:
                    pre_ad_tax = pre_ad_tax.quantize(Decimal("0.01"))
                    pre_ad_profit = pre_ad_pre_tax_subtotal - pre_ad_tax
                    if pre_ad_revenue_total != 0:
                        pre_ad_margin = (
                            pre_ad_profit * Decimal("100") / pre_ad_revenue_total
                        ).quantize(Decimal("0.01"))
                        pre_ad_status = "AVAILABLE"
                        pre_ad_reason = "AFTER_AD_SCENARIO_UNAVAILABLE"
                    else:
                        pre_ad_status = "UNDEFINED_ZERO_REVENUE"
                        pre_ad_reason = "ZERO_REVENUE_DENOMINATOR"
            else:
                pre_ad_reason = "NO_AD_TAX_CALCULATION_UNAVAILABLE"

        components = {field: self._money(value) for field, value in totals.items()}
        for field in after_ad_unknown_components:
            components[field] = None
        if has_extended_expenses:
            components["additional_unit_expenses"] = self._money(additional_expense_total)
        if include_cross_docking:
            components["cross_docking"] = (
                self._money(cross_docking_total) if cross_docking_complete else None
            )
        return {
            "error": False,
            "kind": "SALES_MIX_ECONOMICS",
            "status": "COMPLETE" if all_rows_known and tax_status == "CONFIRMED" else "PARTIAL",
            "period": period_label,
            "selected_rows": len(items),
            "included_rows": len(canonical_rows),
            "excluded_rows": excluded,
            "coverage_complete": all_rows_known,
            "after_ad_status": (
                "INCOMPLETE_ADVERTISING"
                if "advertising" in after_ad_unknown_components
                else "COMPLETE" if all_rows_known else "PARTIAL_INPUTS"
            ),
            "after_ad_unknown_components": sorted(after_ad_unknown_components),
            "total_quantity": sum(row["quantity"] for row in canonical_rows),
            "rows": canonical_rows,
            "components": components,
            **({"cross_docking_status": "CONFIRMED" if cross_docking_complete else "PARTIAL_OR_UNAVAILABLE"}
               if include_cross_docking else {}),
            "fixed_expenses": [
                {"name": name, "amount": self._money(amount), "category": category}
                for name, amount, category in fixed_expenses
            ],
            "fixed_expense_total": self._money(expense_total),
            "profit_before_tax_after_fixed_expenses": (
                None if "profit_before_tax" in after_ad_unknown_components
                else self._money(pre_tax_subtotal)
            ),
            "tax": self._money(tax) if tax is not None and all_rows_known and same_policy else None,
            "tax_status": tax_status,
            "profit": self._money(final_profit) if final_profit is not None else None,
            "margin_percent": self._percent(margin) if margin is not None else None,
            "pre_ad_margin": {
                "schema_version": 1,
                "status": pre_ad_status,
                "basis": "WEIGHTED_AGGREGATE_NO_AD_AFTER_TAX",
                "tax_basis": "AGGREGATE_NO_AD_SCENARIO",
                "revenue_basis": "SELLER_REVENUE_BEFORE_DISCOUNT_POINTS",
                "unit_basis": "AGGREGATE_REVENUE_WEIGHTED",
                "revenue_rub": self._money(pre_ad_revenue_total),
                "profit_before_tax_rub": self._money(pre_ad_pre_tax_subtotal),
                "tax_rub": self._money(pre_ad_tax) if pre_ad_tax is not None else None,
                "profit_rub": self._money(pre_ad_profit) if pre_ad_profit is not None else None,
                "margin_percent": self._percent(pre_ad_margin) if pre_ad_margin is not None else None,
                "expense_scope": {
                    "status": "PARTIAL" if pre_ad_unknown_expense_keys else "COMPLETE",
                    "known_non_ad_expenses_rub": {
                        key: self._money(value)
                        for key, value in sorted(pre_ad_known_expenses.items())
                    },
                    "included_expense_keys": sorted(pre_ad_included_expense_keys),
                    "confirmed_zero_expense_keys": sorted(pre_ad_confirmed_zero_expense_keys),
                    "unknown_non_ad_expense_keys": sorted(pre_ad_unknown_expense_keys),
                    "excluded_expense_keys": sorted(pre_ad_excluded_expense_reasons),
                    "excluded_expense_reasons": pre_ad_excluded_expense_reasons,
                    "fixed_planning_expenses_rub": self._money(fixed_non_ad_expense_total),
                    "fixed_planning_advertising_expenses_rub": self._money(
                        fixed_advertising_expense_total
                    ),
                },
                "reason": pre_ad_reason,
            },
            "margin_status": "DEFINED" if margin is not None else "UNDEFINED_ZERO_REVENUE" if all_rows_known and totals["revenue"] == 0 else "UNAVAILABLE",
            "read_only": True,
            "executed": False,
        }

    def _validate_scope(self, items, quantities, period_label, expenses, expenses_confirmed):
        if not isinstance(items, list) or not 1 <= len(items) <= self.MAX_ITEMS:
            return "INVALID_PLAN_SCOPE"
        if not isinstance(quantities, dict):
            return "INVALID_QUANTITIES"
        keys = set()
        identities = set()
        for item in items:
            if not isinstance(item, dict) or not isinstance(item.get("identity"), dict):
                return "INVALID_PRODUCT_IDENTITY"
            identity = item["identity"]
            if not all(str(identity.get(field) or "").strip() for field in ("product_id", "offer_id", "sku")):
                return "INVALID_PRODUCT_IDENTITY"
            key = str(item.get("row_id") or identity.get("sku") or "")
            exact_identity = tuple(str(identity.get(field) or "").strip() for field in ("product_id", "offer_id", "sku"))
            if not key or key in keys or exact_identity in identities:
                return "DUPLICATE_PRODUCT_IDENTITY"
            keys.add(key)
            identities.add(exact_identity)
        if set(quantities) != keys:
            return "QUANTITY_SCOPE_MISMATCH"
        known_quantity_total = 0
        for quantity in quantities.values():
            if quantity is not None and (type(quantity) is not int or not 0 <= quantity <= self.MAX_QUANTITY_PER_ITEM):
                return "INVALID_QUANTITY"
            if quantity is not None:
                known_quantity_total += quantity
        if known_quantity_total > self.MAX_TOTAL_QUANTITY:
            return "TOTAL_QUANTITY_LIMIT_EXCEEDED"
        if not self._valid_period(period_label):
            return "INVALID_PERIOD"
        if type(expenses_confirmed) is not bool or not expenses_confirmed:
            return "FIXED_EXPENSES_NOT_CONFIRMED"
        if not isinstance(expenses, list) or len(expenses) > self.MAX_FIXED_EXPENSES:
            return "INVALID_FIXED_EXPENSES"
        try:
            expense_total = Decimal("0")
            for expense in expenses:
                if not isinstance(expense, dict):
                    return "INVALID_FIXED_EXPENSES"
                if set(expense) not in (
                    {"name", "amount"},
                    {"name", "amount", "category"},
                ):
                    return "INVALID_FIXED_EXPENSES"
                if not isinstance(expense["name"], str) or not expense["name"].strip() or len(expense["name"]) > 80:
                    return "INVALID_FIXED_EXPENSES"
                category = expense.get("category", "UNCLASSIFIED")
                if category not in {"OTHER", "ADVERTISING", "UNCLASSIFIED"}:
                    return "INVALID_FIXED_EXPENSES"
                amount = self._decimal(expense["amount"])
                if amount is None or amount < 0 or amount > self.MAX_AMOUNT:
                    return "INVALID_FIXED_EXPENSES"
                expense_total += amount
                if expense_total > self.MAX_FIXED_EXPENSE_TOTAL:
                    return "FIXED_EXPENSE_TOTAL_LIMIT_EXCEEDED"
        except (KeyError, TypeError):
            return "INVALID_FIXED_EXPENSES"
        return None

    def _validated_expenses(self, expenses):
        return [
            (
                " ".join(expense["name"].split()),
                self._decimal(expense["amount"]).quantize(Decimal("0.01")),
                expense.get("category", "UNCLASSIFIED"),
            )
            for expense in expenses
        ]

    @staticmethod
    def _valid_period(value):
        if not isinstance(value, str) or len(value) > 80:
            return False
        match = re.fullmatch(r"\s*(.+?)\s+(?:-|—|–)\s+(.+?)\s*", value)
        if match is None:
            return False
        parsed = []
        for part in match.groups():
            try:
                parsed.append(date.fromisoformat(part))
            except ValueError:
                try:
                    parsed.append(datetime.strptime(part, "%d.%m.%Y").date())
                except ValueError:
                    return False
        return parsed[0] <= parsed[1] and (parsed[1] - parsed[0]).days + 1 <= 366

    @staticmethod
    def _tax_policy(inputs):
        mode = str(inputs.get("tax_mode") or "").upper()
        if not mode:
            return None
        if mode == "NONE":
            return (mode, None, None)
        rate = SalesMixPlanningService._decimal(inputs.get("tax_rate"))
        minimum = SalesMixPlanningService._decimal(inputs.get("minimum_tax_rate"))
        if rate is None or (mode == "USN_INCOME_MINUS_EXPENSES" and minimum is None):
            return None
        return (mode, rate, minimum)

    @staticmethod
    def _row_result(row_id, label, quantity, components, *, unit_price=None,
                    cost_allocation=None):
        profit_before_tax = components.get("profit_before_tax")
        result = {
            "row_id": row_id,
            "label": label,
            "quantity": quantity,
            "price_per_unit": SalesMixPlanningService._money(unit_price) if unit_price is not None else None,
            "components": {
                key: SalesMixPlanningService._money(value) if value is not None else None
                for key, value in components.items()
            },
            "profit_before_tax_contribution": (
                SalesMixPlanningService._money(profit_before_tax)
                if profit_before_tax is not None else None
            ),
        }
        if isinstance(cost_allocation, dict):
            result["cost_allocation"] = cost_allocation
        return result

    def _fifo_quantity_cost(self, item, inputs, quantity, unit):
        """Apply exact FIFO totals only for a matching, non-overridden basis."""
        sources = item.get("sources") if isinstance(item.get("sources"), dict) else {}
        completeness = sources.get("completeness")
        completeness = completeness if isinstance(completeness, dict) else {}
        cost_source = completeness.get("cost")
        cost_source = cost_source if isinstance(cost_source, dict) else {}
        basis = cost_source.get("quantity_allocation_basis")
        method = str(cost_source.get("method") or "").upper()
        is_fifo = method.startswith("FIFO_") or (
            isinstance(basis, dict) and basis.get("method") == "FIFO_CURRENT_SNAPSHOT"
        )
        if not is_fifo:
            return None, Decimal("0.00"), None

        provenance = item.get("provenance")
        provenance = provenance if isinstance(provenance, dict) else {}
        cost_provenance = str(provenance.get("cost") or "").strip().lower()
        manual_cost = cost_provenance in {
            "manual", "manual_seller_assumption", "manual_unit_economics_input",
        }
        input_cost = self._decimal(inputs.get("cost"))
        if input_cost is None:
            return None, Decimal("0.00"), "FIFO_PLANNING_UNIT_COST_MISSING"
        input_cost = input_cost.quantize(Decimal("0.01"))
        if manual_cost:
            total = (input_cost * quantity).quantize(Decimal("0.01"))
            return {
                "status": "MANUAL_SCENARIO_OVERRIDE",
                "method": "MANUAL_SCENARIO_COST",
                "quantity": quantity,
                "unit_cost_rub": self._money(input_cost),
                "total_cost_rub": self._money(total),
                "average_cost_rub": self._money(input_cost),
                "reference_fifo_revision": cost_source.get("revision"),
                "model_only": True,
                "factual_period_profit_eligible": False,
                "lines": [],
            }, Decimal("0.00"), None

        source_cost = self._decimal(cost_source.get("amount"))
        if source_cost is None or source_cost.quantize(Decimal("0.01")) != input_cost:
            return None, Decimal("0.00"), "FIFO_PLANNING_COST_SOURCE_MISMATCH"
        if not isinstance(basis, dict):
            return None, Decimal("0.00"), "FIFO_PLANNING_BASIS_UNAVAILABLE"
        allocation = self.fifo_allocator.allocate(quantity=quantity, basis=basis)
        if allocation.get("status") != "COMPLETE":
            return None, Decimal("0.00"), allocation.get("reason_code") or "FIFO_PLANNING_ALLOCATION_INCOMPLETE"
        baseline_cost = self._decimal(unit.get("cost"))
        if baseline_cost is None:
            return None, Decimal("0.00"), "FIFO_PLANNING_UNIT_COST_MISSING"
        baseline_total = (baseline_cost * quantity).quantize(Decimal("0.01"))
        exact_total = Decimal(allocation["total_cost_rub"])
        # Positive delta means exact FIFO COGS is lower than next-unit × Q,
        # so pre-tax contribution rises by the same amount.
        return allocation, baseline_total - exact_total, None

    @staticmethod
    def _safe_label(identity):
        value = str(identity.get("product_name") or identity.get("offer_id") or identity.get("sku") or "Товар")
        return " ".join(value.replace("\r", " ").replace("\n", " ").split())[:60]

    @staticmethod
    def _decimal(value):
        if isinstance(value, bool) or value is None:
            return None
        try:
            parsed = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            return None
        return parsed if parsed.is_finite() else None

    @staticmethod
    def _money(value):
        return format(value.quantize(Decimal("0.01")), ".2f")

    @staticmethod
    def _percent(value):
        rounded = value.quantize(Decimal("0.01"))
        return "0.00" if rounded == 0 else format(rounded, ".2f")

    @staticmethod
    def _error(code):
        return {"error": True, "code": code, "status": code, "read_only": True, "executed": False}
