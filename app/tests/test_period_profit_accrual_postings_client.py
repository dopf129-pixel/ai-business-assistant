import unittest

from api.base_ozon_client import OzonClient as BaseOzonClient
from api.period_profit_ozon_client import PeriodProfitOzonClient
from api.period_profit_runtime_ozon_client import PeriodProfitRuntimeOzonClient
from services.period_profit_finance_service import PeriodProfitFinanceService


class RecordingOzonClient(PeriodProfitOzonClient):
    def __init__(self):
        self.calls = []

    def _post(self, endpoint, data, timeout=20, max_attempts=3):
        self.calls.append((endpoint, data, timeout, max_attempts))
        return {
            "posting_accruals": [
                {
                    "posting_number": "12345-1-1",
                    "accruals": [
                        {"sku": 3398133813, "quantity": 3},
                    ],
                }
            ]
        }


class RecordingRuntimeOzonClient(PeriodProfitRuntimeOzonClient):
    def __init__(self):
        self.calls = []

    def _post(self, endpoint, data, timeout=20, max_attempts=3):
        self.calls.append((endpoint, data, timeout, max_attempts))
        return {
            "posting_accruals": [
                {
                    "posting_number": "fixture-posting-1",
                    "accruals": [
                        {
                            "type_id": 69,
                            "accrued": {"amount": "-16.53", "currency": "RUB"},
                        }
                    ],
                }
            ]
        }


class TestPeriodProfitAccrualPostingsClient(unittest.TestCase):
    def test_base_client_exposes_read_only_accrual_postings_method(self):
        self.assertTrue(callable(getattr(BaseOzonClient, "get_accruals_by_postings", None)))

    def test_period_profit_finance_uses_real_client_method_for_quantity(self):
        ozon = RecordingOzonClient()
        service = PeriodProfitFinanceService()
        service.ozon = ozon

        result = service.get_sale_posting_quantity_evidence(["12345-1-1"])

        self.assertFalse(result["error"])
        self.assertTrue(result["complete"])
        self.assertEqual(result["records"], [
            {
                "posting_number": "12345-1-1",
                "sku": "3398133813",
                "quantity": 3,
                "source": "OZON_FINANCE_ACCRUAL_POSTINGS",
            }
        ])
        self.assertEqual(ozon.calls, [
            (
                "/v1/finance/accrual/postings",
                {"posting_numbers": ["12345-1-1"]},
                30,
                3,
            )
        ])

    def test_runtime_client_requests_current_per_posting_accrual_endpoint(self):
        ozon = RecordingRuntimeOzonClient()

        result = ozon.get_accruals_by_postings(
            ["fixture-posting-1", "fixture-posting-1"]
        )

        self.assertFalse(result["error"])
        self.assertEqual(result["posting_accruals"][0]["accruals"][0]["accrued"]["amount"], "-16.53")
        self.assertEqual(ozon.calls, [
            (
                "/v1/finance/accrual/postings",
                {"posting_numbers": ["fixture-posting-1"]},
                30,
                3,
            )
        ])


if __name__ == "__main__":
    unittest.main()
