from datetime import timedelta

from services.period_profit_finance_sku_scope_service import (
    PeriodProfitFinanceSkuScopeService,
)


class PeriodProfitLegacySkuIdentityScopeService(PeriodProfitFinanceSkuScopeService):
    """Recover retired Ozon SKUs through stable offer identity.

    Ozon finance is authoritative for the SKU that was present on a historical
    posting, while the current product catalog can expose a newer SKU for the
    same seller offer.  Direct SKU matching therefore remains the first choice.
    When it fails, this adapter reads FBO posting evidence for the requested
    period, proves that the historical SKU maps to exactly one ``offer_id``, and
    joins that offer to exactly one current catalog product.

    The recovery is identity-only.  It never copies the current cost into the
    historical period.  The downstream effective-cost reconciler still resolves
    seller-confirmed cost evidence independently for every sale date and stays
    fail-closed when that evidence is absent or ambiguous.
    """

    PAGE_SIZE = 1000
    MAX_PAGES = 50
    WINDOW_PADDING_DAYS = 31

    def __init__(self, summary_service, finance_service, sku_ozon_client=None):
        super().__init__(summary_service, finance_service, sku_ozon_client=sku_ozon_client)
        self._legacy_identity_cache = {}
        self._catalog_by_offer = {}
        self._scope_start = None
        self._scope_end = None

    def _scope_products(self, date_from, date_to, products):
        normalized = self._product_index(products)
        self._catalog_by_offer = self._offer_index(
            normalized.get("products", {}).values()
            if isinstance(normalized, dict)
            else []
        )
        self._scope_start = self._date(date_from)
        self._scope_end = self._date(date_to)
        self._legacy_identity_cache = {}
        return super()._scope_products(date_from, date_to, products)

    def _recover_missing_product(self, sku, at_date):
        direct = super()._recover_missing_product(sku, at_date)
        if direct is not None:
            return direct

        recovered = self._recover_catalog_product_from_fbo(sku)
        if recovered is None:
            return None

        # Require a seller-known cost row for the mapped stable product identity.
        # This is not historical cost authority; it only prevents an unrelated
        # catalog offer from entering Period Profit. Exact dated cost evidence is
        # still enforced downstream by PeriodProfitEffectiveCostSaleQuantitySummaryService.
        getter = getattr(self.cost_service, "get_cost", None)
        if not callable(getter):
            return None
        try:
            current_cost_row = getter(recovered.get("product_id"))
        except Exception:
            return None
        if current_cost_row is None:
            return None

        result = dict(recovered)
        result["sku"] = str(sku)
        result["historical_sku_identity_recovered"] = True
        result["historical_sku_identity_source"] = "OZON_FBO_POSTING_OFFER_ID"
        return result

    def _recover_catalog_product_from_fbo(self, sku):
        sku_key = self._text(sku)
        if not sku_key or self._scope_start is None or self._scope_end is None:
            return None
        if sku_key in self._legacy_identity_cache:
            cached = self._legacy_identity_cache[sku_key]
            return dict(cached) if isinstance(cached, dict) else None

        client = self.sku_ozon_client
        getter = getattr(client, "get_fbo_postings", None)
        if not callable(getter):
            self._legacy_identity_cache[sku_key] = None
            return None

        since_date = self._scope_start - timedelta(days=self.WINDOW_PADDING_DAYS)
        to_date = self._scope_end + timedelta(days=1)
        since = since_date.isoformat() + "T00:00:00Z"
        to = to_date.isoformat() + "T23:59:59Z"

        offer_ids = set()
        offset = 0

        for _ in range(self.MAX_PAGES):
            try:
                response = getter(
                    since,
                    to,
                    limit=self.PAGE_SIZE,
                    offset=offset,
                    direction="ASC",
                    status="",
                )
            except Exception:
                self._legacy_identity_cache[sku_key] = None
                return None

            page = self._parse_fbo_identity_page(response, sku_key)
            if page is None:
                self._legacy_identity_cache[sku_key] = None
                return None

            page_offers, row_count, has_next = page
            offer_ids.update(page_offers)
            if len(offer_ids) > 1:
                self._legacy_identity_cache[sku_key] = None
                return None

            if has_next is False or (has_next is None and row_count < self.PAGE_SIZE):
                break
            if row_count <= 0:
                self._legacy_identity_cache[sku_key] = None
                return None
            offset += row_count
        else:
            self._legacy_identity_cache[sku_key] = None
            return None

        if len(offer_ids) != 1:
            self._legacy_identity_cache[sku_key] = None
            return None

        offer_id = next(iter(offer_ids))
        candidates = self._catalog_by_offer.get(offer_id) or []
        product_ids = {
            self._text(candidate.get("product_id"))
            for candidate in candidates
            if self._text(candidate.get("product_id"))
        }
        if len(product_ids) != 1:
            self._legacy_identity_cache[sku_key] = None
            return None

        product_id = next(iter(product_ids))
        matching = [
            candidate
            for candidate in candidates
            if self._text(candidate.get("product_id")) == product_id
        ]
        if not matching:
            self._legacy_identity_cache[sku_key] = None
            return None

        recovered = dict(matching[0])
        recovered["product_id"] = product_id
        recovered["offer_id"] = offer_id
        self._legacy_identity_cache[sku_key] = dict(recovered)
        return recovered

    @classmethod
    def _parse_fbo_identity_page(cls, response, target_sku):
        if not isinstance(response, dict) or response.get("error") is True:
            return None

        result = response.get("result")
        if isinstance(result, list):
            postings = result
        elif isinstance(result, dict):
            postings = result.get("postings")
        else:
            postings = response.get("postings")
        if not isinstance(postings, list):
            return None

        has_next = response.get("has_next")
        if has_next is None and isinstance(result, dict):
            has_next = result.get("has_next")
        if has_next is not None and type(has_next) is not bool:
            return None

        offer_ids = set()
        for posting in postings:
            if not isinstance(posting, dict):
                continue
            products = posting.get("products")
            if not isinstance(products, list):
                continue
            for product in products:
                if not isinstance(product, dict):
                    continue
                if cls._text(product.get("sku")) != target_sku:
                    continue
                offer_id = cls._text(product.get("offer_id"))
                if not offer_id:
                    return None
                offer_ids.add(offer_id)

        return offer_ids, len(postings), has_next

    @classmethod
    def _offer_index(cls, products):
        indexed = {}
        for product in products or []:
            if not isinstance(product, dict):
                continue
            offer_id = cls._text(product.get("offer_id"))
            if not offer_id:
                continue
            indexed.setdefault(offer_id, []).append(dict(product))
        return indexed
