from services.finance_analytics_service import (
    FinanceAnalyticsService
)


class StorePeriodProfitService:

    def __init__(
        self,
        finance_service,
        cost_service,
        profit_service
    ):

        self.finance_analytics = (
            FinanceAnalyticsService(
                finance_service
            )
        )

        self.cost_service = (
            cost_service
        )

        self.profit_service = (
            profit_service
        )


    def calculate_period_profit(
        self,
        date_from,
        date_to,
        products
    ):

        if not products:

            return {
                "error": False,
                "products_count": 0,
                "profits": []
            }


        profits = []


        for product in products:

            product_id = (
                product.get(
                    "product_id"
                )
            )

            sku = (
                product.get(
                    "sku"
                )
            )


            if sku is None:

                continue


            finance = (
                self.finance_analytics
                .get_period_finance(
                    date_from,
                    date_to,
                    sku
                )
            )


            if finance.get(
                "error"
            ):

                continue


            cost = (
                self.cost_service
                .get_cost(
                    product_id
                )
            )


            if not cost:

                continue


            profit = (
                self.profit_service
                .calculate(
                    finance,
                    cost[3]
                )
            )


            if profit.get(
                "error"
            ):

                continue


            profit = dict(
                profit
            )

            profit[
                "product_id"
            ] = product_id

            profit[
                "sku"
            ] = sku


            for field in (
                "commission",
                "logistics",
                "acquiring",
                "other_fees"
            ):

                profit[field] = (
                    finance.get(field)
                )


            profit[
                "fee_breakdown"
            ] = dict(
                finance.get(
                    "fee_breakdown",
                    {}
                )
                or {}
            )


            profits.append(
                profit
            )


        return {
            "error": False,
            "products_count": len(
                profits
            ),
            "profits": profits
        }