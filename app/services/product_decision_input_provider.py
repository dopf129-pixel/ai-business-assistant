class ProductDecisionInputProvider:

    IDENTITY_MISMATCH = "IDENTITY_MISMATCH"

    def build(
        self,
        sales_metrics=None,
        stock_metrics=None,
        unit_economics=None
    ):
        sales = dict(sales_metrics or {})
        stock = dict(stock_metrics or {})
        economics = dict(unit_economics or {})

        product_id = self._first_value(
            sales.get("product_id"),
            stock.get("product_id"),
            economics.get("product_id")
        )
        sku = self._first_value(
            sales.get("sku"),
            stock.get("sku"),
            economics.get("sku")
        )

        missing_data = self._merge_missing_data(
            sales.get("missing_data"),
            stock.get("missing_data"),
            economics.get("missing_data")
        )

        if self._identity_mismatch(
            product_id=product_id,
            sku=sku,
            sources=(sales, stock, economics)
        ):
            missing_data = self._append_unique(
                missing_data,
                self.IDENTITY_MISMATCH
            )

        result = {
            "product_id": product_id,
            "sku": sku,
            "sales_velocity": sales.get("sales_velocity"),
            "sales_trend": sales.get("sales_trend"),
            "current_stock": stock.get("current_stock"),
            "days_of_stock": stock.get("days_of_stock"),
            "stock_priority": self._first_value(
                stock.get("stock_priority"),
                stock.get("priority")
            ),
            "profit_per_unit": self._first_value(
                economics.get("profit_per_unit"),
                economics.get("net_profit_per_unit")
            ),
            "margin_percent": economics.get("margin_percent"),
            "missing_data": missing_data
        }

        for field in (
            "product_id",
            "sku",
            "sales_velocity",
            "sales_trend",
            "current_stock",
            "days_of_stock",
            "stock_priority",
            "profit_per_unit",
            "margin_percent"
        ):
            if result.get(field) is None:
                result["missing_data"] = self._append_unique(
                    result["missing_data"],
                    field
                )

        return result

    def _identity_mismatch(self, product_id, sku, sources):
        for source in sources:
            source_product_id = source.get("product_id")
            source_sku = source.get("sku")

            if (
                source_product_id is not None
                and product_id is not None
                and str(source_product_id) != str(product_id)
            ):
                return True

            if (
                source_sku is not None
                and sku is not None
                and str(source_sku) != str(sku)
            ):
                return True

        return False

    def _merge_missing_data(self, *groups):
        result = []

        for group in groups:
            for item in list(group or []):
                result = self._append_unique(result, item)

        return result

    def _append_unique(self, values, item):
        result = list(values)

        if item not in result:
            result.append(item)

        return result

    def _first_value(self, *values):
        for value in values:
            if value is not None:
                return value
        return None
