from math import isfinite


class FinanceContextProvider:

    PROFIT_SCOPE = "PERIOD_GROSS_PROFIT"

    def build(
        self,
        period_data
    ):
        if not isinstance(
            period_data,
            dict
        ):
            return None

        finance_data = self._build_finance_data(
            period_data.get(
                "current_profits",
                []
            )
        )
        previous_data = self._build_finance_data(
            period_data.get(
                "previous_profits",
                []
            )
        )

        if not finance_data or not previous_data:
            return None

        return {
            "finance_context": {
                "finance_data": finance_data,
                "previous_data": previous_data
            }
        }

    def _build_finance_data(
        self,
        profits
    ):
        if not isinstance(
            profits,
            (list, tuple)
        ):
            return None

        valid_profits = []

        for item in profits:
            if not isinstance(
                item,
                dict
            ):
                return None

            if item.get(
                "error"
            ):
                continue

            gross_sales = self._number(
                item.get(
                    "gross_sales"
                )
            )
            gross_profit = self._number(
                item.get(
                    "gross_profit"
                )
            )

            if (
                gross_sales is None
                or gross_profit is None
            ):
                return None

            valid_profits.append(
                (
                    gross_sales,
                    gross_profit
                )
            )

        if not valid_profits:
            return None

        revenue = sum(
            item[0]
            for item in valid_profits
        )
        profit = sum(
            item[1]
            for item in valid_profits
        )
        expenses = revenue - profit
        margin = (
            profit / revenue * 100
            if revenue
            else 0
        )

        return {
            "revenue": round(revenue, 2),
            "expenses": round(expenses, 2),
            "profit": round(profit, 2),
            "margin": round(margin, 2),
            "profit_scope": self.PROFIT_SCOPE
        }

    def _number(
        self,
        value
    ):
        if (
            value is None
            or isinstance(value, bool)
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

        if not isfinite(
            number
        ):
            return None

        return number
