from datetime import timedelta
from math import isfinite

from services.period_profit_critical_finance_summary_service import (
    PeriodProfitCriticalFinanceSummaryService,
)
from services.period_profit_sale_quantity_summary_service import (
    PeriodProfitSaleQuantitySummaryService,
)
from services.period_profit_cost_exclusion_context import cost_excluded
from services.period_profit_fifo_explanation_view_service import (
    PeriodProfitFifoExplanationViewService,
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

    def __init__(
        self, finance_service, cost_service, tax_rate=0.06,
        sale_quantity_ozon_client=None, fifo_cost_source_service=None,
    ):
        super().__init__(
            finance_service, cost_service, tax_rate=tax_rate,
            sale_quantity_ozon_client=sale_quantity_ozon_client,
        )
        self.fifo_cost_source_service = fifo_cost_source_service

    OFFER_KEY_PREFIX = "@offer:"

    @staticmethod
    def _text(value):
        return str(value or "").strip()

    def calculate(self, date_from, date_to, products):
        self._begin_quantity_evidence_session()
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

        if cost_excluded():
            # A pre-COGS view is monetary-only: physical sale quantity is needed
            # solely to multiply units by cost. Requiring realization/FBO evidence
            # here can fail a valid finance-only calculation for no accounting
            # benefit. The critical finance summary already has zero COGS under
            # this context, so return it without quantity reconciliation.
            pre_cogs = dict(result)
            pre_cogs["sale_quantity_reconciled"] = False
            pre_cogs["sale_quantity_required"] = False
            pre_cogs["product_cost"] = 0.0
            return pre_cogs

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
        self._active_quantity_products = list(products or [])
        try:
            return self._reconcile_sale_quantities(
                enriched,
                date_from,
                date_to,
            )
        finally:
            self._active_quantity_products = []

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

        selected_finance_skus = {
            str(product.get("sku") or "").strip()
            for product in (getattr(self, "_active_quantity_products", []) or [])
            if isinstance(product, dict)
            and product.get("_period_profit_selected_scope") is True
            and str(product.get("sku") or "").strip()
        }

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
            if selected_finance_skus and sku not in selected_finance_skus:
                continue
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
        fifo_sku_count = 0
        legacy_sku_count = 0
        mixed_sku_count = 0
        fifo_allocation_revisions = set()
        fifo_sales_by_finance_sku = {}
        fifo_alias_products_by_finance_sku = {}
        fifo_source = getattr(self, "fifo_cost_source_service", None)
        scope_identity_reader = getattr(fifo_source, "resolve_scope_identity", None)
        if fifo_source is not None and not cost_excluded() and callable(scope_identity_reader):
            sales_by_finance_sku = {}
            for sale in physical_sales:
                sales_by_finance_sku.setdefault(sale["sku"], []).append(sale)
            groups = {}
            for row in product_rows:
                finance_sku = self._text(row.get("finance_sku") or row.get("sku"))
                if not finance_sku:
                    continue
                try:
                    scope = scope_identity_reader(row)
                except Exception:
                    continue
                if not isinstance(scope, dict) or scope.get("error") is not False:
                    continue
                scope_fields = (
                    scope.get("store_id"), scope.get("product_id") or "",
                    scope.get("offer_id") or "", scope.get("sku"),
                )
                if (
                    not isinstance(scope_fields[0], str) or not scope_fields[0]
                    or not isinstance(scope_fields[1], str)
                    or not isinstance(scope_fields[2], str)
                    or not scope_fields[1] and not scope_fields[2]
                    or not isinstance(scope_fields[3], str) or not scope_fields[3]
                ):
                    # Lightweight test/compatibility sources may expose only an
                    # active flag. Do not combine rows unless the exact stream is
                    # proven by the scope response.
                    continue
                groups.setdefault(scope_fields, []).append((finance_sku, row))
            for aliases in groups.values():
                if len(aliases) < 2:
                    continue
                alias_skus = {finance_sku for finance_sku, _row in aliases}
                grouped_sales = [
                    sale for finance_sku in alias_skus
                    for sale in sales_by_finance_sku.get(finance_sku, ())
                ]
                alias_products = [row for _finance_sku, row in aliases]
                for finance_sku in alias_skus:
                    fifo_sales_by_finance_sku[finance_sku] = grouped_sales
                    fifo_alias_products_by_finance_sku[finance_sku] = alias_products

        for row in product_rows:
            finance_sku = self._text(row.get("finance_sku") or row.get("sku"))
            if not finance_sku:
                return self._quantity_error("PERIOD_PROFIT_SALE_QUANTITY_RESULT_INVALID")
            net_accrual = self._number(row.get("net_accrual"), missing_zero=True)
            tax = self._number(row.get("tax"), missing_zero=True)
            revenue = self._number(row.get("revenue"), missing_zero=True)
            if None in (net_accrual, tax, revenue):
                return self._quantity_error("PERIOD_PROFIT_SALE_QUANTITY_RESULT_INVALID")

            if fifo_source is not None and not cost_excluded():
                fifo_sales = fifo_sales_by_finance_sku.get(finance_sku)
                if fifo_sales is None:
                    fifo_sales = [
                        sale for sale in physical_sales if sale["sku"] == finance_sku
                    ]
                fifo_alias_products = fifo_alias_products_by_finance_sku.get(
                    finance_sku
                )
                try:
                    reconcile_kwargs = {
                        "product": row,
                        "finance_sku": finance_sku,
                        "date_from": start.isoformat(),
                        "date_to": end.isoformat(),
                        "sales": fifo_sales,
                    }
                    if fifo_alias_products is not None:
                        reconcile_kwargs["finance_sku_alias_products"] = (
                            fifo_alias_products
                        )
                    fifo = fifo_source.reconcile_period_sales(
                        **reconcile_kwargs,
                    )
                except Exception:
                    fifo = None
                if not isinstance(fifo, dict) or fifo.get("error") is not False:
                    error = self._quantity_error(
                        "PERIOD_PROFIT_FIFO_COGS_UNAVAILABLE"
                    )
                    if isinstance(fifo, dict) and fifo.get("code"):
                        error["fifo_reason_code"] = fifo["code"]
                    return error
                if fifo.get("active") is True:
                    if fifo.get("complete") is not True:
                        error = self._quantity_error(
                            "PERIOD_PROFIT_FIFO_COGS_INCOMPLETE"
                        )
                        error["fifo_reason_code"] = (
                            fifo.get("reason_code") or "FIFO_ALLOCATION_INCOMPLETE"
                        )
                        if self._date(fifo.get("cutoff_date")) is not None:
                            error["fifo_cutoff_date"] = self._date(
                                fifo.get("cutoff_date"),
                            ).isoformat()
                        return error
                    if fifo.get("partitioned_cutoff") is True:
                        mixed = self._resolve_cutoff_partitioned_cogs(
                            fifo=fifo,
                            row=row,
                            finance_sku=finance_sku,
                            sales=physical_sales,
                            fifo_source=fifo_source,
                            alias_products=(fifo_alias_products or [row]),
                        )
                        if mixed.get("error") is True:
                            error = self._quantity_error(
                                "PERIOD_PROFIT_FIFO_COGS_INCOMPLETE",
                            )
                            error["fifo_reason_code"] = mixed.get("code")
                            error["fifo_cutoff_date"] = fifo.get("cutoff_date")
                            return error
                        profit = net_accrual - mixed["product_cost"] - tax
                        if not isfinite(profit):
                            return self._quantity_error(
                                "PERIOD_PROFIT_SALE_QUANTITY_RESULT_INVALID"
                            )
                        next_row = dict(row)
                        next_row.update({
                            "units_sold": mixed["units_sold"],
                            "product_cost": mixed["product_cost"],
                            "cost_per_unit": (
                                round(mixed["product_cost"] / mixed["units_sold"], 2)
                                if mixed["units_sold"] else None
                            ),
                            "profit": round(profit, 2),
                            "margin_percent": self._margin(profit, revenue),
                            "cost_source": "CUTOFF_PARTITIONED_FIFO_AND_LEGACY",
                            "fifo_cogs_reconciliation_required": False,
                            "fifo_stream_revision": fifo.get("stream_revision"),
                            "fifo_allocation_revision": fifo.get("allocation_revision"),
                            "fifo_cutoff_date": fifo.get("cutoff_date"),
                            "fifo_cutoff_mapping_revision": fifo.get(
                                "cutoff_mapping_revision",
                            ),
                            "fifo_cutoff_mapping_complete_through": fifo.get(
                                "cutoff_mapping_complete_through",
                            ),
                            "fifo_cutoff_bridge_fingerprint": fifo.get(
                                "cutoff_bridge_fingerprint",
                            ),
                            "fifo_units_sold": mixed["fifo_units_sold"],
                            "fifo_product_cost": mixed["fifo_product_cost"],
                            "legacy_cutoff_units_sold": mixed["legacy_units_sold"],
                            "legacy_cutoff_product_cost": mixed["legacy_product_cost"],
                            "legacy_cutoff_cost_reconciled": True,
                            "fifo_cost_explanation": fifo.get("fifo_cost_explanation"),
                            "effective_cost_versioned": mixed["effective_cost_versioned"],
                        })
                        if next_row["margin_percent"] is None:
                            return self._quantity_error(
                                "PERIOD_PROFIT_SALE_QUANTITY_RESULT_INVALID"
                            )
                        next_rows.append(next_row)
                        covered_skus.add(finance_sku)
                        total_units += mixed["units_sold"]
                        total_product_cost += mixed["product_cost"]
                        if mixed["fifo_units_sold"]:
                            fifo_sku_count += 1
                            if fifo.get("allocation_revision") is not None:
                                fifo_allocation_revisions.add(
                                    fifo["allocation_revision"]
                                )
                        if mixed["legacy_units_sold"]:
                            legacy_sku_count += 1
                            historical_bucket_count += mixed["legacy_sale_count"]
                        if mixed["fifo_units_sold"] and mixed["legacy_units_sold"]:
                            mixed_sku_count += 1
                        continue
                    units = fifo.get("units_sold")
                    product_cost_value = self._number(fifo.get("product_cost"))
                    if (
                        type(units) is not int or units < 0
                        or product_cost_value is None
                    ):
                        return self._quantity_error(
                            "PERIOD_PROFIT_FIFO_COGS_RESPONSE_INVALID"
                        )
                    profit = net_accrual - product_cost_value - tax
                    if not isfinite(profit):
                        return self._quantity_error(
                            "PERIOD_PROFIT_SALE_QUANTITY_RESULT_INVALID"
                        )
                    next_row = dict(row)
                    next_row["units_sold"] = units
                    next_row["product_cost"] = round(product_cost_value, 2)
                    next_row["cost_per_unit"] = (
                        round(product_cost_value / units, 2) if units else None
                    )
                    next_row["profit"] = round(profit, 2)
                    next_row["margin_percent"] = self._margin(
                        next_row["profit"], revenue,
                    )
                    if next_row["margin_percent"] is None:
                        return self._quantity_error(
                            "PERIOD_PROFIT_SALE_QUANTITY_RESULT_INVALID"
                        )
                    next_row["cost_source"] = "FIFO_ALLOCATION_REVISION"
                    next_row["fifo_cogs_reconciliation_required"] = False
                    next_row["fifo_stream_revision"] = fifo.get("stream_revision")
                    next_row["fifo_allocation_revision"] = fifo.get(
                        "allocation_revision"
                    )
                    next_row["fifo_cutoff_date"] = fifo.get("cutoff_date")
                    next_row["fifo_cutoff_mapping_revision"] = fifo.get(
                        "cutoff_mapping_revision",
                    )
                    next_row["fifo_cutoff_mapping_complete_through"] = fifo.get(
                        "cutoff_mapping_complete_through",
                    )
                    if isinstance(fifo.get("fifo_cost_explanation"), dict):
                        next_row["fifo_cost_explanation"] = fifo[
                            "fifo_cost_explanation"
                        ]
                    next_rows.append(next_row)
                    covered_skus.add(finance_sku)
                    total_units += units
                    total_product_cost += product_cost_value
                    fifo_sku_count += 1
                    if fifo.get("allocation_revision") is not None:
                        fifo_allocation_revisions.add(fifo["allocation_revision"])
                    continue

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
            next_row["cost_source"] = "LEGACY_DATED_COST"
            next_row["fifo_cogs_reconciliation_required"] = False
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
            legacy_sku_count += 1

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
        enriched["fifo_cogs_reconciliation_required"] = False
        enriched["fifo_cogs_reconciled"] = True
        enriched["fifo_cost_source_counts"] = {
            "fifo": fifo_sku_count,
            "legacy": legacy_sku_count,
        }
        if mixed_sku_count:
            enriched["fifo_cost_source_counts"]["mixed_cutoff"] = mixed_sku_count
        enriched["fifo_allocation_revision_count"] = len(
            fifo_allocation_revisions
        )
        enriched["historical_cost_bucket_count"] = historical_bucket_count
        enriched["legacy_current_cost_bucket_count"] = 0
        fifo_explanation = PeriodProfitFifoExplanationViewService().build(enriched)
        if isinstance(fifo_explanation, dict):
            enriched["fifo_cost_explanation"] = fifo_explanation
        return enriched

    def _resolve_cutoff_partitioned_cogs(
        self, *, fifo, row, finance_sku, sales, fifo_source, alias_products,
    ):
        """Price pre-cutoff physical sales from dated legacy history and post-cutoff
        sales from the exact FIFO allocation revision; never infer the split from
        the financial period dates.
        """
        cutoff = self._date(fifo.get("cutoff_date"))
        fifo_units = fifo.get("fifo_units_sold")
        fifo_cost = self._number(fifo.get("fifo_product_cost"))
        legacy_units = fifo.get("legacy_units_sold")
        legacy_sales = fifo.get("legacy_sales")
        digest_builder = getattr(fifo_source, "build_sale_identity_digest", None)
        if (
            cutoff is None or type(fifo_units) is not int or fifo_units < 0
            or fifo_cost is None or fifo_cost < 0
            or type(legacy_units) is not int or legacy_units < 0
            or not isinstance(legacy_sales, list) or len(legacy_sales) > 100_000
            or not callable(digest_builder)
        ):
            return {"error": True, "code": "PERIOD_PROFIT_FIFO_COGS_RESPONSE_INVALID"}

        aliases = {}
        for product in alias_products:
            if isinstance(product, dict):
                sku = self._text(product.get("sku"))
                if sku is not None and sku not in aliases:
                    aliases[sku] = product
        sale_by_digest = {}
        selected_sales = [sale for sale in sales if sale.get("sku") == finance_sku]
        selected_units = 0
        try:
            for sale in selected_sales:
                alias_product = aliases.get(sale.get("sku"), row)
                identity = digest_builder(alias_product, sale)
                if not isinstance(identity, dict) or identity.get("error") is True:
                    return {"error": True, "code": "FIFO_CUTOFF_SALE_IDENTITY_INVALID"}
                digest = identity.get("source_identity_digest")
                quantity = sale.get("quantity")
                if (
                    not isinstance(digest, str) or len(digest) != 64
                    or type(quantity) is not int or quantity < 1
                    or digest in sale_by_digest
                ):
                    return {"error": True, "code": "FIFO_CUTOFF_SALE_IDENTITY_INVALID"}
                sale_by_digest[digest] = sale
                selected_units += quantity

            total_legacy_cost = 0.0
            used = set()
            versions = set()
            for legacy in legacy_sales:
                if not isinstance(legacy, dict):
                    return {"error": True, "code": "FIFO_CUTOFF_LEGACY_SALE_MAPPING_INVALID"}
                digest = legacy.get("source_identity_digest")
                quantity = legacy.get("quantity")
                physical_date = self._date(legacy.get("physical_effective_date"))
                sale = sale_by_digest.get(digest)
                if (
                    digest in used or sale is None or physical_date is None
                    or physical_date > cutoff
                    or type(quantity) is not int or quantity < 1
                    or sale.get("quantity") != quantity
                ):
                    return {"error": True, "code": "PERIOD_PROFIT_FIFO_COGS_INCOMPLETE"}
                evidence = self._effective_cost_evidence(
                    row, physical_date.isoformat(),
                )
                if (
                    not isinstance(evidence, dict)
                    or evidence.get("error") is True
                    or evidence.get("effective_cost_confirmed") is not True
                ):
                    return {"error": True, "code": "PERIOD_PROFIT_EFFECTIVE_COST_UNAVAILABLE"}
                cost = self._number(evidence.get("cost_price"))
                signature = self._cost_version_signature(evidence, cost)
                if cost is None or cost < 0 or signature is None:
                    return {"error": True, "code": "PERIOD_PROFIT_EFFECTIVE_COST_UNAVAILABLE"}
                total_legacy_cost += quantity * cost
                if not isfinite(total_legacy_cost):
                    return {"error": True, "code": "PERIOD_PROFIT_SALE_QUANTITY_RESULT_INVALID"}
                used.add(digest)
                versions.add(signature)
        except Exception:
            return {"error": True, "code": "FIFO_CUTOFF_LEGACY_COST_RESOLUTION_FAILED"}

        if (
            selected_units != fifo_units + legacy_units
            or len(used) != len(legacy_sales)
        ):
            return {"error": True, "code": "FIFO_CUTOFF_SALE_COVERAGE_MISMATCH"}
        legacy_cost = round(total_legacy_cost, 2)
        fifo_cost = round(fifo_cost, 2)
        return {
            "error": False,
            "units_sold": selected_units,
            "fifo_units_sold": fifo_units,
            "fifo_product_cost": fifo_cost,
            "legacy_units_sold": legacy_units,
            "legacy_product_cost": legacy_cost,
            "legacy_sale_count": len(legacy_sales),
            "product_cost": round(fifo_cost + legacy_cost, 2),
            "effective_cost_versioned": len(versions) > 1,
        }

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
        if cost_excluded():
            return {
                "error": False,
                "effective_cost_confirmed": True,
                "historical_cost_confirmed": True,
                "cost_price": 0.0,
                "cost_basis": "SELLER_CONFIRMED_BOUNDED_PERIOD",
                "effective_from": str(accrual_date),
                "effective_through": str(accrual_date),
                "history_id": "PRE_COGS_VIEW",
                "source": "PERIOD_PROFIT_PRE_COGS_VIEW",
            }
        getter = getattr(self.cost_service, "get_effective_cost_evidence", None)
        if not callable(getter):
            return None
        try:
            evidence = getter(
                accrual_date,
                product_id=row.get("product_id"),
                # Stable seller/catalog identity is the cost authority for an
                # accrual whose finance SKU may have been retired or rewritten.
                sku=row.get("catalog_sku") or row.get("sku"),
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
