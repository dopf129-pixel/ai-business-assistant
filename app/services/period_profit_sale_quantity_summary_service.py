from collections import defaultdict
from datetime import date, datetime, timedelta
from math import isfinite

from services.period_profit_critical_finance_summary_service import (
    PeriodProfitCriticalFinanceSummaryService,
)


class PeriodProfitSaleQuantitySummaryService(
    PeriodProfitCriticalFinanceSummaryService
):
    """Reconcile standard-sale unit quantities from read-only Ozon evidence.

    Finance accrual-by-day is the monetary authority but its posting product schema does
    not expose quantity.  Standard COGS therefore needs a separate quantity authority.
    The primary source is the monthly realization-by-posting report joined by exact
    posting_number + SKU.  Missing exact matches fall back to read-only posting detail.
    """

    def __init__(
        self,
        finance_service,
        cost_service,
        tax_rate=0.06,
        sale_quantity_ozon_client=None,
    ):
        super().__init__(finance_service, cost_service, tax_rate=tax_rate)
        self.sale_quantity_ozon_client = sale_quantity_ozon_client
        self._realization_quantity_cache = {}
        self._posting_quantity_cache = {}

    def calculate(self, date_from, date_to, products):
        result = super().calculate(date_from, date_to, products)
        if not isinstance(result, dict) or result.get("error") is not False:
            return result
        if self.sale_quantity_ozon_client is None:
            return result

        reconciled = self._reconcile_sale_quantities(
            result,
            date_from,
            date_to,
        )
        return reconciled

    def _reconcile_sale_quantities(self, result, date_from, date_to):
        start = self._date(date_from)
        end = self._date(date_to)
        if start is None or end is None or start > end:
            return self._quantity_error("PERIOD_PROFIT_SALE_QUANTITY_PERIOD_INVALID")

        getter = getattr(
            self.finance_service,
            "get_daily_sale_posting_evidence",
            None,
        )
        if not callable(getter):
            return self._quantity_error("PERIOD_PROFIT_SALE_QUANTITY_FINANCE_EVIDENCE_UNAVAILABLE")

        sale_records = []
        current = start
        while current <= end:
            try:
                evidence = getter(current.isoformat())
            except Exception:
                return self._quantity_error("PERIOD_PROFIT_SALE_QUANTITY_FINANCE_EVIDENCE_UNAVAILABLE")
            if (
                not isinstance(evidence, dict)
                or evidence.get("error") is True
                or evidence.get("complete") is not True
                or not isinstance(evidence.get("records"), list)
            ):
                return self._quantity_error("PERIOD_PROFIT_SALE_QUANTITY_FINANCE_EVIDENCE_INCOMPLETE")
            sale_records.extend(evidence["records"])
            current += timedelta(days=1)

        grouped = {}
        for record in sale_records:
            if not isinstance(record, dict):
                return self._quantity_error("PERIOD_PROFIT_SALE_QUANTITY_FINANCE_EVIDENCE_INVALID")
            posting_number = str(record.get("posting_number") or "").strip()
            sku = str(record.get("sku") or "").strip()
            if not posting_number or not sku:
                return self._quantity_error("PERIOD_PROFIT_SALE_QUANTITY_FINANCE_EVIDENCE_INVALID")
            key = (posting_number, sku)
            if key in grouped:
                return self._quantity_error("PERIOD_PROFIT_SALE_QUANTITY_DUPLICATE_SALE_EVIDENCE")
            grouped[key] = record

        realization_map = self._load_realization_quantity_map(start, end)
        if realization_map is None:
            realization_map = {}

        units_by_sku = defaultdict(int)
        for posting_number, sku in grouped:
            quantity = realization_map.get((posting_number, sku))
            if quantity is None:
                quantity = self._load_posting_quantity(posting_number, sku)
            if quantity is None:
                return self._quantity_error("PERIOD_PROFIT_SALE_QUANTITY_EVIDENCE_UNAVAILABLE")
            units_by_sku[sku] += quantity

        product_rows = result.get("products")
        if not isinstance(product_rows, list):
            return self._quantity_error("PERIOD_PROFIT_SALE_QUANTITY_RESULT_INVALID")

        next_rows = []
        covered_skus = set()
        total_units = 0
        total_product_cost = 0.0

        for row in product_rows:
            if not isinstance(row, dict):
                return self._quantity_error("PERIOD_PROFIT_SALE_QUANTITY_RESULT_INVALID")
            sku = str(row.get("sku") or "").strip()
            if not sku:
                return self._quantity_error("PERIOD_PROFIT_SALE_QUANTITY_RESULT_INVALID")
            cost = self._number(row.get("cost_per_unit"))
            net_accrual = self._number(row.get("net_accrual"), missing_zero=True)
            tax = self._number(row.get("tax"), missing_zero=True)
            revenue = self._number(row.get("revenue"), missing_zero=True)
            if None in (cost, net_accrual, tax, revenue):
                return self._quantity_error("PERIOD_PROFIT_SALE_QUANTITY_RESULT_INVALID")

            units = int(units_by_sku.get(sku, 0))
            product_cost = units * cost
            profit = net_accrual - product_cost - tax
            if not all(isfinite(v) for v in (product_cost, profit)):
                return self._quantity_error("PERIOD_PROFIT_SALE_QUANTITY_RESULT_INVALID")

            next_row = dict(row)
            next_row["units_sold"] = units
            next_row["product_cost"] = round(product_cost, 2)
            next_row["profit"] = round(profit, 2)
            next_row["margin_percent"] = self._margin(
                next_row["profit"],
                revenue,
            )
            if next_row["margin_percent"] is None:
                return self._quantity_error("PERIOD_PROFIT_SALE_QUANTITY_RESULT_INVALID")
            next_rows.append(next_row)
            covered_skus.add(sku)
            total_units += units
            total_product_cost += product_cost

        if any(sku not in covered_skus for sku in units_by_sku):
            return self._quantity_error("PERIOD_PROFIT_SALE_QUANTITY_SKU_SCOPE_INCOMPLETE")

        net_accrual = self._number(result.get("net_accrual"), missing_zero=True)
        tax = self._number(result.get("tax"), missing_zero=True)
        revenue = self._number(result.get("revenue"), missing_zero=True)
        if None in (net_accrual, tax, revenue):
            return self._quantity_error("PERIOD_PROFIT_SALE_QUANTITY_RESULT_INVALID")

        profit = net_accrual - total_product_cost - tax
        if not isfinite(profit):
            return self._quantity_error("PERIOD_PROFIT_SALE_QUANTITY_RESULT_INVALID")

        enriched = dict(result)
        enriched["products"] = next_rows
        enriched["units_sold"] = total_units
        enriched["product_cost"] = round(total_product_cost, 2)
        enriched["profit"] = round(profit, 2)
        enriched["margin_percent"] = self._margin(enriched["profit"], revenue)
        if enriched["margin_percent"] is None:
            return self._quantity_error("PERIOD_PROFIT_SALE_QUANTITY_RESULT_INVALID")
        enriched["sale_quantity_reconciled"] = True
        enriched["sale_quantity_source"] = (
            "OZON_REALIZATION_POSTING_OR_EXACT_POSTING_DETAIL"
        )
        enriched["sale_quantity_record_count"] = len(grouped)
        return enriched

    def _load_realization_quantity_map(self, start, end):
        client = self.sale_quantity_ozon_client
        getter = getattr(client, "get_realization_posting", None)
        if not callable(getter):
            return None

        combined = {}
        for year, month in self._evidence_months(start, end):
            key = (year, month)
            if key not in self._realization_quantity_cache:
                try:
                    response = getter(year, month)
                except Exception:
                    response = None
                self._realization_quantity_cache[key] = self._parse_realization(response)
            month_map = self._realization_quantity_cache[key]
            if month_map is None:
                continue
            for posting_key, quantity in month_map.items():
                existing = combined.get(posting_key)
                if existing is not None and existing != quantity:
                    return None
                combined[posting_key] = quantity
        return combined

    @classmethod
    def _parse_realization(cls, response):
        if not isinstance(response, dict) or response.get("error") is True:
            return None
        rows = response.get("rows")
        if not isinstance(rows, list):
            result = response.get("result")
            rows = result.get("rows") if isinstance(result, dict) else None
        if not isinstance(rows, list):
            return None

        parsed = {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            order = row.get("order") or {}
            item = row.get("item") or {}
            delivery = row.get("delivery_commission") or {}
            posting_number = str(order.get("posting_number") or "").strip()
            sku = str(item.get("sku") or "").strip()
            quantity = cls._quantity(delivery.get("quantity"))
            if not posting_number or not sku or quantity is None:
                continue
            key = (posting_number, sku)
            existing = parsed.get(key)
            if existing is not None and existing != quantity:
                return None
            parsed[key] = quantity
        return parsed

    def _load_posting_quantity(self, posting_number, sku):
        key = (posting_number, sku)
        if key in self._posting_quantity_cache:
            return self._posting_quantity_cache[key]

        client = self.sale_quantity_ozon_client
        quantity = None
        for method_name in ("get_fbo_posting", "get_fbs_posting"):
            getter = getattr(client, method_name, None)
            if not callable(getter):
                continue
            try:
                response = getter(posting_number)
            except Exception:
                continue
            quantity = self._quantity_from_posting_response(
                response,
                posting_number,
                sku,
            )
            if quantity is not None:
                break

        self._posting_quantity_cache[key] = quantity
        return quantity

    @classmethod
    def _quantity_from_posting_response(cls, response, posting_number, sku):
        if not isinstance(response, dict) or response.get("error") is True:
            return None
        result = response.get("result")
        if not isinstance(result, dict):
            result = response
        returned = str(result.get("posting_number") or "").strip()
        products = result.get("products")
        if returned and returned != posting_number:
            return None
        if not isinstance(products, list):
            return None

        quantities = []
        for product in products:
            if not isinstance(product, dict):
                continue
            if str(product.get("sku") or "").strip() != sku:
                continue
            quantity = cls._quantity(product.get("quantity"))
            if quantity is not None:
                quantities.append(quantity)
        if len(quantities) != 1:
            return None
        return quantities[0]

    @staticmethod
    def _quantity(value):
        if isinstance(value, bool):
            return None
        try:
            quantity = int(value)
        except (TypeError, ValueError):
            return None
        return quantity if quantity > 0 else None

    @classmethod
    def _evidence_months(cls, start, end):
        first = cls._shift_month(date(start.year, start.month, 1), -1)
        last = cls._shift_month(date(end.year, end.month, 1), 1)
        months = []
        current = first
        while current <= last:
            months.append((current.year, current.month))
            current = cls._shift_month(current, 1)
        return months

    @staticmethod
    def _shift_month(value, delta):
        number = value.year * 12 + (value.month - 1) + delta
        return date(number // 12, number % 12 + 1, 1)

    @staticmethod
    def _quantity_error(code):
        return {
            "error": True,
            "code": code,
            "status": "PERIOD_PROFIT_SALE_QUANTITY_UNAVAILABLE",
            "message": "Данные о количестве проданных товаров недоступны",
            "complete": False,
            "read_only": True,
            "executed": False,
        }
