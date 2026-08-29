from datetime import date, datetime, timedelta


class PeriodProfitSummaryService:
    """Read-only period profit aggregation over existing finance and cost services."""

    def __init__(self, finance_service, cost_service, tax_rate=0.06):
        self.finance_service = finance_service
        self.cost_service = cost_service
        self.tax_rate = float(tax_rate)

    def calculate(self, date_from, date_to, products):
        start = self._date(date_from)
        end = self._date(date_to)
        if start is None or end is None or start > end:
            return self._error("PERIOD_PROFIT_PERIOD_INVALID", "Некорректный период")

        rows = []
        totals = self._empty_totals()
        for product in products or []:
            if not isinstance(product, dict):
                continue
            sku = product.get("sku")
            offer_id = product.get("offer_id") or sku
            if sku is None:
                continue
            cost = self._resolve_cost(offer_id, product)
            if cost is None:
                return self._error("PERIOD_PROFIT_COST_UNAVAILABLE", f"Не указана себестоимость для {offer_id}")
            row = self._calculate_product(start, end, str(sku), str(offer_id), cost)
            if row.get("error"):
                return row
            rows.append(row)
            for key in totals:
                totals[key] += row[key]

        totals = {key: round(value, 2) for key, value in totals.items()}
        revenue = totals["revenue"]
        totals["margin_percent"] = round(totals["profit"] / revenue * 100, 2) if revenue else 0.0
        return {
            "error": False,
            "status": "PERIOD_PROFIT_SUMMARY_READY",
            "date_from": start.isoformat(),
            "date_to": end.isoformat(),
            "product_count": len(rows),
            "products": rows,
            **totals,
            "returns_included": False,
            "advertising_included": False,
            "storage_included": False,
            "profit_scope": "OZON_ACCRUALS_COST_AND_CONFIGURED_TAX_V1",
        }

    def _calculate_product(self, start, end, sku, offer_id, cost):
        values = self._empty_totals()
        current = start
        while current <= end:
            finance = self.finance_service.get_daily_finance(current.isoformat(), sku=sku)
            if not isinstance(finance, dict) or finance.get("error"):
                return self._error("PERIOD_PROFIT_FINANCE_UNAVAILABLE", f"Финансовые данные недоступны за {current.isoformat()}")
            sales = int(finance.get("sales_count") or 0)
            revenue = float(finance.get("gross_sales") or 0)
            net_accrual = float(finance.get("net_accrual") or 0)
            product_cost = sales * cost
            tax = revenue * self.tax_rate
            profit = net_accrual - product_cost - tax
            values["units_sold"] += sales
            values["revenue"] += revenue
            values["net_accrual"] += net_accrual
            values["product_cost"] += product_cost
            values["tax"] += tax
            values["profit"] += profit
            current += timedelta(days=1)
        rounded = {key: round(value, 2) for key, value in values.items()}
        rounded["margin_percent"] = round(rounded["profit"] / rounded["revenue"] * 100, 2) if rounded["revenue"] else 0.0
        return {"error": False, "sku": sku, "offer_id": offer_id, "cost_per_unit": round(cost, 2), **rounded}

    def _resolve_cost(self, offer_id, product):
        value = product.get("cost")
        if value is not None:
            return float(value)
        getter = getattr(self.cost_service, "get_cost", None)
        if getter is None:
            return None
        result = getter(offer_id)
        if isinstance(result, dict):
            result = result.get("cost")
        return float(result) if result is not None else None

    @staticmethod
    def _date(value):
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        try:
            return datetime.strptime(str(value), "%Y-%m-%d").date()
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _empty_totals():
        return {"units_sold": 0, "revenue": 0.0, "net_accrual": 0.0, "product_cost": 0.0, "tax": 0.0, "profit": 0.0}

    @staticmethod
    def _error(code, message):
        return {"error": True, "code": code, "status": "PERIOD_PROFIT_SUMMARY_UNAVAILABLE", "message": message}
