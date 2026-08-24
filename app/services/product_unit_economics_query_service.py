class ProductUnitEconomicsQueryService:

    DEFAULT_MISSING_FIELDS = (
        "advertising",
        "storage",
        "returns"
    )

    MISSING_FIELD_LABELS = {
        "advertising": "Реклама",
        "storage": "Хранение",
        "returns": "Возвраты",
        "tax": "Налог"
    }

    FEE_LABELS = {
        "commission": "Комиссия",
        "logistics": "Логистика",
        "acquiring": "Эквайринг",
        "other_fees": "Прочие удержания"
    }

    def __init__(
        self,
        product_service,
        period_profit_service,
        analytics_service,
        unit_economics_provider
    ):
        self.product_service = product_service
        self.period_profit_service = period_profit_service
        self.analytics_service = analytics_service
        self.unit_economics_provider = (
            unit_economics_provider
        )

    def query(self, sku):
        target_sku = str(sku or "").strip()

        if not target_sku:
            return {
                "error": True,
                "code": "SKU_REQUIRED",
                "message": "SKU не указан"
            }

        product = self._find_product(target_sku)

        if product is None:
            return {
                "error": True,
                "code": "SKU_NOT_FOUND",
                "sku": target_sku,
                "message": "SKU не найден"
            }

        period = self.analytics_service.get_period()

        if not period or period.get("error"):
            return {
                "error": True,
                "code": "PERIOD_UNAVAILABLE",
                "sku": target_sku,
                "message": "Период анализа недоступен"
            }

        result = (
            self.period_profit_service
            .calculate_period_profit(
                period.get("date_from"),
                period.get("date_to"),
                [product]
            )
        )

        if not result or result.get("error"):
            return self._empty_result(target_sku)

        metrics = self.unit_economics_provider.build(
            result.get("profits", [])
        )

        if not metrics:
            return self._empty_result(target_sku)

        metric = metrics[0]
        units_sold = int(
            metric.get("units_sold") or 0
        )

        if units_sold <= 0:
            return self._empty_result(target_sku)

        missing_fields = list(
            self.DEFAULT_MISSING_FIELDS
        )

        tax = metric.get("tax")

        if tax is None:
            missing_fields.append("tax")

        marketplace_fees = self._per_unit(
            metric.get("marketplace_fees"),
            units_sold
        )

        return {
            "error": False,
            "available": True,
            "product_id": metric.get("product_id"),
            "sku": metric.get("sku", target_sku),
            "unit_price": self._per_unit(
                metric.get("revenue"),
                units_sold
            ),
            "cost": self._per_unit(
                metric.get("product_cost"),
                units_sold
            ),
            "marketplace_fees": marketplace_fees,
            "fee_breakdown": (
                self._per_unit_fee_breakdown(
                    metric.get("fee_breakdown"),
                    units_sold,
                    marketplace_fees
                )
            ),
            "tax": self._per_unit(
                tax,
                units_sold
            ),
            "net_profit_per_unit": metric.get(
                "profit_per_unit"
            ),
            "margin_percent": metric.get(
                "margin_percent"
            ),
            "missing_fields": missing_fields,
            "note": self._build_note(
                missing_fields
            )
        }

    def format_response(self, result):
        if result.get("error"):
            return result.get(
                "message",
                "Юнит-экономика недоступна"
            )

        sku = result.get("sku", "—")
        lines = [
            f"Unit Economics — {sku}",
            "",
            "Цена продажи:",
            self._format_money(
                result.get("unit_price")
            ),
            "",
            "Себестоимость:",
            self._format_money(
                result.get("cost")
            ),
            "",
            "Удержания Ozon:"
        ]

        fee_breakdown = (
            result.get("fee_breakdown")
            or {}
        )

        for field in (
            "commission",
            "logistics",
            "acquiring",
            "other_fees"
        ):
            lines.extend(
                [
                    "",
                    self.FEE_LABELS[field] + ":",
                    self._format_money(
                        fee_breakdown.get(field)
                    )
                ]
            )

        lines.extend(
            [
                "",
                "----------------",
                "",
                "Всего удержания Ozon:",
                self._format_money(
                    result.get("marketplace_fees")
                ),
                "",
                "Налог:",
                self._format_money(
                    result.get("tax")
                )
            ]
        )

        for field in self.DEFAULT_MISSING_FIELDS:
            lines.extend(
                [
                    "",
                    self.MISSING_FIELD_LABELS[
                        field
                    ] + ":",
                    "—"
                ]
            )

        lines.extend(
            [
                "",
                "----------------",
                "",
                "Расчётная прибыль с 1 шт:",
                self._format_money(
                    result.get(
                        "net_profit_per_unit"
                    )
                ),
                "",
                "Маржа:",
                self._format_percent(
                    result.get("margin_percent")
                ),
                "",
                result.get(
                    "note",
                    self._build_note(
                        result.get(
                            "missing_fields",
                            []
                        )
                    )
                )
            ]
        )

        return "\n".join(lines)

    def _find_product(self, sku):
        products = self.product_service.load_products()

        for product in (products or []):
            normalized = self._normalize_product(product)

            if normalized is None:
                continue

            if str(normalized.get("sku")) == sku:
                return normalized

        return None

    def _normalize_product(self, product):
        if isinstance(product, dict):
            if product.get("sku") is None:
                return None
            return dict(product)

        try:
            return {
                "product_id": product[0],
                "offer_id": product[1],
                "sku": product[2]
            }
        except (
            TypeError,
            IndexError
        ):
            return None

    def _empty_result(self, sku):
        missing_fields = [
            "unit_price",
            "cost",
            "marketplace_fees",
            "tax",
            "net_profit_per_unit",
            "margin_percent",
            *self.DEFAULT_MISSING_FIELDS
        ]

        return {
            "error": False,
            "available": False,
            "sku": sku,
            "unit_price": None,
            "cost": None,
            "marketplace_fees": None,
            "fee_breakdown": None,
            "tax": None,
            "net_profit_per_unit": None,
            "margin_percent": None,
            "missing_fields": missing_fields,
            "note": self._build_note(
                missing_fields
            )
        }

    def _per_unit(self, value, units_sold):
        if value is None or units_sold <= 0:
            return None

        return round(
            float(value) / units_sold,
            2
        )

    def _per_unit_fee_breakdown(
        self,
        breakdown,
        units_sold,
        marketplace_fees
    ):
        if not breakdown or units_sold <= 0:
            return None

        commission = self._per_unit(
            breakdown.get("commission"),
            units_sold
        )
        logistics = self._per_unit(
            breakdown.get("logistics"),
            units_sold
        )
        acquiring = self._per_unit(
            breakdown.get("acquiring"),
            units_sold
        )

        if any(
            value is None
            for value in (
                commission,
                logistics,
                acquiring,
                marketplace_fees
            )
        ):
            return None

        other_fees = round(
            marketplace_fees
            - commission
            - logistics
            - acquiring,
            2
        )

        return {
            "commission": commission,
            "logistics": logistics,
            "acquiring": acquiring,
            "other_fees": other_fees
        }

    def _build_note(self, missing_fields):
        if missing_fields:
            return (
                "Расчётная прибыль с 1 шт. "
                "без учёта отсутствующих расходов"
            )

        return "Расчётная прибыль с 1 шт."

    def _format_money(self, value):
        if value is None:
            return "—"

        return f"{value:.2f} ₽"

    def _format_percent(self, value):
        if value is None:
            return "—"

        return f"{value:.2f}%"
