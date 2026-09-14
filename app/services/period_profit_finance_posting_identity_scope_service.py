from services.period_profit_cached_legacy_sku_identity_scope_service import (
    PeriodProfitCachedLegacySkuIdentityScopeService,
)
from services.period_profit_finance_sku_scope_service import (
    PeriodProfitFinanceSkuScopeService,
)


class PeriodProfitFinancePostingIdentityScopeService(
    PeriodProfitCachedLegacySkuIdentityScopeService
):
    """Resolve legacy finance SKUs without making FBO a critical dependency.

    The period finance cache is prefetched first so the SKU scope and downstream
    summary reuse the same READ-ONLY daily evidence. Direct seller-confirmed cost
    identity remains the first authority. When that is unavailable, exact finance
    posting numbers observed for the legacy SKU are reconciled against
    ``/v1/finance/accrual/postings`` and exactly one current catalog SKU may be
    accepted. Ambiguous/missing evidence fails closed. FBO is intentionally not
    entered from this production scope.
    """

    def __init__(self, summary_service, finance_service, sku_ozon_client=None):
        super().__init__(
            summary_service,
            finance_service,
            sku_ozon_client=sku_ozon_client,
        )
        self._catalog_by_sku = {}

    def _scope_products(self, date_from, date_to, products):
        prefetch = getattr(self.finance_service, "prefetch_daily_accruals", None)
        if callable(prefetch):
            try:
                result = prefetch(date_from, date_to)
            except Exception:
                return self._error(
                    "PERIOD_PROFIT_FINANCE_PREFETCH_UNAVAILABLE",
                    "Финансовые данные Ozon недоступны",
                )
            if not isinstance(result, dict) or result.get("error") is True:
                code = (
                    str(result.get("code") or "PERIOD_PROFIT_FINANCE_PREFETCH_UNAVAILABLE")
                    if isinstance(result, dict)
                    else "PERIOD_PROFIT_FINANCE_PREFETCH_UNAVAILABLE"
                )
                return self._error(
                    code,
                    "Финансовые данные Ozon недоступны",
                )

        self._catalog_by_sku = self._unique_catalog_sku_index(products)
        return super()._scope_products(date_from, date_to, products)

    def _recover_missing_product(self, sku, at_date):
        direct = PeriodProfitFinanceSkuScopeService._recover_missing_product(
            self,
            sku,
            at_date,
        )
        if direct is not None:
            result = dict(direct)
            result["historical_sku_identity_recovered"] = True
            result["historical_sku_identity_source"] = (
                "SELLER_CONFIRMED_HISTORICAL_COST_IDENTITY"
                if result.get("historical_cost_evidence") is True
                else "SELLER_CURRENT_COST_EXACT_SKU_IDENTITY"
            )
            return result

        return self._recover_from_finance_posting_identity(sku)

    def _recover_from_finance_posting_identity(self, sku):
        finance_sku = self._text(sku)
        posting_numbers = set(
            self._finance_posting_numbers_by_sku.get(finance_sku) or ()
        )
        if not finance_sku or not posting_numbers:
            return None

        getter = getattr(
            self.finance_service,
            "get_sale_posting_quantity_evidence",
            None,
        )
        if not callable(getter):
            return None

        try:
            evidence = getter(sorted(posting_numbers))
        except Exception:
            return None
        if (
            not isinstance(evidence, dict)
            or evidence.get("error") is True
            or evidence.get("complete") is not True
        ):
            return None

        records = evidence.get("records")
        if not isinstance(records, list):
            return None

        candidates_by_posting = {}
        for record in records:
            if not isinstance(record, dict):
                return None
            posting_number = self._text(record.get("posting_number"))
            observed_sku = self._text(record.get("sku"))
            if posting_number not in posting_numbers or not observed_sku:
                continue
            if observed_sku == finance_sku:
                continue
            if observed_sku not in self._catalog_by_sku:
                continue
            candidates_by_posting.setdefault(posting_number, set()).add(observed_sku)

        if not candidates_by_posting:
            return None
        if any(len(values) != 1 for values in candidates_by_posting.values()):
            return None

        candidate_skus = {
            next(iter(values))
            for values in candidates_by_posting.values()
        }
        if len(candidate_skus) != 1:
            return None

        catalog_sku = next(iter(candidate_skus))
        candidate = self._catalog_by_sku.get(catalog_sku)
        if not isinstance(candidate, dict):
            return None

        product_id = self._text(candidate.get("product_id"))
        offer_id = self._text(candidate.get("offer_id"))
        if not product_id:
            return None

        result = dict(candidate)
        result["product_id"] = product_id
        result["offer_id"] = offer_id or catalog_sku
        result["catalog_sku"] = catalog_sku
        result["sku"] = finance_sku
        result["historical_sku_identity_recovered"] = True
        result["historical_sku_identity_source"] = (
            "OZON_FINANCE_POSTING_TO_CURRENT_CATALOG_SKU"
        )
        return result

    @classmethod
    def _unique_catalog_sku_index(cls, products):
        indexed = {}
        duplicates = set()
        for product in products or []:
            if isinstance(product, dict):
                candidate = dict(product)
                sku = cls._text(candidate.get("sku"))
            elif isinstance(product, (tuple, list)) and len(product) >= 3:
                candidate = {
                    "product_id": product[0],
                    "offer_id": product[1],
                    "sku": product[2],
                }
                sku = cls._text(product[2])
            else:
                continue
            if not sku:
                continue
            if sku in indexed:
                duplicates.add(sku)
                continue
            indexed[sku] = candidate
        for sku in duplicates:
            indexed.pop(sku, None)
        return indexed
