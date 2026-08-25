from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation


class ReturnsFinanceAttributionFactsSource:
    """Match confirmed return events to Ozon finance accruals by posting number."""

    CATEGORIES = (
        "customer_non_buyout",
        "customer_return",
    )

    def __init__(self, ozon_client, returns_buyout_facts_source):
        self.ozon_client = ozon_client
        self.returns_buyout_facts_source = returns_buyout_facts_source

    def get(self, sku, finance_sku, since, to):
        target_sku = str(sku or "").strip()
        target_finance_sku = str(finance_sku or "").strip()
        if not target_sku or not target_finance_sku:
            return {
                "error": True,
                "code": "SKU_REQUIRED",
                "message": "SKU не указан",
            }

        period = self._period(since, to)
        if period is None:
            return {
                "error": True,
                "code": "PERIOD_INVALID",
                "sku": target_sku,
                "message": "Период анализа задан неверно",
            }

        returns_facts = self.returns_buyout_facts_source.get(
            sku=target_sku,
            since=since,
            to=to,
        )
        if returns_facts.get("error"):
            return dict(returns_facts)

        events = self._eligible_events(returns_facts)
        target_numbers = set(events)
        rows_by_posting = {
            posting_number: []
            for posting_number in target_numbers
        }
        finance_errors = []

        current_date, final_date = period
        while current_date <= final_date:
            response = self.ozon_client.get_accruals_by_day(
                current_date.isoformat()
            )
            if not response or response.get("error"):
                finance_errors.append(current_date.isoformat())
                current_date += timedelta(days=1)
                continue

            for accrual in response.get("accruals") or []:
                posting_number = str(
                    accrual.get("unit_number") or ""
                )
                if posting_number not in target_numbers:
                    continue
                if not self._matches_finance_sku(
                    accrual,
                    target_finance_sku,
                ):
                    continue
                rows_by_posting[posting_number].append(accrual)

            current_date += timedelta(days=1)

        categories = {}
        for category in self.CATEGORIES:
            category_events = {
                number: event
                for number, event in events.items()
                if event["category"] == category
            }
            categories[category] = self._category_facts(
                category_events,
                rows_by_posting,
                target_finance_sku,
            )

        classification_complete = (
            returns_facts.get("postings_complete", False)
            and returns_facts.get("returns_complete", False)
            and not returns_facts.get("ambiguous_cancelled_units")
        )
        finance_complete = not finance_errors and all(
            not item["finance_unmatched_posting_numbers"]
            and not item["non_attributable_posting_numbers"]
            for item in categories.values()
        )

        missing_data = []
        if not classification_complete:
            missing_data.append("returns_classification_incomplete")
        if finance_errors:
            missing_data.append("finance_days_unavailable")
        if any(
            item["finance_unmatched_posting_numbers"]
            for item in categories.values()
        ):
            missing_data.append("finance_postings_unmatched")
        if any(
            item["non_attributable_posting_numbers"]
            for item in categories.values()
        ):
            missing_data.append("multi_product_accruals")

        return {
            "error": False,
            "sku": target_sku,
            "finance_sku": target_finance_sku,
            "since": str(since),
            "to": str(to),
            "categories": categories,
            "classification_complete": classification_complete,
            "finance_complete": finance_complete,
            "complete": classification_complete and finance_complete,
            "missing_data": missing_data,
            "finance_error_dates": finance_errors,
            "note": (
                "Финансовые суммы являются наблюдаемыми и рассчитаны "
                "только по начислениям, сопоставленным по posting_number."
            ),
        }

    def _eligible_events(self, returns_facts):
        cancelled_numbers = {
            str(item.get("posting_number") or "")
            for item in returns_facts.get("postings") or []
            if item.get("status") == "cancelled"
        }
        events = {}

        for event in returns_facts.get("return_events") or []:
            category = event.get("category")
            if category not in self.CATEGORIES:
                continue

            posting_number = str(
                event.get("posting_number") or ""
            )
            if not posting_number:
                continue
            if (
                category == "customer_non_buyout"
                and posting_number not in cancelled_numbers
            ):
                continue

            quantity = self._integer(event.get("quantity"))
            if quantity <= 0:
                continue

            current = events.get(posting_number)
            if current is None:
                events[posting_number] = {
                    "posting_number": posting_number,
                    "category": category,
                    "quantity": quantity,
                }
                continue

            if current["category"] == category:
                current["quantity"] += quantity

        return events

    def _category_facts(
        self,
        events,
        rows_by_posting,
        finance_sku,
    ):
        matched = []
        unmatched = []
        non_attributable = []
        posting_amounts = {}
        posting_fee_amounts = {}
        fee_totals = {}
        fee_postings = {}

        for posting_number, event in events.items():
            rows = rows_by_posting.get(posting_number) or []
            if not rows:
                unmatched.append(posting_number)
                continue

            matched.append(posting_number)
            if not all(
                self._is_attributable(row, finance_sku)
                for row in rows
            ):
                non_attributable.append(posting_number)
                continue

            amount = sum(
                (
                    self._decimal(
                        (row.get("total_amount") or {}).get("amount")
                    )
                    for row in rows
                ),
                Decimal("0"),
            )
            posting_amounts[posting_number] = amount
            posting_fee_amount = Decimal("0")

            for row in rows:
                for fee in self._fees(row, finance_sku):
                    posting_fee_amount += fee["amount"]
                    type_id = fee["type_id"]
                    fee_totals[type_id] = (
                        fee_totals.get(type_id, Decimal("0"))
                        + fee["amount"]
                    )
                    fee_postings.setdefault(type_id, set()).add(
                        posting_number
                    )
            posting_fee_amounts[posting_number] = (
                posting_fee_amount
            )

        observed_count = len(posting_amounts)
        observed_total = (
            sum(posting_amounts.values(), Decimal("0"))
            if posting_amounts
            else None
        )
        observed_average = (
            observed_total / observed_count
            if observed_total is not None and observed_count
            else None
        )
        observed_fee_total = (
            sum(posting_fee_amounts.values(), Decimal("0"))
            if posting_fee_amounts
            else None
        )
        observed_fee_average = (
            observed_fee_total / observed_count
            if observed_fee_total is not None and observed_count
            else None
        )

        return {
            "event_posting_count": len(events),
            "event_units": sum(
                item["quantity"]
                for item in events.values()
            ),
            "finance_matched_posting_count": len(matched),
            "finance_unmatched_posting_numbers": sorted(unmatched),
            "non_attributable_posting_numbers": sorted(
                non_attributable
            ),
            "observed_posting_count": observed_count,
            "observed_net_amount_total": self._money(
                observed_total
            ),
            "observed_net_amount_average": self._money(
                observed_average
            ),
            "observed_fee_amount_total": self._money(
                observed_fee_total
            ),
            "observed_fee_amount_average": self._money(
                observed_fee_average
            ),
            "fees": {
                str(type_id): {
                    "posting_count": len(
                        fee_postings.get(type_id, set())
                    ),
                    "observed_total": self._money(amount),
                    "observed_average_per_posting": self._money(
                        amount / observed_count
                        if observed_count
                        else None
                    ),
                }
                for type_id, amount in sorted(fee_totals.items())
            },
        }

    def _fees(self, accrual, finance_sku):
        result = []
        posting = accrual.get("posting") or {}
        for product in posting.get("products") or []:
            if str(product.get("sku")) != finance_sku:
                continue
            delivery = product.get("delivery") or {}
            for service in delivery.get("services") or []:
                result.append({
                    "type_id": service.get("type_id"),
                    "amount": self._decimal(
                        (service.get("accrued") or {}).get("amount")
                    ),
                })

        item_fees = accrual.get("item_fees") or {}
        for item in item_fees.get("fees") or []:
            if str(item.get("sku")) != finance_sku:
                continue
            for fee in item.get("fees") or []:
                result.append({
                    "type_id": fee.get("type_id"),
                    "amount": self._decimal(
                        (fee.get("accrued") or {}).get("amount")
                    ),
                })
        return result

    def _matches_finance_sku(self, accrual, finance_sku):
        return bool(self._accrual_skus(accrual) & {finance_sku})

    def _is_attributable(self, accrual, finance_sku):
        skus = self._accrual_skus(accrual)
        return bool(skus) and skus == {finance_sku}

    def _accrual_skus(self, accrual):
        result = set()
        posting = accrual.get("posting") or {}
        for product in posting.get("products") or []:
            if product.get("sku") is not None:
                result.add(str(product.get("sku")))

        item_fees = accrual.get("item_fees") or {}
        for item in item_fees.get("fees") or []:
            if item.get("sku") is not None:
                result.add(str(item.get("sku")))
        return result

    def _period(self, since, to):
        start = self._date(since)
        finish = self._date(to)
        if start is None or finish is None or start > finish:
            return None
        return start, finish

    def _date(self, value):
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        try:
            return datetime.fromisoformat(
                str(value).replace("Z", "+00:00")
            ).date()
        except (TypeError, ValueError):
            return None

    def _decimal(self, value):
        try:
            return Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            return Decimal("0")

    def _integer(self, value):
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    def _money(self, value):
        if value is None:
            return None
        return float(value.quantize(Decimal("0.01")))
