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

        products = self.product_service.load_products()
        period = self.analytics_service.get_period()

        if (
            not products
            or period.get("error")
            or not period.get("days")
        ):
            return {
                "low_stock": False
            }

        for product in products:
            if isinstance(product, dict):
                product_id = product.get("product_id")
                sku = product.get("sku")
            else:
                product_id = product[0]
                sku = product[2]

            if product_id is None or sku is None:
                continue

            metrics_result = (
                self.metrics_service
                .get_product_metrics(product_id)
            )

            if metrics_result.get("error"):
                continue

            current_stock = (
                metrics_result
                .get("metrics", {})
                .get("fbo_available")
            )

            if current_stock is None:
                continue

            sales_result = (
                self.analytics_service
                .analyze_finance(sku=sku)
            )

            if sales_result.get("error"):
                continue

            sales_count = sales_result.get("sales_count")

            if sales_count is None:
                continue

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
                    "period_days": period.get("days")
                }
            }

        return {
            "low_stock": False
        }
