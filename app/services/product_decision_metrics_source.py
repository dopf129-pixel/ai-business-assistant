from datetime import datetime, timezone


class ProductDecisionMetricsSource:

    def __init__(
        self,
        product_service,
        analytics_service,
        metrics_service,
        stock_intelligence_service,
        observation_clock=None
    ):
        self.product_service = product_service
        self.analytics_service = analytics_service
        self.metrics_service = metrics_service
        self.stock_intelligence_service = stock_intelligence_service
        self.observation_clock = observation_clock or (
            lambda: datetime.now(timezone.utc)
        )
        self._cache = {}

    def sales(self, sku):
        target_sku = str(sku or "").strip()
        prepared = self._load(target_sku, refresh=True)
        return dict(prepared.get("sales") or {})

    def stock(self, sku):
        target_sku = str(sku or "").strip()
        prepared = self._load(target_sku)
        self._cache.pop(target_sku, None)
        return dict(prepared.get("stock") or {})

    def _load(self, sku, refresh=False):
        target_sku = str(sku or "").strip()

        if not refresh and target_sku in self._cache:
            return self._cache[target_sku]

        product = self._find_product(target_sku)

        if product is None:
            result = {
                "sales": {"error": True},
                "stock": {"error": True},
            }
            self._cache[target_sku] = result
            return result

        product_id = product.get("product_id")
        current_period = self.analytics_service.get_period()
        previous_period = self.analytics_service.get_previous_period()

        if (
            not isinstance(current_period, dict)
            or current_period.get("error")
            or not isinstance(previous_period, dict)
            or previous_period.get("error")
        ):
            result = self._missing_result(
                product_id=product_id,
                sku=target_sku,
                missing=(
                    "sales_velocity",
                    "sales_trend",
                    "current_stock",
                    "days_of_stock",
                    "stock_priority",
                )
            )
            self._cache[target_sku] = result
            return result

        current_finance = self.analytics_service.analyze_finance(
            sku=target_sku
        )
        previous_finance = self._previous_finance(
            previous_period,
            target_sku
        )

        current_sales = self._sales_count(current_finance)
        previous_sales = self._sales_count(previous_finance)
        stock_snapshot = self._current_stock_snapshot(product_id)
        current_stock = stock_snapshot["current_stock"]
        period_days = current_period.get("days")

        stock_result = self.stock_intelligence_service.analyze(
            stock_data=(
                {
                    "product_id": str(product_id),
                    "current_stock": current_stock,
                }
                if current_stock is not None
                else None
            ),
            sales_data=(
                {
                    "product_id": str(product_id),
                    "sales_count": current_sales,
                }
                if current_sales is not None
                else None
            ),
            period_days=period_days
        )

        sales_velocity = (
            stock_result.get("sales_velocity")
            if isinstance(stock_result, dict)
            else None
        )
        sales_trend = self._sales_trend(
            current_sales=current_sales,
            previous_sales=previous_sales
        )

        sales_missing = []
        if sales_velocity is None:
            sales_missing.append("sales_velocity")
        if sales_trend is None:
            sales_missing.append("sales_trend")

        stock_missing = []
        if current_stock is None:
            stock_missing.append("current_stock")
        if not isinstance(stock_result, dict) or stock_result.get("error"):
            stock_missing.extend(
                ["days_of_stock", "stock_priority"]
            )

        sales_payload = {
            "product_id": str(product_id),
            "sku": target_sku,
            "sales_velocity": sales_velocity,
            "sales_trend": sales_trend,
            "sales_period_from": current_period.get("date_from"),
            "sales_period_to": current_period.get("date_to"),
            "sales_observed_at": self._observed_at(),
            "missing_data": self._unique(sales_missing),
        }
        self._copy_exact_evidence(
            sales_payload,
            current_finance,
            "sales_source_recorded_at"
        )

        stock_payload = {
            "product_id": str(product_id),
            "sku": target_sku,
            "current_stock": current_stock,
            "days_of_stock": (
                stock_result.get("days_of_stock")
                if isinstance(stock_result, dict)
                else None
            ),
            "priority": (
                stock_result.get("priority")
                if isinstance(stock_result, dict)
                and not stock_result.get("error")
                else None
            ),
            "stock_observed_at": self._observed_at(),
            "missing_data": self._unique(stock_missing),
        }
        self._copy_exact_evidence(
            stock_payload,
            stock_snapshot,
            "stock_source_recorded_at"
        )

        result = {
            "sales": sales_payload,
            "stock": stock_payload,
        }

        self._cache[target_sku] = result
        return result

    def _find_product(self, sku):
        for product in self.product_service.load_products() or []:
            normalized = self._normalize_product(product)
            if normalized and sku in {
                str(normalized.get("offer_id") or ""),
                str(normalized.get("sku") or ""),
            }:
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
                "sku": product[2],
            }
        except (TypeError, IndexError):
            return None

    def _previous_finance(self, previous_period, sku):
        finance_analytics = getattr(
            self.analytics_service,
            "finance_analytics",
            None
        )

        if finance_analytics is None:
            return None

        return finance_analytics.get_period_finance(
            date_from=previous_period.get("date_from"),
            date_to=previous_period.get("date_to"),
            sku=sku
        )

    def _sales_count(self, result):
        if not isinstance(result, dict) or result.get("error"):
            return None
        value = result.get("sales_count")
        if value is None:
            return None
        return int(value)

    def _current_stock(self, product_id):
        return self._current_stock_snapshot(
            product_id
        )["current_stock"]

    def _current_stock_snapshot(self, product_id):
        result = self.metrics_service.get_product_metrics(product_id)

        if not isinstance(result, dict) or result.get("error"):
            return {
                "current_stock": None,
                "stock_source_recorded_at": None,
            }

        metrics = result.get("metrics") or {}
        source_recorded_at = result.get(
            "stock_source_recorded_at"
        )
        if source_recorded_at is None and isinstance(metrics, dict):
            source_recorded_at = metrics.get(
                "stock_source_recorded_at"
            )

        return {
            "current_stock": metrics.get("fbo_available"),
            "stock_source_recorded_at": source_recorded_at,
        }

    def _sales_trend(self, current_sales, previous_sales):
        if current_sales is None or previous_sales is None:
            return None

        comparison_service = getattr(
            self.analytics_service,
            "comparison_service",
            None
        )

        if comparison_service is not None:
            comparison = comparison_service.compare_value(
                "Продажи",
                current_sales,
                previous_sales
            )
            change = comparison.get("change_percent")
        else:
            if previous_sales == 0:
                change = 0 if current_sales == 0 else 100
            else:
                change = (
                    (current_sales - previous_sales)
                    / abs(previous_sales)
                ) * 100

        if change > 0:
            return "GROWING"
        if change < 0:
            return "DECLINING"
        return "STABLE"

    def _missing_result(self, product_id, sku, missing):
        common = {
            "product_id": (
                str(product_id)
                if product_id is not None
                else None
            ),
            "sku": sku,
        }
        return {
            "sales": {
                **common,
                "sales_velocity": None,
                "sales_trend": None,
                "missing_data": [
                    item for item in missing
                    if item in {"sales_velocity", "sales_trend"}
                ],
            },
            "stock": {
                **common,
                "current_stock": None,
                "days_of_stock": None,
                "priority": None,
                "missing_data": [
                    item for item in missing
                    if item in {
                        "current_stock",
                        "days_of_stock",
                        "stock_priority",
                    }
                ],
            },
        }

    def _copy_exact_evidence(self, target, source, field):
        if not isinstance(source, dict):
            return
        if field not in source or source.get(field) is None:
            return
        target[field] = source.get(field)

    def _observed_at(self):
        value = self.observation_clock()
        if isinstance(value, datetime):
            if value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
            return value.astimezone(timezone.utc).isoformat()
        return str(value)

    def _unique(self, values):
        result = []
        for value in values:
            if value not in result:
                result.append(value)
        return result
