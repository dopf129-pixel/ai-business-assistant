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

    POSTINGS_PAGE_SIZE = 1000
    RETURNS_PAGE_SIZE = 500
    MAX_PAGES = 10

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

        postings, postings_complete, posting_error = self._load_postings(
            since=since,
            to=to,
        )

        if posting_error:
            return {
                "error": True,
                "code": "FBO_POSTINGS_UNAVAILABLE",
                "sku": target_sku,
                "message": "FBO postings недоступны",
            }

        return_items, returns_available, returns_complete = self._load_returns(
            target_sku=target_sku,
            since=since,
            to=to,
        )

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
            for item in return_items:
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
                        "return_id": item.get("id"),
                        "posting_number": item.get("posting_number"),
                        "type": item.get("type"),
                        "reason": reason or None,
                        "quantity": quantity,
                        "category": category,
                    }
                )

        total_units = sum(item["quantity"] for item in matched)
        cancelled_postings = [
            item for item in matched
            if item["status"] == self.CANCELLED_STATUS
        ]
        cancelled_units = sum(item["quantity"] for item in cancelled_postings)
        delivered_units = sum(
            item["quantity"]
            for item in matched
            if item["status"] in self.DELIVERED_STATUSES
        )

        customer_non_buyout_units = self._known_category_units(
            return_events,
            "customer_non_buyout",
            returns_available,
            returns_complete,
        )
        customer_return_units = self._known_category_units(
            return_events,
            "customer_return",
            returns_available,
            returns_complete,
        )
        customer_cancelled_units = self._known_category_units(
            return_events,
            "customer_cancel",
            returns_available,
            returns_complete,
        )
        delivery_failure_units = self._known_category_units(
            return_events,
            "delivery_failure",
            returns_available,
            returns_complete,
        )
        unknown_return_units = self._known_category_units(
            return_events,
            "unknown",
            returns_available,
            returns_complete,
        )

        ambiguous_cancelled_postings = list(cancelled_postings)
        if returns_available and returns_complete:
            classified_posting_numbers = {
                str(item.get("posting_number") or "")
                for item in return_events
                if item.get("category") in {
                    "customer_non_buyout",
                    "customer_cancel",
                    "delivery_failure",
                }
            }
            ambiguous_cancelled_postings = [
                item
                for item in cancelled_postings
                if str(item.get("posting_number") or "")
                not in classified_posting_numbers
            ]

        ambiguous_cancelled_units = sum(
            item["quantity"] for item in ambiguous_cancelled_postings
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
            "ambiguous_cancelled_postings": ambiguous_cancelled_postings,
            "customer_non_buyout_units": customer_non_buyout_units,
            "customer_return_units": customer_return_units,
            "customer_cancelled_units": customer_cancelled_units,
            "delivery_failure_units": delivery_failure_units,
            "unknown_return_units": unknown_return_units,
            "postings_complete": postings_complete,
            "returns_available": returns_available,
            "returns_complete": returns_complete,
            "postings": matched,
            "return_events": return_events,
            "note": self._note(
                returns_available,
                returns_complete,
                postings_complete,
                ambiguous_cancelled_units,
            ),
        }

    def _load_postings(self, since, to):
        all_postings = []
        offset = 0

        for _ in range(self.MAX_PAGES):
            response = self.ozon_client.get_fbo_postings(
                since=since,
                to=to,
                limit=self.POSTINGS_PAGE_SIZE,
                offset=offset,
                direction="DESC",
            )

            if not response or response.get("error"):
                return [], False, True

            page = self._extract_postings(response)
            all_postings.extend(page)

            if len(page) < self.POSTINGS_PAGE_SIZE:
                return all_postings, True, False

            offset += len(page)

        return all_postings, False, False

    def _load_returns(self, target_sku, since, to):
        all_returns = []
        last_id = 0

        for page_number in range(self.MAX_PAGES):
            response = self.ozon_client.get_returns(
                offer_id=target_sku,
                return_schema="FBO",
                since=since,
                to=to,
                limit=self.RETURNS_PAGE_SIZE,
                last_id=last_id,
            )

            if not response or response.get("error"):
                if page_number == 0:
                    return [], False, False
                return all_returns, True, False

            page = response.get("returns") or []
            all_returns.extend(page)

            if not response.get("has_next"):
                return all_returns, True, True

            if not page:
                return all_returns, True, False

            next_id = page[-1].get("id")
            try:
                next_id = int(next_id)
            except (TypeError, ValueError):
                return all_returns, True, False

            if next_id == last_id:
                return all_returns, True, False

            last_id = next_id

        return all_returns, True, False

    def _extract_postings(self, response):
        result = response.get("result") or []
        if isinstance(result, list):
            return result
        if isinstance(result, dict):
            return result.get("postings") or []
        return []

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

    def _known_category_units(
        self,
        events,
        category,
        returns_available,
        returns_complete,
    ):
        if not returns_available or not returns_complete:
            return None
        return self._category_units(events, category)

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

    def _note(
        self,
        returns_available,
        returns_complete,
        postings_complete,
        ambiguous_cancelled_units,
    ):
        if not postings_complete:
            return "FBO postings выборка неполная; метрики нельзя считать окончательными."
        if not returns_available:
            return (
                "Returns API недоступен: cancelled FBO postings остаются "
                "неоднозначными и не считаются невыкупами."
            )
        if not returns_complete:
            return "Returns API выборка неполная; невыкупы и возвраты оставлены неизвестными."
        if ambiguous_cancelled_units:
            return (
                "Невыкупы и возвраты классифицированы по Returns API; часть "
                "cancelled postings пока не сопоставлена с причиной."
            )
        return (
            "Невыкупы, возвраты и прочие отмены классифицированы по "
            "причинам Ozon Returns API."
        )
