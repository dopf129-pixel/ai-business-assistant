class FinanceContextProvider:

    def build(
        self,
        period_data
    ):
        period_data = period_data or {}

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
        valid_profits = [
            profit
            for profit in (profits or [])
            if not profit.get("error")
        ]

        if not valid_profits:
            return None

        revenue = sum(
            float(
                profit.get(
                    "gross_sales",
                    0
                )
                or 0
            )
            for profit in valid_profits
        )
        profit = sum(
            float(
                item.get(
                    "gross_profit",
                    0
                )
                or 0
            )
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
            "margin": round(margin, 2)
        }
