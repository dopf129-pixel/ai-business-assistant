class ReturnsBuyoutFactsSource:
    """Prepare conservative FBO posting and returns facts for analytics."""

    DELIVERED_STATUSES = {
        "delivered",
        "delivering",
    }

    CANCELLED_STATUS = "cancelled"
    CLIENT_RETURN_TYPE = "clientreturn"
    CANCELLATION_TYPE = "cancellation"
    NON_BUYOUT_REASON_PREFIX = "покупатель отказался при вручении"
    CUSTOMER_CANCEL_REASON_PREFIX = "покупатель отменил заказ"
    DELIVERY_FAILURE_REASON_PREFIX = "не удалось доставить заказ"

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

        posting_response = self.ozon_client.get_fbo_postings(
            since=since,
            to=to,
        )

        if not posting_response or posting_response.get("error"):
            return {
                "error": True,
                "code": "FBO_POSTINGS_UNAVAILABLE",
                "sku": target_sku,
                "message": "FBO postings недоступны",
            }

        returns_response = self.ozon_client.get_returns(
            offer_id=target_sku,
            return_schema="FBO",
            limit=100,
            last_id=0,
        )

        returns_available = bool(
            returns_response and not returns_response.get("error")
        )

        postings = self._extract_postings(posting_response)
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

        return_events = []
        if returns_available:
            for item in returns_response.get("returns") or []:
                product = item.get("product") or {}
                if not self._return_matches(product, target_sku):
                    continue

                quantity = self._return_quantity(product)
                if quantity <= 0:
                    continue

                event_type = str(item.get("type") or "").lower()
                reason = str(item.get("return_reason_name") or "").strip()
                category = self._return_category(event_type, reason)

                return_events.append(
                    {
                        "posting_number": item.get("posting_number"),
                        "type": item.get("type"),
                        "reason": reason or None,
                        "quantity": quantity,
                        "category": category,
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

        customer_non_buyout_units = self._category_units(
            return_events,
            "customer_non_buyout",
        ) if returns_available else None
        customer_return_units = self._category_units(
            return_events,
            "customer_return",
        ) if returns_available else None
        customer_cancelled_units = self._category_units(
            return_events,
            "customer_cancel",
        ) if returns_available else None
        delivery_failure_units = self._category_units(
            return_events,
            "delivery_failure",
        ) if returns_available else None
        unknown_return_units = self._category_units(
            return_events,
            "unknown",
        ) if returns_available else None

        known_cancel_units = None
        ambiguous_cancelled_units = cancelled_units
        if returns_available:
            known_cancel_units = sum(
                value or 0
                for value in (
                    customer_non_buyout_units,
                    customer_cancelled_units,
                    delivery_failure_units,
                )
            )
            ambiguous_cancelled_units = max(
                cancelled_units - known_cancel_units,
                0,
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
            "ambiguous_cancelled_units": ambiguous_cancelled_units,
            "customer_non_buyout_units": customer_non_buyout_units,
            "customer_return_units": customer_return_units,
            "customer_cancelled_units": customer_cancelled_units,
            "delivery_failure_units": delivery_failure_units,
            "unknown_return_units": unknown_return_units,
            "returns_available": returns_available,
            "postings": matched,
            "return_events": return_events,
            "note": self._note(returns_available, ambiguous_cancelled_units),
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

    def _return_matches(self, product, target_sku):
        return target_sku in {
            str(product.get("offer_id") or ""),
            str(product.get("sku") or ""),
        }

    def _return_quantity(self, product):
        try:
            return int(product.get("quantity") or 0)
        except (TypeError, ValueError):
            return 0

    def _return_category(self, event_type, reason):
        normalized_reason = reason.lower()

        if event_type == self.CLIENT_RETURN_TYPE:
            return "customer_return"
        if (
            event_type == self.CANCELLATION_TYPE
            and normalized_reason.startswith(self.NON_BUYOUT_REASON_PREFIX)
        ):
            return "customer_non_buyout"
        if (
            event_type == self.CANCELLATION_TYPE
            and normalized_reason.startswith(self.CUSTOMER_CANCEL_REASON_PREFIX)
        ):
            return "customer_cancel"
        if (
            event_type == self.CANCELLATION_TYPE
            and normalized_reason.startswith(self.DELIVERY_FAILURE_REASON_PREFIX)
        ):
            return "delivery_failure"
        return "unknown"

    def _category_units(self, events, category):
        return sum(
            item["quantity"]
            for item in events
            if item["category"] == category
        )

    def _cancel_reason_id(self, posting):
        cancellation = posting.get("cancellation") or {}
        return cancellation.get("cancel_reason_id")

    def _cancel_reason(self, posting):
        cancellation = posting.get("cancellation") or {}
        return (
            cancellation.get("cancel_reason")
            or cancellation.get("cancellation_type")
        )

    def _note(self, returns_available, ambiguous_cancelled_units):
        if not returns_available:
            return (
                "Returns API недоступен: cancelled FBO postings остаются "
                "неоднозначными и не считаются невыкупами."
            )
        if ambiguous_cancelled_units:
            return (
                "Невыкупы и возвраты классифицированы по Returns API; часть "
                "cancelled postings пока не сопоставлена с причиной."
            )
        return (
            "Невыкупы, возвраты и прочие отмены классифицированы по "
            "причинам Ozon Returns API."
        )
