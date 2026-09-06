from services.period_profit_summary_service import PeriodProfitSummaryService


class PeriodProfitCriticalFinanceSummaryService(PeriodProfitSummaryService):
    """Keep canonical profit available while exposing ancillary fee incompleteness."""

    def calculate(self, date_from, date_to, products):
        result = super().calculate(date_from, date_to, products)
        if not isinstance(result, dict) or result.get("error") is not False:
            return result

        cache = getattr(self.finance_service, "_daily_accrual_cache", {})
        complete = True
        incomplete_count = 0
        if isinstance(cache, dict):
            for response in cache.values():
                if not isinstance(response, dict):
                    continue
                state = response.get("_period_profit_finance_completeness")
                if not isinstance(state, dict):
                    continue
                if state.get("fee_components_included") is False:
                    complete = False
                    incomplete_count += int(
                        state.get("ancillary_incomplete_count") or 0
                    )

        enriched = dict(result)
        enriched["fee_components_included"] = complete
        enriched["ancillary_finance_incomplete_count"] = incomplete_count
        return enriched
