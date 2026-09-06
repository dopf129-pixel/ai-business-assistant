import copy

from api.period_profit_ozon_client import PeriodProfitOzonClient


class PeriodProfitRuntimeOzonClient(PeriodProfitOzonClient):
    """Runtime adapter for valid POSTING rows that carry no sale-money evidence."""

    def _normalize_period_profit_canonical_finance(self, endpoint, result):
        if endpoint != self.FINANCE_ACCRUAL_BY_DAY or not isinstance(result, dict):
            return super()._normalize_period_profit_canonical_finance(endpoint, result)

        prepared = copy.deepcopy(result)
        accruals = prepared.get("accruals")
        if not isinstance(accruals, list):
            return super()._normalize_period_profit_canonical_finance(endpoint, prepared)

        for accrual in accruals:
            if not isinstance(accrual, dict) or accrual.get("accrued_category") != "POSTING":
                continue
            posting = accrual.get("posting")
            if not isinstance(posting, dict):
                continue
            products = posting.get("products")
            if not isinstance(products, list):
                continue

            for product in products:
                if not isinstance(product, dict):
                    continue
                commission = product.get("commission")

                # FinanceService and its sale-evidence path historically interpret an
                # absent commission block / wholly absent sale-money fields as a
                # non-sale POSTING row. Preserve that structural distinction instead of
                # turning it into a day-level finance outage. A partially present sale
                # tuple is still ambiguous and remains fail-closed in the parent client.
                if commission is None:
                    commission = {}
                    product["commission"] = commission
                elif not isinstance(commission, dict):
                    continue

                if self._valid_money(commission.get("sale_amount")):
                    continue

                component_values = [
                    commission.get(field)
                    for field in self.SALE_AMOUNT_COMPONENT_FIELDS
                ]
                if any(value is not None for value in component_values):
                    continue

                commission["sale_amount"] = {
                    "amount": "0",
                    "currency": "RUB",
                }

        return super()._normalize_period_profit_canonical_finance(endpoint, prepared)
