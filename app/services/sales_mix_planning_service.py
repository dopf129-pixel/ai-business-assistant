"""Pure aggregate economics for explicitly planned successful unit sales."""

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import re


class SalesMixPlanningService:
    MAX_ITEMS = 10
    MAX_QUANTITY_PER_ITEM = 1_000_000
    MAX_FIXED_EXPENSES = 50
    MAX_AMOUNT = Decimal("999999999999.99")
    MONEY_COMPONENTS = (
        "revenue", "cost_of_goods", "discount_points", "commission", "advertising", "fees",
        "profit_before_tax",
    )

    def __init__(self, scenario_service, tax_service=None):
        self.scenario_service = scenario_service
        self.tax_service = tax_service or getattr(scenario_service, "tax_service", None)

    def calculate(self, items, *, quantities, period_label, expenses, expenses_confirmed):
        error = self._validate_scope(items, quantities, period_label, expenses, expenses_confirmed)
        if error:
            return self._error(error)

        quantity_map = quantities
        canonical_rows = []
        excluded = []
        totals = {field: Decimal("0.00") for field in self.MONEY_COMPONENTS}
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
                excluded.append({"row_id": row_id, "label": label, "reason": "QUANTITY_UNKNOWN"})
                continue

            inputs = item.get("inputs") if isinstance(item.get("inputs"), dict) else {}
            policy = self._tax_policy(inputs)
            if policy is None:
                policy_missing = True
            else:
                policy_set.add(policy)

            if quantity == 0:
                row_components = {field: Decimal("0.00") for field in self.MONEY_COMPONENTS}
                unit_price = self._decimal(inputs.get("price"))
                canonical_rows.append(self._row_result(
                    row_id, label, quantity, row_components,
                    unit_price=unit_price.quantize(Decimal("0.01")) if unit_price is not None else None,
                ))
                continue

            projected = self.scenario_service.calculate_components_only(inputs)
            if projected.get("available") is not True:
                complete = False
                excluded.append({
                    "row_id": row_id,
                    "label": label,
                    "reason": "UNIT_INPUTS_INCOMPLETE",
                    "missing_inputs": list(projected.get("missing_inputs") or [])[:12],
                    "invalid_inputs": list(projected.get("invalid_inputs") or [])[:12],
                })
                continue

            unit = projected.get("calculated") or {}
            row_components = {}
            for field in self.MONEY_COMPONENTS:
                source_field = "cost" if field == "cost_of_goods" else field
                value = self._decimal(unit.get(source_field))
                if value is None:
                    complete = False
                    break
                row_components[field] = (value * quantity).quantize(Decimal("0.01"))
                totals[field] += row_components[field]
            if len(row_components) != len(self.MONEY_COMPONENTS):
                excluded.append({"row_id": row_id, "label": label, "reason": "UNIT_COMPONENT_UNKNOWN"})
                continue
            canonical_rows.append(self._row_result(
                row_id, label, quantity, row_components,
                unit_price=self._decimal(unit.get("revenue")),
            ))

        fixed_expenses = self._validated_expenses(expenses)
        expense_total = sum((amount for _name, amount in fixed_expenses), Decimal("0.00"))
        pre_tax_subtotal = totals["profit_before_tax"] - expense_total
        all_rows_known = quantity_known and complete and not excluded
        same_policy = len(policy_set) == 1 and not policy_missing
        tax = None
        final_profit = None
        margin = None
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
                else:
                    tax_status = "TAX_CALCULATION_UNAVAILABLE"

        return {
            "error": False,
            "kind": "SALES_MIX_ECONOMICS",
            "status": "COMPLETE" if all_rows_known and tax_status == "CONFIRMED" else "PARTIAL",
            "period": period_label,
            "selected_rows": len(items),
            "included_rows": len(canonical_rows),
            "excluded_rows": excluded,
            "coverage_complete": all_rows_known,
            "total_quantity": sum(row["quantity"] for row in canonical_rows),
            "rows": canonical_rows,
            "components": {field: self._money(value) for field, value in totals.items()},
            "fixed_expenses": [
                {"name": name, "amount": self._money(amount)}
                for name, amount in fixed_expenses
            ],
            "fixed_expense_total": self._money(expense_total),
            "profit_before_tax_after_fixed_expenses": self._money(pre_tax_subtotal),
            "tax": self._money(tax) if tax is not None and all_rows_known and same_policy else None,
            "tax_status": tax_status,
            "profit": self._money(final_profit) if final_profit is not None else None,
            "margin_percent": self._money(margin) if margin is not None else None,
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
        for quantity in quantities.values():
            if quantity is not None and (type(quantity) is not int or not 0 <= quantity <= self.MAX_QUANTITY_PER_ITEM):
                return "INVALID_QUANTITY"
        if not self._valid_period(period_label):
            return "INVALID_PERIOD"
        if type(expenses_confirmed) is not bool or not expenses_confirmed:
            return "FIXED_EXPENSES_NOT_CONFIRMED"
        if not isinstance(expenses, list) or len(expenses) > self.MAX_FIXED_EXPENSES:
            return "INVALID_FIXED_EXPENSES"
        try:
            for expense in expenses:
                if not isinstance(expense, dict) or set(expense) != {"name", "amount"}:
                    return "INVALID_FIXED_EXPENSES"
                if not isinstance(expense["name"], str) or not expense["name"].strip() or len(expense["name"]) > 80:
                    return "INVALID_FIXED_EXPENSES"
                amount = self._decimal(expense["amount"])
                if amount is None or amount < 0 or amount > self.MAX_AMOUNT:
                    return "INVALID_FIXED_EXPENSES"
        except (KeyError, TypeError):
            return "INVALID_FIXED_EXPENSES"
        return None

    def _validated_expenses(self, expenses):
        return [
            (" ".join(expense["name"].split()), self._decimal(expense["amount"]).quantize(Decimal("0.01")))
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
        return parsed[0] <= parsed[1]

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
    def _row_result(row_id, label, quantity, components, *, unit_price=None):
        return {
            "row_id": row_id,
            "label": label,
            "quantity": quantity,
            "price_per_unit": SalesMixPlanningService._money(unit_price) if unit_price is not None else None,
            "components": {key: SalesMixPlanningService._money(value) for key, value in components.items()},
            "profit_before_tax_contribution": SalesMixPlanningService._money(components["profit_before_tax"]),
        }

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
    def _error(code):
        return {"error": True, "code": code, "status": code, "read_only": True, "executed": False}
