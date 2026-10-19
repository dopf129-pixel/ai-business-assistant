"""Pure comparison of a saved sales plan with exact-scope finalized facts."""

from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from services.ozon_account_repository import split_store_tenant_scope


class PeriodProfitPlanFactComparisonService:
    """Compare only metrics with an explicit, compatible basis.

    The first version compares planned successful-unit volume and gross revenue
    with the canonical Period Profit rows. Profit is shown as unavailable for
    delta purposes because advertising, store expenses, and committed return
    COGS are not consistently attributable to the selected SKU group.
    """

    VERSION = 1
    MAX_ITEMS = 10
    MONEY = Decimal("0.01")

    def __init__(self, sales_mix_planning_service):
        self.sales_mix_planning_service = sales_mix_planning_service

    def compare(self, document_result, fact_result, *, tenant_scope, generated_at_utc):
        document = (document_result or {}).get("document")
        if not isinstance(document, dict):
            return self._error("PLAN_FACT_DOCUMENT_INVALID")
        if not isinstance(tenant_scope, str) or not tenant_scope.strip():
            return self._error("PLAN_FACT_TENANT_REQUIRED")
        owner_id, store_id = split_store_tenant_scope(tenant_scope)
        owner_id = str(owner_id or "")
        store_id = str(store_id or "")
        if (
            str(document.get("owner_id") or "") != owner_id
            or str(document.get("store_id") or "") != store_id
        ):
            return self._error("PLAN_FACT_SCOPE_MISMATCH")
        if type(document.get("revision")) is not int or document["revision"] < 1:
            return self._error("PLAN_FACT_REVISION_INVALID")
        payload = document.get("payload")
        mix = payload.get("sales_mix") if isinstance(payload, dict) else None
        items = payload.get("items") if isinstance(payload, dict) else None
        if not isinstance(mix, dict) or not isinstance(items, list):
            return self._error("PLAN_FACT_SALES_MIX_REQUIRED")
        if len(items) < 1 or len(items) > self.MAX_ITEMS:
            return self._error("PLAN_FACT_SCOPE_INVALID")
        if payload.get("calculation_version") != self.sales_mix_planning_service.scenario_service.VERSION:
            return self._error("PLAN_FACT_CALCULATION_VERSION_INCOMPATIBLE")

        period = self._period(mix.get("period_label"))
        if period is None:
            return self._error("PLAN_FACT_PERIOD_INVALID")
        if (
            not isinstance(fact_result, dict)
            or fact_result.get("error") is not False
            or fact_result.get("status") != "PERIOD_PROFIT_QUERY_READY"
            or fact_result.get("period_profit_final_application_complete") is not True
        ):
            return self._error("PLAN_FACT_FINALIZED_RESULT_REQUIRED")
        request = fact_result.get("request") or {}
        if (request.get("date_from"), request.get("date_to")) != period:
            return self._error("PLAN_FACT_PERIOD_MISMATCH")
        summary = fact_result.get("summary")
        if not isinstance(summary, dict) or summary.get("status") != "PERIOD_PROFIT_SUMMARY_READY":
            return self._error("PLAN_FACT_SUMMARY_UNAVAILABLE")
        actual_rows = summary.get("products")
        if not isinstance(actual_rows, list):
            return self._error("PLAN_FACT_ROWS_UNAVAILABLE")

        quantities = mix.get("quantities")
        plan = self.sales_mix_planning_service.calculate(
            items,
            quantities=quantities,
            period_label=mix.get("period_label"),
            expenses=mix.get("expenses"),
            expenses_confirmed=mix.get("confirmed") is True,
        )
        if plan.get("error") is True:
            return self._error("PLAN_FACT_PLAN_PROJECTION_UNAVAILABLE")

        exact_plan_rows = {}
        for item in items:
            if not isinstance(item, dict) or not isinstance(item.get("identity"), dict):
                return self._error("PLAN_FACT_IDENTITY_INVALID")
            identity = item["identity"]
            key = self._identity(identity)
            if key is None or key in exact_plan_rows:
                return self._error("PLAN_FACT_IDENTITY_AMBIGUOUS")
            exact_plan_rows[key] = item

        exact_actual_rows = {}
        for row in actual_rows:
            if not isinstance(row, dict):
                return self._error("PLAN_FACT_ROW_INVALID")
            key = self._identity(row)
            if key is None:
                return self._error("PLAN_FACT_ROW_IDENTITY_UNAVAILABLE")
            if key in exact_actual_rows:
                return self._error("PLAN_FACT_ACTUAL_IDENTITY_AMBIGUOUS")
            exact_actual_rows[key] = row
        if set(exact_actual_rows) != set(exact_plan_rows):
            return self._error("PLAN_FACT_ACTUAL_SCOPE_MISMATCH")

        plan_rows_by_id = {
            str(row.get("row_id")): row for row in plan.get("rows", [])
        }
        output_rows = []
        total_plan_revenue = Decimal("0.00")
        total_fact_revenue = Decimal("0.00")
        total_plan_quantity = 0
        total_fact_quantity = 0
        plan_revenue_complete = True
        plan_quantity_complete = True
        all_quantities_confirmed = summary.get("sale_quantity_reconciled") is True
        for key, item in exact_plan_rows.items():
            identity = item["identity"]
            actual = exact_actual_rows[key]
            row_id = str(item.get("row_id") or identity.get("sku"))
            planned = plan_rows_by_id.get(row_id)
            inputs = item.get("inputs") if isinstance(item.get("inputs"), dict) else {}
            plan_quantity = quantities.get(row_id) if isinstance(quantities, dict) else None
            if plan_quantity is not None and (type(plan_quantity) is not int or plan_quantity < 0):
                return self._error("PLAN_FACT_PLAN_QUANTITY_INVALID")
            if plan_quantity is None:
                plan_quantity_complete = False
            price = self._decimal(inputs.get("price"))
            plan_revenue = (
                (price * Decimal(plan_quantity)).quantize(self.MONEY)
                if price is not None and plan_quantity is not None
                else None
            )
            actual_revenue = self._decimal(actual.get("revenue"))
            if actual_revenue is None:
                return self._error("PLAN_FACT_REVENUE_INVALID")
            if price is None:
                plan_revenue_complete = False
            fact_quantity = self._integer(actual.get("units_sold"))
            if fact_quantity is None:
                all_quantities_confirmed = False
            else:
                total_fact_quantity += fact_quantity
            if plan_quantity is not None:
                total_plan_quantity += plan_quantity
            if plan_revenue is not None:
                total_plan_revenue += plan_revenue
            else:
                plan_revenue_complete = False
            total_fact_revenue += actual_revenue
            per_unit_price = price
            quantity_effect = None
            average_revenue_effect = None
            actual_average_revenue = None
            if fact_quantity is not None and per_unit_price is not None and plan_quantity is not None:
                quantity_effect = (Decimal(fact_quantity - plan_quantity) * per_unit_price).quantize(self.MONEY)
                average_revenue_effect = (actual_revenue - Decimal(fact_quantity) * per_unit_price).quantize(self.MONEY)
                if fact_quantity:
                    actual_average_revenue = (actual_revenue / Decimal(fact_quantity)).quantize(self.MONEY)
                if quantity_effect + average_revenue_effect != actual_revenue - plan_revenue:
                    return self._error("PLAN_FACT_REVENUE_BRIDGE_INVALID")
            output_rows.append({
                "row_id": row_id,
                "identity": {
                    "product_id": key[0],
                    "offer_id": key[1],
                    "sku": key[2],
                    "label": self._safe_label(identity),
                },
                "plan_quantity": plan_quantity,
                "actual_quantity": fact_quantity,
                "quantity_status": "CONFIRMED" if fact_quantity is not None and all_quantities_confirmed else "UNAVAILABLE",
                "plan_price_per_unit": self._money(per_unit_price),
                "plan_revenue": self._money(plan_revenue),
                "actual_revenue": self._money(actual_revenue),
                "revenue_delta": self._money(actual_revenue - plan_revenue) if plan_revenue is not None else None,
                "quantity_effect": self._money(quantity_effect),
                "actual_average_revenue_effect": self._money(average_revenue_effect),
                "actual_average_revenue_per_unit": self._money(actual_average_revenue),
                "actual_components": self._actual_components(actual),
            })

        revenue_delta = (
            total_fact_revenue - total_plan_revenue
            if plan_revenue_complete and plan_quantity_complete
            else None
        )
        quantity_effect = None
        average_revenue_effect = None
        if all_quantities_confirmed and plan_quantity_complete and plan_revenue_complete:
            quantity_effect = sum(
                (self._decimal(row["quantity_effect"]) for row in output_rows),
                Decimal("0.00"),
            ).quantize(self.MONEY)
            average_revenue_effect = sum(
                (self._decimal(row["actual_average_revenue_effect"]) for row in output_rows),
                Decimal("0.00"),
            ).quantize(self.MONEY)
            if revenue_delta is None or quantity_effect + average_revenue_effect != revenue_delta:
                return self._error("PLAN_FACT_TOTAL_REVENUE_BRIDGE_INVALID")
        compatible = (
            all_quantities_confirmed
            and summary.get("sale_quantity_source")
            == "OZON_REALIZATION_POSTING_OR_FBO_LIST_OR_EXACT_POSTING_DETAIL"
        )
        return {
            "error": False,
                "status": "COMPARABLE" if compatible and plan_revenue_complete and plan_quantity_complete else "PARTIAL",
            "comparison_version": self.VERSION,
            "plan": {
                "document_id": str(document.get("document_id") or ""),
                "revision": document["revision"],
                "period": {"date_from": period[0], "date_to": period[1]},
                "selected_rows": len(items),
                "quantity": total_plan_quantity if plan_quantity_complete else None,
                "quantity_status": "CONFIRMED" if plan_quantity_complete else "PARTIAL",
                "revenue": self._money(total_plan_revenue) if plan_revenue_complete and plan_quantity_complete else None,
                "revenue_status": "CONFIRMED" if plan_revenue_complete and plan_quantity_complete else "PARTIAL",
                "revenue_basis": "SELLER_PRICE_TIMES_MANUAL_SUCCESSFUL_SALES",
                "profit": plan.get("profit"),
                "profit_status": "PLAN_ONLY",
                "margin_percent": plan.get("margin_percent"),
            },
            "actual": {
                "quantity": total_fact_quantity if all_quantities_confirmed else None,
                "quantity_status": "CONFIRMED" if all_quantities_confirmed else "UNAVAILABLE",
                "quantity_basis": summary.get("sale_quantity_source") if all_quantities_confirmed else None,
                "revenue": self._money(total_fact_revenue),
                "revenue_basis": "OZON_FINANCE_GROSS_SALES_POINTS_SEPARATE",
                "profit": self._money(self._decimal(summary.get("profit"))),
                "profit_status": "NOT_COMPARABLE",
                "profit_reason_codes": [
                    "ADVERTISING_NOT_PROVEN_FOR_SELECTED_SCOPE",
                    "EXTERNAL_EXPENSES_NOT_ATTRIBUTED_TO_SELECTED_SCOPE",
                    "RETURN_COGS_NOT_PROVEN_PER_SELECTED_SKU",
                ],
            },
            "revenue_comparison": {
                "status": "COMPARABLE_GROSS_REVENUE_POINTS_SEPARATE",
                "delta": self._money(revenue_delta),
                "quantity_effect": self._money(quantity_effect),
                "actual_average_revenue_effect": self._money(average_revenue_effect),
                "bridge_reconciled": quantity_effect is not None and average_revenue_effect is not None,
                "note": "Арифметическое разложение; остаток по фактической выручке на единицу не доказывает изменение установленной цены.",
            },
            "rows": output_rows,
            "coverage": {
                "selected_identities": len(items),
                "matched_exact_identities": len(output_rows),
                "quantity_status": "CONFIRMED" if all_quantities_confirmed else "UNAVAILABLE",
                "financial_scope": summary.get("profit_scope"),
                "advertising_included": summary.get("advertising_included") is True,
                "return_cogs_applied": summary.get("return_cogs_profit_applied") is True,
                "external_expenses_included": False,
            },
            "generated_at_utc": generated_at_utc,
            "read_only": True,
            "executed": False,
        }

    @classmethod
    def _identity(cls, source):
        if not isinstance(source, dict):
            return None
        values = tuple(str(source.get(field) or "").strip() for field in (
            "product_id", "offer_id", "sku",
        ))
        return values if all(values) else None

    @staticmethod
    def _period(value):
        if not isinstance(value, str) or len(value) > 80:
            return None
        import re
        match = re.fullmatch(r"\s*(.+?)\s+(?:-|—|–)\s+(.+?)\s*", value)
        if match is None:
            return None
        parsed = []
        for part in match.groups():
            try:
                parsed.append(date.fromisoformat(part.strip()))
            except ValueError:
                try:
                    parsed.append(datetime.strptime(part.strip(), "%d.%m.%Y").date())
                except ValueError:
                    return None
        if parsed[0] > parsed[1]:
            return None
        return parsed[0].isoformat(), parsed[1].isoformat()

    @staticmethod
    def _decimal(value):
        if isinstance(value, bool) or value is None:
            return None
        try:
            result = Decimal(str(value).strip().replace(",", "."))
        except (InvalidOperation, TypeError, ValueError):
            return None
        return result if result.is_finite() else None

    @staticmethod
    def _integer(value):
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            return None
        return value

    @classmethod
    def _money(cls, value):
        return format(value.quantize(cls.MONEY), ".2f") if value is not None else None

    @staticmethod
    def _safe_label(identity):
        return " ".join(str(identity.get("product_name") or identity.get("offer_id") or identity.get("sku") or "Товар").replace("\r", " ").replace("\n", " ").split())[:60]

    @classmethod
    def _actual_components(cls, row):
        fields = (
            "revenue", "discount_points", "commission", "logistics", "acquiring",
            "other_fees", "product_cost", "tax", "profit",
        )
        values = {}
        for field in fields:
            amount = cls._decimal(row.get(field))
            values[field] = cls._money(amount)
        return values

    @staticmethod
    def _error(code):
        return {
            "error": True,
            "code": code,
            "status": "PLAN_FACT_COMPARISON_UNAVAILABLE",
            "read_only": True,
            "executed": False,
        }
