from api.period_profit_ozon_client import PeriodProfitOzonClient
from api.period_profit_runtime_ozon_client import PeriodProfitRuntimeOzonClient
from services.finance_service import FinanceService


class PeriodProfitFinanceService(FinanceService):
    """FinanceService adapter that preserves Period Profit completeness metadata."""

    @property
    def ozon(self):
        return self._ozon

    @ozon.setter
    def ozon(self, value):
        # The factory and older callers still assign PeriodProfitOzonClient directly.
        # Route only that production assignment through the runtime structural adapter;
        # test doubles and unrelated clients remain untouched.
        if type(value) is PeriodProfitOzonClient:
            value = PeriodProfitRuntimeOzonClient()
        self._ozon = value

    def get_daily_finance(self, accrual_date, sku=None):
        result = super().get_daily_finance(accrual_date, sku=sku)
        if not isinstance(result, dict) or result.get("error") is True:
            return result

        cached = self._daily_accrual_cache.get(str(accrual_date))
        completeness = (
            cached.get("_period_profit_finance_completeness")
            if isinstance(cached, dict)
            else None
        )

        enriched = dict(result)
        if isinstance(completeness, dict):
            enriched["fee_components_included"] = (
                completeness.get("fee_components_included") is not False
            )
            enriched["ancillary_incomplete_count"] = int(
                completeness.get("ancillary_incomplete_count") or 0
            )
        else:
            enriched["fee_components_included"] = True
            enriched["ancillary_incomplete_count"] = 0
        return enriched
