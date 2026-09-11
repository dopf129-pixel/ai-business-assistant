from datetime import timedelta
from math import isfinite

from services.period_profit_critical_finance_summary_service import (
    PeriodProfitCriticalFinanceSummaryService,
)
from services.period_profit_sale_quantity_summary_service import (
    PeriodProfitSaleQuantitySummaryService,
)


class PeriodProfitEffectiveCostSaleQuantitySummaryService(
    PeriodProfitSaleQuantitySummaryService
):
    """Reconcile physical sale quantity with seller-confirmed cost evidence.

    Finance SKU is the monetary identity. Ozon posting evidence can expose a newer
    catalog SKU for the same seller offer, so posting quantity is reconciled by
    exact finance SKU first and then by the already-scoped stable offer identity.
    Historical cost remains independently resolved by stable product identity and
    sale date; current mutable cost is never used as retroactive authority.
    """

    OFFER_KEY_PREFIX = "@offer:"

    def calculate(self, date_from, date_to, products):
        # PeriodProfitSaleQuantitySummaryService.calculate() reconciles quantity
        # immediately after the critical finance summary. Insert stable identity
        # metadata at that boundary so a retired finance SKU does not erase the
        # product_id/offer_id already proven by the outer SKU-scope service.
        result = PeriodProfitCriticalFinanceSummaryService.calculate(
            self,
            date_from,
            date_to,
            products,
        )
        if not isinstance(result, dict) or result.get("error") is not False:
            return result

        identity_by_finance_sku = self._identity_by_finance_sku(products)
        rows = result.get("products")
        if not isinstance(rows, list):
            return self._quantity_error("PERIOD_PROFIT_SALE_QUANTITY_RESULT_INVALID")

        enriched_rows = []
        for row in rows:
            if not isinstance(row, dict):
                return self._quantity_error("PERIOD_PROFIT_SALE_QUANTITY_RESULT_INVALID")
            finance_sku = self._text(row.get("sku"))
            identity = identity_by_finance_sku.get(finance_sku)
            next_row = dict(row)
            next_row["finance_sku"] = finance_sku
            if identity is not None:
                product_id = self._text(identity.get("product_id"))
                offer_id = self._text(identity.get("offer_id"))
                catalog_sku = self._text(identity.get("catalog_sku"))
                if product_id:
                    next_row["product_id"] = product_id
                if offer_id:
                    next_row["offer_id"] = offer_id
                if catalog_sku:
                    next_row["catalog_sku"] = catalog_sku
                for field in (
                    "historical_sku_identity_recovered",
                    "historical_sku_identity_source",
                ):
                    if field in identity:
                        next_row[field] = identity[field]
            enriched_rows.append(next_row)

        enriched = dict(result)
        enriched["products"] = enriched_rows
        return self._reconcile_sale_quantities(
            enriched,
            date_from,
            date_to,
        )

    @classmethod
    def _identity_by_finance_sku(cls, products):
        indexed = {}
        for product in products or []:
            if isinstance(product, dict):
                identity = dict(product)
                finance_sku = cls._text(identity.get("sku"))
            elif isinstance(product, (tuple, list)) and len(product) >= 3:
                identity = {
                    "product_id": product[0],
                    "offer_id": product[1],
                    "sku": product[2],
                }
                finance_sku = cls._text(product[2])
            else:
                continue
            if not finance_sku:
                continue
            existing = indexed.get(finance_sku)
            if existing is not None and not cls._same_stable_identity(existing, identity):
                # Ambiguous input identity must not be used for a posting join.
                indexed[finance_sku] = None
                continue
            if finance_sku not in indexed:
                indexed[finance_sku] = identity
        return indexed

    @classmethod
    def _same_stable_identity(cls, left, right):
        left_product = cls._text(left.get("product_id"))
        right_product = cls._text(right.get("product_id"))
        left_offer = cls._text(left.get("offer_id"))
        right_offer = cls._text(right.get("offer_id"))
        if left_product and right_product and left_product != right_product:
            return False
        if left_offer and right_offer and left_offer != right_offer:
            return False
        return True

    def _reconcile_sale_quantities(self, result, date_from, date_to):
        start = self._date(date_from)
        end = self._date(date_to)
        if start is None or end is None or start > end:
            return self._quantity_error("PERIOD_PROFIT_SALE_QUANTITY_PERIOD_INVALID")

        getter = getattr(self.finance_service, "get_daily_sale_posting_evidence", None)
        if not callable(getter):
            return self._quantity_error(
                "PERIOD_PROFIT_SALE_QUANTITY_FINANCE_EVIDENCE_UNAVAILABLE"
            )

        sale_records = []
        current = start
        while current <= end:
            try:
                evidence = getter(current.isoformat())
            except Exception:
                return self._quantity_error(
                    "PERIOD_PROFIT_SALE_QUANTITY_FINANCE_EVIDENCE_UNAVAILABLE"
                )
            if (
                not isinstance(evidence, dict)
                or evidence.get("error") is True
                or evidence.get("complete") is not True
                or not isinstance(evidence.get("records"), list)
            ):
                return self._quantity_error(
                    "PERIOD_PROFIT_SALE_QUANTITY_FINANCE_EVIDENCE_INCOMPLETE"
                )
            sale_records.extend(evidence["records"])
            current += timedelta(days=1)

        grouped = {}
        reaccrued_event_count = 0
        for record in sale_records:
            if not isinstance(record, dict):
                return self._quantity_error(
                    "PERIOD_PROFIT_SALE_QUANTITY_FINANCE_EVIDENCE_INVALID"
                )
            posting_number = self._text(record.get("posting_number"))
            sku = self._text(record.get("sku"))
            accrual_date = self._date(record.get("accrual_date"))
            if not posting_number or not sku or accrual_date is None:
                return self._quantity_error(
                    "PERIOD_PROFIT_SALE_QUANTITY_FINANCE_EVIDENCE_INVALID"
                )
            key = (posting_number, sku)
            if key in grouped:
                reaccrued_event_count += 1
                grouped[key]["accrual_dates"].add(accrual_date.isoformat())
                continue
            grouped[key] = {
                "record": dict(record, accrual_date=accrual_date.isoformat()),
                "accrual_dates": {accrual_date.isoformat()},
            }

        product_rows = result.get("products")
        if not isinstance(product_rows, list):
            return self._quantity_error("PERIOD_PROFIT_SALE_QUANTITY_RESULT_INVALID")
        row_by_finance_sku = {}
        for row in product_rows:
            if not isinstance(row, dict):
                return self._quantity_error("PERIOD_PROFIT_SALE_QUANTITY_RESULT_INVALID")
            finance_sku = self._text(row.get("finance_sku") or row.get("sku"))
            if not finance_sku or finance_sku in row_by_finance_sku:
                return self._quantity_error("PERIOD_PROFIT_SALE_QUANTITY_RESULT_INVALID")
            row_by_finance_sku[finance_sku] = row

        realization_map = self._load_realization_quantity_map(start, end)
        if realization_map is None:
            realization_map = {}

        unresolved_records = []
        for key, grouped_record in grouped.items():
            posting_number, finance_sku = key
            row = row_by_finance_sku.get(finance_sku)
            if row is None:
                return self._quantity_error(
                    "PERIOD_PROFIT_SALE_QUANTITY_SKU_SCOPE_INCOMPLETE"
                )
            if self._quantity_from_identity_map(
                realization_map,
                posting_number,
                finance_sku,
                row,
                allow_offer=False,
            ) is not None:
                continue
            base_record = grouped_record["record"]
            for accrual_date in sorted(grouped_record["accrual_dates"]):
                unresolved_records.append(
                    dict(base_record, accrual_date=accrual_date)
                )

        fbo_list_map = self._load_fbo_list_quantity_map(unresolved_records)
        if fbo_list_map is None:
            fbo_list_map = {}

        physical_sales = []
        for key, grouped_record in grouped.items():
            posting_number, finance_sku = key
            row = row_by_finance_sku.get(finance_sku)
            if row is None:
                return self._quantity_error(
                    "PERIOD_PROFIT_SALE_QUANTITY_SKU_SCOPE_INCOMPLETE"
                )

            quantity = self._quantity_from_identity_map(
                realization_map,
                posting_number,
                finance_sku,
                row,
                allow_offer=False,
            )
            if quantity is None:
                quantity = self._quantity_from_identity_map(
                    fbo_list_map,
                    posting_number,
                    finance_sku,
                    row,
                    allow_offer=True,
                )
            if quantity is None:
                quantity = self._load_posting_quantity_for_identity(
                    posting_number,
                    finance_sku,
                    row,
                )
            if quantity is None:
                return self._quantity_error(
                    "PERIOD_PROFIT_SALE_QUANTITY_EVIDENCE_UNAVAILABLE"
                )
            physical_sales.append({
                "posting_number": posting_number,
                "sku": finance_sku,
                "quantity": quantity,
                "accrual_dates": sorted(grouped_record["accrual_dates"]),
            })

        next_rows = []
        covered_skus = set()
        total_units = 0
        total_product_cost = 0.0
        historical_bucket_count = 0

        for row in product_rows:
            finance_sku = self._text(row.get("finance_sku") or row.get("sku"))
            if not finance_sku:
                return self._quantity_error("PERIOD_PROFIT_SALE_QUANTITY_RESULT_INVALID")
            net_accrual = self._number(row.get("net_accrual"), missing_zero=True)
            tax = self._number(row.get("tax"), missing_zero=True)
            revenue = self._number(row.get("revenue"), missing_zero=True)
            if None in (net_accrual, tax, revenue):
                return self._quantity_error("PERIOD_PROFIT_SALE_QUANTITY_RESULT_INVALID")

            units = 0
            product_cost = 0.0
            applied_versions = set()
            for sale in physical_sales:
                if sale["sku"] != finance_sku:
                    continue

                version_signatures = set()
                resolved_cost = None
                for accrual_date in sale["accrual_dates"]:
                    cost_evidence = self._effective_cost_evidence(row, accrual_date)
                    if cost_evidence is None:
                        return self._quantity_error(
                            "PERIOD_PROFIT_EFFECTIVE_COST_UNAVAILABLE"
                        )
                    cost = self._number(cost_evidence.get("cost_price"))
                    if cost is None:
                        return self._quantity_error(
                            "PERIOD_PROFIT_EFFECTIVE_COST_UNAVAILABLE"
                        )
                    signature = self._cost_version_signature(cost_evidence, cost)
                    if signature is None:
                        return self._quantity_error(
                            "PERIOD_PROFIT_EFFECTIVE_COST_UNAVAILABLE"
                        )
                    version_signatures.add(signature)
                    resolved_cost = cost

                if len(version_signatures) != 1 or resolved_cost is None:
                    return self._quantity_error(
                        "PERIOD_PROFIT_REACCRUAL_COST_VERSION_AMBIGUOUS"
                    )

                candidate = product_cost + sale["quantity"] * resolved_cost
                if not isfinite(candidate):
                    return self._quantity_error(
                        "PERIOD_PROFIT_SALE_QUANTITY_RESULT_INVALID"
                    )
                product_cost = candidate
                units += sale["quantity"]
                applied_versions.update(version_signatures)
                historical_bucket_count += 1

            profit = net_accrual - product_cost - tax
            if not all(isfinite(v) for v in (product_cost, profit)):
                return self._quantity_error("PERIOD_PROFIT_SALE_QUANTITY_RESULT_INVALID")

            next_row = dict(row)
            next_row["units_sold"] = units
            next_row["product_cost"] = round(product_cost, 2)
            if units > 0:
                next_row["cost_per_unit"] = round(product_cost / units, 2)
            next_row["profit"] = round(profit, 2)
            next_row["margin_percent"] = self._margin(next_row["profit"], revenue)
            if next_row["margin_percent"] is None:
                return self._quantity_error("PERIOD_PROFIT_SALE_QUANTITY_RESULT_INVALID")
            next_row["effective_cost_versioned"] = len(applied_versions) > 1
            next_rows.append(next_row)
            covered_skus.add(finance_sku)
            total_units += units
            total_product_cost += product_cost

        if any(sale["sku"] not in covered_skus for sale in physical_sales):
            return self._quantity_error(
                "PERIOD_PROFIT_SALE_QUANTITY_SKU_SCOPE_INCOMPLETE"
            )

        net_accrual = self._number(result.get("net_accrual"), missing_zero=True)
        tax = self._number(result.get("tax"), missing_zero=True)
        revenue = self._number(result.get("revenue"), missing_zero=True)
        if None in (net_accrual, tax, revenue):
            return self._quantity_error("PERIOD_PROFIT_SALE_QUANTITY_RESULT_INVALID")

        profit = net_accrual - total_product_cost - tax
        if not isfinite(profit):
            return self._quantity_error("PERIOD_PROFIT_SALE_QUANTITY_RESULT_INVALID")

        enriched = dict(result)
        enriched["products"] = next_rows
        enriched["units_sold"] = total_units
        enriched["product_cost"] = round(total_product_cost, 2)
        enriched["profit"] = round(profit, 2)
        enriched["margin_percent"] = self._margin(enriched["profit"], revenue)
        if enriched["margin_percent"] is None:
            return self._quantity_error("PERIOD_PROFIT_SALE_QUANTITY_RESULT_INVALID")
        enriched["sale_quantity_reconciled"] = True
        enriched["sale_quantity_source"] = (
            "OZON_REALIZATION_POSTING_OR_FBO_STABLE_IDENTITY_OR_EXACT_POSTING_DETAIL"
        )
        enriched["sale_quantity_record_count"] = len(grouped)
        enriched["sale_quantity_positive_event_count"] = len(sale_records)
        enriched["sale_quantity_reaccrued_event_count"] = reaccrued_event_count
        enriched["effective_cost_reconciled"] = True
        enriched["effective_cost_source"] = (
            "SELLER_CONFIRMED_BOUNDED_HISTORY_OR_OPERATIONAL_SWITCH"
        )
        enriched["historical_cost_bucket_count"] = historical_bucket_count
        enriched["legacy_current_cost_bucket_count"] = 0
        return enriched

    def _quantity_from_identity_map(
        self,
        quantity_map,
        posting_number,
        finance_sku,
        row,
        *,
        allow_offer,
    ):
        if not isinstance(quantity_map, dict):
            return None
        keys = [(posting_number, finance_sku)]
        catalog_sku = self._text(row.get("catalog_sku"))
        if catalog_sku and catalog_sku != finance_sku:
            keys.append((posting_number, catalog_sku))
        if allow_offer:
            offer_id = self._text(row.get("offer_id"))
            if offer_id:
                keys.append((posting_number, self.OFFER_KEY_PREFIX + offer_id))

        values = {
            quantity_map[key]
            for key in keys
            if key in quantity_map and self._quantity(quantity_map[key]) is not None
        }
        if len(values) != 1:
            return None
        return next(iter(values))

    @classmethod
    def _parse_fbo_posting_list(cls, response):
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

        parsed = {}
        for posting in postings:
            if not isinstance(posting, dict):
                continue
            posting_number = cls._text(posting.get("posting_number"))
            products = posting.get("products")
            if not posting_number or not isinstance(products, list):
                continue
            seen = set()
            for product in products:
                if not isinstance(product, dict):
                    continue
                sku = cls._text(product.get("sku"))
                offer_id = cls._text(product.get("offer_id"))
                quantity = cls._quantity(product.get("quantity"))
                if quantity is None or (not sku and not offer_id):
                    continue
                keys = []
                if sku:
                    keys.append((posting_number, sku))
                if offer_id:
                    keys.append((posting_number, cls.OFFER_KEY_PREFIX + offer_id))
                for key in keys:
                    if key in seen:
                        return None
                    seen.add(key)
                    existing = parsed.get(key)
                    if existing is not None and existing != quantity:
                        return None
                    parsed[key] = quantity

        return parsed, len(postings), has_next

    def _load_posting_quantity_for_identity(self, posting_number, finance_sku, row):
        offer_id = self._text(row.get("offer_id"))
        catalog_sku = self._text(row.get("catalog_sku"))
        cache = getattr(self, "_identity_posting_quantity_cache", None)
        if not isinstance(cache, dict):
            cache = {}
            self._identity_posting_quantity_cache = cache
        key = (posting_number, finance_sku, catalog_sku, offer_id)
        if key in cache:
            return cache[key]

        quantity = None
        client = self.sale_quantity_ozon_client
        for method_name in ("get_fbo_posting", "get_fbs_posting"):
            getter = getattr(client, method_name, None)
            if not callable(getter):
                continue
            try:
                response = getter(posting_number)
            except Exception:
                continue
            quantity = self._quantity_from_posting_identity_response(
                response,
                posting_number,
                finance_sku,
                catalog_sku,
                offer_id,
            )
            if quantity is not None:
                break

        cache[key] = quantity
        return quantity

    @classmethod
    def _quantity_from_posting_identity_response(
        cls,
        response,
        posting_number,
        finance_sku,
        catalog_sku,
        offer_id,
    ):
        if not isinstance(response, dict) or response.get("error") is True:
            return None
        result = response.get("result")
        if not isinstance(result, dict):
            result = response
        returned = cls._text(result.get("posting_number"))
        products = result.get("products")
        if returned and returned != posting_number:
            return None
        if not isinstance(products, list):
            return None

        sku_aliases = {finance_sku}
        if catalog_sku:
            sku_aliases.add(catalog_sku)
        sku_quantities = []
        offer_quantities = []
        for product in products:
            if not isinstance(product, dict):
                continue
            quantity = cls._quantity(product.get("quantity"))
            if quantity is None:
                continue
            if cls._text(product.get("sku")) in sku_aliases:
                sku_quantities.append(quantity)
            if offer_id and cls._text(product.get("offer_id")) == offer_id:
                offer_quantities.append(quantity)

        candidates = []
        if len(sku_quantities) == 1:
            candidates.append(sku_quantities[0])
        elif len(sku_quantities) > 1:
            return None
        if len(offer_quantities) == 1:
            candidates.append(offer_quantities[0])
        elif len(offer_quantities) > 1:
            return None
        if not candidates or len(set(candidates)) != 1:
            return None
        return candidates[0]

    def _effective_cost_evidence(self, row, accrual_date):
        getter = getattr(self.cost_service, "get_effective_cost_evidence", None)
        if not callable(getter):
            return None
        try:
            evidence = getter(
                accrual_date,
                product_id=row.get("product_id"),
                sku=row.get("sku"),
                offer_id=row.get("offer_id"),
            )
        except Exception:
            return None
        if (
            not isinstance(evidence, dict)
            or evidence.get("error") is True
            or evidence.get("effective_cost_confirmed") is not True
            or evidence.get("historical_cost_confirmed") is not True
        ):
            return None
        return evidence

    @staticmethod
    def _cost_version_signature(evidence, cost):
        effective_from = str(evidence.get("effective_from") or "").strip()
        source = str(evidence.get("source") or "").strip()
        basis = str(evidence.get("cost_basis") or "").strip()
        if not effective_from or not source or not basis:
            return None

        if basis == "SELLER_CONFIRMED_OPERATIONAL_SWITCH":
            switch_id = evidence.get("switch_id")
            if switch_id is None:
                return None
            return (
                "SWITCH",
                str(switch_id),
                effective_from,
                source,
                round(cost, 2),
            )

        if basis != "SELLER_CONFIRMED_BOUNDED_PERIOD":
            return None
        effective_through = str(evidence.get("effective_through") or "").strip()
        history_id = evidence.get("history_id")
        if not effective_through or history_id is None:
            return None
        return (
            "BOUNDED_HISTORY",
            str(history_id),
            effective_from,
            effective_through,
            source,
            round(cost, 2),
        )
