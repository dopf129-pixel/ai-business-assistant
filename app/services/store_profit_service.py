class StoreProfitService:

    def calculate(
        self,
        profits
    ):

        total_sales = 0
        total_gross_sales = 0.0
        total_net_accrual = 0.0
        total_cost = 0.0
        total_profit = 0.0

        profitable_products = 0
        loss_products = 0

        for profit in profits:

            if profit.get("error"):
                continue

            total_sales += int(
                profit.get(
                    "sales_count",
                    0
                )
            )

            total_gross_sales += float(
                profit.get(
                    "gross_sales",
                    0
                )
            )

            total_net_accrual += float(
                profit.get(
                    "net_accrual",
                    0
                )
            )

            total_cost += float(
                profit.get(
                    "total_cost",
                    0
                )
            )

            gross_profit = float(
                profit.get(
                    "gross_profit",
                    0
                )
            )

            total_profit += gross_profit

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