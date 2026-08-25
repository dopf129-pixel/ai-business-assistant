from datetime import datetime, timedelta, timezone


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

    CURRENT_MISSING_LABELS = {
        "unit_price": "Актуальная цена продавца",
        "buyer_price": "Цена покупателя Ozon",
        "cost": "Себестоимость",
        "commission_amount": "Комиссия Ozon",
        "logistics": "Логистика",
        "last_mile": "Последняя миля",
        "acquiring_average": "Эквайринг",
        "tax": "Налог"
    }

    def __init__(
        self,
        product_service,
        period_profit_service,
        analytics_service,
        unit_economics_provider,
        current_economics_source=None,
        cost_service=None,
        current_finance_days=2,
        returns_finance_impact_query=None,
        current_tax_base_policy="SELLER_PRICE"
    ):
        self.product_service = product_service
        self.period_profit_service = period_profit_service
        self.analytics_service = analytics_service
        self.unit_economics_provider = (
            unit_economics_provider
        )
        self.current_economics_source = (
            current_economics_source
        )
        self.cost_service = cost_service
        self.current_finance_days = max(
            1,
            int(current_finance_days)
        )
        self.returns_finance_impact_query = (
            returns_finance_impact_query
        )
        self.current_tax_base_policy = str(
            current_tax_base_policy
            or "SELLER_PRICE"
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

        if self.current_economics_source is not None:
            result = self._query_current(
                target_sku,
                product
            )
        else:
            result = self._query_historical(
                target_sku,
                product
            )

        return self._attach_returns_impact(
            target_sku,
            result
        )

    def _query_current(self, sku, product):
        offer_id = product.get("offer_id") or sku
        finance_sku = product.get("sku")

        facts = self.current_economics_source.get(
            sku=str(offer_id),
            product_id=product.get("product_id"),
            finance_sku=finance_sku,
            accrual_dates=self._recent_complete_dates()
        )

        if facts.get("error"):
            return {
                "error": True,
                "code": "CURRENT_DATA_UNAVAILABLE",
                "sku": sku,
                "message": (
                    facts.get("message")
                    or "Актуальные данные Ozon недоступны"
                )
            }

        if facts.get("seller_price") is None:
            return self._empty_current_result(
                sku,
                facts
            )

        cost = self._current_cost(
            facts,
            product
        )
        prepared_facts = dict(facts)
        prepared_facts["tax_base_policy"] = (
            self.current_tax_base_policy
        )
        metric = self.unit_economics_provider.build_current(
            prepared_facts,
            cost
        )

        result = {
            "error": False,
            "available": True,
            "source": "current",
            **metric
        }
        result["note"] = self._build_current_note(
            result
        )
        return result

    def _query_historical(self, target_sku, product):
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

        return {
            "error": False,
            "available": True,
            "source": "historical",
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
            "marketplace_fees": self._per_unit(
                metric.get("marketplace_fees"),
                units_sold
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

        if result.get("source") == "current":
            return self._format_current_response(result)

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
            "Расходы маркетплейса:",
            self._format_money(
                result.get("marketplace_fees")
            ),
            "",
            "Налог:",
            self._format_money(
                result.get("tax")
            )
        ]

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

    def _format_current_response(self, result):
        sku = result.get("sku", "—")
        price = result.get("unit_price")

        lines = [
            f"💰 Юнит-экономика — {sku}",
            "",
            "Актуальная цена продавца:",
            self._format_money_with_share(
                price,
                price
            ),
            "",
            "Цена покупателя Ozon:",
            self._format_money_with_share(
                result.get("buyer_price"),
                price
            ),
            "",
            "Компенсация скидки Ozon:",
            self._format_money_with_share(
                result.get("ozon_discount_compensation"),
                price
            ),
            "",
            "Комиссия Ozon:",
            self._format_money_with_share(
                result.get("commission"),
                price
            ),
            "",
            "Логистика:",
            self._format_money_with_share(
                result.get("logistics"),
                price
            ),
            "",
            "Последняя миля:",
            self._format_money_with_share(
                result.get("last_mile"),
                price
            ),
            "",
            "Эквайринг:",
            self._format_money_with_share(
                result.get("acquiring"),
                price
            ),
            "",
            "Себестоимость:",
            self._format_money_with_share(
                result.get("cost"),
                price
            ),
            "",
            "Налоговая база:",
            self._format_money_with_share(
                result.get("tax_base"),
                price
            ),
            "",
            "Ставка налога:",
            self._format_percent(
                result.get("tax_rate")
            ),
            "",
            "Налог:",
            self._format_money_with_share(
                result.get("tax"),
                price
            ),
            "",
            "Эффективный налог от цены продавца:",
            self._format_percent(
                result.get("tax_effective_percent")
            ),
            "",
            "----------------",
            "",
            "Расчётная прибыль с 1 шт:",
            self._format_money_with_share(
                result.get("net_profit_per_unit"),
                price
            ),
            "",
            "Маржа:",
            self._format_percent(
                result.get("margin_percent")
            )
        ]

        self._append_returns_impact(
            lines,
            result
        )

        missing = result.get("missing_fields") or []
        if missing:
            labels = [
                self.CURRENT_MISSING_LABELS.get(
                    field,
                    field
                )
                for field in missing
            ]
            lines.extend(
                [
                    "",
                    "Не хватает данных:",
                    ", ".join(labels)
                ]
            )

        note = result.get("note")
        if note:
            lines.extend(["", note])

        if (
            result.get("tax_base_policy")
            == "OZON_BUYER_PRICE"
        ):
            lines.extend([
                "",
                (
                    "Налог рассчитан по цене покупателя Ozon; "
                    "компенсация скидки баллами в базу "
                    "управленческого расчёта не включена."
                ),
            ])

        updated = self._format_as_of(
            result.get("as_of")
        )
        if updated:
            lines.extend(
                [
                    "",
                    f"Данные обновлены: {updated}"
                ]
            )

        return "\n".join(lines)

    def _attach_returns_impact(
        self,
        sku,
        result
    ):
        if (
            result.get("error")
            or self.returns_finance_impact_query is None
        ):
            return result

        impact = self.returns_finance_impact_query.query(sku)
        output = dict(result)
        output["returns_finance_impact"] = impact

        if not isinstance(impact, dict) or impact.get("error"):
            output["returns_finance_complete"] = False
            output["returns_observed_cost_total"] = None
            output["returns_observed_event_count"] = None
            output["returns_delivered_units"] = None
            output["returns_cost_per_delivered_unit"] = None
            output["risk_adjusted_profit_per_unit"] = None
            output["risk_adjusted_margin_percent"] = None
            return output

        categories = impact.get("categories") or {}
        costs = []
        event_count = 0
        category_costs_known = True

        for key in (
            "customer_non_buyout",
            "customer_return",
        ):
            item = categories.get(key) or {}
            category_events = int(
                item.get("event_posting_count") or 0
            )
            value = item.get("observed_cost_total")
            event_count += category_events

            if value is not None:
                costs.append(float(value))
            elif category_events:
                category_costs_known = False

        delivered_units = self._positive_integer(
            impact.get("delivered_units")
        )
        complete = bool(impact.get("complete"))
        observed_total = (
            round(sum(costs), 2)
            if costs
            else (0.0 if complete and not event_count else None)
        )
        base_profit = result.get("net_profit_per_unit")
        allocation_ready = (
            complete
            and delivered_units is not None
            and category_costs_known
            and observed_total is not None
            and base_profit is not None
        )

        cost_per_delivered = None
        adjusted_profit = None
        adjusted_margin = None

        if allocation_ready:
            cost_per_delivered = round(
                observed_total / delivered_units,
                2
            )
            adjusted_profit = round(
                float(base_profit) - cost_per_delivered,
                2
            )
            price = result.get("unit_price")
            if price not in (None, 0):
                adjusted_margin = round(
                    adjusted_profit / float(price) * 100,
                    2
                )

        output["returns_finance_complete"] = complete
        output["returns_observed_cost_total"] = observed_total
        output["returns_observed_event_count"] = event_count
        output["returns_delivered_units"] = delivered_units
        output["returns_cost_per_delivered_unit"] = (
            cost_per_delivered
        )
        output["risk_adjusted_profit_per_unit"] = (
            adjusted_profit
        )
        output["risk_adjusted_margin_percent"] = (
            adjusted_margin
        )

        if allocation_ready:
            missing = list(output.get("missing_fields") or [])
            output["missing_fields"] = [
                field
                for field in missing
                if field != "returns"
            ]

        return output


    def _append_returns_impact(
        self,
        lines,
        result
    ):
        impact = result.get("returns_finance_impact")
        if not isinstance(impact, dict):
            return

        lines.extend([
            "",
            "----------------",
            "",
            "Возвраты и невыкупы за период:",
        ])

        if impact.get("error"):
            lines.extend([
                "Наблюдаемые расходы:",
                "—",
                "",
                "Расход на доставленную единицу:",
                "—",
                "",
                "Скорректированная прибыль с 1 шт:",
                "—",
                "",
                "Данные расходов на возвраты недоступны.",
            ])
            return

        categories = impact.get("categories") or {}
        for key in (
            "customer_non_buyout",
            "customer_return",
        ):
            item = categories.get(key) or {}
            lines.extend([
                "",
                str(item.get("label") or key) + ":",
                "События: "
                + str(item.get("event_posting_count") or 0),
                "Покрытие: "
                + self._format_percent(
                    item.get("finance_coverage_percent")
                ),
                "Наблюдаемые расходы: "
                + self._format_money(
                    item.get("observed_cost_total")
                ),
                "Среднее на сопоставленное событие: "
                + self._format_money(
                    item.get("observed_cost_average")
                ),
            ])

        lines.extend([
            "",
            "Всего наблюдаемых расходов:",
            self._format_money(
                result.get("returns_observed_cost_total")
            ),
            "",
            "Доставлено единиц за тот же период:",
            (
                str(result.get("returns_delivered_units"))
                if result.get("returns_delivered_units") is not None
                else "—"
            ),
            "",
            "Расход на доставленную единицу:",
            self._format_money(
                result.get("returns_cost_per_delivered_unit")
            ),
            "",
            "Скорректированная прибыль с 1 шт:",
            self._format_money(
                result.get("risk_adjusted_profit_per_unit")
            ),
            "",
            "Скорректированная маржа:",
            self._format_percent(
                result.get("risk_adjusted_margin_percent")
            ),
        ])

        if result.get("risk_adjusted_profit_per_unit") is not None:
            lines.extend([
                "",
                (
                    "Расходы распределены по подтверждённым "
                    "доставленным единицам того же периода."
                ),
            ])
        else:
            lines.extend([
                "",
                (
                    "Расходы не вычитались из прибыли: "
                    "для безопасного распределения не хватает "
                    "полных данных."
                ),
            ])

        if not impact.get("complete"):
            lines.extend([
                "",
                (
                    "⚠️ Финансовая атрибуция неполна; "
                    "экстраполяция не выполнялась."
                ),
            ])


    def _positive_integer(
        self,
        value
    ):
        try:
            number = int(value)
        except (TypeError, ValueError):
            return None

        return number if number > 0 else None


    def _find_product(self, sku):
        products = self.product_service.load_products()

        for product in (products or []):
            normalized = self._normalize_product(product)

            if normalized is None:
                continue

            if (
                str(normalized.get("sku")) == sku
                or str(normalized.get("offer_id")) == sku
            ):
                return normalized

        return None

    def _normalize_product(self, product):
        if isinstance(product, dict):
            if (
                product.get("sku") is None
                and product.get("offer_id") is None
            ):
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

    def _current_cost(self, facts, product):
        if self.cost_service is None:
            return None

        candidate_ids = []
        for value in (
            facts.get("product_id"),
            product.get("product_id")
        ):
            if value is None:
                continue
            text = str(value)
            if text not in candidate_ids:
                candidate_ids.append(text)

        for product_id in candidate_ids:
            row = self.cost_service.get_cost(product_id)
            if row and len(row) > 3:
                return row[3]

        return None

    def _recent_complete_dates(self):
        today = datetime.now(timezone.utc).date()
        return [
            (
                today - timedelta(days=offset)
            ).isoformat()
            for offset in range(
                1,
                self.current_finance_days + 1
            )
        ]

    def _empty_current_result(self, sku, facts):
        missing = list(
            facts.get("missing_data") or []
        )
        if "unit_price" not in missing:
            missing.insert(0, "unit_price")

        return {
            "error": False,
            "available": False,
            "source": "current",
            "product_id": facts.get("product_id"),
            "sku": sku,
            "unit_price": facts.get("seller_price"),
            "cost": None,
            "commission": facts.get("commission_amount"),
            "commission_rate": facts.get("commission_rate"),
            "logistics": facts.get("logistics"),
            "last_mile": facts.get("last_mile"),
            "acquiring": facts.get("acquiring_average"),
            "marketplace_fees": None,
            "tax": None,
            "net_profit_per_unit": None,
            "margin_percent": None,
            "missing_fields": missing,
            "as_of": facts.get("as_of"),
            "note": "Актуальный расчёт пока недоступен"
        }

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
            "source": "historical",
            "sku": sku,
            "unit_price": None,
            "cost": None,
            "marketplace_fees": None,
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

    def _build_note(self, missing_fields):
        if missing_fields:
            return (
                "Расчётная прибыль с 1 шт. "
                "без учёта отсутствующих расходов"
            )

        return "Расчётная прибыль с 1 шт."

    def _build_current_note(self, result):
        missing = result.get("missing_fields") or []
        if missing:
            return (
                "Прибыль не рассчитана, пока не получены "
                "все обязательные данные."
            )

        sales = result.get("finance_sample_sales")
        days = result.get("finance_sample_days")
        if sales and days:
            return (
                "Основано на последних финансовых начислениях "
                f"Ozon: {sales} продаж за {days} дн."
            )

        return "Расчёт по актуальной цене продавца."

    def _format_as_of(self, value):
        if not value:
            return None

        try:
            parsed = datetime.fromisoformat(
                str(value).replace("Z", "+00:00")
            )
        except (TypeError, ValueError):
            return None

        return parsed.strftime("%d.%m.%Y %H:%M UTC")

    def _format_money(self, value):
        if value is None:
            return "—"

        return f"{value:.2f} ₽"

    def _format_money_with_share(self, value, price):
        if value is None:
            return "—"

        money = self._format_money(value)
        share = self._share(value, price)
        if share is None:
            return money
        return f"{money} — {share:.1f}%"

    def _share(self, value, price):
        if value is None or price in (None, 0):
            return None
        return float(value) / float(price) * 100

    def _format_percent(self, value):
        if value is None:
            return "—"

        return f"{value:.2f}%"
