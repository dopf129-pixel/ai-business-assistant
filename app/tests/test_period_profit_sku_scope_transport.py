import os
import sys
import unittest


APP_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if APP_ROOT not in sys.path:
    sys.path.insert(0, APP_ROOT)

from services.period_profit_finance_sku_scope_service import (  # noqa: E402
    PeriodProfitFinanceSkuScopeService,
)


class DummySummary:
    cost_service = None
    tax_rate = 0.0


class StrictFinanceThatWouldFail:
    def _get_accruals_by_day(self, _date):
        return {"error": True, "code": "FINANCE_PERIOD_PROFIT_MONEY_UNAVAILABLE"}


class RawSkuClient:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def get_accruals_by_day(self, accrual_date):
        self.calls.append(accrual_date)
        return self.response


class PeriodProfitSkuScopeTransportTests(unittest.TestCase):
    def test_sku_discovery_uses_raw_read_only_client_not_strict_money_wrapper(self):
        raw = RawSkuClient(
            {
                "error": False,
                "accruals": [
                    {
                        "accrued_category": "POSTING",
                        "posting": {
                            "products": [
                                {"sku": 3921245627, "commission": {}},
                                {"sku": "SKU-2"},
                            ]
                        },
                    },
                    {
                        "accrued_category": "ITEM",
                        "posting": None,
                    },
                ],
            }
        )
        service = PeriodProfitFinanceSkuScopeService(
            DummySummary(),
            StrictFinanceThatWouldFail(),
            sku_ozon_client=raw,
        )

        result = service._load_period_skus("2026-08-09", "2026-08-09")

        self.assertFalse(result["error"])
        self.assertEqual(result["skus"], ["3921245627", "SKU-2"])
        self.assertEqual(raw.calls, ["2026-08-09"])

    def test_raw_transport_error_still_fails_closed(self):
        raw = RawSkuClient({"error": True, "status_code": 503})
        service = PeriodProfitFinanceSkuScopeService(
            DummySummary(),
            StrictFinanceThatWouldFail(),
            sku_ozon_client=raw,
        )

        result = service._load_period_skus("2026-08-09", "2026-08-09")

        self.assertTrue(result["error"])
        self.assertEqual(result["code"], "PERIOD_PROFIT_FINANCE_SKU_SCOPE_UNAVAILABLE")
        self.assertTrue(result["read_only"])
        self.assertFalse(result["executed"])


if __name__ == "__main__":
    unittest.main()
