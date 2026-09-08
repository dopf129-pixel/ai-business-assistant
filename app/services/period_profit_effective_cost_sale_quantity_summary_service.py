from datetime import timedelta
from math import isfinite

from services.period_profit_sale_quantity_summary_service import (
    PeriodProfitSaleQuantitySummaryService,
)


class PeriodProfitEffectiveCostSaleQuantitySummaryService(
    PeriodProfitSaleQuantitySummaryService
):
    """Reconcile physical sale quantity with bounded seller cost evidence."""

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
            posting_number = str(record.get("posting_number") or "").strip()
            sku = str(record.get("sku") or "").strip()
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

        realization_map = self._load_realization_quantity_map(start, end)
        if realization_map is None:
            realization_map = {}

        unresolved_records = []
        for key, grouped_record in grouped.items():
            if key in realization_map:
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
            posting_number, sku = key
            quantity = realization_map.get(key)
            if quantity is None:
                quantity = fbo_list_map.get(key)
            if quantity is None:
                quantity = self._load_posting_quantity(posting_number, sku)
            if quantity is None:
                return self._quantity_error(
                    "PERIOD_PROFIT_SALE_QUANTITY_EVIDENCE_UNAVAILABLE"
                )
            physical_sales.append({
                "posting_number": posting_number,
                "sku": sku,
                "quantity": quantity,
                "accrual_dates": sorted(grouped_record["accrual_dates"]),
            })

        product_rows = result.get("products")
        if not isinstance(product_rows, list):
            return self._quantity_error("PERIOD_PROFIT_SALE_QUANTITY_RESULT_INVALID")

        next_rows = []
        covered_skus = set()
        total_units = 0
        total_product_cost = 0.0
        historical_bucket_count = 0

        for row in product_rows:
            if not isinstance(row, dict):
                return self._quantity_error("PERIOD_PROFIT_SALE_QUANTITY_RESULT_INVALID")
            sku = str(row.get("sku") or "").strip()
            if not sku:
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
                if sale["sku"] != sku:
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
            covered_skus.add(sku)
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
            "OZON_REALIZATION_POSTING_OR_FBO_LIST_OR_EXACT_POSTING_DETAIL"
        )
        enriched["sale_quantity_record_count"] = len(grouped)
        enriched["sale_quantity_positive_event_count"] = len(sale_records)
        enriched["sale_quantity_reaccrued_event_count"] = reaccrued_event_count
        enriched["effective_cost_reconciled"] = True
        enriched["effective_cost_source"] = "SELLER_CONFIRMED_BOUNDED_HISTORY"
        enriched["historical_cost_bucket_count"] = historical_bucket_count
        enriched["legacy_current_cost_bucket_count"] = 0
        return enriched

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
        effective_through = str(evidence.get("effective_through") or "").strip()
        source = str(evidence.get("source") or "").strip()
        if not effective_from or not effective_through or not source:
            return None
        history_id = evidence.get("history_id")
        return (
            str(history_id) if history_id is not None else "",
            effective_from,
            effective_through,
            source,
            round(cost, 2),
        )
