class ReturnsBuyoutAnalyticsService:
    """Derive conservative buyout metrics from prepared FBO posting facts.

    The service never guesses customer non-buyouts from ambiguous cancellations.
    It only calculates ratios whose numerator and denominator are known.
    """

    def analyze(self, facts):
        source = dict(facts or {})

        if source.get("error"):
            return {
                "error": True,
                "code": source.get("code") or "RETURNS_BUYOUT_FACTS_UNAVAILABLE",
                "sku": source.get("sku"),
                "message": source.get("message") or "Данные возвратов и выкупа недоступны",
            }

        delivered = self._number(source.get("delivered_units"))
        cancelled = self._number(source.get("cancelled_units"))
        ambiguous_cancelled = self._number(source.get("ambiguous_cancelled_units"))
        customer_non_buyout = self._number(source.get("customer_non_buyout_units"))
        customer_returns = self._number(source.get("customer_return_units"))

        missing_data = []
        if customer_non_buyout is None:
            missing_data.append("customer_non_buyout_units")
        if customer_returns is None:
            missing_data.append("customer_return_units")

        buyout_rate = None
        buyout_sample_size = None
        if delivered is not None and customer_non_buyout is not None:
            sample = delivered + customer_non_buyout
            buyout_sample_size = sample
            if sample > 0:
                buyout_rate = round(delivered / sample * 100, 2)

        return {
            "error": False,
            "sku": source.get("sku"),
            "since": source.get("since"),
            "to": source.get("to"),
            "delivered_units": delivered,
            "cancelled_units": cancelled,
            "ambiguous_cancelled_units": ambiguous_cancelled,
            "customer_non_buyout_units": customer_non_buyout,
            "customer_return_units": customer_returns,
            "buyout_rate": buyout_rate,
            "buyout_sample_size": buyout_sample_size,
            "missing_data": missing_data,
            "complete": not missing_data,
            "note": self._note(missing_data, ambiguous_cancelled),
        }

    def _number(self, value):
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _note(self, missing_data, ambiguous_cancelled):
        if "customer_non_buyout_units" in missing_data:
            if ambiguous_cancelled:
                return (
                    "Процент выкупа не рассчитан: отменённые FBO postings "
                    "пока нельзя достоверно считать невыкупами покупателя."
                )
            return "Процент выкупа не рассчитан: нет достоверных данных о невыкупах."
        if "customer_return_units" in missing_data:
            return "Процент выкупа доступен, но данные о возвратах пока неполные."
        return "Метрики выкупа и возвратов рассчитаны по подготовленным фактам."
