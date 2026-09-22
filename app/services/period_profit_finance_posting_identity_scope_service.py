from concurrent.futures import ThreadPoolExecutor
from contextvars import ContextVar, copy_context

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
    MAX_SELECTED_POSTING_SAMPLE_PROBES = 64
    SELECTED_POSTING_SAMPLE_WORKERS = 8
    MAX_SELECTED_RELATED_DISCOVERY_CALLS = 64
    RELATED_DISCOVERY_BATCH_SIZE = 200

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
        "_realization_identity_responses",
        "_selected_identity_candidates",
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
        self._realization_identity_responses = {}
        self._selected_identity_candidates = []

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
        self._legacy_identity_cache = {}
        self._fbo_identity_snapshot = None
        self._fbo_identity_snapshot_loaded = False
        self._finance_posting_numbers_by_sku = {}
        self._realization_identity_responses = {}
        self._selected_identity_candidates = []
        self._scope_start = self._date(date_from)
        self._scope_end = self._date(date_to)
        # Enter the canonical finance scope directly.  Legacy parent setup uses
        # a one-to-many offer index intended for store-wide FBO recovery; this
        # selected-aware service requires the unique catalog offer index above.
        # Letting the parent overwrite it made every posting/realization candidate
        # a list, so exact selected-offer recovery could never return a product.
        scoped = PeriodProfitFinanceSkuScopeService._scope_products(
            self,
            date_from,
            date_to,
            products,
        )
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
            result = super()._load_period_skus(date_from, date_to)
        finally:
            self.sku_ozon_client = original_client
        if not isinstance(result, dict) or result.get("error") is True:
            return result

        selected = self._selected_scope_catalog_product()
        if selected is None:
            return result

        all_skus = set(result.get("skus") or ())
        candidates = self._selected_finance_sku_candidates(
            all_skus,
            selected,
            date_to,
        )
        trace = current_period_profit_trace()
        if trace is not None:
            trace.record_identity_stage(
                "final",
                finance_sku_count=len(all_skus),
                candidate_count=len(candidates),
                status=(
                    "matched" if candidates else
                    "no_proven_candidate:" + ",".join(
                        sorted(self._sku_recovery_diagnostic_codes)
                    )
                ),
            )
            trace.update(
                "selected_finance_sku_prefilter",
                service=type(self).__name__,
                method="_load_period_skus",
                catalog_sku=self._text(selected.get("sku")),
                status=(
                    "matched" if candidates else "no_proven_candidate"
                ),
            )
            if not candidates:
                trace.dump_worker_stack(
                    reason="selected_finance_sku_unresolved"
                )
        return {
            **result,
            "skus": sorted(candidates),
            "identity_candidates": [
                dict(candidate) for candidate in self._selected_identity_candidates
            ],
        }

    def _selected_scope_catalog_product(self):
        selected = [
            product for product in self._catalog_by_sku.values()
            if isinstance(product, dict)
            and product.get("_period_profit_selected_scope") is True
        ]
        return selected[0] if len(selected) == 1 else None

    def _selected_finance_sku_candidates(self, all_skus, selected, at_date):
        selected_sku = self._text(selected.get("sku"))
        selected_offer = self._text(selected.get("offer_id"))
        candidates = set()
        if selected_sku in all_skus:
            candidates.add(selected_sku)

        # Local seller evidence is cheap and authoritative.  Evaluate it before
        # any network fallback so explicit historical/current mappings survive
        # the selected-SKU prefilter.
        mapping_getter = getattr(
            self,
            "_recover_from_seller_confirmed_mapping",
            None,
        )
        for finance_sku in sorted(all_skus - candidates):
            direct = PeriodProfitFinanceSkuScopeService._recover_missing_product(
                self,
                finance_sku,
                at_date,
            )
            if self._same_selected_product(direct, selected):
                candidates.add(finance_sku)
                continue
            if callable(mapping_getter):
                status, mapped = mapping_getter(finance_sku)
                if status == "READY" and self._same_selected_product(mapped, selected):
                    candidates.add(finance_sku)

        trace = current_period_profit_trace()
        if trace is not None:
            trace.record_identity_stage(
                "local",
                finance_sku_count=len(all_skus),
                candidate_count=len(candidates),
            )

        posting_owners = self._posting_owners()
        realization_rows = self._period_realization_rows()
        for row in realization_rows:
            order = row.get("order") if isinstance(row, dict) else None
            item = row.get("item") if isinstance(row, dict) else None
            if not isinstance(order, dict) or not isinstance(item, dict):
                continue
            if self._text(item.get("offer_id")) != selected_offer:
                continue
            posting_number = self._text(order.get("posting_number"))
            observed_sku = self._text(item.get("sku"))
            if observed_sku in all_skus:
                candidates.add(observed_sku)
            owners = posting_owners.get(posting_number) or set()
            if len(owners) == 1:
                candidates.update(owners)
        if trace is not None:
            trace.record_identity_stage(
                "realization",
                row_count=len(realization_rows),
                candidate_count=len(candidates),
            )

        if not candidates:
            candidates.update(
                self._selected_finance_posting_sku_candidates(all_skus, selected)
            )

        if not candidates:
            candidates.update(
                self._selected_posting_offer_candidates(all_skus, selected)
            )

        # Ask Ozon for the exact related-SKU group of the selected current SKU.
        # This is one bounded request and proves which retired finance SKUs belong
        # to this variant.  Never scan the account-wide paginated FBO history in
        # selected-SKU mode: large accounts can require hundreds of pages.
        if not candidates:
            candidates.update(
                self._selected_related_finance_candidates(all_skus, selected)
            )

        return candidates & all_skus

    def _selected_finance_posting_sku_candidates(self, all_skus, selected):
        """Use one exact finance posting per SKU as a batched identity sample."""
        selected_sku = self._text(selected.get("sku"))
        getter = getattr(
            self.finance_service,
            "get_sale_posting_quantity_evidence",
            None,
        )
        if not selected_sku or not callable(getter):
            trace = current_period_profit_trace()
            if trace is not None:
                trace.record_identity_stage("finance_posting", status="unavailable")
            return set()

        posting_owners = self._posting_owners()
        samples = []
        for finance_sku in sorted(all_skus):
            posting_numbers = sorted(
                self._finance_posting_numbers_by_sku.get(finance_sku) or ()
            )
            if posting_numbers:
                samples.append(posting_numbers[0])
        if not samples:
            trace = current_period_profit_trace()
            if trace is not None:
                trace.record_identity_stage("finance_posting", status="no_samples")
            return set()

        try:
            evidence = getter(samples)
        except Exception:
            trace = current_period_profit_trace()
            if trace is not None:
                trace.record_identity_stage(
                    "finance_posting",
                    sample_count=len(samples),
                    status="exception",
                )
            return set()
        if (
            not isinstance(evidence, dict)
            or evidence.get("error") is True
            or evidence.get("complete") is not True
            or not isinstance(evidence.get("records"), list)
        ):
            trace = current_period_profit_trace()
            if trace is not None:
                trace.record_identity_stage(
                    "finance_posting",
                    sample_count=len(samples),
                    status="invalid_or_incomplete",
                )
            return set()

        candidates = set()
        for record in evidence["records"]:
            if not isinstance(record, dict):
                return set()
            posting_number = self._text(record.get("posting_number"))
            observed_sku = self._text(record.get("sku"))
            owners = posting_owners.get(posting_number) or set()
            if observed_sku == selected_sku and len(owners) == 1:
                candidates.update(owners)

        product_id = self._text(selected.get("product_id"))
        if candidates and not product_id:
            return set()
        for finance_sku in candidates:
            recovered = dict(selected)
            recovered["catalog_sku"] = selected_sku
            recovered["sku"] = finance_sku
            recovered["historical_sku_identity_recovered"] = True
            recovered["historical_sku_identity_source"] = (
                "OZON_FINANCE_POSTING_TO_CURRENT_CATALOG_SKU"
            )
            self._related_sku_identity_cache[finance_sku] = recovered
        trace = current_period_profit_trace()
        if trace is not None:
            trace.record_identity_stage(
                "finance_posting",
                sample_count=len(samples),
                record_count=len(evidence["records"]),
                candidate_count=len(candidates),
                status="matched" if candidates else "no_match",
            )
        return candidates

    def _selected_posting_offer_candidates(self, all_skus, selected):
        """Resolve rewritten posting SKUs by exact offer on one posting per SKU."""
        selected_offer = self._text(selected.get("offer_id"))
        selected_sku = self._text(selected.get("sku"))
        product_id = self._text(selected.get("product_id"))
        ozon = getattr(self.finance_service, "ozon", None)
        trace = current_period_profit_trace()
        if not selected_offer or not selected_sku or not product_id or ozon is None:
            return set()

        posting_owners = self._posting_owners()
        samples = []
        for finance_sku in sorted(all_skus):
            numbers = sorted(
                self._finance_posting_numbers_by_sku.get(finance_sku) or ()
            )
            if numbers:
                samples.append((finance_sku, numbers[0]))
        if len(samples) > self.MAX_SELECTED_POSTING_SAMPLE_PROBES:
            if trace is not None:
                trace.record_identity_stage(
                    "posting_offer",
                    sample_count=len(samples),
                    status="probe_budget_exhausted",
                )
            return set()

        def probe(sample):
            finance_sku, posting_number = sample
            for method_name in ("get_fbo_posting", "get_fbs_posting"):
                getter = getattr(ozon, method_name, None)
                if not callable(getter):
                    continue
                if trace is not None:
                    trace.record_posting(posting_number)
                try:
                    response = getter(posting_number)
                except Exception:
                    response = None
                products = self._posting_products(response, posting_number)
                if not products:
                    continue
                offers = {
                    self._text(product.get("offer_id"))
                    for product in products
                    if isinstance(product, dict)
                    and self._text(product.get("offer_id"))
                }
                owners = posting_owners.get(posting_number) or set()
                if len(offers) == 1 and owners == {finance_sku}:
                    offer_id = next(iter(offers))
                    return {
                        "finance_sku": finance_sku,
                        "offer_id": offer_id,
                        "matches_selected": offer_id == selected_offer,
                    }
                return None
            return None

        workers = min(self.SELECTED_POSTING_SAMPLE_WORKERS, len(samples))
        if not workers:
            return set()
        try:
            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = [
                    executor.submit(copy_context().run, probe, sample)
                    for sample in samples
                ]
                matches = [future.result() for future in futures]
        except Exception:
            if trace is not None:
                trace.record_identity_stage(
                    "posting_offer",
                    sample_count=len(samples),
                    status="exception",
                )
            return set()

        evidence = [value for value in matches if isinstance(value, dict)]
        self._selected_identity_candidates = sorted(
            [
                {
                    "finance_sku": value["finance_sku"],
                    "historical_offer_id": value["offer_id"],
                }
                for value in evidence
                if value.get("matches_selected") is not True
            ],
            key=lambda value: (
                value["historical_offer_id"],
                value["finance_sku"],
            ),
        )
        candidates = {
            value["finance_sku"]
            for value in evidence
            if value.get("matches_selected") is True
        }
        for finance_sku in candidates:
            recovered = dict(selected)
            recovered["catalog_sku"] = selected_sku
            recovered["sku"] = finance_sku
            recovered["historical_sku_identity_recovered"] = True
            recovered["historical_sku_identity_source"] = (
                "OZON_FINANCE_POSTING_TO_CURRENT_CATALOG_OFFER_ID"
            )
            self._related_sku_identity_cache[finance_sku] = recovered
        if trace is not None:
            trace.record_identity_stage(
                "posting_offer",
                sample_count=len(samples),
                candidate_count=len(candidates),
                status="matched" if candidates else "no_match",
            )
        return candidates

    def _selected_related_finance_candidates(self, all_skus, selected):
        selected_sku = self._text(selected.get("sku"))
        if not selected_sku or all_skus == {selected_sku}:
            return set()

        ozon = getattr(self.finance_service, "ozon", None)
        getter = getattr(ozon, "get_related_skus", None)
        if not callable(getter):
            self._record_sku_recovery_diagnostic("RELATED_API_UNAVAILABLE")
            return set()
        try:
            response = getter([selected_sku])
        except Exception:
            self._record_sku_recovery_diagnostic("RELATED_API_EXCEPTION")
            return set()
        if not isinstance(response, dict) or response.get("error") is True:
            self._record_sku_recovery_diagnostic("RELATED_API_ERROR")
            return set()
        items = response.get("items")
        errors = response.get("errors") or []
        if not isinstance(items, list) or not isinstance(errors, list):
            self._record_sku_recovery_diagnostic("RELATED_RESPONSE_INVALID")
            return set()
        if any(
            not isinstance(error, dict)
            or self._text(error.get("sku")) == selected_sku
            for error in errors
        ):
            self._record_sku_recovery_diagnostic("RELATED_SKU_REJECTED")
            return set()

        related_skus = set()
        for item in items:
            if not isinstance(item, dict):
                self._record_sku_recovery_diagnostic("RELATED_RESPONSE_INVALID")
                return set()
            sku = self._text(item.get("sku"))
            if sku:
                related_skus.add(sku)
        if selected_sku not in related_skus:
            self._record_sku_recovery_diagnostic("RELATED_TARGET_MISSING")
            return set()

        result = related_skus & set(all_skus)
        if not result:
            result = self._discover_directional_related_finance_skus(
                all_skus,
                selected_sku,
                getter,
            )
        trace = current_period_profit_trace()
        if trace is not None:
            trace.record_identity_stage(
                "related",
                related_item_count=len(related_skus),
                candidate_count=len(result),
                status="matched" if result else "no_match",
            )
        catalog_sku = self._text(selected.get("sku"))
        product_id = self._text(selected.get("product_id"))
        if not product_id:
            self._record_sku_recovery_diagnostic("RELATED_PRODUCT_ID_MISSING")
            return set()
        for finance_sku in result:
            recovered = dict(selected)
            recovered["catalog_sku"] = catalog_sku
            recovered["sku"] = finance_sku
            recovered["historical_sku_identity_recovered"] = True
            recovered["historical_sku_identity_source"] = (
                "OZON_RELATED_SKU_TO_CURRENT_CATALOG"
            )
            self._related_sku_identity_cache[finance_sku] = recovered
        return result

    def _discover_directional_related_finance_skus(
        self,
        all_skus,
        selected_sku,
        getter,
    ):
        """Find directional related identities without per-SKU N+1 probing.

        Ozon may return historical -> current relations when asked for the
        historical SKU, but omit the same historical SKU for the reverse query.
        A batch is therefore used as a membership oracle and only positive
        batches are bisected.  A candidate is accepted only after an exact
        singleton request returns the selected current SKU.
        """
        pending = []
        values = sorted(set(all_skus) - {selected_sku})
        for offset in range(0, len(values), self.RELATED_DISCOVERY_BATCH_SIZE):
            pending.append(values[offset:offset + self.RELATED_DISCOVERY_BATCH_SIZE])

        calls = 0
        proven = set()
        while pending and calls < self.MAX_SELECTED_RELATED_DISCOVERY_CALLS:
            batch = pending.pop(0)
            if not batch:
                continue
            try:
                response = getter(batch)
            except Exception:
                self._record_sku_recovery_diagnostic("RELATED_API_EXCEPTION")
                return set()
            calls += 1
            if not isinstance(response, dict) or response.get("error") is True:
                self._record_sku_recovery_diagnostic("RELATED_API_ERROR")
                return set()
            items = response.get("items")
            errors = response.get("errors") or []
            if not isinstance(items, list) or not isinstance(errors, list):
                self._record_sku_recovery_diagnostic("RELATED_RESPONSE_INVALID")
                return set()
            if any(not isinstance(item, dict) for item in items):
                self._record_sku_recovery_diagnostic("RELATED_RESPONSE_INVALID")
                return set()
            returned = {self._text(item.get("sku")) for item in items}
            if selected_sku not in returned:
                continue
            if len(batch) == 1:
                proven.add(batch[0])
                continue
            middle = len(batch) // 2
            pending.insert(0, batch[middle:])
            pending.insert(0, batch[:middle])

        if pending:
            self._record_sku_recovery_diagnostic(
                "RELATED_DISCOVERY_BUDGET_EXHAUSTED"
            )
            return set()
        trace = current_period_profit_trace()
        if trace is not None:
            trace.record_identity_stage(
                "directional_related",
                discovery_call_count=calls,
                candidate_count=len(proven),
                status="matched" if proven else "no_match",
            )
        return proven

    def _posting_owners(self):
        owners = {}
        for finance_sku, posting_numbers in self._finance_posting_numbers_by_sku.items():
            for posting_number in posting_numbers or ():
                owners.setdefault(self._text(posting_number), set()).add(
                    self._text(finance_sku)
                )
        return owners

    def _period_realization_rows(self):
        ozon = getattr(self.finance_service, "ozon", None)
        getter = getattr(ozon, "get_realization_posting", None)
        if (
            not callable(getter)
            or self._scope_start is None
            or self._scope_end is None
        ):
            return []
        trace = current_period_profit_trace()
        rows = []
        for year, month in self._evidence_months(self._scope_start, self._scope_end):
            key = ("get_realization_posting", year, month)
            if key in self._realization_identity_responses:
                response = self._realization_identity_responses[key]
            else:
                try:
                    response = getter(year, month)
                except Exception:
                    response = None
                self._realization_identity_responses[key] = response
                if trace is not None:
                    trace.posting_response_cache[key] = response
            parsed = self._realization_rows(response)
            if parsed is not None:
                rows.extend(parsed)
        return rows

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

        prefetched = self._related_sku_identity_cache.get(self._text(sku))
        if isinstance(prefetched, dict):
            return self._cache_identity(cache_key, dict(prefetched))

        posting = self._recover_from_finance_posting_identity(sku)
        if posting is not None:
            return self._cache_identity(cache_key, posting)

        realization = self._recover_from_realization_offer_identity(sku)
        if realization is not None:
            return self._cache_identity(cache_key, realization)

        # Account-wide FBO pagination is valid only for store-wide recovery.
        # Selected-SKU requests use exact realization/related/posting evidence.
        if self._selected_scope_catalog_product() is None:
            fbo_snapshot = self._recover_from_fbo_snapshot_offer_identity(sku)
            if fbo_snapshot is not None:
                return self._cache_identity(cache_key, fbo_snapshot)

        related = self._recover_from_related_sku_identity(sku)
        if related is not None:
            return self._cache_identity(cache_key, related)

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

    def _recover_from_realization_offer_identity(self, sku):
        """Resolve exact finance posting/SKU identity from monthly realization.

        The realization report already carries posting_number, finance SKU and
        stable seller offer_id for both fulfillment schemas.  Reading each
        intersecting month once avoids serial FBO/FBS detail probing while still
        requiring exact, unambiguous evidence.
        """
        finance_sku = self._text(sku)
        posting_numbers = set(
            self._finance_posting_numbers_by_sku.get(finance_sku) or ()
        )
        if (
            not finance_sku
            or not posting_numbers
            or not self._catalog_by_offer
            or self._scope_start is None
            or self._scope_end is None
        ):
            return None

        ozon = getattr(self.finance_service, "ozon", None)
        getter = getattr(ozon, "get_realization_posting", None)
        if not callable(getter):
            return None

        trace = current_period_profit_trace()
        matched_offers = set()
        posting_owners = {}
        for owner_sku, owner_postings in self._finance_posting_numbers_by_sku.items():
            for posting_number in owner_postings or ():
                posting_owners.setdefault(self._text(posting_number), set()).add(
                    self._text(owner_sku)
                )
        for year, month in self._evidence_months(self._scope_start, self._scope_end):
            cache_key = ("get_realization_posting", year, month)
            if cache_key in self._realization_identity_responses:
                response = self._realization_identity_responses[cache_key]
                if trace is not None:
                    trace.update(
                        "realization_identity_cache",
                        service=type(self).__name__,
                        method="get_realization_posting",
                        cache="hit",
                        finance_sku=finance_sku,
                    )
            else:
                try:
                    response = getter(year, month)
                except Exception:
                    response = None
                self._realization_identity_responses[cache_key] = response
                if trace is not None:
                    trace.posting_response_cache[cache_key] = response

            rows = self._realization_rows(response)
            if rows is None:
                continue
            for row in rows:
                order = row.get("order") if isinstance(row, dict) else None
                item = row.get("item") if isinstance(row, dict) else None
                if not isinstance(order, dict) or not isinstance(item, dict):
                    continue
                posting_number = self._text(order.get("posting_number"))
                observed_sku = self._text(item.get("sku"))
                offer_id = self._text(item.get("offer_id"))
                owners = posting_owners.get(posting_number) or set()
                identity_is_exact = observed_sku == finance_sku
                identity_is_unique_posting = owners == {finance_sku}
                if (
                    posting_number in posting_numbers
                    and (identity_is_exact or identity_is_unique_posting)
                    and offer_id in self._catalog_by_offer
                ):
                    matched_offers.add(offer_id)

        if len(matched_offers) > 1:
            self._record_sku_recovery_diagnostic("REALIZATION_OFFER_AMBIGUOUS")
            return None
        if len(matched_offers) != 1:
            return None

        offer_id = next(iter(matched_offers))
        candidate = self._catalog_by_offer.get(offer_id)
        if not isinstance(candidate, dict):
            return None
        result = dict(candidate)
        result["catalog_sku"] = self._text(candidate.get("sku"))
        result["sku"] = finance_sku
        result["historical_sku_identity_recovered"] = True
        result["historical_sku_identity_source"] = (
            "OZON_REALIZATION_POSTING_TO_CURRENT_CATALOG_OFFER_ID"
        )
        return result

    def _recover_from_fbo_snapshot_offer_identity(self, sku):
        """Resolve all FBO posting evidence from a paged period snapshot."""
        finance_sku = self._text(sku)
        posting_numbers = set(
            self._finance_posting_numbers_by_sku.get(finance_sku) or ()
        )
        if not finance_sku or not posting_numbers or not self._catalog_by_offer:
            return None

        postings = self._load_fbo_identity_snapshot()
        if postings is None:
            return None
        parsed = self._parse_fbo_identity_page(
            {"postings": postings},
            finance_sku,
            posting_numbers,
            set(self._catalog_by_offer),
        )
        if parsed is None:
            self._record_sku_recovery_diagnostic("FBO_SNAPSHOT_AMBIGUOUS")
            return None
        exact_offers, posting_offers, _count, _has_next = parsed
        if len(exact_offers) > 1 or len(posting_offers) > 1:
            self._record_sku_recovery_diagnostic("FBO_SNAPSHOT_AMBIGUOUS")
            return None
        if exact_offers and posting_offers and exact_offers != posting_offers:
            self._record_sku_recovery_diagnostic("FBO_SNAPSHOT_AMBIGUOUS")
            return None
        offers = exact_offers or posting_offers
        if len(offers) != 1:
            return None

        offer_id = next(iter(offers))
        candidate = self._catalog_by_offer.get(offer_id)
        if not isinstance(candidate, dict):
            return None
        result = dict(candidate)
        result["catalog_sku"] = self._text(candidate.get("sku"))
        result["sku"] = finance_sku
        result["historical_sku_identity_recovered"] = True
        result["historical_sku_identity_source"] = (
            "OZON_FBO_SNAPSHOT_TO_CURRENT_CATALOG_OFFER_ID"
        )
        return result

    @staticmethod
    def _realization_rows(response):
        if not isinstance(response, dict) or response.get("error") is True:
            return None
        rows = response.get("rows")
        if not isinstance(rows, list):
            result = response.get("result")
            rows = result.get("rows") if isinstance(result, dict) else None
        return rows if isinstance(rows, list) else None

    @staticmethod
    def _evidence_months(start, end):
        year, month = start.year, start.month
        values = []
        while (year, month) <= (end.year, end.month):
            values.append((year, month))
            if month == 12:
                year, month = year + 1, 1
            else:
                month += 1
        return values

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
