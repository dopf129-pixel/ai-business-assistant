from datetime import date, datetime, timedelta
from math import isfinite


class PeriodProfitFinanceSkuScopeService:
    """Scope product cost calculation to unique SKUs actually present in Ozon finance."""

    def __init__(self, summary_service, finance_service, sku_ozon_client=None):
        self.summary_service = summary_service
        self.finance_service = finance_service
        self.sku_ozon_client = sku_ozon_client
        self.cost_service = getattr(summary_service, "cost_service", None)
        self.tax_rate = getattr(summary_service, "tax_rate", None)

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
            result["historical_sku_recovery_count"] = scoped["historical_sku_recovery_count"]

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
        product_by_sku = dict(normalized["products"])
        historical_recovery_count = 0

        if not finance_skus:
            return {
                "error": False,
                "products": list(product_by_sku.values()),
                "finance_sku_scope_applied": True,
                "finance_sku_count": 0,
                "catalog_duplicate_sku_count": duplicate_count,
                "historical_sku_recovery_count": 0,
            }

        selected_scope = self._selected_product_scope(product_by_sku)
        unresolved = []
        scoped_products = {}
        for sku in finance_skus:
            if sku in product_by_sku:
                candidate = product_by_sku[sku]
            else:
                candidate = self._recover_missing_product(
                    sku,
                    date_to,
                )
                if candidate is None:
                    if selected_scope is None:
                        unresolved.append(sku)
                    continue
                historical_recovery_count += 1

            if selected_scope is not None:
                if not self._same_selected_product(candidate, selected_scope):
                    continue
                candidate = dict(candidate)
                candidate.pop("_period_profit_selected_scope", None)
            scoped_products[sku] = candidate

        if selected_scope is not None:
            product_by_sku = scoped_products
        else:
            product_by_sku.update(scoped_products)

        if unresolved:
            preview = ", ".join(unresolved[:5])
            if len(unresolved) > 5:
                preview += ", ..."
            if self.cost_service is None:
                return self._error(
                    "PERIOD_PROFIT_FINANCE_SKU_CATALOG_COVERAGE_INCOMPLETE",
                    "Не найдены товары для SKU из финансов Ozon: " + preview,
                )
            return self._error(
                "PERIOD_PROFIT_FINANCE_SKU_COST_COVERAGE_INCOMPLETE",
                "Не найдена подтвержденная себестоимость для SKU из финансов Ozon: " + preview,
            )

        return {
            "error": False,
            "products": [
                product_by_sku[sku]
                for sku in finance_skus
                if sku in product_by_sku
            ],
            "finance_sku_scope_applied": True,
            "finance_sku_count": (
                len(product_by_sku)
                if selected_scope is not None
                else len(finance_skus)
            ),
            "catalog_duplicate_sku_count": duplicate_count,
            "historical_sku_recovery_count": historical_recovery_count,
        }

    def _recover_missing_product(self, sku, at_date):
        cost_service = self.cost_service
        if cost_service is None:
            return None

        historical_getter = getattr(
            cost_service,
            "get_historical_cost_evidence",
            None,
        )
        if callable(historical_getter):
            try:
                evidence = historical_getter(
                    at_date,
                    sku=sku,
                )
            except Exception:
                evidence = None

            candidate = self._product_from_cost_evidence(
                evidence,
                sku,
                require_historical=True,
            )
            if candidate is not None:
                return candidate

        current_getter = getattr(
            cost_service,
            "get_all_costs",
            None,
        )
        if not callable(current_getter):
            return None

        try:
            rows = current_getter()
        except Exception:
            return None

        if not isinstance(rows, (list, tuple)):
            return None

        matches = []
        for row in rows:
            candidate = self._product_from_current_cost_row(
                row,
                sku,
            )
            if candidate is not None:
                matches.append(candidate)

        product_ids = {
            item["product_id"]
            for item in matches
        }
        if len(product_ids) != 1:
            return None

        return matches[0]

    @classmethod
    def _product_from_cost_evidence(
        cls,
        evidence,
        sku,
        require_historical=False,
    ):
        if not isinstance(evidence, dict):
            return None
        if evidence.get("error") is not False:
            return None
        if require_historical and evidence.get("historical_cost_confirmed") is not True:
            return None

        evidence_sku = cls._text(evidence.get("sku"))
        if evidence_sku and evidence_sku != sku:
            return None

        product_id = cls._text(evidence.get("product_id"))
        cost = cls._cost(evidence.get("cost_price"))
        currency = cls._text(evidence.get("currency")).upper()
        if not product_id or cost is None or currency != "RUB":
            return None

        return {
            "product_id": product_id,
            "sku": sku,
            "offer_id": cls._text(evidence.get("offer_id")) or sku,
            "cost_price": cost,
            "historical_cost_evidence": bool(require_historical),
        }

    @classmethod
    def _product_from_current_cost_row(cls, row, sku):
        if not isinstance(row, (tuple, list)) or len(row) < 5:
            return None

        product_id = cls._text(row[0])
        row_sku = cls._text(row[1])
        offer_id = cls._text(row[2])
        cost = cls._cost(row[3])
        currency = cls._text(row[4]).upper()

        if (
            not product_id
            or row_sku != sku
            or cost is None
            or currency != "RUB"
        ):
            return None

        return {
            "product_id": product_id,
            "sku": sku,
            "offer_id": offer_id or sku,
            "cost_price": cost,
            "historical_cost_evidence": False,
        }

    def _load_period_skus(self, date_from, date_to):
        start = self._date(date_from)
        end = self._date(date_to)
        if start is None or end is None or start > end:
            return self._error(
                "PERIOD_PROFIT_PERIOD_INVALID",
                "Некорректный период",
            )

        if self.sku_ozon_client is not None:
            getter = getattr(self.sku_ozon_client, "get_accruals_by_day", None)
        else:
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

    @classmethod
    def _selected_product_scope(cls, product_by_sku):
        selected = [
            product for product in product_by_sku.values()
            if isinstance(product, dict)
            and product.get("_period_profit_selected_scope") is True
        ]
        if len(selected) != 1:
            return None
        return selected[0]

    @classmethod
    def _same_selected_product(cls, candidate, selected):
        if not isinstance(candidate, dict) or not isinstance(selected, dict):
            return False
        selected_product_id = cls._text(selected.get("product_id"))
        candidate_product_id = cls._text(candidate.get("product_id"))
        if selected_product_id and candidate_product_id:
            return selected_product_id == candidate_product_id
        selected_offer = cls._text(selected.get("offer_id"))
        candidate_offer = cls._text(candidate.get("offer_id"))
        if selected_offer and candidate_offer:
            return selected_offer == candidate_offer
        return cls._text(candidate.get("sku")) == cls._text(selected.get("sku"))

    @staticmethod
    def _text(value):
        if value is None:
            return ""
        return str(value).strip()

    @staticmethod
    def _cost(value):
        if isinstance(value, bool):
            return None
        try:
            number = float(value)
        except (TypeError, ValueError, OverflowError):
            return None
        if not isfinite(number) or number < 0:
            return None
        return number

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
