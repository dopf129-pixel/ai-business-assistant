from math import isfinite


class StockContextProvider:

    def __init__(
        self,
        product_service=None,
        analytics_service=None,
        metrics_service=None
    ):
        self.product_service = product_service
        self.analytics_service = analytics_service
        self.metrics_service = metrics_service

    def build(self):
        if not all(
            [
                self.product_service,
                self.analytics_service,
                self.metrics_service
            ]
        ):
            return self._unavailable_result()

        products = self.product_service.load_products()

        if not isinstance(
            products,
            (list, tuple)
        ) or not products:
            return self._unavailable_result()

        period = self.analytics_service.get_period()

        if not isinstance(
            period,
            dict
        ) or period.get("error"):
            return self._unavailable_result()

        period_days = self._positive_number(
            period.get("days")
        )

        if period_days is None:
            return self._unavailable_result()

        evidence_complete = True
        checked_products = 0

        for product in products:
            target = self._product_target(
                product
            )

            if target is None:
                evidence_complete = False
                continue

            product_id, sku = target

            metrics_result = (
                self.metrics_service
                .get_product_metrics(product_id)
            )

            if (
                not isinstance(metrics_result, dict)
                or metrics_result.get("error")
            ):
                evidence_complete = False
                continue

            metrics = metrics_result.get(
                "metrics"
            )

            if not isinstance(
                metrics,
                dict
            ):
                evidence_complete = False
                continue

            current_stock = self._non_negative_number(
                metrics.get("fbo_available")
            )

            if current_stock is None:
                evidence_complete = False
                continue

            sales_result = (
                self.analytics_service
                .analyze_finance(sku=sku)
            )

            if (
                not isinstance(sales_result, dict)
                or sales_result.get("error")
            ):
                evidence_complete = False
                continue

            sales_count = self._non_negative_number(
                sales_result.get("sales_count")
            )

            if sales_count is None:
                evidence_complete = False
                continue

            checked_products += 1

            if current_stock > sales_count:
                continue

            return {
                "low_stock": True,
                "stock_context": {
                    "stock_data": {
                        "product_id": str(product_id),
                        "current_stock": current_stock
                    },
                    "sales_data": {
                        "product_id": str(product_id),
                        "sales_count": sales_count
                    },
                    "period_days": period_days
                }
            }

        if (
            not evidence_complete
            or checked_products != len(products)
        ):
            return self._unavailable_result()

        return {
            "low_stock": False,
            "stock_evidence_available": True
        }

    def _unavailable_result(self):
        return {
            "low_stock": False,
            "stock_evidence_available": False
        }

    def _product_target(
        self,
        product
    ):
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
        elif (
            isinstance(product, (list, tuple))
            and len(product) >= 3
        ):
            product_id = product[0]
            sku = product[2]
        else:
            return None

        if product_id is None or sku is None:
            return None

        return product_id, sku

    def _positive_number(
        self,
        value
    ):
        number = self._number(
            value
        )

        if number is None or number <= 0:
            return None

        return number

    def _non_negative_number(
        self,
        value
    ):
        number = self._number(
            value
        )

        if number is None or number < 0:
            return None

        return number

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
            number = float(value)
        except (
            TypeError,
            ValueError
        ):
            return None

        if not isfinite(
            number
        ):
            return None

        if number.is_integer():
            return int(number)

        return number
