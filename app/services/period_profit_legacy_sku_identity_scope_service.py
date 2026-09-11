from datetime import timedelta

from services.period_profit_finance_sku_scope_service import (
    PeriodProfitFinanceSkuScopeService,
)


class PeriodProfitLegacySkuIdentityScopeService(PeriodProfitFinanceSkuScopeService):
    """Recover retired Ozon SKUs through stable seller-offer identity.

    Finance can retain the SKU that existed when a historical posting was
    accrued, while the current product catalog and FBO posting API expose a new
    SKU for the same seller offer. Direct SKU matching remains the first choice.
    When it fails, this adapter proves identity through READ-ONLY FBO evidence.

    The preferred bridge is exact historical SKU -> offer_id. If Ozon's current
    FBO representation has already rewritten the SKU, the finance POSTING
    ``unit_number`` is matched to FBO ``posting_number`` and the posting may
    identify exactly one current catalog offer. Ambiguous evidence always fails
    closed.

    Identity recovery never supplies historical cost. The downstream dated
    effective-cost reconciler remains authoritative for every sale date.
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
        self._finance_posting_numbers_by_sku = {}

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
        self._finance_posting_numbers_by_sku = {}
        return super()._scope_products(date_from, date_to, products)

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
        postings_by_sku = {}
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

                unit_number = self._text(accrual.get("unit_number"))
                for product in products:
                    if not isinstance(product, dict):
                        return self._error(
                            "PERIOD_PROFIT_FINANCE_SKU_SCOPE_INVALID",
                            "Некорректные финансовые данные SKU",
                        )
                    sku = self._text(product.get("sku"))
                    if not sku:
                        return self._error(
                            "PERIOD_PROFIT_FINANCE_SKU_SCOPE_INVALID",
                            "В финансовой операции Ozon отсутствует SKU товара",
                        )
                    skus.add(sku)
                    if unit_number:
                        postings_by_sku.setdefault(sku, set()).add(unit_number)

            current += timedelta(days=1)

        self._finance_posting_numbers_by_sku = postings_by_sku
        return {
            "error": False,
            "skus": sorted(skus),
        }

    def _recover_missing_product(self, sku, at_date):
        direct = super()._recover_missing_product(sku, at_date)
        if direct is not None:
            return direct

        recovered = self._recover_catalog_product_from_fbo(sku)
        if recovered is None:
            return None

        # Require a seller-known cost row for the mapped stable product identity.
        # This is identity validation only; it is not historical cost authority.
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
        result["historical_sku_identity_source"] = recovered.get(
            "historical_sku_identity_source",
            "OZON_FBO_POSTING_OFFER_ID",
        )
        result.pop("_identity_source", None)
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

        exact_offer_ids = set()
        posting_offer_ids = set()
        finance_posting_numbers = self._finance_posting_numbers_by_sku.get(sku_key) or set()
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

            page = self._parse_fbo_identity_page(
                response,
                sku_key,
                finance_posting_numbers,
                set(self._catalog_by_offer),
            )
            if page is None:
                self._legacy_identity_cache[sku_key] = None
                return None

            page_exact, page_posting, row_count, has_next = page
            exact_offer_ids.update(page_exact)
            posting_offer_ids.update(page_posting)
            if len(exact_offer_ids) > 1 or len(posting_offer_ids) > 1:
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

    @classmethod
    def _parse_fbo_identity_page(
        cls,
        response,
        target_sku,
        finance_posting_numbers=None,
        catalog_offer_ids=None,
    ):
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

        finance_posting_numbers = set(finance_posting_numbers or ())
        catalog_offer_ids = set(catalog_offer_ids or ())
        exact_offer_ids = set()
        posting_offer_ids = set()

        for posting in postings:
            if not isinstance(posting, dict):
                continue
            products = posting.get("products")
            if not isinstance(products, list):
                continue

            posting_number = cls._text(posting.get("posting_number"))
            posting_matches_finance = (
                posting_number
                and posting_number in finance_posting_numbers
            )
            current_catalog_offers = set()

            for product in products:
                if not isinstance(product, dict):
                    continue
                offer_id = cls._text(product.get("offer_id"))
                if cls._text(product.get("sku")) == target_sku:
                    if not offer_id:
                        return None
                    exact_offer_ids.add(offer_id)
                if posting_matches_finance and offer_id in catalog_offer_ids:
                    current_catalog_offers.add(offer_id)

            if posting_matches_finance:
                if len(current_catalog_offers) > 1:
                    return None
                posting_offer_ids.update(current_catalog_offers)

        return exact_offer_ids, posting_offer_ids, len(postings), has_next

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
