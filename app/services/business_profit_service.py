class BusinessProfitService:

    def calculate(
        self,
        store_profit,
        tax,
        advertising_cost=0,
        other_expenses=0
    ):

        if not store_profit:

            return {
                "error": True,
                "message": (
                    "Нет данных о прибыли магазина"
                )
            }

        if tax.get("error"):

            return {
                "error": True,
                "message": tax.get(
                    "message",
                    "Не удалось рассчитать налог"
                )
            }

        gross_sales = float(
            store_profit.get(
                "gross_sales",
                0
            )
        )

        gross_profit = float(
            store_profit.get(
                "gross_profit",
                0
            )
        )

        tax_amount = float(
            tax.get(
                "tax_amount",
                0
            )
        )

        advertising_cost = float(
            advertising_cost or 0
        )

        other_expenses = float(
            other_expenses or 0
        )

        business_profit = (
            gross_profit
            - tax_amount
            - advertising_cost
            - other_expenses
        )

        margin_percent = 0.0

        if gross_sales > 0:

            margin_percent = (
                business_profit
                / gross_sales
                * 100
            )

        return {
            "error": False,
            "gross_sales": round(
                gross_sales,
                2
            ),
            "gross_profit": round(
                gross_profit,
                2
            ),
            "tax_amount": round(
                tax_amount,
                2
            ),
            "advertising_cost": round(
                advertising_cost,
                2
            ),
            "other_expenses": round(
                other_expenses,
                2
            ),
            "business_profit": round(
                business_profit,
                2
            ),
            "margin_percent": round(
                margin_percent,
                2
            )
        }