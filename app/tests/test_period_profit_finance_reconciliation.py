import os
import sys
import unittest


APP_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if APP_ROOT not in sys.path:
    sys.path.insert(0, APP_ROOT)

from api.period_profit_ozon_client import PeriodProfitOzonClient  # noqa: E402
from services.finance_service import FinanceService  # noqa: E402


def money(amount, currency=None):
    result = {"amount": str(amount)}
    if currency is not None:
        result["currency"] = currency
    return result


def posting_accrual(*, total_amount, sale_amount, sku="SKU-1"):
    return {
        "accrued_category": "POSTING",
        "total_amount": money(total_amount),
        "posting": {
            "products": [
                {
                    "sku": sku,
                    "commission": {
                        "sale_amount": money(sale_amount),
                        "sale_commission": money("0"),
                    },
                }
            ]
        },
    }


class FinanceServiceSaleUnitReconciliationTests(unittest.TestCase):
    def _service_with_accruals(self, accruals):
        service = FinanceService.__new__(FinanceService)
        service.accrual_types = {1: {"name": "fixture", "description": "fixture"}}
        service._daily_accrual_cache = {}
        service._get_accruals_by_day = lambda _date: {
            "error": False,
            "accruals": accruals,
        }
        return service

    def test_real_operation_classes_count_only_positive_sale_amount(self):
        accruals = [
            posting_accrual(total_amount="50", sale_amount="100"),
            posting_accrual(total_amount="10", sale_amount="0"),
            posting_accrual(total_amount="2", sale_amount="0"),
            posting_accrual(total_amount="-20", sale_amount="-30"),
        ]
        service = self._service_with_accruals(accruals)

        result = service.get_daily_finance("2026-08-09", sku="SKU-1")

        self.assertFalse(result["error"])
        self.assertEqual(result["operations"], 4)
        self.assertEqual(result["sales_count"], 1)
        self.assertEqual(result["gross_sales"], 70.0)
        self.assertEqual(result["net_accrual"], 42.0)

    def test_zero_sale_posting_does_not_create_cogs_unit(self):
        service = self._service_with_accruals(
            [posting_accrual(total_amount="15", sale_amount="0")]
        )

        result = service.get_daily_finance("2026-08-09", sku="SKU-1")

        self.assertEqual(result["sales_count"], 0)
        self.assertEqual(result["gross_sales"], 0.0)
        self.assertEqual(result["net_accrual"], 15.0)

    def test_negative_return_does_not_create_standard_sale_cogs_unit(self):
        service = self._service_with_accruals(
            [posting_accrual(total_amount="-20", sale_amount="-30")]
        )

        result = service.get_daily_finance("2026-08-09", sku="SKU-1")

        self.assertEqual(result["sales_count"], 0)
        self.assertEqual(result["gross_sales"], -30.0)
        self.assertEqual(result["net_accrual"], -20.0)


class PeriodProfitOzonRevenueReconciliationTests(unittest.TestCase):
    def _payload(self):
        return {
            "accruals": [
                {
                    "accrued_category": "POSTING",
                    "total_amount": money("42.15"),
                    "posting": {
                        "products": [
                            {
                                "sku": "SKU-1",
                                "commission": {
                                    "sale_amount": money("100.00"),
                                    "seller_price": money("99.00"),
                                    "sale_price": money("80.00"),
                                    "bonus": money("15.00"),
                                    "coinvestment": money("5.00"),
                                    "sale_commission": money("-12.00"),
                                },
                            }
                        ]
                    },
                }
            ]
        }

    def test_normalization_preserves_official_sale_amount(self):
        client = PeriodProfitOzonClient.__new__(PeriodProfitOzonClient)

        normalized = client._normalize_period_profit_finance(
            client.FINANCE_ACCRUAL_BY_DAY,
            self._payload(),
        )

        commission = normalized["accruals"][0]["posting"]["products"][0][
            "commission"
        ]
        self.assertEqual(commission["sale_amount"]["amount"], "100.00")
        self.assertEqual(commission["seller_price"]["amount"], "99.00")
        diagnostics = normalized["_period_profit_revenue_diagnostics"]["fields"]
        self.assertEqual(diagnostics["sale_amount"]["amount"], "100.00")
        self.assertEqual(diagnostics["seller_price"]["amount"], "99.00")

    def test_missing_sale_amount_recovers_from_explicit_ozon_components(self):
        client = PeriodProfitOzonClient.__new__(PeriodProfitOzonClient)
        payload = self._payload()
        commission = payload["accruals"][0]["posting"]["products"][0]["commission"]
        del commission["sale_amount"]

        normalized = client._normalize_period_profit_finance(
            client.FINANCE_ACCRUAL_BY_DAY,
            payload,
        )

        recovered = normalized["accruals"][0]["posting"]["products"][0][
            "commission"
        ]["sale_amount"]
        self.assertEqual(recovered["amount"], "100.00")
        diagnostics = normalized["_period_profit_revenue_diagnostics"]["fields"]
        self.assertFalse(diagnostics["sale_amount"]["complete"])
        self.assertEqual(diagnostics["sale_amount"]["missing_records"], 1)

    def test_real_ozon_posting_components_recover_exact_sale_amount(self):
        client = PeriodProfitOzonClient.__new__(PeriodProfitOzonClient)
        payload = self._payload()
        commission = payload["accruals"][0]["posting"]["products"][0]["commission"]
        commission["seller_price"] = money("90", "RUB")
        commission["sale_price"] = money("67.62", "RUB")
        commission["bonus"] = money("22.38", "RUB")
        commission["coinvestment"] = money("0", "RUB")
        commission["sale_commission"] = money("-12.6", "RUB")
        del commission["sale_amount"]

        normalized = client._normalize_period_profit_finance(
            client.FINANCE_ACCRUAL_BY_DAY,
            payload,
        )

        recovered = normalized["accruals"][0]["posting"]["products"][0][
            "commission"
        ]["sale_amount"]
        self.assertEqual(recovered, {"amount": "90.00", "currency": "RUB"})

    def test_missing_sale_amount_still_fails_when_component_is_unknown(self):
        client = PeriodProfitOzonClient.__new__(PeriodProfitOzonClient)
        payload = self._payload()
        commission = payload["accruals"][0]["posting"]["products"][0]["commission"]
        del commission["sale_amount"]
        del commission["bonus"]

        normalized = client._normalize_period_profit_finance(
            client.FINANCE_ACCRUAL_BY_DAY,
            payload,
        )

        self.assertTrue(normalized["error"])
        self.assertEqual(
            normalized["code"],
            "FINANCE_PERIOD_PROFIT_MONEY_UNAVAILABLE",
        )
        self.assertFalse(normalized["complete"])


if __name__ == "__main__":
    unittest.main()
