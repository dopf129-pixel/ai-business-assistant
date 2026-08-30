from math import isfinite


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
        normalized_products = self._normalize_products(
            products
        )

        if not normalized_products:
            return self._unavailable_result()

        current_period = (
            self.analytics_service
            .get_period()
        )
        previous_period = (
            self.analytics_service
            .get_previous_period()
        )

        if (
            not self._valid_period(current_period)
            or not self._valid_period(previous_period)
        ):
            return self._unavailable_result()

        current = (
            self.period_profit_service
            .calculate_period_profit(
                current_period.get("date_from"),
                current_period.get("date_to"),
                normalized_products
            )
        )
        previous = (
            self.period_profit_service
            .calculate_period_profit(
                previous_period.get("date_from"),
                previous_period.get("date_to"),
                normalized_products
            )
        )

        if (
            not self._valid_profit_result(current)
            or not self._valid_profit_result(previous)
        ):
            return self._unavailable_result()

        period_data = {
            "current_profits": list(
                current.get("profits")
            ),
            "previous_profits": list(
                previous.get("profits")
            )
        }

        previous_result = (
            self.analytics_service
            .analyze(
                previous.get("profits")
            )
        )

        if not self._valid_analysis_result(
            previous_result
        ):
            return self._unavailable_result(
                period_data=period_data
            )

        current_result = (
            self.analytics_service
            .analyze(
                current.get("profits"),
                previous_result=previous_result
            )
        )

        if not self._valid_analysis_result(
            current_result
        ):
            return self._unavailable_result(
                period_data=period_data
            )

        change_percent = self._revenue_change(
            current_result
        )

        if change_percent is None:
            return self._unavailable_result(
                period_data=period_data
            )

        sales_context = {
            "profits": list(
                current.get("profits")
            ),
            "previous_result": previous_result
        }

        if change_percent < 0:
            return {
                "report": {
                    "sales_down": True,
                    "sales_context": sales_context
                },
                "period_data": period_data
            }

        return {
            "report": {
                "sales_down": False,
                "sales_evidence_available": True,
                "sales_context": sales_context
            },
            "period_data": period_data
        }

    def _unavailable_result(
        self,
        period_data=None
    ):
        return {
            "report": {
                "sales_down": False,
                "sales_evidence_available": False
            },
            "period_data": period_data
        }

    def _normalize_products(
        self,
        products
    ):
        if (
            not isinstance(
                products,
                (list, tuple)
            )
            or not products
        ):
            return None

        normalized = []

        for product in products:
            if isinstance(
                product,
                dict
            ):
                product_id = product.get(
                    "product_id"
                )
                sku = product.get(
                    "sku"
                )

                if (
                    product_id is None
                    or sku is None
                ):
                    return None

                normalized.append(
                    dict(product)
                )
                continue

            if (
                not isinstance(
                    product,
                    (list, tuple)
                )
                or len(product) < 3
            ):
                return None

            product_id = product[0]
            sku = product[2]

            if (
                product_id is None
                or sku is None
            ):
                return None

            normalized.append(
                {
                    "product_id": product_id,
                    "offer_id": product[1],
                    "sku": sku
                }
            )

        return normalized

    def _valid_period(
        self,
        period
    ):
        if (
            not isinstance(period, dict)
            or period.get("error")
        ):
            return False

        return (
            period.get("date_from") is not None
            and period.get("date_to") is not None
        )

    def _valid_profit_result(
        self,
        result
    ):
        if (
            not isinstance(result, dict)
            or result.get("error")
        ):
            return False

        profits = result.get(
            "profits"
        )

        if (
            not isinstance(
                profits,
                (list, tuple)
            )
            or not profits
        ):
            return False

        for item in profits:
            if (
                not isinstance(item, dict)
                or item.get("error")
            ):
                return False

            if self._number(
                item.get("gross_sales")
            ) is None:
                return False

        return True

    def _valid_analysis_result(
        self,
        result
    ):
        return (
            isinstance(result, dict)
            and not result.get("error")
        )

    def _revenue_change(
        self,
        result
    ):
        comparison = result.get(
            "comparison"
        )

        if (
            not isinstance(comparison, dict)
            or comparison.get("error")
        ):
            return None

        comparison_items = comparison.get(
            "comparison"
        )

        if not isinstance(
            comparison_items,
            dict
        ):
            return None

        revenue = comparison_items.get(
            "revenue"
        )

        if not isinstance(
            revenue,
            dict
        ):
            return None

        return self._number(
            revenue.get(
                "change_percent"
            )
        )

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
