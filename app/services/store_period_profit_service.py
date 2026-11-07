from services.finance_analytics_service import (
    FinanceAnalyticsService
)


class StorePeriodProfitService:

    def __init__(
        self,
        finance_service,
        cost_service,
        profit_service,
        fifo_cost_source_service=None,
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

        # The aggregate finance reader used here cannot prove per-sale FIFO
        # allocations. When a SKU has crossed its FIFO cutoff, never price it
        # from the legacy current-cost row.
        self.fifo_cost_source_service = fifo_cost_source_service


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

            if self.fifo_cost_source_service is not None:
                scope = self.fifo_cost_source_service.get_scope_mode(
                    product,
                    date_from=date_from,
                    date_to=date_to,
                )
                if (
                    not isinstance(scope, dict)
                    or scope.get("error") is True
                ):
                    return {
                        "error": True,
                        "code": "PERIOD_PROFIT_FIFO_SCOPE_UNAVAILABLE",
                        "products_count": 0,
                        "profits": [],
                    }
                if scope.get("active") is True:
                    return {
                        "error": True,
                        "code": "PERIOD_PROFIT_FIFO_ALLOCATION_REQUIRED",
                        "reason_code": scope.get("code"),
                        "products_count": 0,
                        "profits": [],
                    }
                if scope.get("active") is not False:
                    return {
                        "error": True,
                        "code": "PERIOD_PROFIT_FIFO_SCOPE_UNAVAILABLE",
                        "products_count": 0,
                        "profits": [],
                    }

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
