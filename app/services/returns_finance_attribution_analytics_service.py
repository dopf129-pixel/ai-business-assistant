class ReturnsFinanceAttributionAnalyticsService:
    """Derive observed finance impact without extrapolating unmatched events."""

    CATEGORY_LABELS = {
        "customer_non_buyout": "Невыкуп",
        "customer_return": "Возврат покупателя",
    }

    def analyze(self, facts):
        source = dict(facts or {})
        if source.get("error"):
            return {
                "error": True,
                "code": (
                    source.get("code")
                    or "RETURNS_FINANCE_FACTS_UNAVAILABLE"
                ),
                "sku": source.get("sku"),
                "message": (
                    source.get("message")
                    or "Финансовые данные возвратов недоступны"
                ),
            }

        categories = {}
        for category, label in self.CATEGORY_LABELS.items():
            item = dict(
                (source.get("categories") or {}).get(category)
                or {}
            )
            categories[category] = self._category(
                item,
                label,
            )

        missing_data = list(source.get("missing_data") or [])
        complete = bool(source.get("complete")) and all(
            item["complete"]
            for item in categories.values()
        )

        return {
            "error": False,
            "sku": source.get("sku"),
            "finance_sku": source.get("finance_sku"),
            "since": source.get("since"),
            "to": source.get("to"),
            "categories": categories,
            "classification_complete": bool(
                source.get("classification_complete")
            ),
            "finance_complete": bool(
                source.get("finance_complete")
            ),
            "complete": complete,
            "missing_data": missing_data,
            "note": self._note(complete, missing_data),
        }

    def _category(self, item, label):
        event_count = self._integer(
            item.get("event_posting_count")
        )
        event_units = self._integer(item.get("event_units"))
        matched_count = self._integer(
            item.get("finance_matched_posting_count")
        )
        observed_count = self._integer(
            item.get("observed_posting_count")
        )
        unmatched = list(
            item.get("finance_unmatched_posting_numbers") or []
        )
        non_attributable = list(
            item.get("non_attributable_posting_numbers") or []
        )
        net_total = self._number(
            item.get("observed_net_amount_total")
        )
        net_average = self._number(
            item.get("observed_net_amount_average")
        )

        coverage = None
        if event_count > 0:
            coverage = round(
                matched_count / event_count * 100,
                2,
            )

        return {
            "label": label,
            "event_posting_count": event_count,
            "event_units": event_units,
            "finance_matched_posting_count": matched_count,
            "finance_unmatched_posting_count": len(unmatched),
            "non_attributable_posting_count": len(
                non_attributable
            ),
            "finance_coverage_percent": coverage,
            "observed_posting_count": observed_count,
            "observed_net_amount_total": net_total,
            "observed_net_amount_average": net_average,
            "observed_cost_total": self._cost(net_total),
            "observed_cost_average": self._cost(net_average),
            "fees": self._fees(item.get("fees")),
            "complete": (
                not unmatched
                and not non_attributable
                and matched_count == event_count
            ),
            "note": self._category_note(
                event_count,
                observed_count,
                unmatched,
                non_attributable,
            ),
        }

    def _fees(self, fees):
        result = {}
        for type_id, item in (fees or {}).items():
            source = dict(item or {})
            total = self._number(source.get("observed_total"))
            average = self._number(
                source.get("observed_average_per_posting")
            )
            result[str(type_id)] = {
                "posting_count": self._integer(
                    source.get("posting_count")
                ),
                "observed_net_amount_total": total,
                "observed_net_amount_average": average,
                "observed_cost_total": self._cost(total),
                "observed_cost_average": self._cost(average),
            }
        return result

    def _cost(self, net_amount):
        if net_amount is None:
            return None
        if net_amount == 0:
            return 0.0
        return round(-net_amount, 2)

    def _integer(self, value):
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    def _number(self, value):
        if value is None:
            return None
        try:
            return round(float(value), 2)
        except (TypeError, ValueError):
            return None

    def _category_note(
        self,
        event_count,
        observed_count,
        unmatched,
        non_attributable,
    ):
        if not event_count:
            return "Подтверждённых событий в периоде нет."
        if unmatched or non_attributable:
            return (
                "Стоимость является наблюдаемой только по "
                f"{observed_count} сопоставленным событиям; "
                "экстраполяция не выполнялась."
            )
        return (
            "Стоимость рассчитана по всем подтверждённым "
            "событиям периода."
        )

    def _note(self, complete, missing_data):
        if complete:
            return (
                "Финансовый эффект рассчитан по всем "
                "сопоставленным событиям."
            )
        if "finance_postings_unmatched" in missing_data:
            return (
                "Показаны только наблюдаемые расходы: часть "
                "posting_number не найдена в финансовых начислениях."
            )
        return (
            "Финансовая атрибуция неполна; неизвестные значения "
            "не заменялись нулями."
        )
