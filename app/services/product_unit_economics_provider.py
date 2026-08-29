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

    CURRENT_EXPENSE_FIELDS = (
        "commission_amount",
        "logistics",
        "last_mile",
        "acquiring_average"
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

    def build_current(self, facts, product_cost):
        facts = dict(facts or {})
        seller_price = self._number(
            facts.get("seller_price")
        )
        buyer_price = self._number(
            facts.get("buyer_price")
        )
        compensation = self._number(
            facts.get("ozon_discount_compensation")
        )
        requested_tax_policy = str(
            facts.get("tax_base_policy")
            or "SELLER_PRICE"
        )
        tax_base_policy = "SELLER_PRICE"
        tax_base = seller_price

        if (
            requested_tax_policy == "OZON_BUYER_PRICE"
            and self.tax_mode == "USN_INCOME"
        ):
            tax_base_policy = "OZON_BUYER_PRICE"
            tax_base = buyer_price

        cost = self._number(product_cost)

        values = {
            field: self._number(facts.get(field))
            for field in self.CURRENT_EXPENSE_FIELDS
        }

        missing_fields = []
        if seller_price is None:
            missing_fields.append("unit_price")
        if (
            tax_base_policy == "OZON_BUYER_PRICE"
            and buyer_price is None
        ):
            missing_fields.append("buyer_price")
        if cost is None:
            missing_fields.append("cost")
        for field, value in values.items():
            if value is None:
                missing_fields.append(field)

        commission = values["commission_amount"]
        logistics = values["logistics"]
        last_mile = values["last_mile"]
        acquiring = values["acquiring_average"]

        marketplace_fees = None
        gross_profit = None
        tax = None
        net_profit = None
        margin_percent = None
        tax_effective_percent = None

        if not missing_fields:
            marketplace_fees = sum(
                (
                    commission,
                    logistics,
                    last_mile,
                    acquiring
                )
            )
            gross_profit = (
                seller_price
                - marketplace_fees
                - cost
            )
            tax = self._calculate_tax(
                revenue=tax_base,
                gross_profit=gross_profit
            )
            if tax is None:
                missing_fields.append("tax")
            else:
                net_profit = gross_profit - tax
                margin_percent = (
                    net_profit / seller_price * 100
                    if seller_price > 0
                    else None
                )
                tax_effective_percent = (
                    tax / seller_price * 100
                    if seller_price > 0
                    else None
                )
        elif not self.tax_service or not self.tax_mode:
            missing_fields.append("tax")

        result = {
            "product_id": (
                str(facts.get("product_id"))
                if facts.get("product_id") is not None
                else None
            ),
            "sku": (
                str(facts.get("sku"))
                if facts.get("sku") is not None
                else None
            ),
            "unit_price": self._round(seller_price),
            "buyer_price": self._round(buyer_price),
            "ozon_discount_compensation": self._round(
                compensation
            ),
            "tax_base_policy": tax_base_policy,
            "tax_base": self._round(tax_base),
            "tax_rate": self._number(self.tax_rate),
            "tax_effective_percent": self._round(
                tax_effective_percent
            ),
            "cost": self._round(cost),
            "commission": self._round(commission),
            "commission_rate": self._number(
                facts.get("commission_rate")
            ),
            "logistics": self._round(logistics),
            "last_mile": self._round(last_mile),
            "acquiring": self._round(acquiring),
            "marketplace_fees": self._round(
                marketplace_fees
            ),
            "tax": self._round(tax),
            "net_profit_per_unit": self._round(
                net_profit
            ),
            "margin_percent": self._round(
                margin_percent
            ),
            "missing_fields": list(dict.fromkeys(
                missing_fields
            )),
            "as_of": facts.get("as_of"),
            "finance_sample_sales": facts.get(
                "finance_sample_sales"
            ),
            "finance_sample_days": facts.get(
                "finance_sample_days"
            )
        }

        for field in (
            "unit_economics_source_recorded_at",
            "unit_economics_observed_at",
        ):
            if field in facts and facts.get(field) is not None:
                result[field] = facts.get(field)

        return result

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

    def _number(self, value):
        if value in (None, ""):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _round(self, value):
        return (
            round(value, 2)
            if value is not None
            else None
        )
