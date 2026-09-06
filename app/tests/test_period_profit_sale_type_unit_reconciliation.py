import os
import sys
import unittest


APP_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if APP_ROOT not in sys.path:
    sys.path.insert(0, APP_ROOT)

from services.period_profit_finance_service import PeriodProfitFinanceService  # noqa: E402


def money(amount):
    return {"amount": str(amount), "currency": "RUB"}


def posting(type_id, sale_amount, sku="SKU-1"):
    return {
        "type_id": type_id,
        "accrued_category": "POSTING",
        "total_amount": money(sale_amount),
        "posting": {
            "products": [{
                "sku": sku,
                "commission": {
                    "sale_amount": money(sale_amount),
                    "sale_commission": money("0"),
                },
            }]
        },
    }


class PeriodProfitSaleTypeUnitReconciliationTests(unittest.TestCase):
    def _service(self, accruals):
        service = PeriodProfitFinanceService.__new__(PeriodProfitFinanceService)
        service.accrual_types = {
            10: {"name": "Sale", "description": "Выручка"},
            11: {"name": "Return", "description": "Возврат выручки"},
            12: {"name": "Discount", "description": "Баллы за скидки"},
        }
        service._daily_accrual_cache = {}
        service._get_accruals_by_day = lambda _date: {
            "error": False,
            "accruals": accruals,
        }
        return service

    def test_zero_money_explicit_revenue_still_counts_one_sold_unit(self):
        result = self._service([posting(10, "0")]).get_daily_finance(
            "2026-06-01", sku="SKU-1"
        )
        self.assertEqual(result["sales_count"], 1)
        self.assertEqual(result["gross_sales"], 0.0)

    def test_positive_revenue_is_not_double_counted(self):
        result = self._service([posting(10, "21")]).get_daily_finance(
            "2026-06-01", sku="SKU-1"
        )
        self.assertEqual(result["sales_count"], 1)

    def test_return_is_never_promoted_to_standard_sale_unit(self):
        result = self._service([posting(11, "-21")]).get_daily_finance(
            "2026-06-01", sku="SKU-1"
        )
        self.assertEqual(result["sales_count"], 0)

    def test_zero_money_non_revenue_posting_remains_non_sale(self):
        result = self._service([posting(12, "0")]).get_daily_finance(
            "2026-06-01", sku="SKU-1"
        )
        self.assertEqual(result["sales_count"], 0)

    def test_unknown_type_keeps_legacy_positive_money_fallback(self):
        result = self._service([posting(999, "21")]).get_daily_finance(
            "2026-06-01", sku="SKU-1"
        )
        self.assertEqual(result["sales_count"], 1)


if __name__ == "__main__":
    unittest.main()
