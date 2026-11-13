from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from hashlib import sha256
from math import isfinite
from time import monotonic
from services.ozon_account_repository import split_store_tenant_scope
from services.tenant_context import get_current_tenant_user_id
from services.product_unit_economics_historical_pre_ad_margin_service import (
    ProductUnitEconomicsHistoricalPreAdMarginService,
)


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
        "discount_points": "Баллы за скидки",
        "tax": "Налог"
    }

    PRE_AD_TAX_MODE_LABELS = {
        "USN_INCOME": "УСН Доходы",
        "USN_INCOME_MINUS_EXPENSES": "УСН Доходы минус расходы",
        "NONE": "без налога",
    }
    PRE_AD_EXPENSE_LABELS = {
        "COGS": "себестоимость",
        "OZON_COMMISSION": "комиссия Ozon",
        "LOGISTICS": "логистика",
        "LAST_MILE": "последняя миля",
        "ACQUIRING": "эквайринг",
        "ROUNDING_ADJUSTMENT": "корректировка округления",
        "CROSS_DOCKING": "кросс-докинг",
        "STORAGE": "хранение",
        "PLACEMENT": "размещение",
        "RETURNS_AND_CANCELLATIONS": "возвраты и отмены",
        "UNMAPPED_NON_AD_EXPENSES": "прочие расходы",
    }
    PRE_AD_REASON_LABELS = {
        "CURRENT_PRE_AD_INPUTS_MISSING": "не хватает обязательных данных для текущего расчёта",
        "SELLER_REVENUE_DENOMINATOR_UNAVAILABLE": "не подтверждена выручка продавца для процента",
        "HISTORICAL_PERIOD_RESULT_UNAVAILABLE": "нет результата за выбранный период",
        "HISTORICAL_SUCCESSFUL_UNITS_UNAVAILABLE": "не подтверждено число успешных продаж",
        "HISTORICAL_SELLER_REVENUE_UNAVAILABLE": "не подтверждена выручка продавца",
        "HISTORICAL_PERIOD_RESULT_INCOMPLETE": "исторический финансовый результат неполный",
        "HISTORICAL_ADVERTISING_EVIDENCE_NOT_CONNECTED": "точные расходы на рекламу не подключены",
        "HISTORICAL_ADVERTISING_IDENTITY_UNCONFIRMED": "не удалось подтвердить привязку рекламы к SKU",
        "HISTORICAL_ADVERTISING_PERIOD_MISMATCH": "период рекламных данных не совпадает",
        "HISTORICAL_ADVERTISING_EVIDENCE_INVALID": "источник рекламных данных не подтвердил результат",
        "HISTORICAL_ADVERTISING_SCOPE_INCOMPLETE": "не все типы расходов на рекламу подтверждены",
        "HISTORICAL_ADVERTISING_COMPONENTS_INCOMPLETE": "разбивка расходов на рекламу неполная",
        "HISTORICAL_ADVERTISING_OWNERSHIP_MISMATCH": "состав расходов нельзя однозначно отнести к SKU",
        "HISTORICAL_ADVERTISING_NET_CREDIT_REQUIRES_REVIEW": "корректировка рекламы требует проверки",
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
        cache_timestamp_provider=None,
        historical_pre_ad_margin_service=None,
        cost_adapter=None,
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
        self.cost_adapter = cost_adapter
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
        self.historical_pre_ad_margin_service = (
            historical_pre_ad_margin_service
            or ProductUnitEconomicsHistoricalPreAdMarginService()
        )
        self._query_cache = {}

    def query(self, sku):
        return self._query(sku, force_refresh=False)

    def refresh(self, sku):
        """Bypass a fresh cache entry for an explicit user-requested refresh."""
        return self._query(sku, force_refresh=True)

    def _query(self, sku, *, force_refresh):
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

        return self.query_for_product(
            target_sku, product, force_refresh=force_refresh,
        )

    def query_for_product(self, sku, product, *, force_refresh=False):
        """Run the existing economics query with an already resolved catalog row."""
        target_sku = str(sku or "").strip()
        normalized_product = self._normalize_product(product)
        if not target_sku:
            return {
                "error": True,
                "code": "SKU_REQUIRED",
                "message": "SKU не указан",
            }
        if normalized_product is None or target_sku not in {
            str(normalized_product.get("offer_id") or "").strip(),
            str(normalized_product.get("sku") or "").strip(),
        }:
            return {
                "error": True,
                "code": "PRODUCT_IDENTITY_MISMATCH",
                "sku": target_sku,
            }
        product = normalized_product

        tenant_scope = str(get_current_tenant_user_id() or "").strip() or None
        _owner, active_store = split_store_tenant_scope(tenant_scope)
        cost_date = self._current_cost_date_scope()
        cost_evidence = (
            self._resolve_current_cost_basis(product, active_store, cost_date)
            if self.current_economics_source is not None
            and self.cost_adapter is not None else None
        )
        cache_key = (
            tenant_scope,
            str(active_store or ""),
            str(product.get("product_id") or ""),
            str(product.get("offer_id") or ""),
            str(product.get("sku") or target_sku),
            str(cost_date or ""),
            str(cost_evidence.get("cost_revision") or "")
            if isinstance(cost_evidence, dict) else "",
        )
        if isinstance(cost_evidence, dict):
            # Keep only the current fingerprint for this exact store/SKU/date;
            # restores and corrections must not leave reusable old snapshots.
            for previous_key in tuple(self._query_cache):
                if previous_key != cache_key and previous_key[:6] == cache_key[:6]:
                    self._query_cache.pop(previous_key, None)
        cached = self._query_cache.get(cache_key)
        now = self.cache_clock()

        if (
            not force_refresh
            and self.cache_ttl_seconds > 0
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
                product,
                cost_evidence=cost_evidence,
            )
        else:
            result = self._query_historical(
                target_sku,
                product
            )

        if isinstance(cost_evidence, dict) and result.get("error") is False:
            # The UI uses this private identity to validate a rendered detail
            # snapshot against the exact current FIFO/cost revision. The
            # Telegram handler removes it before returning the response.
            result["_cost_cache_identity"] = {
                "store_id": str(active_store or ""),
                "product_id": str(product.get("product_id") or ""),
                "offer_id": str(product.get("offer_id") or ""),
                "sku": str(product.get("sku") or ""),
            }

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

        cross_docking = result.get("cross_docking")
        if (
            result.get("source") == "current"
            and isinstance(cross_docking, dict)
            and cross_docking.get("evidence_complete") is not True
        ):
            # Let the next explicit query resume the bounded source checkpoint.
            return False

        cost_basis = result.get("cost_basis")
        if (
            result.get("source") == "current"
            and isinstance(cost_basis, dict)
            and cost_basis.get("completeness") not in {
                "CONFIRMED_SNAPSHOT_MODEL_ONLY",
                "CONFIRMED_REPLAY_MODEL_ONLY",
                "LEGACY_EFFECTIVE_COST_CONFIRMED",
            }
        ):
            # Retry an incomplete FIFO read on the next query instead of
            # caching it as a settled cost for the normal economics TTL.
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

    def _query_current(self, sku, product, *, cost_evidence=None):
        offer_id = product.get("offer_id") or sku
        finance_sku = product.get("sku")
        accrual_dates = self._recent_complete_dates()

        facts = self.current_economics_source.get(
            sku=str(offer_id),
            product_id=product.get("product_id"),
            finance_sku=finance_sku,
            accrual_dates=accrual_dates
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
                facts,
                accrual_dates=accrual_dates,
                cost_evidence=cost_evidence,
            )

        if isinstance(cost_evidence, dict):
            cost = cost_evidence.get("cost_per_unit_rub")
        else:
            cost = self._current_cost(facts, product)
        prepared_facts = dict(facts)
        prepared_facts["tax_base_policy"] = (
            self.current_tax_base_policy
        )
        prepared_facts["pre_ad_source_periods"] = (
            self._current_pre_ad_source_periods(facts, accrual_dates)
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
        if isinstance(cost_evidence, dict):
            result["cost_basis"] = deepcopy(
                cost_evidence.get("cost_basis") or {}
            )
            result["cost_method"] = cost_evidence.get("cost_method")
            result["cost_revision"] = cost_evidence.get("cost_revision")
            result["cost_as_of"] = cost_evidence.get("cost_updated_at")
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

        raw_profit_rows = result.get("profits", [])
        metrics = self.unit_economics_provider.build(
            raw_profit_rows
        )

        if not metrics:
            return self._empty_result(target_sku)

        metric = metrics[0]
        raw_metric = self._matching_historical_source_row(
            raw_profit_rows,
            metric,
        )
        units_sold = int(
            metric.get("units_sold") or 0
        )

        if units_sold <= 0:
            empty = self._empty_result(target_sku)
            empty["pre_ad_margin"] = self.historical_pre_ad_margin_service.build(
                metric,
                self._historical_evidence(raw_metric),
                self._historical_expected_identity(raw_metric),
                period,
            )
            return empty

        missing_fields = list(
            self.DEFAULT_MISSING_FIELDS
        )

        tax = metric.get("tax")

        if tax is None:
            missing_fields.append("tax")

        pre_ad_margin = self.historical_pre_ad_margin_service.build(
            metric,
            self._historical_evidence(raw_metric),
            self._historical_expected_identity(raw_metric),
            period,
        )

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
            "discount_points": self._per_unit(
                metric.get("discount_points"),
                units_sold,
            ),
            "revenue_tax_base": self._per_unit(
                metric.get("revenue_tax_base"),
                units_sold,
            ),
            "tax_base": self._per_unit(
                metric.get("tax_base"),
                units_sold,
            ),
            "tax_effective_percent": metric.get(
                "tax_effective_percent"
            ),
            "net_profit_per_unit": metric.get(
                "profit_per_unit"
            ),
            "margin_percent": metric.get(
                "margin_percent"
            ),
            "pre_ad_margin": pre_ad_margin,
            "missing_fields": missing_fields,
            "note": self._build_note(
                missing_fields
            )
        }

    @staticmethod
    def _matching_historical_source_row(rows, metric):
        if not isinstance(rows, list) or not isinstance(metric, dict):
            return None
        product_id = str(metric.get("product_id") or "").strip()
        sku = str(metric.get("sku") or "").strip()
        matches = [
            row for row in rows
            if isinstance(row, dict)
            and str(row.get("product_id") or "").strip() == product_id
            and str(row.get("sku") or "").strip() == sku
        ]
        return matches[0] if len(matches) == 1 else None

    @staticmethod
    def _historical_evidence(source_row):
        if not isinstance(source_row, dict):
            return None
        return source_row.get("historical_advertising_evidence")

    @staticmethod
    def _historical_expected_identity(source_row):
        if not isinstance(source_row, dict):
            return None
        return source_row.get("historical_expected_identity")

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
            *self._format_pre_ad_summary(result),
            "",
            "Цена продажи:",
            self._format_money(
                result.get("unit_price")
            ),
            "",
            "Баллы за скидки:",
            self._format_money_with_share(
                result.get("discount_points"),
                result.get("unit_price"),
            ),
            "Выручка для расчёта налога:",
            self._format_money_with_share(
                result.get("revenue_tax_base"),
                result.get("unit_price"),
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
            self._format_money_with_share(
                result.get("tax"),
                result.get("unit_price"),
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

    def format_expense_breakdown(self, result):
        """Explain the exact existing pre-ad snapshot without re-reading sources."""
        if not isinstance(result, dict) or result.get("error") is True:
            return "Расшифровка недоступна: нет результата юнит-экономики."
        projection = result.get("pre_ad_margin")
        if not isinstance(projection, dict):
            return "Расшифровка недоступна: в результате нет маржи до рекламы."

        lines = [
            f"🧾 Из чего складывается маржа — SKU {result.get('sku') or '—'}",
            "Снимок той же карточки; источники повторно не запрашивались.",
        ]
        status = projection.get("status")
        if status != "AVAILABLE":
            reason = projection.get("reason")
            if isinstance(reason, str) and reason:
                explanation = self.PRE_AD_REASON_LABELS.get(
                    reason,
                    "данных недостаточно или они несовместимы",
                )
                lines.append("Маржа до рекламы не рассчитана: " + explanation + ".")
            else:
                lines.append("Маржа до рекламы пока не рассчитана.")
            lines.append("Неизвестные суммы не заменены нулём.")
            self._append_unavailable_expense_scope(lines, projection)
            self._append_pre_ad_next_steps(lines, result, projection)
            self._append_breakdown_periods(lines, result, projection)
            return "\n".join(lines)

        if projection.get("basis") == "CURRENT_MODEL":
            lines.extend(self._format_current_expense_breakdown(result, projection))
        elif projection.get("basis") == "HISTORICAL_RECONCILIATION":
            lines.extend(self._format_historical_expense_breakdown(projection))
        else:
            lines.append("Основание расчёта не поддерживается для расшифровки.")
        self._append_pre_ad_next_steps(lines, result, projection)
        self._append_breakdown_periods(lines, result, projection)
        return "\n".join(lines)

    def _append_pre_ad_next_steps(self, lines, result, projection):
        scope = projection.get("expense_scope")
        scope = scope if isinstance(scope, dict) else {}
        unknown = scope.get("unknown_non_ad_expense_keys") or []
        if "COGS" in unknown:
            if getattr(self, "cost_service", None) is not None:
                lines.append(
                    "Действие: себестоимость можно указать для этого SKU в разделе "
                    "«Себестоимость»; дату начала и применение ко всей истории "
                    "нужно подтвердить отдельно."
                )
            else:
                lines.append(
                    "Себестоимость не подключена к локальному хранилищу: её нельзя "
                    "сохранить из этой карточки. Значение остаётся неизвестным, не 0 ₽."
                )
        if "OZON_COMMISSION" in unknown:
            lines.append(
                "Комиссия Ozon не подтверждена для этой цены. В плановой экономике "
                "можно указать ставку вручную; она останется допущением сценария, "
                "а не фактическим тарифом или начислением."
            )
        if projection.get("advertising_status") == "UNKNOWN":
            lines.append(
                "Расходы на рекламу по SKU не подтверждены. В плановом сценарии "
                "можно задать рекламное допущение; оно не меняет фактическую маржу."
            )
        unsupported = [
            key for key in unknown
            if key not in {"COGS", "OZON_COMMISSION"}
        ]
        if unsupported:
            labels = [
                self.PRE_AD_EXPENSE_LABELS[key]
                for key in unsupported
                if isinstance(key, str) and key in self.PRE_AD_EXPENSE_LABELS
            ]
            if labels:
                lines.append(
                    "Для отдельных SKU нет подтверждённого источника или поддерживаемого "
                    "ввода по статьям: " + ", ".join(labels)
                    + ". Они не распределены на товар и не заменены нулём."
                )

    def _append_unavailable_expense_scope(self, lines, projection):
        scope = projection.get("expense_scope")
        if not isinstance(scope, dict):
            return
        unknown = scope.get("unknown_non_ad_expense_keys") or []
        labels = [
            self.PRE_AD_EXPENSE_LABELS[key]
            for key in unknown
            if isinstance(key, str) and key in self.PRE_AD_EXPENSE_LABELS
        ]
        if labels:
            lines.append("Не подтверждены: " + ", ".join(labels) + ".")
        if projection.get("advertising_status") == "UNKNOWN":
            lines.append("Реклама: сумма неизвестна, не считается нулём.")
        excluded = scope.get("excluded_expense_keys") or []
        if "FIXED_STORE_OVERHEAD" in excluded:
            lines.append("Постоянные расходы магазина не распределяются на SKU.")

    def _format_current_expense_breakdown(self, result, projection):
        lines = [
            "Основание: текущая модель; до рекламы, после налога.",
            "Знаменатель: 1 успешная единица; процент — от цены продавца до баллов.",
        ]
        tax_mode = self.PRE_AD_TAX_MODE_LABELS.get(
            projection.get("tax_mode"),
            "не подтверждён",
        )
        lines.append("Налоговая политика: " + tax_mode + ".")
        price = self._breakdown_decimal(projection.get("price_per_unit_rub"))
        tax = self._breakdown_decimal(projection.get("tax_per_unit_rub"))
        profit = self._breakdown_decimal(projection.get("profit_per_unit_rub"))
        scope = projection.get("expense_scope")
        known = scope.get("known_non_ad_expenses_rub") if isinstance(scope, dict) else None
        known = known if isinstance(known, dict) else {}
        expenses = {}
        for key, value in known.items():
            amount = self._breakdown_decimal(value)
            if amount is not None and key in self.PRE_AD_EXPENSE_LABELS:
                expenses[key] = amount

        if price is None or tax is None or profit is None:
            lines.append("Сверка сумм недоступна: обязательная сумма отсутствует.")
            return lines

        lines.append("\nНа 1 успешную единицу:")
        lines.append("Выручка продавца: " + self._signed_breakdown_money(price))
        for key in sorted(expenses):
            contribution = -expenses[key]
            label = self.PRE_AD_EXPENSE_LABELS[key].capitalize()
            source = self._current_expense_source(key, result, projection)
            lines.append(
                f"{label}: {self._signed_breakdown_money(contribution)}"
                + (" · " + source if source else "")
            )

        subtotal_before_tax = price - sum(expenses.values(), Decimal("0.00"))
        lines.append(
            "Прибыль до налога по учтённым расходам: "
            + self._signed_breakdown_money(subtotal_before_tax)
        )
        lines.append("Налог: " + self._signed_breakdown_money(-tax))
        reconciled = subtotal_before_tax - tax
        lines.append("Маржа до рекламы: " + self._signed_breakdown_money(reconciled))
        difference = reconciled - profit
        if difference == Decimal("0.00"):
            lines.append("Сверка с карточкой: 0.00 ₽ расхождения.")
        else:
            lines.append(
                "⚠️ Сверка с карточкой не сошлась: "
                + self._signed_breakdown_money(difference)
                + ". Суммы не скорректированы автоматически."
            )

        unknown = scope.get("unknown_non_ad_expense_keys") or [] if isinstance(scope, dict) else []
        unknown_labels = [
            self.PRE_AD_EXPENSE_LABELS[key]
            for key in unknown
            if isinstance(key, str) and key in self.PRE_AD_EXPENSE_LABELS
        ]
        if unknown_labels:
            lines.append("Не включены: " + ", ".join(unknown_labels) + " — суммы не подтверждены.")
        advertising = projection.get("advertising_status")
        if advertising == "UNKNOWN":
            lines.append("Реклама исключена из показателя до рекламы; фактическая сумма неизвестна, это не 0 ₽.")
        excluded = scope.get("excluded_expense_keys") or [] if isinstance(scope, dict) else []
        if "FIXED_STORE_OVERHEAD" in excluded:
            lines.append("Постоянные расходы магазина не распределяются на SKU.")

        cross_docking = result.get("cross_docking")
        if "CROSS_DOCKING" in expenses and isinstance(cross_docking, dict):
            amount = (
                cross_docking.get("expense_by_sku")
                if cross_docking.get("method") == "sku_accrual_cost_per_delivered_crossdock_unit"
                else cross_docking.get("expense_total")
            )
            units = (
                cross_docking.get("supplied_units_sku")
                if cross_docking.get("method") == "sku_accrual_cost_per_delivered_crossdock_unit"
                else cross_docking.get("supplied_units_store")
            )
            if amount is not None and units is not None:
                normalized_amount = self._breakdown_decimal(amount)
                lines.append(
                    "Кросс-докинг — детализация строки выше: начисления "
                    + (f"{normalized_amount:.2f} ₽" if normalized_amount is not None else "—")
                    + " / фактически принято "
                    + str(units)
                    + " шт.; повторно не прибавлять."
                )
        return lines

    def _format_historical_expense_breakdown(self, projection):
        scope = projection.get("expense_scope")
        scope = scope if isinstance(scope, dict) else {}
        advertising = projection.get("advertising")
        advertising = advertising if isinstance(advertising, dict) else {}
        units = projection.get("units_sold")
        revenue = self._breakdown_decimal(projection.get("revenue_rub"))
        before_profit = self._breakdown_decimal(projection.get("profit_rub"))
        tax = self._breakdown_decimal(projection.get("tax_rub"))
        ad = self._breakdown_decimal(advertising.get("amount_rub"))
        known = scope.get("known_non_ad_expenses_rub")
        known = known if isinstance(known, dict) else {}
        known_expenses = {
            key: amount
            for key, value in known.items()
            if key in self.PRE_AD_EXPENSE_LABELS
            and (amount := self._breakdown_decimal(value)) is not None
        }
        if (
            type(units) is not int or units <= 0
            or revenue is None or before_profit is None or tax is None
            or ad is None or advertising.get("included_in_net") is not True
        ):
            return [
                "Историческая расшифровка неполная: нет точного объёма, налога "
                "или подтверждённых рекламных начислений."
            ]

        known_total = sum(known_expenses.values(), Decimal("0.00"))
        other_remainder = revenue - known_total - tax - before_profit
        after_ad = projection.get("after_ad")
        after_total = (
            self._breakdown_decimal(after_ad.get("profit_rub"))
            if isinstance(after_ad, dict)
            else None
        )
        lines = [
            "Основание: сверка исторического SKU; налог сохранён из результата периода.",
            f"Знаменатель: {units} успешных единиц; источник — точные начисления по SKU.",
            "\nЗа весь период:",
            "Выручка продавца: " + self._signed_breakdown_money(revenue),
        ]
        for key in sorted(known_expenses):
            lines.append(
                self.PRE_AD_EXPENSE_LABELS[key].capitalize()
                + ": "
                + self._signed_breakdown_money(-known_expenses[key])
                + " · известная часть expense scope"
            )
        lines.append(
            "Остаток прочих не рекламных начислений (расчётный, не разбит по типам): "
            + self._signed_breakdown_money(-other_remainder)
        )
        lines.append("Налог периода: " + self._signed_breakdown_money(-tax))
        lines.append("Маржа до рекламы: " + self._signed_breakdown_money(before_profit))
        lines.append(
            "Сверка до рекламы: "
            + self._signed_breakdown_money(revenue - known_total - other_remainder - tax)
            + " (ожидается " + self._format_money(before_profit) + ")."
        )
        pre_ad_difference = revenue - known_total - other_remainder - tax - before_profit
        lines.append(
            "Сверка суммы до рекламы: "
            + self._format_money(pre_ad_difference)
            + " расхождения; остаток прочих начислений рассчитан балансом."
        )
        lines.append(
            "Реклама exact-SKU, уже включённая в net: "
            + self._signed_breakdown_money(-ad)
            + f" · {units} шт., корректировки учтены один раз"
        )
        if after_total is not None:
            lines.append("Прибыль после рекламы: " + self._signed_breakdown_money(after_total))
            ad_difference = before_profit - ad - after_total
            if ad_difference == Decimal("0.00"):
                lines.append("Сверка after-ad: 0.00 ₽ расхождения.")
            else:
                lines.append(
                    "⚠️ Сверка after-ad не сошлась: "
                    + self._signed_breakdown_money(ad_difference)
                    + ". Суммы не скорректированы."
                )
        unknown = scope.get("unknown_non_ad_expense_keys") or []
        labels = [
            self.PRE_AD_EXPENSE_LABELS[key]
            for key in unknown
            if isinstance(key, str) and key in self.PRE_AD_EXPENSE_LABELS
        ]
        if labels:
            lines.append("Не распределены по отдельным типам: " + ", ".join(labels) + ".")
        lines.append("Расчётный остаток — баланс, а не подпись операции Ozon; не считайте подтипы повторно.")
        return lines

    def _current_expense_source(self, key, result, projection):
        if key == "COGS":
            return "себестоимость из локальной записи, на 1 шт."
        if key == "CROSS_DOCKING":
            evidence = result.get("cross_docking")
            if isinstance(evidence, dict):
                period = " — ".join(
                    str(evidence.get(field))
                    for field in ("date_from", "date_to")
                    if evidence.get(field)
                )
                method = "SKU" if evidence.get("method") == "sku_accrual_cost_per_delivered_crossdock_unit" else "магазин"
                return f"среднее по {method}, delivered cross-dock units" + (f", период {period}" if period else "")
        periods = projection.get("source_periods") or {}
        finance = periods.get("current_finance_averages") if isinstance(periods, dict) else None
        if isinstance(finance, dict):
            start, end = finance.get("date_from"), finance.get("date_to")
            if start and end:
                return f"среднее финансовых начислений за {start} — {end}, на 1 шт."
        return "текущая модель, на 1 шт."

    def _append_breakdown_periods(self, lines, result, projection):
        periods = projection.get("source_periods")
        if not isinstance(periods, dict):
            return
        seller_price = periods.get("seller_price")
        if isinstance(seller_price, dict):
            as_of = self._format_as_of(seller_price.get("as_of"))
            if as_of:
                lines.append("Цена продавца: актуальна на " + as_of + ".")
        finance = periods.get("current_finance_averages")
        if isinstance(finance, dict) and finance.get("observed_sales_days") is not None:
            sales = result.get("finance_sample_sales") if isinstance(result, dict) else None
            sales_text = str(sales) if type(sales) is int and sales >= 0 else "—"
            requested = finance.get("requested_days")
            requested_text = str(requested) if type(requested) is int else "—"
            lines.append(
                "Окно начислений: "
                + sales_text
                + " продаж; дни с продажами "
                + str(finance.get("observed_sales_days"))
                + "/"
                + requested_text
                + "."
            )
        historical = periods.get("historical_window")
        if isinstance(historical, dict):
            start, end = historical.get("date_from"), historical.get("date_to")
            if start and end:
                lines.append(f"Окно начислений Ozon: {start} — {end}.")
        cross = periods.get("cross_docking")
        if isinstance(cross, dict):
            start, end = cross.get("date_from"), cross.get("date_to")
            if start and end:
                days = cross.get("days_complete")
                expected = cross.get("days_expected")
                completeness = f" · полные дни {days}/{expected}" if days is not None and expected is not None else ""
                lines.append(f"Окно кросс-докинга: {start} — {end}{completeness}.")

    @staticmethod
    def _breakdown_decimal(value):
        if isinstance(value, bool) or value in (None, ""):
            return None
        try:
            amount = Decimal(str(value))
            if not amount.is_finite():
                return None
            return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        except (InvalidOperation, ValueError, TypeError):
            return None

    @classmethod
    def _signed_breakdown_money(cls, amount):
        value = cls._breakdown_decimal(amount)
        if value is None:
            return "—"
        sign = "+" if value >= 0 else "−"
        return sign + f"{abs(value):.2f} ₽"

    def _format_current_response(self, result):
        sku = result.get("sku", "—")
        price = result.get("unit_price")

        lines = [
            f"💰 Юнит-экономика — {sku}",
            *self._format_pre_ad_summary(result),
            "",
            "Цена:",
            self._format_money_with_share(
                price,
                price
            ),
            "",
            "Баллы за скидки:",
            self._format_money_with_share(
                result.get("discount_points"),
                price,
            ),
            "Выручка для расчёта налога:",
            self._format_money_with_share(
                result.get("revenue_tax_base"),
                price,
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
            *self._format_current_cost_basis(result.get("cost_basis")),
            "",
            "Налог:",
            self._format_money_with_share(
                result.get("tax"),
                price
            ),
        ]

        cross_docking = result.get("cross_docking")
        if isinstance(cross_docking, dict):
            amount = result.get("cross_docking_per_unit")
            if amount is not None:
                period = " — ".join(
                    value for value in (
                        str(cross_docking.get("date_from") or ""),
                        str(cross_docking.get("date_to") or ""),
                    ) if value
                )
                label = "Кросс-докинг — на фактически поставленную единицу"
                if period:
                    label += " за " + period
                lines.extend([
                    "",
                    label + ":",
                    self._format_money_with_share(amount, price),
                ])
                basis = self._cross_docking_basis(cross_docking)
                if basis:
                    lines.append(basis)
            else:
                lines.extend([
                    "",
                    "Кросс-докинг — на фактически поставленную единицу:",
                    "не учтён: нет подтверждённой применимой ставки",
                ])

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

        note = result.get("note")
        if note:
            lines.extend(["", note])

        return "\n".join(lines)

    @classmethod
    def _format_current_cost_basis(cls, basis):
        if not isinstance(basis, dict):
            return []
        methods = {
            "FIFO_FINITE_LAYER": "FIFO: следующая единица из текущего слоя",
            "FIFO_OPEN_RATE": "FIFO: открытая ставка, остаток слоя неизвестен",
            "FIFO_UNAVAILABLE": "FIFO: следующая стоимость не подтверждена",
            "LEGACY_EFFECTIVE_DATED": "датированная себестоимость (FIFO ещё не задан)",
            "LEGACY_UNAVAILABLE": "датированная себестоимость не найдена",
            "UNAVAILABLE": "источник себестоимости недоступен",
        }
        method = methods.get(str(basis.get("method") or ""))
        lines = [method + "."] if method else []
        as_of = str(basis.get("as_of_date") or "")
        cutoff = str(basis.get("cutoff_date") or "")
        if as_of:
            lines.append("Срез себестоимости на " + as_of + ".")
        if cutoff:
            lines.append("Точка фактической отсечки FIFO: " + cutoff + ".")
        remaining = basis.get("next_layer_remaining_units")
        if type(remaining) is int and remaining >= 0:
            lines.append(f"Остаток текущего слоя: {remaining} шт.")
        planned = basis.get("next_planned_rate")
        if isinstance(planned, dict):
            amount = cls._breakdown_decimal(planned.get("unit_cost_rub"))
            effective = str(planned.get("effective_date") or "")
            if amount is not None:
                lines.append(
                    "Следующая ставка: " + f"{amount:.2f} ₽/шт."
                    + (" с " + effective if effective else "")
                    + "; она не подменяет текущий FIFO-слой."
                )
        completeness = str(basis.get("completeness") or "")
        if completeness in {
            "CONFIRMED_SNAPSHOT_MODEL_ONLY",
            "CONFIRMED_REPLAY_MODEL_ONLY",
            "LEGACY_EFFECTIVE_COST_CONFIRMED",
        }:
            lines.append("Полнота себестоимости: подтверждена для текущей плановой оценки.")
        else:
            reason = str(basis.get("reason_code") or completeness or "данные неполны")
            lines.append("Расчёт неполный: " + reason + "; себестоимость не подставлена.")
        if basis.get("model_only") is True:
            lines.append("FIFO-себестоимость используется только для плановой оценки.")
        return lines

    def _format_pre_ad_summary(self, result):
        projection = result.get("pre_ad_margin")
        if not isinstance(projection, dict):
            return []

        lines = ["", "Маржа до рекламы (после налога):"]
        profit = projection.get("profit_per_unit_rub")
        margin = projection.get("margin_percent")
        if (
            projection.get("status") == "AVAILABLE"
            and profit is not None
            and margin is not None
        ):
            lines.append(
                self._format_money(profit)
                + " / шт. · "
                + self._format_percent(margin)
                + " от цены продавца"
            )
        else:
            lines.append("не рассчитана")
            reason = projection.get("reason")
            if isinstance(reason, str) and reason:
                lines.append(
                    "Причина: "
                    + self.PRE_AD_REASON_LABELS.get(
                        reason,
                        "данных недостаточно или они несовместимы",
                    )
                )

        basis = projection.get("tax_basis")
        tax = projection.get("tax_per_unit_rub")
        if tax is None:
            tax = result.get("tax")
        if basis == "CURRENT_TAX_POLICY":
            mode = self.PRE_AD_TAX_MODE_LABELS.get(
                projection.get("tax_mode"),
                "не подтверждён",
            )
            tax_text = self._format_money(tax) + " / шт."
            lines.append("Налог: " + mode + " · " + tax_text)
        elif basis == "AS_RECORDED_IN_PERIOD_RESULT":
            lines.append(
                "Налог сохранён из результата исторического периода: "
                + self._format_money(tax)
                + " / шт."
            )
        elif basis:
            lines.append("Налоговое основание: " + str(basis))
        else:
            lines.append("Налог: не подтверждён")

        scope = projection.get("expense_scope")
        scope_status = scope.get("status") if isinstance(scope, dict) else None
        if scope_status == "COMPLETE":
            lines.append("Полнота расходов без рекламы: подтверждена")
        elif scope_status == "PARTIAL":
            lines.append("Полнота расходов без рекламы: частичная")
            unknown = scope.get("unknown_non_ad_expense_keys") or []
            labels = [
                self.PRE_AD_EXPENSE_LABELS[key]
                for key in unknown
                if key in self.PRE_AD_EXPENSE_LABELS
            ]
            if labels:
                lines.append("Не подтверждены: " + ", ".join(labels[:5]))
        else:
            lines.append("Полнота расходов без рекламы: неизвестна")

        advertising_status = projection.get("advertising_status")
        after_ad = projection.get("after_ad")
        if (
            advertising_status == "CONFIRMED_INCLUDED_IN_NET"
            and isinstance(after_ad, dict)
            and after_ad.get("profit_per_unit_rub") is not None
            and after_ad.get("margin_percent") is not None
        ):
            lines.append(
                "После учтённой рекламы: "
                + self._format_money(after_ad.get("profit_per_unit_rub"))
                + " / шт. · "
                + self._format_percent(after_ad.get("margin_percent"))
            )
        elif advertising_status == "UNKNOWN":
            lines.append(
                "После рекламы: не рассчитана — расход рекламы неизвестен"
            )
        else:
            lines.append("После рекламы: нет подтверждённого результата")

        periods = projection.get("source_periods")
        if isinstance(periods, dict):
            seller_price = periods.get("seller_price")
            as_of = (
                self._format_as_of(seller_price.get("as_of"))
                if isinstance(seller_price, dict)
                else None
            )
            finance = periods.get("current_finance_averages")
            if isinstance(finance, dict):
                start = finance.get("date_from")
                end = finance.get("date_to")
                days = finance.get("observed_sales_days")
                if start and end:
                    period_text = f"Начисления Ozon: {start} — {end}"
                    if days is not None:
                        period_text += f" · дни с продажами: {days}"
                    lines.append(period_text)
            historical = periods.get("historical_window")
            if isinstance(historical, dict):
                start = historical.get("date_from")
                end = historical.get("date_to")
                if start and end:
                    lines.append(
                        f"Исторический период начислений Ozon: {start} — {end}"
                    )
            if as_of:
                lines.append("Цена продавца актуальна на " + as_of)

        return lines

    def _cross_docking_basis(self, evidence):
        method = evidence.get("method")
        is_sku_rate = (
            method == "sku_accrual_cost_per_delivered_crossdock_unit"
        )
        label = "оценка по SKU" if is_sku_rate else "оценка по магазину"
        cost = evidence.get("expense_by_sku") if is_sku_rate else evidence.get("expense_total")
        units = (
            evidence.get("supplied_units_sku")
            if is_sku_rate
            else evidence.get("supplied_units_store")
        )
        parts = [label]
        try:
            unit_count = int(units)
            if unit_count > 0 and cost is not None:
                amount = float(cost)
                if amount >= 0 and amount < float("inf"):
                    parts.append(
                        "начисления " + self._format_money(amount)
                        + " / фактически принято " + str(unit_count) + " шт."
                    )
        except (TypeError, ValueError, OverflowError):
            pass
        days_complete = evidence.get("days_complete")
        days_expected = evidence.get("days_expected")
        if days_complete is not None and days_expected is not None:
            parts.append(
                "покрытие " + str(days_complete) + "/" + str(days_expected) + " дней"
            )
        return "; ".join(parts)

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

    def _current_cost_date_scope(self):
        getter = getattr(
            self.cost_adapter or self.cost_service,
            "get_current_cost_date",
            None,
        )
        if not callable(getter):
            return None
        try:
            value = getter()
        except Exception:
            return None
        return str(value) if value else None

    def _resolve_current_cost_basis(self, product, store_id, cost_date):
        try:
            resolved = self.cost_adapter.resolve_current_cost(
                product,
                store_id=store_id,
                as_of_date=cost_date,
            )
        except Exception:
            resolved = None
        if (
            not isinstance(resolved, dict)
            or not isinstance(resolved.get("cost_basis"), dict)
            or not str(resolved.get("cost_revision") or "").strip()
        ):
            revision = sha256(
                ("COST_ADAPTER_UNAVAILABLE:" + str(cost_date or "")).encode()
            ).hexdigest()
            return {
                "cost_per_unit_rub": None,
                "cost_updated_at": None,
                "cost_method": "UNAVAILABLE",
                "cost_revision": revision,
                "cost_basis": {
                    "method": "UNAVAILABLE",
                    "completeness": "COST_ADAPTER_UNAVAILABLE",
                    "reason_code": "FIFO_COST_ADAPTER_UNAVAILABLE",
                    "as_of_date": cost_date,
                    "next_unit_cost_rub": None,
                    "next_layer_remaining_units": None,
                    "next_planned_rate": None,
                    "model_only": True,
                    "factual_period_profit_eligible": False,
                    "cache_revision": revision,
                },
            }
        return resolved

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

    def _empty_current_result(
        self, sku, facts, accrual_dates=None, cost_evidence=None,
    ):
        missing = list(
            facts.get("missing_data") or []
        )
        if "unit_price" not in missing:
            missing.insert(0, "unit_price")

        prepared_facts = dict(facts)
        prepared_facts["tax_base_policy"] = self.current_tax_base_policy
        prepared_facts["pre_ad_source_periods"] = (
            self._current_pre_ad_source_periods(facts, accrual_dates or [])
        )
        pre_ad_margin = self.unit_economics_provider.build_current(
            prepared_facts,
            product_cost=None,
        ).get("pre_ad_margin")

        result = {
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
            "discount_points": facts.get("discount_points_per_unit"),
            "revenue_tax_base": None,
            "tax_base": None,
            "tax": None,
            "tax_effective_percent": None,
            "net_profit_per_unit": None,
            "margin_percent": None,
            "missing_fields": missing,
            "as_of": facts.get("as_of"),
            "pre_ad_margin": pre_ad_margin,
            "note": "Актуальный расчёт пока недоступен"
        }
        if isinstance(cost_evidence, dict):
            result["cost"] = cost_evidence.get("cost_per_unit_rub")
            result["cost_basis"] = deepcopy(
                cost_evidence.get("cost_basis") or {}
            )
            result["cost_method"] = cost_evidence.get("cost_method")
            result["cost_revision"] = cost_evidence.get("cost_revision")
            result["cost_as_of"] = cost_evidence.get("cost_updated_at")
        return result

    def _current_pre_ad_source_periods(self, facts, accrual_dates):
        return {
            "seller_price": {
                "as_of": facts.get("as_of"),
            },
            "current_finance_averages": {
                "date_from": min(accrual_dates) if accrual_dates else None,
                "date_to": max(accrual_dates) if accrual_dates else None,
                "requested_days": len(accrual_dates),
                "observed_sales_days": facts.get("finance_sample_days"),
            },
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
            "pre_ad_margin": self.historical_pre_ad_margin_service.build(
                None,
            ),
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
            note = (
                "Прибыль не рассчитана, пока не получены "
                "все обязательные данные."
            )
        else:
            sales = result.get("finance_sample_sales")
            days = result.get("finance_sample_days")
            if sales and days:
                note = (
                    "Основано на последних финансовых начислениях "
                    f"Ozon: {sales} продаж за {days} дн."
                )
            else:
                note = "Расчёт по актуальной цене продавца."

        cross_docking = result.get("cross_docking")
        if isinstance(cross_docking, dict):
            if result.get("cross_docking_included") is True:
                note += (
                    " Учтено среднее начислений кросс-докинга за 56 завершённых дней; "
                    "знаменатель — фактически поставленные единицы."
                )
            else:
                note += (
                    " Расчёт показан без кросс-докинга: "
                    + str(cross_docking.get("reason") or "нет подтверждённой ставки")
                    + "."
                )
        pre_ad = result.get("pre_ad_margin")
        expense_scope = (
            pre_ad.get("expense_scope")
            if isinstance(pre_ad, dict)
            else None
        )
        if isinstance(expense_scope, dict) and expense_scope.get("status") == "PARTIAL":
            note += (
                " Маржа до рекламы рассчитана по учтённым расходам; "
                "хранение, потери от возвратов и часть прочих расходов "
                "не подтверждены."
            )
        return note

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
        formatted_share = f"{share:.1f}"
        if formatted_share == "-0.0":
            formatted_share = "0.0"
        return f"{money} — {formatted_share}%"

    def _share(self, value, price):
        if value is None or price in (None, 0):
            return None
        return float(value) / float(price) * 100

    def _format_percent(self, value):
        if value is None:
            return "—"

        formatted = f"{value:.2f}"
        if formatted == "-0.00":
            formatted = "0.00"
        return f"{formatted}%"
