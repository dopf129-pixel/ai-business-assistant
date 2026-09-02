import math


class StoreProfitService:

    def calculate(
        self,
        profits
    ):

        if not isinstance(
            profits,
            (list, tuple)
        ):

            return self._data_invalid()

        total_sales = 0
        total_gross_sales = 0.0
        total_net_accrual = 0.0
        total_cost = 0.0
        total_profit = 0.0

        profitable_products = 0
        loss_products = 0

        for profit in profits:

            if not isinstance(
                profit,
                dict
            ):

                return self._data_invalid()

            if profit.get("error"):
                continue

            sales_count = self._count(
                profit.get(
                    "sales_count",
                    0
                )
            )

            gross_sales = self._number(
                profit.get(
                    "gross_sales",
                    0
                )
            )

            net_accrual = self._number(
                profit.get(
                    "net_accrual",
                    0
                )
            )

            total_cost_value = self._number(
                profit.get(
                    "total_cost",
                    0
                )
            )

            gross_profit = self._number(
                profit.get(
                    "gross_profit",
                    0
                )
            )

            if (
                sales_count is None
                or gross_sales is None
                or net_accrual is None
                or total_cost_value is None
                or gross_profit is None
            ):

                return self._data_invalid()

            total_sales += sales_count
            total_gross_sales += gross_sales
            total_net_accrual += net_accrual
            total_cost += total_cost_value
            total_profit += gross_profit

            if not all(
                math.isfinite(value)
                for value in (
                    total_gross_sales,
                    total_net_accrual,
                    total_cost,
                    total_profit
                )
            ):

                return self._result_invalid()

            if gross_profit >= 0:
                profitable_products += 1
            else:
                loss_products += 1

        margin_percent = 0.0

        if total_gross_sales > 0:

            margin_percent = (
                total_profit
                / total_gross_sales
                * 100
            )

            if not math.isfinite(
                margin_percent
            ):

                return self._result_invalid()

        return {
            "sales_count": total_sales,
            "gross_sales": round(
                total_gross_sales,
                2
            ),
            "net_accrual": round(
                total_net_accrual,
                2
            ),
            "total_cost": round(
                total_cost,
                2
            ),
            "gross_profit": round(
                total_profit,
                2
            ),
            "margin_percent": round(
                margin_percent,
                2
            ),
            "profitable_products": profitable_products,
            "loss_products": loss_products
        }

    @staticmethod
    def _count(
        value
    ):

        if isinstance(
            value,
            bool
        ):

            return None

        try:
            number = float(
                value
            )
        except (
            TypeError,
            ValueError
        ):
            return None

        if (
            not math.isfinite(
                number
            )
            or number < 0
            or not number.is_integer()
        ):
            return None

        return int(
            number
        )

    @staticmethod
    def _number(
        value
    ):

        if isinstance(
            value,
            bool
        ):

            return None

        try:
            number = float(
                value
            )
        except (
            TypeError,
            ValueError
        ):
            return None

        if not math.isfinite(
            number
        ):
            return None

        return number

    @staticmethod
    def _data_invalid():

        return {
            "error": True,
            "code": "STORE_PROFIT_DATA_INVALID",
            "message": (
                "Некорректные данные о прибыли товаров"
            )
        }

    @staticmethod
    def _result_invalid():

        return {
            "error": True,
            "code": "STORE_PROFIT_RESULT_INVALID",
            "message": (
                "Некорректный итог прибыли магазина"
            )
        }
