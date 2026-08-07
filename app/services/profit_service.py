class ProfitService:

    def calculate(
        self,
        finance,
        cost_price
    ):

        if finance.get("error"):

            return {
                "error": True,
                "message": finance.get(
                    "message",
                    "Финансовые данные недоступны"
                )
            }

        sales_count = int(
            finance.get(
                "sales_count",
                0
            )
        )

        gross_sales = float(
            finance.get(
                "gross_sales",
                0
            )
        )

        net_accrual = float(
            finance.get(
                "net_accrual",
                0
            )
        )

        cost_price = float(
            cost_price or 0
        )

        total_cost = (
            sales_count
            * cost_price
        )

        gross_profit = (
            net_accrual
            - total_cost
        )

        profit_per_unit = 0.0

        if sales_count > 0:

            profit_per_unit = (
                gross_profit
                / sales_count
            )

        margin_percent = 0.0

        if gross_sales > 0:

            margin_percent = (
                gross_profit
                / gross_sales
                * 100
            )

        return {
            "error": False,
            "sales_count": sales_count,
            "gross_sales": round(
                gross_sales,
                2
            ),
            "cost_price": round(
                cost_price,
                2
            ),
            "total_cost": round(
                total_cost,
                2
            ),
            "net_accrual": round(
                net_accrual,
                2
            ),
            "gross_profit": round(
                gross_profit,
                2
            ),
            "profit_per_unit": round(
                profit_per_unit,
                2
            ),
            "margin_percent": round(
                margin_percent,
                2
            )
        }