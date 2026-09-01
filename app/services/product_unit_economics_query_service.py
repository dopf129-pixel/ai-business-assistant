from copy import deepcopy
from datetime import datetime, timedelta, timezone
from math import isfinite
from time import monotonic


class ProductUnitEconomicsQueryService:

    DEFAULT_MISSING_FIELDS = (
        "advertising",
        "storage",
        "returns"
    )

    RETURNS_FINANCE_CATEGORIES = (
        "customer_non_buyout",
        "customer_return",
    )
    CODE_RETURNS_FINANCE_IMPACT_INVALID = (
        "RETURNS_FINANCE_IMPACT_RESULT_INVALID"
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
        current_tax_base_policy="SELLER_PRICE",
        cache_ttl_seconds=0,
        cache_clock=None,
        cache_timestamp_provider=None
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
        self.cache_ttl_seconds = max(
            0,
            int(cache_ttl_seconds)
        )
        self.cache_clock = cache_clock or monotonic
        self.cache_timestamp_provider = (
            cache_timestamp_provider
            or (lambda: datetime.now(timezone.utc))
        )
        self._query_cache = {}

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

        cache_key = str(
            product.get("offer_id")
            or product.get("sku")
            or target_sku
        )
        cached = self._query_cache.get(cache_key)
        now = self.cache_clock()

        if (
            self.cache_ttl_seconds > 0
            and cached is not None
            and now - cached["stored_at"]
            < self.cache_ttl_seconds
        ):
            return self._with_cache_metadata(
                cached["result"],
                status="hit",
                age_seconds=now - cached["stored_at"],
                cached_at=cached["cached_at"],
            )

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

        result = self._attach_returns_impact(
            target_sku,
            result
        )

        if self.cache_ttl_seconds <= 0:
            return result

        if self._is_cacheable_result(result):
            stored = deepcopy(result)
            cached_at = self._cache_timestamp()
            self._query_cache[cache_key] = {
                "stored_at": now,
                "cached_at": cached_at,
                "result": stored,
            }
            return self._with_cache_metadata(
                stored,
                status="miss",
                age_seconds=0,
                cached_at=cached_at,
            )

        if cached is not None:
            fallback = self._with_cache_metadata(
                cached["result"],
                status="stale",
                age_seconds=now - cached["stored_at"],
                cached_at=cached["cached_at"],
            )
            impact = result.get(
                "returns_finance_impact"
            )
            fallback["cache"]["refresh_error"] = (
                result.get("code")
                or (
                    impact.get("code")
                    if isinstance(impact, dict)
                    else None
                )
                or "REFRESH_FAILED"
            )
            return fallback

        return self._with_cache_metadata(
            result,
            status="miss",
            age_seconds=0,
        )

    def _is_cacheable_result(
        self,
        result
    ):
        if not isinstance(result, dict) or result.get("error"):
            return False

        impact = result.get("returns_finance_impact")
        if isinstance(impact, dict) and impact.get("error"):
            return False

        return True

    def _with_cache_metadata(
        self,
        result,
        status,
        age_seconds,
        cached_at=None
    ):
        output = deepcopy(result)
        output["cache"] = {
            "status": status,
            "hit": status == "hit",
            "stale": status == "stale",
            "age_seconds": round(
                max(0, float(age_seconds)),
                2
            ),
            "ttl_seconds": self.cache_ttl_seconds,
            "cached_at": (
                cached_at
                if cached_at is not None
                else self._cache_timestamp()
            ),
        }
        return output

    def _cache_timestamp(self):
        value = self.cache_timestamp_provider()
        if isinstance(value, datetime):
            if value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
            return value.astimezone(timezone.utc).isoformat()
        return str(value)

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
            "Цена:",
            self._format_money_with_share(
                price,
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
            "Налог:",
            self._format_money_with_share(
                result.get("tax"),
                price
            ),
        ]

        if isinstance(
            result.get("returns_finance_impact"),
            dict
        ):
            self._append_returns_impact(
                lines,
                result
            )
        else:
            lines.extend([
                "",
                "----------------",
                "",
                "Прибыль с 1 шт:",
                self._format_money_with_share(
                    result.get("net_profit_per_unit"),
                    price
                ),
            ])

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

        output = dict(result)
        empty_fields = self._empty_returns_finance_fields()

        try:
            raw_impact = self.returns_finance_impact_query.query(sku)
        except (OSError, ValueError, TypeError, KeyError, AttributeError):
            output["returns_finance_impact"] = (
                self._invalid_returns_finance_impact()
            )
            output.update(empty_fields)
            return output

        if (
            not isinstance(raw_impact, dict)
            or type(raw_impact.get("error")) is not bool
        ):
            output["returns_finance_impact"] = (
                self._invalid_returns_finance_impact()
            )
            output.update(empty_fields)
            return output

        if raw_impact["error"] is True:
            output["returns_finance_impact"] = deepcopy(raw_impact)
            output.update(empty_fields)
            return output

        impact = self._validated_returns_finance_impact(raw_impact)
        if impact is None:
            output["returns_finance_impact"] = (
                self._invalid_returns_finance_impact()
            )
            output.update(empty_fields)
            return output

        output["returns_finance_impact"] = deepcopy(impact)
        categories = impact["categories"]
        costs = []
        event_count = 0
        category_costs_known = True

        for key in self.RETURNS_FINANCE_CATEGORIES:
            item = categories[key]
            category_events = item["event_posting_count"]
            value = item.get("observed_cost_total")
            event_count += category_events

            if value is not None:
                costs.append(float(value))
            elif category_events:
                category_costs_known = False

        delivered_units = self._positive_integer(
            impact.get("delivered_units")
        )
        complete = impact["complete"]
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
            adjusted_margin = self._profit_margin(
                adjusted_profit,
                result.get("unit_price")
            )

        estimate = self._estimate_returns_impact(
            impact=impact,
            categories=categories,
            delivered_units=delivered_units,
            base_profit=base_profit,
            price=result.get("unit_price"),
        )

        output.update(empty_fields)
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
        output.update(estimate)

        if allocation_ready:
            missing = list(output.get("missing_fields") or [])
            output["missing_fields"] = [
                field
                for field in missing
                if field != "returns"
            ]

        return output


    def _empty_returns_finance_fields(self):
        return {
            "returns_finance_complete": False,
            "returns_observed_cost_total": None,
            "returns_observed_event_count": None,
            "returns_delivered_units": None,
            "returns_cost_per_delivered_unit": None,
            "risk_adjusted_profit_per_unit": None,
            "risk_adjusted_margin_percent": None,
            "returns_estimate_available": False,
            "estimated_returns_cost_total": None,
            "estimated_returns_cost_per_unit": None,
            "estimated_profit_per_unit": None,
            "estimated_margin_percent": None,
            "returns_estimate_coverage_percent": None,
        }


    def _invalid_returns_finance_impact(self):
        return {
            "error": True,
            "code": self.CODE_RETURNS_FINANCE_IMPACT_INVALID,
            "complete": False,
            "missing_data": ["returns_finance"],
        }


    def _validated_returns_finance_impact(self, impact):
        if (
            type(impact.get("complete")) is not bool
            or type(impact.get("classification_complete")) is not bool
            or type(impact.get("finance_complete")) is not bool
            or not isinstance(impact.get("missing_data"), list)
            or any(
                not isinstance(item, str) or not item.strip()
                for item in impact["missing_data"]
            )
        ):
            return None

        delivered_units = impact.get("delivered_units")
        if (
            delivered_units is not None
            and (
                type(delivered_units) is not int
                or delivered_units < 0
            )
        ):
            return None

        categories = impact.get("categories")
        if not isinstance(categories, dict):
            return None

        for key in self.RETURNS_FINANCE_CATEGORIES:
            item = categories.get(key)
            if not self._valid_returns_finance_category(item):
                return None

        if impact["complete"]:
            if (
                impact["classification_complete"] is not True
                or impact["finance_complete"] is not True
                or any(
                    categories[key]["complete"] is not True
                    for key in self.RETURNS_FINANCE_CATEGORIES
                )
            ):
                return None

        return deepcopy(impact)


    def _valid_returns_finance_category(self, item):
        if not isinstance(item, dict):
            return False

        if type(item.get("complete")) is not bool:
            return False

        counts = {}
        for field in (
            "event_posting_count",
            "finance_matched_posting_count",
            "observed_posting_count",
        ):
            value = item.get(field)
            if type(value) is not int or value < 0:
                return False
            counts[field] = value

        events = counts["event_posting_count"]
        matched = counts["finance_matched_posting_count"]
        observed = counts["observed_posting_count"]

        if matched > events or observed > matched:
            return False

        if item["complete"] and matched != events:
            return False

        observed_cost = item.get("observed_cost_total")
        if (
            observed_cost is not None
            and not self._is_finite_number(observed_cost)
        ):
            return False

        if observed > 0 and observed_cost is None:
            return False

        return True


    def _is_finite_number(self, value):
        return (
            type(value) in (int, float)
            and isfinite(float(value))
        )


    def _estimate_returns_impact(
        self,
        impact,
        categories,
        delivered_units,
        base_profit,
        price
    ):
        empty = {
            "returns_estimate_available": False,
            "estimated_returns_cost_total": None,
            "estimated_returns_cost_per_unit": None,
            "estimated_profit_per_unit": None,
            "estimated_margin_percent": None,
            "returns_estimate_coverage_percent": None,
        }
        missing_data = set(impact["missing_data"])

        if (
            "finance_days_unavailable" in missing_data
            or delivered_units is None
            or base_profit is None
        ):
            return empty

        estimated_total = 0.0
        coverages = []
        has_events = False

        for key in self.RETURNS_FINANCE_CATEGORIES:
            item = categories[key]
            events = item["event_posting_count"]
            if events <= 0:
                continue

            has_events = True
            observed = item["observed_posting_count"]
            observed_total = item.get("observed_cost_total")
            if observed <= 0 or observed_total is None:
                return empty

            coverage = observed / events * 100
            if coverage < 80:
                return empty
            if observed < 30 and observed != events:
                return empty

            coverages.append(coverage)
            estimated_total += (
                float(observed_total)
                / observed
                * events
            )

        if not has_events:
            estimated_total = 0.0

        estimated_total = round(estimated_total, 2)
        cost_per_unit = round(
            estimated_total / delivered_units,
            2
        )
        estimated_profit = round(
            float(base_profit) - cost_per_unit,
            2
        )

        return {
            "returns_estimate_available": True,
            "estimated_returns_cost_total": estimated_total,
            "estimated_returns_cost_per_unit": cost_per_unit,
            "estimated_profit_per_unit": estimated_profit,
            "estimated_margin_percent": self._profit_margin(
                estimated_profit,
                price
            ),
            "returns_estimate_coverage_percent": (
                round(min(coverages), 2)
                if coverages
                else 100.0
            ),
        }


    def _profit_margin(
        self,
        profit,
        price
    ):
        if profit is None or price in (None, 0):
            return None

        return round(
            float(profit) / float(price) * 100,
            2
        )


    def _append_returns_impact(
        self,
        lines,
        result
    ):
        impact = result.get("returns_finance_impact")
        price = result.get("unit_price")

        if impact.get("error"):
            lines.extend([
                "",
                "Возвраты и невыкупы:",
                "—",
                "",
                "----------------",
                "",
                "Оценочная прибыль с 1 шт:",
                "—",
                "",
                (
                    "⚠️ Данные возвратов недоступны; "
                    "прибыль не рассчитана."
                ),
            ])
            return

        confirmed_profit = result.get(
            "risk_adjusted_profit_per_unit"
        )
        if confirmed_profit is not None:
            lines.extend([
                "",
                "Возвраты и невыкупы:",
                self._format_money_with_share(
                    result.get(
                        "returns_cost_per_delivered_unit"
                    ),
                    price
                ),
                "",
                "----------------",
                "",
                "Прибыль с 1 шт:",
                self._format_money_with_share(
                    confirmed_profit,
                    price
                ),
            ])
            return

        estimated_profit = result.get(
            "estimated_profit_per_unit"
        )
        lines.extend([
            "",
            "Возвраты и невыкупы:",
            self._format_money_with_share(
                result.get(
                    "estimated_returns_cost_per_unit"
                ),
                price
            ),
            "",
            "----------------",
            "",
            "Оценочная прибыль с 1 шт:",
            self._format_money_with_share(
                estimated_profit,
                price
            ),
        ])

        if estimated_profit is None:
            lines.extend([
                "",
                (
                    "⚠️ Для надёжной оценки возвратов "
                    "недостаточно данных."
                ),
            ])
            return

        coverage = self._format_percent(
            result.get(
                "returns_estimate_coverage_percent"
            )
        )
        period_days = int(
            impact.get("period_days") or 90
        )
        lines.extend([
            "",
            (
                "⚠️ Расчёт по исторической статистике "
                f"за {period_days} полных дней; "
                "финансовое покрытие "
                + coverage
                + "."
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
