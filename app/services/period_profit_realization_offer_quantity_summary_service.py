from services.period_profit_effective_cost_sale_quantity_summary_service import (
    PeriodProfitEffectiveCostSaleQuantitySummaryService,
)


class PeriodProfitRealizationOfferQuantitySummaryService(
    PeriodProfitEffectiveCostSaleQuantitySummaryService
):
    """Use seller offer identity when realization SKU no longer matches catalog state.

    Ozon's per-posting realization report exposes both ``item.sku`` and the stable
    seller ``item.offer_id``. Finance can retain one historical SKU while the live
    catalog has already moved to another SKU. A realization row may therefore be
    valid physical quantity evidence even when neither SKU equals the current
    catalog snapshot, provided the upstream finance scope has already proved the
    stable offer identity.

    Exact finance/catalog SKU evidence is still considered together with the offer
    evidence. Conflicting quantities fail closed through the inherited identity-map
    reconciliation; this adapter never guesses across offers or postings.
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
        reconciled = super()._reconcile_sale_quantities(result, date_from, date_to)
        if (
            isinstance(reconciled, dict)
            and reconciled.get("error") is False
            and reconciled.get("sale_quantity_reconciled") is True
        ):
            reconciled = dict(reconciled)
            reconciled["sale_quantity_source"] = (
                "OZON_REALIZATION_OR_FBO_STABLE_IDENTITY_OR_EXACT_POSTING_DETAIL"
            )
        return reconciled
