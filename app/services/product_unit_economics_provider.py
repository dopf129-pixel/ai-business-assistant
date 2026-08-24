class ProductUnitEconomicsProvider:

    REQUIRED_FIELDS = (
        "product_id",
        "sku",
        "sales_count",
        "gross_sales",
        "total_cost",
        "net_accrual",
        "gross_profit"
    )

    def __init__(
        self,
        tax_service=None,
        tax_mode=None,
        tax_rate=None,
        minimum_tax_rate=1.0
    ):
        self.tax_service = tax_service
        self.tax_mode = tax_mode
        self.tax_rate = tax_rate
        self.minimum_tax_rate = minimum_tax_rate

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

            units_sold = int(
                item.get("sales_count")
            )
            revenue = float(
                item.get("gross_sales")
            )
            product_cost = float(
                item.get("total_cost")
            )
            net_accrual = float(
                item.get("net_accrual")
            )
            gross_profit = float(
                item.get("gross_profit")
            )

            marketplace_fees = (
                revenue - net_accrual
            )

            tax = self._calculate_tax(
                revenue=revenue,
                gross_profit=gross_profit
            )

            if tax is None:
                net_profit = None
                profit_per_unit = None
                margin_percent = None
            else:
                net_profit = gross_profit - tax
                profit_per_unit = (
                    net_profit / units_sold
                    if units_sold > 0
                    else 0.0
                )
                margin_percent = (
                    net_profit / revenue * 100
                    if revenue > 0
                    else 0.0
                )

            metrics.append(
                {
                    "product_id": str(
                        item.get("product_id")
                    ),
                    "sku": str(
                        item.get("sku")
                    ),
                    "units_sold": units_sold,
                    "revenue": round(
                        revenue,
                        2
                    ),
                    "product_cost": round(
                        product_cost,
                        2
                    ),
                    "marketplace_fees": round(
                        marketplace_fees,
                        2
                    ),
                    "tax": (
                        round(tax, 2)
                        if tax is not None
                        else None
                    ),
                    "net_profit": (
                        round(net_profit, 2)
                        if net_profit is not None
                        else None
                    ),
                    "profit_per_unit": (
                        round(profit_per_unit, 2)
                        if profit_per_unit is not None
                        else None
                    ),
                    "margin_percent": (
                        round(margin_percent, 2)
                        if margin_percent is not None
                        else None
                    )
                }
            )

        return metrics

    def _calculate_tax(
        self,
        revenue,
        gross_profit
    ):
        if not self.tax_service or not self.tax_mode:
            return None

        result = self.tax_service.calculate(
            mode=self.tax_mode,
            revenue=revenue,
            gross_profit=gross_profit,
            tax_rate=self.tax_rate,
            minimum_tax_rate=(
                self.minimum_tax_rate
            )
        )

        if result.get("error"):
            return None

        return float(
            result.get("tax_amount", 0)
            or 0
        )
