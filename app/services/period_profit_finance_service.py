from decimal import Decimal

from api.period_profit_ozon_client import PeriodProfitOzonClient
from api.period_profit_runtime_ozon_client import PeriodProfitRuntimeOzonClient
from services.finance_service import FinanceService


class PeriodProfitFinanceService(FinanceService):
    """FinanceService adapter that preserves Period Profit completeness metadata."""

    _REVENUE_TYPE_LABELS = {"выручка", "revenue"}

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

    def _process_posting(self, accrual, sku, result):
        """Count explicit Ozon revenue rows as sold units even at zero sale_amount.

        Money remains signed and authoritative from sale_amount.  Unit identity is a
        different fact: Ozon's accrual type explicitly marks the revenue operation.
        This matters for fully discounted/otherwise zero-money sales, which are still
        one sold unit in the official accrual report and therefore still consume COGS.
        Returns and ancillary POSTING rows are not promoted to sales.
        """
        super()._process_posting(accrual, sku, result)

        if not self._is_explicit_revenue_accrual(accrual):
            return

        posting = accrual.get("posting") or {}
        target_sku = str(sku) if sku is not None else None

        for product in posting.get("products", []):
            product_sku = str(product.get("sku"))
            if target_sku is not None and product_sku != target_sku:
                continue

            commission = product.get("commission") or {}
            sale_amount = self.to_decimal(
                (commission.get("sale_amount") or {}).get("amount")
            )
            if sale_amount <= Decimal("0"):
                result["sales_count"] += 1

    def _is_explicit_revenue_accrual(self, accrual):
        try:
            type_id = int(accrual.get("type_id"))
        except (TypeError, ValueError):
            return False

        type_info = self.accrual_types.get(type_id)
        if not isinstance(type_info, dict):
            return False

        labels = (type_info.get("description"), type_info.get("name"))
        return any(
            str(label or "").strip().casefold() in self._REVENUE_TYPE_LABELS
            for label in labels
        )

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
