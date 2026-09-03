from datetime import date, datetime, timedelta
from math import isfinite


class PeriodProfitSummaryService:
    """Read-only period profit aggregation over existing finance and cost services."""

    DAILY_AMOUNT_FIELDS = (
        "gross_sales",
        "net_accrual",
        "commission",
        "logistics",
        "acquiring",
        "other_fees",
    )

    TOTAL_AMOUNT_FIELDS = (
        "revenue",
        "net_accrual",
        "commission",
        "logistics",
        "acquiring",
        "other_fees",
        "product_cost",
        "tax",
        "profit",
    )

    def __init__(self, finance_service, cost_service, tax_rate=0.06):
        self.finance_service = finance_service
        self.cost_service = cost_service
        self.tax_rate = self._non_negative_number(tax_rate)

    def calculate(self, date_from, date_to, products):
        start = self._date(date_from)
        end = self._date(date_to)
        if start is None or end is None or start > end:
            return self._error(
                "PERIOD_PROFIT_PERIOD_INVALID",
                "Некорректный период",
            )

        if self.tax_rate is None:
            return self._error(
                "PERIOD_PROFIT_TAX_RATE_INVALID",
                "Некорректная ставка налога для расчёта периода",
            )

        normalized_products = []

        for product in products or []:
            normalized = self._normalize_product(
                product
            )
            if normalized is not None:
                normalized_products.append(
                    normalized
                )

        if not normalized_products:
            return self._error(
                "PERIOD_PROFIT_PRODUCTS_UNAVAILABLE",
                "Нет пригодных товаров для расчёта периода",
            )

        rows = []
        totals = self._empty_totals()
        fee_breakdown = {}

        for product in normalized_products:

            sku = product.get("sku")
            offer_id = product.get("offer_id") or sku
            if sku is None:
                continue

            cost, cost_state = self._resolve_cost(product)
            if cost_state == "MISSING":
                return self._error(
                    "PERIOD_PROFIT_COST_UNAVAILABLE",
                    f"Не указана себестоимость для {offer_id}",
                )
            if cost_state == "UNAVAILABLE":
                return self._error(
                    "PERIOD_PROFIT_COST_UNAVAILABLE",
                    f"Себестоимость недоступна для {offer_id}",
                )
            if cost_state == "INVALID":
                return self._error(
                    "PERIOD_PROFIT_COST_INVALID",
                    f"Некорректная себестоимость для {offer_id}",
                )

            row = self._calculate_product(
                start,
                end,
                str(sku),
                str(offer_id),
                cost,
            )
            if row.get("error"):
                return row

            if not self._merge_totals(totals, row):
                return self._aggregate_error()

            if not self._merge_fee_breakdown(
                fee_breakdown,
                row.get("fee_breakdown"),
            ):
                return self._aggregate_error()

            rows.append(row)

        rounded = self._rounded_totals(totals)
        if rounded is None:
            return self._aggregate_error()

        fee_breakdown = self._rounded_breakdown(fee_breakdown)
        if fee_breakdown is None:
            return self._aggregate_error()

        margin = self._margin(
            rounded["profit"],
            rounded["revenue"],
        )
        if margin is None:
            return self._aggregate_error()

        rounded["margin_percent"] = margin

        return {
            "error": False,
            "status": "PERIOD_PROFIT_SUMMARY_READY",
            "date_from": start.isoformat(),
            "date_to": end.isoformat(),
            "product_count": len(rows),
            "products": rows,
            **rounded,
            "fee_breakdown": fee_breakdown,
            "returns_included": False,
            "advertising_included": False,
            "storage_included": False,
            "fee_components_included": True,
            "profit_scope": (
                "OZON_ACCRUALS_COST_AND_CONFIGURED_TAX_V1"
            ),
        }

    def _calculate_product(
        self,
        start,
        end,
        sku,
        offer_id,
        cost,
    ):
        values = self._empty_totals()
        fee_breakdown = {}
        current = start

        while current <= end:
            try:
                finance = self.finance_service.get_daily_finance(
                    current.isoformat(),
                    sku=sku,
                )
            except Exception:
                return self._error(
                    "PERIOD_PROFIT_FINANCE_UNAVAILABLE",
                    (
                        "Финансовые данные недоступны за "
                        f"{current.isoformat()}"
                    ),
                )

            if not isinstance(finance, dict):
                return self._finance_invalid(current)

            error_marker = finance.get("error")
            if (
                error_marker is not None
                and type(error_marker) is not bool
            ):
                return self._finance_invalid(current)

            if error_marker is True:
                return self._error(
                    "PERIOD_PROFIT_FINANCE_UNAVAILABLE",
                    (
                        "Финансовые данные недоступны за "
                        f"{current.isoformat()}"
                    ),
                )

            sales = self._count(
                finance.get("sales_count")
            )
            if sales is None:
                return self._finance_invalid(current)

            amounts = {}
            for field in self.DAILY_AMOUNT_FIELDS:
                amount = self._number(
                    finance.get(field),
                    missing_zero=True,
                )
                if amount is None:
                    return self._finance_invalid(current)
                amounts[field] = amount

            daily_fee_breakdown = self._normalize_fee_breakdown(
                finance.get("fee_breakdown")
            )
            if daily_fee_breakdown is None:
                return self._finance_invalid(current)

            try:
                product_cost = sales * cost
                tax = amounts["gross_sales"] * self.tax_rate
                profit = (
                    amounts["net_accrual"]
                    - product_cost
                    - tax
                )
            except (OverflowError, TypeError, ValueError):
                return self._aggregate_error()

            if not all(
                isfinite(value)
                for value in (
                    product_cost,
                    tax,
                    profit,
                )
            ):
                return self._aggregate_error()

            increments = {
                "revenue": amounts["gross_sales"],
                "net_accrual": amounts["net_accrual"],
                "commission": amounts["commission"],
                "logistics": amounts["logistics"],
                "acquiring": amounts["acquiring"],
                "other_fees": amounts["other_fees"],
                "product_cost": product_cost,
                "tax": tax,
                "profit": profit,
            }

            next_values = dict(values)
            next_values["units_sold"] = (
                values["units_sold"] + sales
            )

            for key, amount in increments.items():
                candidate = values[key] + amount
                if not isfinite(candidate):
                    return self._aggregate_error()
                next_values[key] = candidate

            next_fee_breakdown = dict(fee_breakdown)
            if not self._merge_fee_breakdown(
                next_fee_breakdown,
                daily_fee_breakdown,
            ):
                return self._aggregate_error()

            values = next_values
            fee_breakdown = next_fee_breakdown
            current += timedelta(days=1)

        rounded = self._rounded_totals(values)
        if rounded is None:
            return self._aggregate_error()

        rounded_fee_breakdown = self._rounded_breakdown(
            fee_breakdown
        )
        if rounded_fee_breakdown is None:
            return self._aggregate_error()

        margin = self._margin(
            rounded["profit"],
            rounded["revenue"],
        )
        if margin is None:
            return self._aggregate_error()

        rounded["margin_percent"] = margin

        return {
            "error": False,
            "sku": sku,
            "offer_id": offer_id,
            "cost_per_unit": round(cost, 2),
            **rounded,
            "fee_breakdown": rounded_fee_breakdown,
        }

    def _merge_totals(self, target, source):
        units = source.get("units_sold")
        if (
            not isinstance(units, int)
            or isinstance(units, bool)
            or units < 0
        ):
            return False

        next_values = dict(target)
        next_values["units_sold"] = (
            target["units_sold"] + units
        )

        for key in self.TOTAL_AMOUNT_FIELDS:
            amount = source.get(key)
            if (
                isinstance(amount, bool)
                or not isinstance(amount, (int, float))
                or not isfinite(float(amount))
            ):
                return False

            candidate = target[key] + float(amount)
            if not isfinite(candidate):
                return False

            next_values[key] = candidate

        target.clear()
        target.update(next_values)
        return True

    @staticmethod
    def _merge_fee_breakdown(target, source):
        if not isinstance(source, dict):
            return False

        next_values = dict(target)
        for name, amount in source.items():
            if (
                isinstance(amount, bool)
                or not isinstance(amount, (int, float))
                or not isfinite(float(amount))
            ):
                return False

            key = str(name)
            candidate = (
                next_values.get(key, 0.0)
                + float(amount)
            )
            if not isfinite(candidate):
                return False

            next_values[key] = candidate

        target.clear()
        target.update(next_values)
        return True

    def _normalize_fee_breakdown(self, source):
        if source is None:
            return {}

        if not isinstance(source, dict):
            return None

        result = {}
        for name, amount in source.items():
            value = self._number(
                amount,
                missing_zero=True,
            )
            if value is None:
                return None
            result[str(name)] = value

        return result

    @staticmethod
    def _normalize_product(product):
        if isinstance(product, dict):
            if (
                product.get("product_id") is None
                and product.get("sku") is None
                and product.get("offer_id") is None
            ):
                return None
            return dict(product)

        if isinstance(product, (tuple, list)):
            if len(product) < 3:
                return None

            product_id = product[0]
            offer_id = product[1]
            sku = product[2]

            if (
                product_id is None
                and offer_id is None
                and sku is None
            ):
                return None

            return {
                "product_id": product_id,
                "offer_id": offer_id,
                "sku": sku,
            }

        return None


    def _resolve_cost(self, product):
        for field in ("cost", "cost_price"):
            value = product.get(field)
            if value is not None:
                number = self._non_negative_number(value)
                if number is None:
                    return None, "INVALID"
                return number, None

        getter = getattr(
            self.cost_service,
            "get_cost",
            None,
        )
        if getter is None:
            return None, "MISSING"

        product_id = product.get("product_id")
        if product_id is None:
            return None, "MISSING"

        try:
            result = getter(product_id)
        except Exception:
            return None, "UNAVAILABLE"

        if isinstance(result, dict):
            value = result.get("cost_price")
            if value is None:
                value = result.get("cost")
        elif isinstance(result, (tuple, list)):
            if len(result) <= 3:
                return None, "INVALID"
            value = result[3]
        else:
            value = result

        if value is None:
            return None, "MISSING"

        number = self._non_negative_number(value)
        if number is None:
            return None, "INVALID"

        return number, None

    @staticmethod
    def _count(value):
        if value is None or value == "":
            return 0

        if isinstance(value, bool):
            return None

        if isinstance(value, int):
            return value if value >= 0 else None

        try:
            number = float(value)
        except (TypeError, ValueError, OverflowError):
            return None

        if (
            not isfinite(number)
            or number < 0
            or not number.is_integer()
        ):
            return None

        return int(number)

    @staticmethod
    def _number(value, missing_zero=False):
        if value is None or value == "":
            return 0.0 if missing_zero else None

        if isinstance(value, bool):
            return None

        try:
            number = float(value)
        except (TypeError, ValueError, OverflowError):
            return None

        if not isfinite(number):
            return None

        return number

    @classmethod
    def _non_negative_number(cls, value):
        number = cls._number(value)
        if number is None or number < 0:
            return None
        return number

    @staticmethod
    def _rounded_totals(values):
        result = {
            "units_sold": values["units_sold"],
        }

        for key, value in values.items():
            if key == "units_sold":
                continue
            if not isfinite(value):
                return None
            result[key] = round(value, 2)

        return result

    @staticmethod
    def _rounded_breakdown(values):
        result = {}
        for key, value in values.items():
            if not isfinite(value):
                return None
            result[key] = round(value, 2)
        return result

    @staticmethod
    def _margin(profit, revenue):
        if revenue == 0:
            return 0.0

        try:
            margin = profit / revenue * 100
        except (OverflowError, ZeroDivisionError):
            return None

        if not isfinite(margin):
            return None

        return round(margin, 2)

    @staticmethod
    def _date(value):
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        try:
            return datetime.strptime(
                str(value),
                "%Y-%m-%d",
            ).date()
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _empty_totals():
        return {
            "units_sold": 0,
            "revenue": 0.0,
            "net_accrual": 0.0,
            "commission": 0.0,
            "logistics": 0.0,
            "acquiring": 0.0,
            "other_fees": 0.0,
            "product_cost": 0.0,
            "tax": 0.0,
            "profit": 0.0,
        }

    def _finance_invalid(self, current):
        return self._error(
            "PERIOD_PROFIT_FINANCE_INVALID",
            (
                "Некорректные финансовые данные за "
                f"{current.isoformat()}"
            ),
        )

    def _aggregate_error(self):
        return self._error(
            "PERIOD_PROFIT_AGGREGATE_INVALID",
            "Некорректный итог прибыли за период",
        )

    @staticmethod
    def _error(code, message):
        return {
            "error": True,
            "code": code,
            "status": "PERIOD_PROFIT_SUMMARY_UNAVAILABLE",
            "message": message,
        }
