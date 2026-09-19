from contextvars import ContextVar

from services.period_profit_cached_legacy_sku_identity_scope_service import (
    PeriodProfitCachedLegacySkuIdentityScopeService,
)
from services.period_profit_finance_sku_scope_service import (
    PeriodProfitFinanceSkuScopeService,
)
from services.period_profit_operation_diagnostics import current_period_profit_trace


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

    MAX_SELECTED_POSTING_IDENTITY_PROBES = 3

    _REQUEST_STATE_FIELDS = {
        "_catalog_by_sku",
        "_catalog_by_product_id",
        "_catalog_by_offer",
        "_related_sku_identity_cache",
        "_sku_recovery_diagnostic_codes",
        "_legacy_identity_cache",
        "_scope_start",
        "_scope_end",
        "_finance_posting_numbers_by_sku",
        "_fbo_identity_snapshot",
        "_fbo_identity_snapshot_loaded",
    }

    def __init__(self, summary_service, finance_service, sku_ozon_client=None):
        self._request_state_var = ContextVar(
            "period_profit_identity_scope_state_" + str(id(self)),
            default=None,
        )
        self._default_request_state = {}
        super().__init__(
            summary_service,
            finance_service,
            sku_ozon_client=sku_ozon_client,
        )
        self._catalog_by_sku = {}
        self._catalog_by_product_id = {}
        self._catalog_by_offer = {}
        self._related_sku_identity_cache = {}
        self._sku_recovery_diagnostic_codes = set()

    def __getattribute__(self, name):
        if name in object.__getattribute__(self, "_REQUEST_STATE_FIELDS"):
            state_var = object.__getattribute__(self, "_request_state_var")
            state = state_var.get()
            if state is None:
                state = object.__getattribute__(self, "_default_request_state")
            return state.get(name)
        return object.__getattribute__(self, name)

    def __setattr__(self, name, value):
        if name in type(self)._REQUEST_STATE_FIELDS and hasattr(
            self, "_request_state_var"
        ):
            state = self._request_state_var.get()
            if state is None:
                state = self._default_request_state
            state[name] = value
            return
        object.__setattr__(self, name, value)

    def _scope_products(self, date_from, date_to, products):
        token = self._request_state_var.set(dict(self._default_request_state))
        try:
            return self._scope_products_in_request(date_from, date_to, products)
        finally:
            self._request_state_var.reset(token)

    def _scope_products_in_request(self, date_from, date_to, products):
        trace = current_period_profit_trace()
        if trace is not None:
            trace.update(
                "finance_identity_scope",
                service=type(self).__name__,
                method="_scope_products",
            )
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
        self._catalog_by_offer = self._unique_catalog_offer_index(products)
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
        trace = current_period_profit_trace()
        cache_key = self._identity_cache_key(sku)
        if trace is not None and cache_key in trace.identity_cache:
            cached = trace.identity_cache[cache_key]
            trace.update(
                "finance_identity_cache",
                service=type(self).__name__,
                method="_recover_missing_product",
                finance_sku=self._text(sku),
                cache="hit",
            )
            return dict(cached) if isinstance(cached, dict) else None
        if trace is not None:
            trace.update(
                "finance_identity_cache",
                service=type(self).__name__,
                method="_recover_missing_product",
                finance_sku=self._text(sku),
                cache="miss",
            )

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
            return self._cache_identity(cache_key, result)

        related = self._recover_from_related_sku_identity(sku)
        if related is not None:
            return self._cache_identity(cache_key, related)

        posting = self._recover_from_finance_posting_identity(sku)
        if posting is not None:
            return self._cache_identity(cache_key, posting)

        result = self._recover_from_finance_posting_offer_identity(sku)
        return self._cache_identity(cache_key, result)

    def _identity_cache_key(self, sku):
        catalog = tuple(sorted(
            (self._text(key), self._text(value.get("product_id")))
            for key, value in self._catalog_by_offer.items()
            if isinstance(value, dict)
        ))
        return self._text(sku), catalog

    @staticmethod
    def _cache_identity(cache_key, result):
        trace = current_period_profit_trace()
        if trace is not None:
            trace.identity_cache[cache_key] = (
                dict(result) if isinstance(result, dict) else None
            )
        return result

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

    def _recover_from_finance_posting_offer_identity(self, sku):
        """Bridge finance SKU to catalog by exact posting offer_id.

        Finance accrual SKUs can differ from the current catalog SKU.  When the
        finance posting numbers are known, exact FBO/FBS posting detail gives a
        stronger stable identity: offer_id.  Accept it only when every observed
        matching posting points to one unique catalog offer; ambiguity remains
        fail-closed.
        """
        finance_sku = self._text(sku)
        posting_numbers = sorted(
            self._finance_posting_numbers_by_sku.get(finance_sku) or ()
        )
        if not finance_sku or not posting_numbers or not self._catalog_by_offer:
            return None

        ozon = getattr(self.finance_service, "ozon", None)
        if ozon is None:
            return None

        trace = current_period_profit_trace()
        # One exact posting is sufficient positive identity evidence.  Search a
        # small deterministic set and fail closed if it cannot prove identity;
        # never turn every posting in a 90-day period into a serial HTTP N+1.
        for posting_number in posting_numbers[:self.MAX_SELECTED_POSTING_IDENTITY_PROBES]:
            posting_offers = set()
            # A posting number belongs to exactly one fulfillment schema.  Stop
            # after the first schema that returns usable product rows instead of
            # probing the other endpoint as well.  In production the wrong FBS
            # probe can otherwise spend up to three 30-second network attempts
            # for every FBO posting and block the synchronous Telegram callback.
            for method_name in ("get_fbo_posting", "get_fbs_posting"):
                getter = getattr(ozon, method_name, None)
                if not callable(getter):
                    continue
                response_key = (method_name, posting_number)
                if trace is not None and response_key in trace.posting_response_cache:
                    response = trace.posting_response_cache[response_key]
                    trace.update(
                        "posting_response_cache",
                        service=type(self).__name__,
                        method=method_name,
                        posting_number=posting_number,
                        cache="hit",
                    )
                else:
                    if trace is not None:
                        trace.record_posting(posting_number)
                    try:
                        response = getter(posting_number)
                    except Exception:
                        response = None
                    if trace is not None:
                        trace.posting_response_cache[response_key] = response
                products = self._posting_products(response, posting_number)
                if not products:
                    continue
                for product in products:
                    product_sku = self._text(product.get("sku"))
                    offer_id = self._text(product.get("offer_id"))
                    if product_sku != finance_sku or offer_id not in self._catalog_by_offer:
                        continue
                    posting_offers.add(offer_id)
                break
            if len(posting_offers) > 1:
                self._record_sku_recovery_diagnostic("POSTING_OFFER_AMBIGUOUS")
                return None
            if len(posting_offers) == 1:
                offer_id = next(iter(posting_offers))
                break
        else:
            self._record_sku_recovery_diagnostic("POSTING_OFFER_MISSING")
            return None

        candidate = self._catalog_by_offer.get(offer_id)
        if not isinstance(candidate, dict):
            return None
        result = dict(candidate)
        result["catalog_sku"] = self._text(candidate.get("sku"))
        result["sku"] = finance_sku
        result["historical_sku_identity_recovered"] = True
        result["historical_sku_identity_source"] = (
            "OZON_FINANCE_POSTING_TO_CURRENT_CATALOG_OFFER_ID"
        )
        return result

    @classmethod
    def _posting_products(cls, response, posting_number):
        if not isinstance(response, dict) or response.get("error") is True:
            return []
        result = response.get("result")
        if not isinstance(result, dict):
            result = response
        returned = cls._text(result.get("posting_number"))
        if returned and returned != cls._text(posting_number):
            return []
        products = result.get("products")
        return products if isinstance(products, list) else []

    def _recover_related_sku_from_seller_cost(self, finance_sku, items):
        """Use seller cost storage only as identity, never as cost authority."""

        related_skus = {
            self._text(item.get("sku"))
            for item in items
            if isinstance(item, dict) and self._text(item.get("sku"))
        }
        related_product_ids = {
            self._text(item.get("product_id"))
            for item in items
            if isinstance(item, dict) and self._text(item.get("product_id"))
        }
        cost_service = self.cost_service
        identity_getter = getattr(
            cost_service,
            "get_seller_cost_identities",
            None,
        )
        records = None
        if callable(identity_getter):
            try:
                identity_result = identity_getter()
            except Exception:
                return "UNAVAILABLE", None
            if (
                not isinstance(identity_result, dict)
                or identity_result.get("error") is True
                or not isinstance(identity_result.get("records"), list)
            ):
                return "UNAVAILABLE", None
            records = identity_result["records"]

        matches = []
        if records is not None:
            for record in records:
                if not isinstance(record, dict):
                    return "UNAVAILABLE", None
                sku = self._text(record.get("sku"))
                product_id = self._text(record.get("product_id"))
                offer_id = self._text(record.get("offer_id"))
                if (
                    product_id
                    and (
                        sku in related_skus
                        or product_id in related_product_ids
                    )
                ):
                    matches.append((sku, product_id, offer_id))
        else:
            getter = getattr(cost_service, "get_all_costs", None)
            if not callable(getter):
                return "UNAVAILABLE", None
            try:
                rows = getter()
            except Exception:
                return "UNAVAILABLE", None
            if not isinstance(rows, (list, tuple)):
                return "UNAVAILABLE", None
            for related_sku in related_skus:
                for row in rows:
                    candidate = self._product_from_current_cost_row(
                        row,
                        related_sku,
                    )
                    if candidate is not None:
                        matches.append((
                            related_sku,
                            self._text(candidate.get("product_id")),
                            self._text(candidate.get("offer_id")),
                        ))

        identities = set(matches)
        if not identities:
            return "MISSING", None

        offer_ids = {offer_id for _, _, offer_id in identities if offer_id}
        if len(offer_ids) > 1:
            return "AMBIGUOUS", None
        if offer_ids:
            stable_offer = next(iter(offer_ids))
            identities = {
                identity
                for identity in identities
                if identity[2] == stable_offer
            }
        else:
            stable_offer = ""

        finance_matches = {
            identity for identity in identities if identity[0] == finance_sku
        }
        if len(finance_matches) == 1:
            _, product_id, offer_id = next(iter(finance_matches))
        else:
            product_ids = {identity[1] for identity in identities}
            if len(product_ids) != 1:
                return "AMBIGUOUS", None
            product_id = next(iter(product_ids))
            offer_id = stable_offer

        related_current_skus = {
            sku for sku, _, _ in identities if sku != finance_sku
        }
        catalog_sku = (
            next(iter(related_current_skus))
            if len(related_current_skus) == 1
            else finance_sku
        )
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
    def _unique_catalog_offer_index(cls, products):
        indexed = {}
        duplicates = set()
        for product in products or []:
            if isinstance(product, dict):
                candidate = dict(product)
                offer_id = cls._text(candidate.get("offer_id"))
            elif isinstance(product, (tuple, list)) and len(product) >= 3:
                candidate = {
                    "product_id": product[0],
                    "offer_id": product[1],
                    "sku": product[2],
                }
                offer_id = cls._text(product[1])
            else:
                continue
            if not offer_id:
                continue
            if offer_id in indexed:
                duplicates.add(offer_id)
                continue
            indexed[offer_id] = candidate
        for offer_id in duplicates:
            indexed.pop(offer_id, None)
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
