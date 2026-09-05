from datetime import date, datetime, timedelta


class PeriodProfitFinanceSkuScopeService:
    """Scope product cost calculation to unique SKUs actually present in Ozon finance."""

    def __init__(self, summary_service, finance_service):
        self.summary_service = summary_service
        self.finance_service = finance_service

    def calculate(self, date_from, date_to, products):
        scoped = self._scope_products(date_from, date_to, products)
        if scoped.get("error") is True:
            return scoped

        result = self.summary_service.calculate(
            date_from,
            date_to,
            scoped["products"],
        )
        if not isinstance(result, dict):
            return {
                "error": True,
                "code": "PERIOD_PROFIT_SUMMARY_INVALID",
                "message": "Некорректный результат расчёта прибыли за период",
            }

        if result.get("error") is False:
            result = dict(result)
            result["finance_sku_scope_applied"] = scoped["finance_sku_scope_applied"]
            result["finance_sku_count"] = scoped["finance_sku_count"]
            result["catalog_duplicate_sku_count"] = scoped["catalog_duplicate_sku_count"]

        return result

    def _scope_products(self, date_from, date_to, products):
        normalized = self._product_index(products)
        if normalized is None:
            return self._error(
                "PERIOD_PROFIT_PRODUCTS_UNAVAILABLE",
                "Нет пригодных товаров для расчёта периода",
            )

        sku_result = self._load_period_skus(date_from, date_to)
        if sku_result.get("error") is True:
            return sku_result

        finance_skus = sku_result["skus"]
        duplicate_count = normalized["duplicate_count"]
        product_by_sku = normalized["products"]

        if not finance_skus:
            return {
                "error": False,
                "products": list(product_by_sku.values()),
                "finance_sku_scope_applied": True,
                "finance_sku_count": 0,
                "catalog_duplicate_sku_count": duplicate_count,
            }

        missing = [sku for sku in finance_skus if sku not in product_by_sku]
        if missing:
            preview = ", ".join(missing[:5])
            if len(missing) > 5:
                preview += ", ..."
            return self._error(
                "PERIOD_PROFIT_FINANCE_SKU_CATALOG_COVERAGE_INCOMPLETE",
                "Не найдены товары для SKU из финансов Ozon: " + preview,
            )

        return {
            "error": False,
            "products": [product_by_sku[sku] for sku in finance_skus],
            "finance_sku_scope_applied": True,
            "finance_sku_count": len(finance_skus),
            "catalog_duplicate_sku_count": duplicate_count,
        }

    def _load_period_skus(self, date_from, date_to):
        start = self._date(date_from)
        end = self._date(date_to)
        if start is None or end is None or start > end:
            return self._error(
                "PERIOD_PROFIT_PERIOD_INVALID",
                "Некорректный период",
            )

        getter = getattr(self.finance_service, "_get_accruals_by_day", None)
        if not callable(getter):
            return self._error(
                "PERIOD_PROFIT_FINANCE_SKU_SCOPE_UNAVAILABLE",
                "Финансовые данные SKU недоступны",
            )

        skus = set()
        current = start
        while current <= end:
            try:
                response = getter(current.isoformat())
            except Exception:
                return self._error(
                    "PERIOD_PROFIT_FINANCE_SKU_SCOPE_UNAVAILABLE",
                    "Финансовые данные SKU недоступны",
                )

            if not isinstance(response, dict) or response.get("error") is True:
                return self._error(
                    "PERIOD_PROFIT_FINANCE_SKU_SCOPE_UNAVAILABLE",
                    "Финансовые данные SKU недоступны",
                )

            accruals = response.get("accruals")
            if not isinstance(accruals, list):
                return self._error(
                    "PERIOD_PROFIT_FINANCE_SKU_SCOPE_INVALID",
                    "Некорректные финансовые данные SKU",
                )

            for accrual in accruals:
                if not isinstance(accrual, dict):
                    return self._error(
                        "PERIOD_PROFIT_FINANCE_SKU_SCOPE_INVALID",
                        "Некорректные финансовые данные SKU",
                    )
                if accrual.get("accrued_category") != "POSTING":
                    continue
                posting = accrual.get("posting")
                if posting is None:
                    continue
                if not isinstance(posting, dict):
                    return self._error(
                        "PERIOD_PROFIT_FINANCE_SKU_SCOPE_INVALID",
                        "Некорректные финансовые данные SKU",
                    )
                products = posting.get("products")
                if products is None:
                    continue
                if not isinstance(products, list):
                    return self._error(
                        "PERIOD_PROFIT_FINANCE_SKU_SCOPE_INVALID",
                        "Некорректные финансовые данные SKU",
                    )
                for product in products:
                    if not isinstance(product, dict):
                        return self._error(
                            "PERIOD_PROFIT_FINANCE_SKU_SCOPE_INVALID",
                            "Некорректные финансовые данные SKU",
                        )
                    sku = str(product.get("sku") or "").strip()
                    if not sku:
                        return self._error(
                            "PERIOD_PROFIT_FINANCE_SKU_SCOPE_INVALID",
                            "В финансовой операции Ozon отсутствует SKU товара",
                        )
                    skus.add(sku)

            current += timedelta(days=1)

        return {
            "error": False,
            "skus": sorted(skus),
        }

    @staticmethod
    def _product_index(products):
        if not isinstance(products, list):
            return None

        product_by_sku = {}
        duplicate_count = 0

        for product in products:
            if isinstance(product, dict):
                candidate = dict(product)
                sku = str(candidate.get("sku") or "").strip()
            elif isinstance(product, (tuple, list)) and len(product) >= 3:
                candidate = {
                    "product_id": product[0],
                    "offer_id": product[1],
                    "sku": product[2],
                }
                sku = str(product[2] or "").strip()
            else:
                continue

            if not sku:
                continue

            candidate["sku"] = sku
            if sku in product_by_sku:
                duplicate_count += 1
                existing = product_by_sku[sku]
                if existing.get("product_id") is None and candidate.get("product_id") is not None:
                    product_by_sku[sku] = candidate
                continue

            product_by_sku[sku] = candidate

        if not product_by_sku:
            return None

        return {
            "products": product_by_sku,
            "duplicate_count": duplicate_count,
        }

    @staticmethod
    def _date(value):
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        try:
            return datetime.strptime(str(value), "%Y-%m-%d").date()
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _error(code, message):
        return {
            "error": True,
            "code": code,
            "message": message,
            "status": "PERIOD_PROFIT_QUERY_UNAVAILABLE",
            "read_only": True,
            "executed": False,
        }
