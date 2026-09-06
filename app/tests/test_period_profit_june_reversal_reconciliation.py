import os
import sys
import unittest


APP_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if APP_ROOT not in sys.path:
    sys.path.insert(0, APP_ROOT)

from services.period_profit_finance_service import PeriodProfitFinanceService  # noqa: E402


def money(amount):
    return {"amount": str(amount), "currency": "RUB"}


def posting(sale_amount, total_amount=None, sku="3921245627", unit_number="49885639-0254-1"):
    amount = str(sale_amount)
    return {
        "accrued_category": "POSTING",
        "unit_number": unit_number,
        "total_amount": money(total_amount if total_amount is not None else amount),
        "posting": {
            "products": [{
                "sku": sku,
                "commission": {
                    "sale_amount": money(amount),
                    "sale_commission": money("0"),
                },
            }]
        },
    }


class PeriodProfitJuneReversalReconciliationTests(unittest.TestCase):
    def _service(self, accruals):
        service = PeriodProfitFinanceService.__new__(PeriodProfitFinanceService)
        service.accrual_types = {1: {"name": "fixture", "description": "fixture"}}
        service._daily_accrual_cache = {}
        service._get_accruals_by_day = lambda _date: {
            "error": False,
            "accruals": accruals,
        }
        return service

    def test_sale_and_negative_reversal_consume_cogs_once(self):
        service = self._service([
            posting("100", total_amount="67.62"),
            posting("-100", total_amount="-67.62"),
        ])

        result = service.get_daily_finance("2026-06-19", sku="3921245627")

        self.assertFalse(result["error"])
        self.assertEqual(result["sales_count"], 1)
        self.assertEqual(result["gross_sales"], 0.0)
        self.assertEqual(result["net_accrual"], 0.0)

    def test_negative_sale_reversal_never_creates_standard_sale_cogs(self):
        service = self._service([
            posting("-100", total_amount="-67.62"),
        ])

        result = service.get_daily_finance("2026-06-19", sku="3921245627")

        self.assertEqual(result["sales_count"], 0)
        self.assertEqual(result["gross_sales"], -100.0)
        self.assertEqual(result["net_accrual"], -67.62)

    def test_positive_sale_still_creates_exactly_one_standard_sale_cogs(self):
        service = self._service([
            posting("100", total_amount="67.62"),
        ])

        result = service.get_daily_finance("2026-06-19", sku="3921245627")

        self.assertEqual(result["sales_count"], 1)
        self.assertEqual(result["gross_sales"], 100.0)


if __name__ == "__main__":
    unittest.main()
