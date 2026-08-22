class AssistantEntryService:


    def __init__(
        self,
        main_flow_service,
        product_service=None,
        period_profit_service=None,
        analytics_service=None
    ):

        self.main_flow_service = (
            main_flow_service
        )

        self.product_service = (
            product_service
        )

        self.period_profit_service = (
            period_profit_service
        )

        self.analytics_service = (
            analytics_service
        )



    def handle(
        self,
        text,
        context=None,
        user_id=None
    ):


        report = {
            "sales_down": True,
            "low_stock": True
        }


        sales_report = (
            self._build_sales_report()
        )


        if sales_report:

            report.update(
                sales_report
            )



        return (
            self.main_flow_service
            .process(
                text,
                report,
                context,
                user_id
            )
        )


    def _build_sales_report(
        self
    ):


        if not all(
            [
                self.product_service,
                self.period_profit_service,
                self.analytics_service
            ]
        ):

            return None


        products = (
            self.product_service
            .load_products()
        )


        normalized_products = []


        for product in products:

            if isinstance(
                product,
                dict
            ):

                normalized_products.append(
                    product
                )

                continue


            normalized_products.append(
                {
                    "product_id": product[0],
                    "offer_id": product[1],
                    "sku": product[2]
                }
            )


        current_period = (
            self.analytics_service
            .get_period()
        )

        previous_period = (
            self.analytics_service
            .get_previous_period()
        )


        if (
            current_period.get("error")
            or previous_period.get("error")
        ):

            return None


        current = (
            self.period_profit_service
            .calculate_period_profit(
                current_period.get(
                    "date_from"
                ),
                current_period.get(
                    "date_to"
                ),
                normalized_products
            )
        )

        previous = (
            self.period_profit_service
            .calculate_period_profit(
                previous_period.get(
                    "date_from"
                ),
                previous_period.get(
                    "date_to"
                ),
                normalized_products
            )
        )


        if (
            current.get("error")
            or previous.get("error")
        ):

            return None


        previous_result = (
            self.analytics_service
            .analyze(
                previous.get(
                    "profits",
                    []
                )
            )
        )


        if previous_result.get(
            "error"
        ):

            return None


        current_result = (
            self.analytics_service
            .analyze(
                current.get(
                    "profits",
                    []
                ),
                previous_result=(
                    previous_result
                )
            )
        )


        if current_result.get(
            "error"
        ):

            return None


        revenue_comparison = (
            current_result
            .get(
                "comparison",
                {}
            )
            .get(
                "comparison",
                {}
            )
            .get(
                "revenue",
                {}
            )
        )


        return {
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
        }
