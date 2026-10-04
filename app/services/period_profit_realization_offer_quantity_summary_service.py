from datetime import timedelta

from services.period_profit_effective_cost_sale_quantity_summary_service import (
    PeriodProfitEffectiveCostSaleQuantitySummaryService,
)
from services.period_profit_operation_diagnostics import (
    current_period_profit_trace,
)
from services.period_profit_sale_quantity_summary_service import (
    PeriodProfitSaleQuantitySummaryService,
)


class PeriodProfitRealizationOfferQuantitySummaryService(
    PeriodProfitEffectiveCostSaleQuantitySummaryService
):
    """Reconcile sale quantity from exact evidence with bounded Ozon reads.

    Monthly realization is used first when it proves an exact posting/SKU or
    stable-offer quantity. The current finance endpoint
    ``/v1/finance/accrual/postings`` is queried only for unresolved postings,
    including open rows not represented in realization. This keeps the finance
    source available for ambiguous cases without scaling requests with every
    historical order in a long period.

    Stable seller offer identity is still used when realization/FBO SKU no longer
    matches the finance SKU. Conflicting direct finance quantities fail closed.
    """

    @staticmethod
    def _text(value):
        if value is None:
            return ""
        return str(value).strip()

    @classmethod
    def _parse_realization(cls, response):
        parsed = super()._parse_realization(response)
        if parsed is None:
            return None

        rows = response.get("rows") if isinstance(response, dict) else None
        if not isinstance(rows, list) and isinstance(response, dict):
            result = response.get("result")
            rows = result.get("rows") if isinstance(result, dict) else None
        if not isinstance(rows, list):
            return None

        for row in rows:
            if not isinstance(row, dict):
                continue
            order = row.get("order")
            item = row.get("item")
            delivery = row.get("delivery_commission")
            if not all(isinstance(value, dict) for value in (order, item, delivery)):
                continue

            posting_number = cls._text(order.get("posting_number"))
            offer_id = cls._text(item.get("offer_id"))
            quantity = cls._quantity(delivery.get("quantity"))
            if not posting_number or not offer_id or quantity is None:
                continue

            key = (posting_number, cls.OFFER_KEY_PREFIX + offer_id)
            existing = parsed.get(key)
            if existing is not None and existing != quantity:
                return None
            parsed[key] = quantity

        return parsed

    def _load_direct_finance_quantity_map(
        self,
        date_from,
        date_to,
        product_rows=None,
    ):
        start = self._date(date_from)
        end = self._date(date_to)
        if start is None or end is None or start > end:
            return {"map": {}, "expected": set(), "fatal": None}

        daily_getter = getattr(
            self.finance_service,
            "get_daily_sale_posting_evidence",
            None,
        )
        quantity_getter = getattr(
            self.finance_service,
            "get_sale_posting_quantity_evidence",
            None,
        )
        if not callable(daily_getter) or not callable(quantity_getter):
            return {"map": {}, "expected": set(), "fatal": None}

        expected = set()
        selected_finance_skus = {
            self._text(product.get("sku"))
            for product in (
                getattr(self, "_active_quantity_products", []) or []
            )
            if isinstance(product, dict)
            and product.get("_period_profit_selected_scope") is True
            and self._text(product.get("sku"))
        }
        current = start
        while current <= end:
            try:
                evidence = daily_getter(current.isoformat())
            except Exception:
                return {"map": {}, "expected": set(), "fatal": None}
            if (
                not isinstance(evidence, dict)
                or evidence.get("error") is True
                or evidence.get("complete") is not True
                or not isinstance(evidence.get("records"), list)
            ):
                # Let the inherited reconciler return its canonical daily-evidence
                # error instead of replacing it with a direct-source diagnostic.
                return {"map": {}, "expected": set(), "fatal": None}
            for record in evidence["records"]:
                if not isinstance(record, dict):
                    continue
                posting_number = self._text(record.get("posting_number"))
                sku = self._text(record.get("sku"))
                if (
                    posting_number
                    and sku
                    and (
                        not selected_finance_skus
                        or sku in selected_finance_skus
                    )
                ):
                    expected.add((posting_number, sku))
            current += timedelta(days=1)

        if not expected:
            return {"map": {}, "expected": expected, "fatal": None}

        # Use exact monthly realization evidence for rows it already proves.
        # Direct finance-by-posting remains the source for unresolved postings,
        # especially open rows absent from realization, instead of issuing one
        # batched request for every historical shipment in a long period.
        try:
            realization_map = (
                PeriodProfitSaleQuantitySummaryService
                ._load_realization_quantity_map(self, start, end)
            )
        except Exception:
            realization_map = None
        if not isinstance(realization_map, dict):
            realization_map = {}

        row_by_finance_sku = {}
        for row in product_rows or []:
            if not isinstance(row, dict):
                continue
            finance_sku = self._text(row.get("finance_sku") or row.get("sku"))
            if finance_sku:
                row_by_finance_sku[finance_sku] = row

        unresolved_postings = set()
        for posting_number, finance_sku in expected:
            row = row_by_finance_sku.get(finance_sku) or {
                "finance_sku": finance_sku,
                "sku": finance_sku,
            }
            quantity = self._quantity_from_identity_map(
                realization_map,
                posting_number,
                finance_sku,
                row,
                allow_offer=True,
            )
            if quantity is None:
                unresolved_postings.add(posting_number)

        trace = current_period_profit_trace()
        if trace is not None:
            trace.record_identity_stage(
                "sale_quantity_source_prefilter",
                record_count=len(expected),
                related_item_count=len(unresolved_postings),
                status=(
                    "DIRECT_FINANCE_REQUIRED"
                    if unresolved_postings
                    else "REALIZATION_COVERS_SCOPE"
                ),
            )

        if not unresolved_postings:
            return {"map": {}, "expected": expected, "fatal": None}

        try:
            evidence = quantity_getter(sorted(unresolved_postings))
        except Exception:
            return {"map": {}, "expected": expected, "fatal": None}

        if not isinstance(evidence, dict) or evidence.get("error") is True:
            code = evidence.get("code") if isinstance(evidence, dict) else None
            if code == "FINANCE_SALE_POSTING_QUANTITY_EVIDENCE_CONFLICT":
                return {
                    "map": {},
                    "expected": expected,
                    "fatal": "PERIOD_PROFIT_SALE_QUANTITY_FINANCE_POSTING_CONFLICT",
                }
            return {"map": {}, "expected": expected, "fatal": None}

        records = evidence.get("records")
        if evidence.get("complete") is not True or not isinstance(records, list):
            return {"map": {}, "expected": expected, "fatal": None}

        parsed = {}
        observed_by_posting = {}
        for record in records:
            if not isinstance(record, dict):
                return {"map": {}, "expected": expected, "fatal": None}
            posting_number = self._text(record.get("posting_number"))
            sku = self._text(record.get("sku"))
            quantity = self._quantity(record.get("quantity"))
            if not posting_number or not sku or quantity is None:
                return {"map": {}, "expected": expected, "fatal": None}
            key = (posting_number, sku)
            existing = parsed.get(key)
            if existing is not None and existing != quantity:
                return {
                    "map": {},
                    "expected": expected,
                    "fatal": "PERIOD_PROFIT_SALE_QUANTITY_FINANCE_POSTING_CONFLICT",
                }
            parsed[key] = quantity
            observed_by_posting.setdefault(posting_number, {})[sku] = quantity

        # Ozon can retain a retired SKU in accrual/by-day while accrual/postings
        # exposes the current SKU for the same physical posting. Bridge that SKU
        # drift only when the posting is provably one-to-one on both sides: exactly
        # one finance sale identity and exactly one observed positive quantity line.
        # Multi-item postings remain unresolved and fall through to stable-identity
        # sources instead of guessing.
        expected_by_posting = {}
        for posting_number, sku in expected:
            expected_by_posting.setdefault(posting_number, set()).add(sku)

        for posting_number, expected_skus in expected_by_posting.items():
            if len(expected_skus) != 1:
                continue
            observed = observed_by_posting.get(posting_number) or {}
            if len(observed) != 1:
                continue
            expected_sku = next(iter(expected_skus))
            if (posting_number, expected_sku) in parsed:
                continue
            observed_quantity = next(iter(observed.values()))
            parsed[(posting_number, expected_sku)] = observed_quantity

        return {"map": parsed, "expected": expected, "fatal": None}

    def _load_realization_quantity_map(self, start, end):
        direct = dict(getattr(self, "_direct_finance_quantity_map", {}) or {})
        expected = set(getattr(self, "_direct_finance_expected_keys", set()) or set())
        if expected and expected.issubset(set(direct)):
            return direct

        fallback = super()._load_realization_quantity_map(start, end)
        if fallback is None:
            return direct if direct else None

        merged = dict(fallback)
        # Direct finance posting quantity is authoritative for keys it resolves;
        # realization remains the bounded source for already-proven delivered keys.
        merged.update(direct)
        return merged

    def _quantity_from_identity_map(
        self,
        quantity_map,
        posting_number,
        finance_sku,
        row,
        *,
        allow_offer,
    ):
        return super()._quantity_from_identity_map(
            quantity_map,
            posting_number,
            finance_sku,
            row,
            allow_offer=True,
        )

    def _reconcile_sale_quantities(self, result, date_from, date_to):
        self._direct_finance_quantity_map = {}
        self._direct_finance_expected_keys = set()
        direct = self._load_direct_finance_quantity_map(
            date_from,
            date_to,
            product_rows=(result.get("products") if isinstance(result, dict) else None),
        )
        fatal = direct.get("fatal") if isinstance(direct, dict) else None
        if fatal:
            return self._quantity_error(fatal)
        self._direct_finance_quantity_map = (
            dict(direct.get("map") or {}) if isinstance(direct, dict) else {}
        )
        self._direct_finance_expected_keys = (
            set(direct.get("expected") or set()) if isinstance(direct, dict) else set()
        )

        reconciled = super()._reconcile_sale_quantities(result, date_from, date_to)
        if (
            isinstance(reconciled, dict)
            and reconciled.get("error") is False
            and reconciled.get("sale_quantity_reconciled") is True
        ):
            reconciled = dict(reconciled)
            reconciled["sale_quantity_source"] = (
                "OZON_FINANCE_ACCRUAL_POSTINGS_OR_REALIZATION_OR_"
                "FBO_STABLE_IDENTITY_OR_EXACT_POSTING_DETAIL"
            )
            reconciled["direct_finance_quantity_record_count"] = len(
                self._direct_finance_quantity_map
            )
        return reconciled
