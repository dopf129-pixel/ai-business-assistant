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
    identity remains the first authority. When that is unavailable, Ozon's
    READ-ONLY related-SKU method is used to map retired/hidden SKUs to exactly one
    current catalog product. Exact finance posting evidence remains a secondary
    bridge. Ambiguous/missing evidence fails closed. FBO is intentionally not
    entered from this production scope.
    """

    def __init__(self, summary_service, finance_service, sku_ozon_client=None):
        super().__init__(
            summary_service,
            finance_service,
            sku_ozon_client=sku_ozon_client,
        )
        self._catalog_by_sku = {}
        self._catalog_by_product_id = {}
        self._related_sku_identity_cache = {}
        self._sku_recovery_diagnostic_codes = set()

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
                error = self._error(
                    code,
                    "Финансовые данные Ozon недоступны",
                )
                if isinstance(result, dict):
                    diagnostic = str(
                        result.get("finance_diagnostic_code") or ""
                    ).strip().upper()
                    if diagnostic and all(
                        character.isalnum() or character == "_"
                        for character in diagnostic
                    ):
                        error["finance_diagnostic_code"] = diagnostic
                return error

        self._catalog_by_sku = self._unique_catalog_sku_index(products)
        self._catalog_by_product_id = self._unique_catalog_product_id_index(products)
        self._related_sku_identity_cache = {}
        self._sku_recovery_diagnostic_codes = set()
        scoped = super()._scope_products(date_from, date_to, products)
        if (
            isinstance(scoped, dict)
            and scoped.get("code")
            == "PERIOD_PROFIT_FINANCE_SKU_COST_COVERAGE_INCOMPLETE"
        ):
            diagnostics = sorted(self._sku_recovery_diagnostic_codes)
            if len(diagnostics) == 1:
                diagnostic = diagnostics[0]
            elif diagnostics:
                diagnostic = (
                    "PERIOD_PROFIT_FINANCE_SKU_IDENTITY_MULTIPLE_BLOCKERS"
                )
            else:
                diagnostic = (
                    "PERIOD_PROFIT_FINANCE_SKU_IDENTITY_UNRESOLVED"
                )
            scoped = dict(scoped)
            scoped["finance_diagnostic_code"] = diagnostic
        return scoped

    def _load_period_skus(self, date_from, date_to):
        # The prefetch above populated PeriodProfitFinanceService's normal daily
        # cache. Force the scope reader through that cache instead of making a
        # second set of day-by-day Ozon calls through an identity client.
        original_client = self.sku_ozon_client
        self.sku_ozon_client = None
        try:
            return super()._load_period_skus(date_from, date_to)
        finally:
            self.sku_ozon_client = original_client

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

        related = self._recover_from_related_sku_identity(sku)
        if related is not None:
            return related

        return self._recover_from_finance_posting_identity(sku)

    def _recover_from_related_sku_identity(self, sku):
        finance_sku = self._text(sku)
        if not finance_sku:
            return None
        if finance_sku in self._related_sku_identity_cache:
            cached = self._related_sku_identity_cache[finance_sku]
            return dict(cached) if isinstance(cached, dict) else None

        ozon = getattr(self.finance_service, "ozon", None)
        getter = getattr(ozon, "get_related_skus", None)
        if not callable(getter):
            self._record_sku_recovery_diagnostic("RELATED_API_UNAVAILABLE")
            self._related_sku_identity_cache[finance_sku] = None
            return None

        try:
            response = getter([finance_sku])
        except Exception:
            self._record_sku_recovery_diagnostic("RELATED_API_EXCEPTION")
            self._related_sku_identity_cache[finance_sku] = None
            return None
        if not isinstance(response, dict):
            self._record_sku_recovery_diagnostic("RELATED_RESPONSE_INVALID")
            self._related_sku_identity_cache[finance_sku] = None
            return None
        if response.get("error") is True:
            self._record_sku_recovery_diagnostic("RELATED_API_ERROR")
            self._related_sku_identity_cache[finance_sku] = None
            return None

        items = response.get("items")
        errors = response.get("errors") or []
        if not isinstance(items, list) or not isinstance(errors, list):
            self._record_sku_recovery_diagnostic("RELATED_RESPONSE_INVALID")
            self._related_sku_identity_cache[finance_sku] = None
            return None

        for error in errors:
            if not isinstance(error, dict):
                self._record_sku_recovery_diagnostic("RELATED_RESPONSE_INVALID")
                self._related_sku_identity_cache[finance_sku] = None
                return None
            if self._text(error.get("sku")) == finance_sku:
                self._record_sku_recovery_diagnostic("RELATED_SKU_REJECTED")
                self._related_sku_identity_cache[finance_sku] = None
                return None

        target_seen = False
        candidate_skus = set()
        for item in items:
            if not isinstance(item, dict):
                self._record_sku_recovery_diagnostic("RELATED_RESPONSE_INVALID")
                self._related_sku_identity_cache[finance_sku] = None
                return None
            related_sku = self._text(item.get("sku"))
            product_id = self._text(item.get("product_id"))
            if related_sku == finance_sku:
                target_seen = True
            if related_sku in self._catalog_by_sku:
                candidate_skus.add(related_sku)
            if product_id and product_id in self._catalog_by_product_id:
                candidate = self._catalog_by_product_id[product_id]
                candidate_sku = self._text(candidate.get("sku"))
                if candidate_sku:
                    candidate_skus.add(candidate_sku)

        if not target_seen:
            self._record_sku_recovery_diagnostic("RELATED_TARGET_MISSING")
            self._related_sku_identity_cache[finance_sku] = None
            return None
        if not candidate_skus:
            seller_status, seller_candidate = (
                self._recover_related_sku_from_seller_cost(
                    finance_sku,
                    items,
                )
            )
            if seller_status == "AMBIGUOUS":
                self._record_sku_recovery_diagnostic("RELATED_AMBIGUOUS")
                self._related_sku_identity_cache[finance_sku] = None
                return None
            if seller_candidate is not None:
                self._related_sku_identity_cache[finance_sku] = dict(
                    seller_candidate
                )
                return seller_candidate
            self._record_sku_recovery_diagnostic("RELATED_CATALOG_MISSING")
            self._related_sku_identity_cache[finance_sku] = None
            return None
        if len(candidate_skus) != 1:
            self._record_sku_recovery_diagnostic("RELATED_AMBIGUOUS")
            self._related_sku_identity_cache[finance_sku] = None
            return None

        catalog_sku = next(iter(candidate_skus))
        candidate = self._catalog_by_sku.get(catalog_sku)
        if not isinstance(candidate, dict):
            self._record_sku_recovery_diagnostic("RELATED_CATALOG_MISSING")
            self._related_sku_identity_cache[finance_sku] = None
            return None

        product_id = self._text(candidate.get("product_id"))
        offer_id = self._text(candidate.get("offer_id"))
        if not product_id:
            self._record_sku_recovery_diagnostic("RELATED_PRODUCT_ID_MISSING")
            self._related_sku_identity_cache[finance_sku] = None
            return None

        result = dict(candidate)
        result["product_id"] = product_id
        result["offer_id"] = offer_id or catalog_sku
        result["catalog_sku"] = catalog_sku
        result["sku"] = finance_sku
        result["historical_sku_identity_recovered"] = True
        result["historical_sku_identity_source"] = "OZON_RELATED_SKU_TO_CURRENT_CATALOG"
        self._related_sku_identity_cache[finance_sku] = dict(result)
        return result

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

    def _recover_related_sku_from_seller_cost(self, finance_sku, items):
        """Use seller cost rows only as identity, never as historical cost."""

        cost_service = self.cost_service
        getter = getattr(cost_service, "get_all_costs", None)
        if not callable(getter):
            return "UNAVAILABLE", None
        try:
            rows = getter()
        except Exception:
            return "UNAVAILABLE", None
        if not isinstance(rows, (list, tuple)):
            return "UNAVAILABLE", None

        related_skus = {
            self._text(item.get("sku"))
            for item in items
            if isinstance(item, dict)
            and self._text(item.get("sku"))
            and self._text(item.get("sku")) != finance_sku
        }
        matches = []
        for related_sku in related_skus:
            for row in rows:
                candidate = self._product_from_current_cost_row(
                    row,
                    related_sku,
                )
                if candidate is not None:
                    matches.append((related_sku, candidate))

        identities = {
            (
                related_sku,
                self._text(candidate.get("product_id")),
                self._text(candidate.get("offer_id")),
            )
            for related_sku, candidate in matches
        }
        if not identities:
            return "MISSING", None
        if len(identities) != 1:
            return "AMBIGUOUS", None

        catalog_sku, product_id, offer_id = next(iter(identities))
        if not product_id:
            return "MISSING", None
        return "MATCHED", {
            "product_id": product_id,
            "offer_id": offer_id or catalog_sku,
            "catalog_sku": catalog_sku,
            "sku": finance_sku,
            "historical_sku_identity_recovered": True,
            "historical_sku_identity_source": (
                "OZON_RELATED_SKU_TO_SELLER_COST_IDENTITY"
            ),
        }

    def _record_sku_recovery_diagnostic(self, stage):
        stage = self._text(stage).upper()
        if stage and all(
            character.isalnum() or character == "_"
            for character in stage
        ):
            self._sku_recovery_diagnostic_codes.add(
                "PERIOD_PROFIT_FINANCE_SKU_IDENTITY_" + stage
            )

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

    @classmethod
    def _unique_catalog_product_id_index(cls, products):
        indexed = {}
        duplicates = set()
        for product in products or []:
            if isinstance(product, dict):
                candidate = dict(product)
                product_id = cls._text(candidate.get("product_id"))
            elif isinstance(product, (tuple, list)) and len(product) >= 3:
                candidate = {
                    "product_id": product[0],
                    "offer_id": product[1],
                    "sku": product[2],
                }
                product_id = cls._text(product[0])
            else:
                continue
            if not product_id:
                continue
            if product_id in indexed:
                duplicates.add(product_id)
                continue
            indexed[product_id] = candidate
        for product_id in duplicates:
            indexed.pop(product_id, None)
        return indexed
