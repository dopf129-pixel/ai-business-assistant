class AssistantEntryService:


    def __init__(
        self,
        main_flow_service,
        product_service=None,
        period_profit_service=None,
        analytics_service=None,
        metrics_service=None
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

        self.metrics_service = (
            metrics_service
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


        finance_context = dict(
            (context or {}).get(
                "finance_context"
            )
            or
            {}
        )


        if finance_context:

            report[
                "finance_context"
            ] = finance_context


        stock_context = dict(
            (context or {}).get(
                "stock_context"
            )
            or
            {}
        )


        if stock_context:

            report[
                "stock_context"
            ] = stock_context

        else:

            stock_report = (
                self._build_stock_report()
            )

            if stock_report is not None:

                report.update(
                    stock_report
                )


        sales_report = (
            self._build_sales_report()
        )


        if sales_report:

            if finance_context:

                sales_report.pop(
                    "finance_context",
                    None
                )

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


    def _build_stock_report(
        self
    ):


        if not self.metrics_service:

            return None


        if not all(
            [
                self.product_service,
                self.analytics_service
            ]
        ):

            return {
                "low_stock": False
            }


        products = (
            self.product_service
            .load_products()
        )


        period = (
            self.analytics_service
            .get_period()
        )


        if (
            not products
            or period.get("error")
            or not period.get("days")
        ):

            return {
                "low_stock": False
            }


        for product in products:

            if isinstance(
                product,
                dict
            ):

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

            else:

                product_id = product[0]
                sku = product[2]


            if (
                product_id is None
                or sku is None
            ):

                continue


            metrics_result = (
                self.metrics_service
                .get_product_metrics(
                    product_id
                )
            )


            if metrics_result.get(
                "error"
            ):

                continue


            current_stock = (
                metrics_result
                .get(
                    "metrics",
                    {}
                )
                .get(
                    "fbo_available"
                )
            )


            if current_stock is None:

                continue


            sales_result = (
                self.analytics_service
                .analyze_finance(
                    sku=sku
                )
            )


            if sales_result.get(
                "error"
            ):

                continue


            sales_count = (
                sales_result.get(
                    "sales_count"
                )
            )


            if sales_count is None:

                continue


            if current_stock > sales_count:

                continue


            return {
                "low_stock": True,
                "stock_context": {
                    "stock_data": {
                        "product_id": str(
                            product_id
                        ),
                        "current_stock": (
                            current_stock
                        )
                    },
                    "sales_data": {
                        "product_id": str(
                            product_id
                        ),
                        "sales_count": (
                            sales_count
                        )
                    },
                    "period_days": (
                        period.get(
                            "days"
                        )
                    )
                }
            }


        return {
            "low_stock": False
        }


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


        result = {
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


        finance_data = (
            self._build_finance_data(
                current.get(
                    "profits",
                    []
                )
            )
        )

        previous_data = (
            self._build_finance_data(
                previous.get(
                    "profits",
                    []
                )
            )
        )


        if (
            finance_data
            and previous_data
        ):

            result[
                "finance_context"
            ] = {
                "finance_data": finance_data,
                "previous_data": previous_data
            }


        return result


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

        expenses = (
            revenue
            - profit
        )

        margin = (
            profit
            / revenue
            * 100
            if revenue
            else 0
        )


        return {
            "revenue": round(
                revenue,
                2
            ),
            "expenses": round(
                expenses,
                2
            ),
            "profit": round(
                profit,
                2
            ),
            "margin": round(
                margin,
                2
            )
        }
