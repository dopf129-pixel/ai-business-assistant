import os
import sys
import unittest


APP_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if APP_ROOT not in sys.path:
    sys.path.insert(0, APP_ROOT)

from services.period_profit_finance_service import PeriodProfitFinanceService  # noqa: E402


class _Ozon:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def get_accruals_by_postings(self, posting_numbers):
        self.calls.append(list(posting_numbers))
        return self.response


class PeriodProfitFinancePostingQuantityAuthorityTests(unittest.TestCase):
    def _service(self, response):
        service = PeriodProfitFinanceService.__new__(PeriodProfitFinanceService)
        service.ozon = _Ozon(response)
        return service

    def test_repeated_accrual_types_do_not_multiply_physical_quantity(self):
        service = self._service({
            "error": False,
            "posting_accruals": [
                {
                    "posting_number": "p-1",
                    "accruals": [
                        {"sku": 3398133813, "type_id": 1, "quantity": 3},
                        {"sku": 3398133813, "type_id": 69, "quantity": 3},
                        {"sku": 3398133813, "type_id": 98, "quantity": 3},
                    ],
                }
            ],
        })

        result = service.get_sale_posting_quantity_evidence(["p-1", "p-1"])

        self.assertFalse(result["error"])
        self.assertTrue(result["complete"])
        self.assertEqual(result["record_count"], 1)
        self.assertEqual(
            result["records"],
            [{
                "posting_number": "p-1",
                "sku": "3398133813",
                "quantity": 3,
                "source": "OZON_FINANCE_ACCRUAL_POSTINGS",
            }],
        )
        self.assertEqual(service.ozon.calls, [["p-1"]])
        self.assertTrue(result["read_only"])
        self.assertFalse(result["executed"])

    def test_conflicting_quantities_fail_closed(self):
        service = self._service({
            "error": False,
            "posting_accruals": [
                {
                    "posting_number": "p-1",
                    "accruals": [
                        {"sku": 3398133813, "type_id": 1, "quantity": 2},
                        {"sku": 3398133813, "type_id": 69, "quantity": 3},
                    ],
                }
            ],
        })

        result = service.get_sale_posting_quantity_evidence(["p-1"])

        self.assertTrue(result["error"])
        self.assertEqual(
            result["code"],
            "FINANCE_SALE_POSTING_QUANTITY_EVIDENCE_CONFLICT",
        )
        self.assertTrue(result["read_only"])
        self.assertFalse(result["executed"])


if __name__ == "__main__":
    unittest.main()
