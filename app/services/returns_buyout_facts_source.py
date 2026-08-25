class ReturnsBuyoutFactsSource:
    """Prepare conservative FBO posting facts for returns/buyout analytics.

    This source intentionally does not treat every cancelled posting as a
    customer non-buyout. It exposes normalized counts and keeps ambiguous
    cancellations explicit so downstream analytics can remain trustworthy.
    """

    DELIVERED_STATUSES = {
        "delivered",
        "delivering",
    }

    CANCELLED_STATUS = "cancelled"

    def __init__(self, ozon_client):
        self.ozon_client = ozon_client

    def get(self, sku, since, to):
        target_sku = str(sku or "").strip()
        if not target_sku:
            return {
                "error": True,
                "code": "SKU_REQUIRED",
                "message": "SKU не указан",
            }

        response = self.ozon_client.get_fbo_postings(
            since=since,
            to=to,
        )

        if not response or response.get("error"):
            return {
                "error": True,
                "code": "FBO_POSTINGS_UNAVAILABLE",
                "sku": target_sku,
                "message": "FBO postings недоступны",
            }

        postings = self._extract_postings(response)
        matched = []

        for posting in postings:
            quantity = self._sku_quantity(posting, target_sku)
            if quantity <= 0:
                continue

            matched.append(
                {
                    "posting_number": posting.get("posting_number"),
                    "status": str(posting.get("status") or "").lower(),
                    "quantity": quantity,
                    "cancel_reason_id": self._cancel_reason_id(posting),
                    "cancel_reason": self._cancel_reason(posting),
                }
            )

        total_units = sum(item["quantity"] for item in matched)
        cancelled_units = sum(
            item["quantity"]
            for item in matched
            if item["status"] == self.CANCELLED_STATUS
        )
        delivered_units = sum(
            item["quantity"]
            for item in matched
            if item["status"] in self.DELIVERED_STATUSES
        )

        return {
            "error": False,
            "sku": target_sku,
            "since": str(since),
            "to": str(to),
            "posting_count": len(matched),
            "total_units": total_units,
            "delivered_units": delivered_units,
            "cancelled_units": cancelled_units,
            "ambiguous_cancelled_units": cancelled_units,
            "customer_non_buyout_units": None,
            "customer_return_units": None,
            "postings": matched,
            "note": (
                "Cancelled FBO postings пока считаются неоднозначными и не "
                "приравниваются автоматически к невыкупам покупателя."
            ),
        }

    def _extract_postings(self, response):
        result = response.get("result") or {}
        return result.get("postings") or []

    def _sku_quantity(self, posting, target_sku):
        quantity = 0
        for product in posting.get("products") or []:
            identifiers = {
                str(product.get("offer_id") or ""),
                str(product.get("sku") or ""),
            }
            if target_sku not in identifiers:
                continue
            try:
                quantity += int(product.get("quantity") or 0)
            except (TypeError, ValueError):
                continue
        return quantity

    def _cancel_reason_id(self, posting):
        cancellation = posting.get("cancellation") or {}
        return cancellation.get("cancel_reason_id")

    def _cancel_reason(self, posting):
        cancellation = posting.get("cancellation") or {}
        return (
            cancellation.get("cancel_reason")
            or cancellation.get("cancellation_type")
        )
