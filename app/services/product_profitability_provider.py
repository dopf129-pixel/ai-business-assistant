class ProductProfitabilityProvider:

    REQUIRED_FIELDS = (
        "product_id",
        "sku",
        "sales_count",
        "gross_sales",
        "total_cost",
        "gross_profit",
        "margin_percent"
    )

    def build(
        self,
        profits
    ):
        metrics = []

        for item in (profits or []):
            if not item or item.get("error"):
                continue

            if any(
                item.get(field) is None
                for field in self.REQUIRED_FIELDS
            ):
                continue

            metrics.append(
                {
                    "product_id": str(
                        item.get("product_id")
                    ),
                    "sku": str(
                        item.get("sku")
                    ),
                    "sales_count": int(
                        item.get("sales_count")
                    ),
                    "revenue": round(
                        float(
                            item.get("gross_sales")
                        ),
                        2
                    ),
                    "cost": round(
                        float(
                            item.get("total_cost")
                        ),
                        2
                    ),
                    "profit": round(
                        float(
                            item.get("gross_profit")
                        ),
                        2
                    ),
                    "margin": round(
                        float(
                            item.get("margin_percent")
                        ),
                        2
                    )
                }
            )

        return metrics
