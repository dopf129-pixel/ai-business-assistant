import os
import sys
import unittest


APP_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if APP_ROOT not in sys.path:
    sys.path.insert(0, APP_ROOT)

from services.period_profit_sale_quantity_summary_service import (  # noqa: E402
    PeriodProfitSaleQuantitySummaryService,
)


class FakeFinance:
    def __init__(self):
        self.by_day = {
            "2026-08-06": {
                "error": False,
                "complete": True,
                "records": [{
                    "posting_number": "0226093297-0256-3",
                    "sku": "3921245627",
                    "accrual_date": "2026-08-06",
                    "source": "OZON_FINANCE_ACCRUAL_BY_DAY",
                }],
            },
            "2026-08-09": {
                "error": False,
                "complete": True,
                "records": [{
                    "posting_number": "0226093297-0256-3",
                    "sku": "3921245627",
                    "accrual_date": "2026-08-09",
                    "source": "OZON_FINANCE_ACCRUAL_BY_DAY",
                }],
            },
        }

    def get_daily_sale_posting_evidence(self, day):
        return self.by_day.get(
            day,
            {"error": False, "complete": True, "records": []},
        )


class FakeOzon:
    def get_realization_posting(self, year, month):
        if (year, month) == (2026, 8):
            return {
                "rows": [{
                    "order": {"posting_number": "0226093297-0256-3"},
                    "item": {"sku": "3921245627"},
                    "delivery_commission": {"quantity": 1},
                }]
            }
        return {"rows": []}

    def get_fbo_postings(self, *args, **kwargs):
        return {"result": [], "has_next": False}

    def get_fbo_posting(self, posting_number):
        return {"error": True}

    def get_fbs_posting(self, posting_number):
        return {"error": True}


def result_fixture():
    return {
        "error": False,
        "status": "PERIOD_PROFIT_SUMMARY_READY",
        "date_from": "2026-08-06",
        "date_to": "2026-08-09",
        "product_count": 1,
        "products": [{
            "sku": "3921245627",
            "offer_id": "hook-2",
            "cost_per_unit": 21.0,
            "units_sold": 2,
            "revenue": 90.0,
            "net_accrual": 50.0,
            "commission": 0.0,
            "logistics": 0.0,
            "acquiring": 0.0,
            "other_fees": 0.0,
            "product_cost": 42.0,
            "tax": 0.0,
            "profit": 8.0,
            "margin_percent": 0.0,
            "fee_breakdown": {},
        }],
        "units_sold": 2,
        "revenue": 90.0,
        "net_accrual": 50.0,
        "commission": 0.0,
        "logistics": 0.0,
        "acquiring": 0.0,
        "other_fees": 0.0,
        "product_cost": 42.0,
        "tax": 0.0,
        "profit": 8.0,
        "margin_percent": 0.0,
        "fee_breakdown": {},
    }


class PeriodProfitReaccruedSaleQuantityTests(unittest.TestCase):
    def test_reaccrued_positive_event_counts_one_physical_posting_quantity(self):
        service = PeriodProfitSaleQuantitySummaryService.__new__(
            PeriodProfitSaleQuantitySummaryService
        )
        service.finance_service = FakeFinance()
        service.sale_quantity_ozon_client = FakeOzon()
        service._realization_quantity_cache = {}
        service._posting_quantity_cache = {}
        service._fbo_list_quantity_cache = {}

        result = service._reconcile_sale_quantities(
            result_fixture(),
            "2026-08-06",
            "2026-08-09",
        )

        self.assertFalse(result["error"])
        self.assertEqual(result["units_sold"], 1)
        self.assertEqual(result["product_cost"], 21.0)
        self.assertEqual(result["profit"], 29.0)
        self.assertEqual(result["sale_quantity_record_count"], 1)
        self.assertEqual(result["sale_quantity_positive_event_count"], 2)
        self.assertEqual(result["sale_quantity_reaccrued_event_count"], 1)
        self.assertTrue(result["read_only"] if "read_only" in result else True)


if __name__ == "__main__":
    unittest.main()
