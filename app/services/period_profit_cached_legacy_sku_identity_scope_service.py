from datetime import timedelta

from services.period_profit_finance_sku_scope_service import (
    PeriodProfitFinanceSkuScopeService,
)
from services.period_profit_legacy_sku_identity_scope_service import (
    PeriodProfitLegacySkuIdentityScopeService,
)


class PeriodProfitCachedLegacySkuIdentityScopeService(
    PeriodProfitLegacySkuIdentityScopeService
):
    """Reuse one READ-ONLY FBO posting snapshot for all legacy SKUs in a period."""

    def __init__(self, summary_service, finance_service, sku_ozon_client=None):
        super().__init__(
            summary_service,
            finance_service,
            sku_ozon_client=sku_ozon_client,
        )
        self._fbo_identity_snapshot = None
        self._fbo_identity_snapshot_loaded = False

    def _scope_products(self, date_from, date_to, products):
        self._fbo_identity_snapshot = None
        self._fbo_identity_snapshot_loaded = False
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

        return super()._recover_missing_product(sku, at_date)

    def _load_fbo_identity_snapshot(self):
        if self._fbo_identity_snapshot_loaded:
            return self._fbo_identity_snapshot

        self._fbo_identity_snapshot_loaded = True
        if self._scope_start is None or self._scope_end is None:
            self._fbo_identity_snapshot = None
            return None

        client = self.sku_ozon_client
        if client is None:
            client = getattr(self.finance_service, "ozon", None)
        getter = getattr(client, "get_fbo_postings", None)
        if not callable(getter):
            self._fbo_identity_snapshot = None
            return None

        since_date = self._scope_start - timedelta(days=self.WINDOW_PADDING_DAYS)
        to_date = self._scope_end + timedelta(days=1)
        since = since_date.isoformat() + "T00:00:00Z"
        to = to_date.isoformat() + "T23:59:59Z"
        postings = []
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
                self._fbo_identity_snapshot = None
                return None

            parsed = self._snapshot_page(response)
            if parsed is None:
                self._fbo_identity_snapshot = None
                return None
            page_postings, row_count, has_next = parsed
            postings.extend(page_postings)

            if has_next is False or (
                has_next is None and row_count < self.PAGE_SIZE
            ):
                self._fbo_identity_snapshot = postings
                return postings
            if row_count <= 0:
                self._fbo_identity_snapshot = None
                return None
            offset += row_count

        self._fbo_identity_snapshot = None
        return None

    @staticmethod
    def _snapshot_page(response):
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
        return postings, len(postings), has_next

    def _recover_catalog_product_from_fbo(self, sku):
        sku_key = self._text(sku)
        if not sku_key or self._scope_start is None or self._scope_end is None:
            return None
        if sku_key in self._legacy_identity_cache:
            cached = self._legacy_identity_cache[sku_key]
            return dict(cached) if isinstance(cached, dict) else None

        postings = self._load_fbo_identity_snapshot()
        if postings is None:
            self._legacy_identity_cache[sku_key] = None
            return None

        finance_posting_numbers = (
            self._finance_posting_numbers_by_sku.get(sku_key) or set()
        )
        page = self._parse_fbo_identity_page(
            {"postings": postings},
            sku_key,
            finance_posting_numbers,
            set(self._catalog_by_offer),
        )
        if page is None:
            self._legacy_identity_cache[sku_key] = None
            return None

        exact_offer_ids, posting_offer_ids, _row_count, _has_next = page
        if len(exact_offer_ids) > 1 or len(posting_offer_ids) > 1:
            self._legacy_identity_cache[sku_key] = None
            return None

        source = None
        if len(exact_offer_ids) == 1:
            offer_id = next(iter(exact_offer_ids))
            source = "OZON_FBO_POSTING_OFFER_ID"
            if posting_offer_ids and posting_offer_ids != exact_offer_ids:
                self._legacy_identity_cache[sku_key] = None
                return None
        elif len(posting_offer_ids) == 1:
            offer_id = next(iter(posting_offer_ids))
            source = "OZON_FINANCE_UNIT_TO_FBO_POSTING_OFFER_ID"
        else:
            self._legacy_identity_cache[sku_key] = None
            return None

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
        recovered["historical_sku_identity_source"] = source
        self._legacy_identity_cache[sku_key] = dict(recovered)
        return recovered
