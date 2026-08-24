class SalesContextProvider:

    def __init__(
        self,
        product_service=None,
        period_profit_service=None,
        analytics_service=None
    ):
        self.product_service = product_service
        self.period_profit_service = period_profit_service
        self.analytics_service = analytics_service

    def build(self):
        if not all(
            [
                self.product_service,
                self.period_profit_service,
                self.analytics_service
            ]
        ):
            return {
                "report": None,
                "period_data": None
            }

        products = self.product_service.load_products()
        normalized_products = []

        for product in products:
            if isinstance(product, dict):
                normalized_products.append(product)
                continue

            normalized_products.append(
                {
                    "product_id": product[0],
                    "offer_id": product[1],
                    "sku": product[2]
                }
            )

        current_period = self.analytics_service.get_period()
        previous_period = self.analytics_service.get_previous_period()

        if (
            current_period.get("error")
            or previous_period.get("error")
        ):
            return {
                "report": None,
                "period_data": None
            }

        current = self.period_profit_service.calculate_period_profit(
            current_period.get("date_from"),
            current_period.get("date_to"),
            normalized_products
        )
        previous = self.period_profit_service.calculate_period_profit(
            previous_period.get("date_from"),
            previous_period.get("date_to"),
            normalized_products
        )

        if current.get("error") or previous.get("error"):
            return {
                "report": None,
                "period_data": None
            }

        previous_result = self.analytics_service.analyze(
            previous.get("profits", [])
        )

        if previous_result.get("error"):
            return {
                "report": None,
                "period_data": None
            }

        current_result = self.analytics_service.analyze(
            current.get("profits", []),
            previous_result=previous_result
        )

        if current_result.get("error"):
            return {
                "report": None,
                "period_data": None
            }

        revenue_comparison = (
            current_result
            .get("comparison", {})
            .get("comparison", {})
            .get("revenue", {})
        )

        return {
            "report": {
                "sales_down": (
                    revenue_comparison.get(
                        "change_percent",
                        0
                    )
                    < 0
                ),
                "sales_context": {
                    "profits": current.get(
                        "profits",
                        []
                    ),
                    "previous_result": previous_result
                }
            },
            "period_data": {
                "current_profits": current.get(
                    "profits",
                    []
                ),
                "previous_profits": previous.get(
                    "profits",
                    []
                )
            }
        }
