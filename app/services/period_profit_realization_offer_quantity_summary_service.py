from datetime import timedelta

from services.period_profit_effective_cost_sale_quantity_summary_service import (
    PeriodProfitEffectiveCostSaleQuantitySummaryService,
)


class PeriodProfitRealizationOfferQuantitySummaryService(
    PeriodProfitEffectiveCostSaleQuantitySummaryService
):
    """Reconcile sale quantity using direct finance evidence before legacy fallbacks.

    The current Ozon finance family exposes ``/v1/finance/accrual/postings`` with
    exact ``posting_number``, ``sku`` and ``quantity``. That evidence is the first
    physical-quantity authority because it belongs to the same finance lineage as
    the by-day monetary evidence. Realization and posting APIs remain strict
    READ-ONLY fallbacks when the direct finance endpoint has no usable row.

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

    def _load_direct_finance_quantity_map(self, date_from, date_to):
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
        posting_numbers = set()
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
                if posting_number and sku:
                    posting_numbers.add(posting_number)
                    expected.add((posting_number, sku))
            current += timedelta(days=1)

        if not posting_numbers:
            return {"map": {}, "expected": expected, "fatal": None}

        try:
            evidence = quantity_getter(sorted(posting_numbers))
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
        # Direct finance posting quantity is intentionally authoritative over the
        # older monthly realization representation for the exact same identity.
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
        direct = self._load_direct_finance_quantity_map(date_from, date_to)
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
