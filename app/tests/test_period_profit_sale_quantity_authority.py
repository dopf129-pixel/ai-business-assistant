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
    def __init__(self, evidence_by_day):
        self.evidence_by_day = evidence_by_day

    def get_daily_sale_posting_evidence(self, day):
        return self.evidence_by_day.get(
            day,
            {
                "error": False,
                "complete": True,
                "records": [],
            },
        )


class FakeOzon:
    def __init__(self, realization=None, fbo=None, fbs=None):
        self.realization = realization or {}
        self.fbo = fbo or {}
        self.fbs = fbs or {}
        self.realization_calls = []
        self.fbo_calls = []
        self.fbs_calls = []

    def get_realization_posting(self, year, month):
        self.realization_calls.append((year, month))
        return self.realization.get((year, month), {"rows": []})

    def get_fbo_posting(self, posting_number):
        self.fbo_calls.append(posting_number)
        return self.fbo.get(posting_number, {"error": True})

    def get_fbs_posting(self, posting_number):
        self.fbs_calls.append(posting_number)
        return self.fbs.get(posting_number, {"error": True})


def sale_record(posting_number, sku):
    return {
        "posting_number": posting_number,
        "sku": sku,
        "accrual_date": "2026-05-01",
        "source": "OZON_FINANCE_ACCRUAL_BY_DAY",
    }


def realization_row(posting_number, sku, quantity):
    return {
        "order": {"posting_number": posting_number},
        "item": {"sku": sku},
        "delivery_commission": {"quantity": quantity},
    }


def result_fixture(units=2, cost=21.0):
    return {
        "error": False,
        "status": "PERIOD_PROFIT_SUMMARY_READY",
        "date_from": "2026-05-01",
        "date_to": "2026-05-01",
        "product_count": 1,
        "products": [{
            "sku": "3921245627",
            "offer_id": "hook-2",
            "cost_per_unit": cost,
            "units_sold": units,
            "revenue": 200.0,
            "net_accrual": 100.0,
            "commission": 0.0,
            "logistics": 0.0,
            "acquiring": 0.0,
            "other_fees": 0.0,
            "product_cost": units * cost,
            "tax": 0.0,
            "profit": 100.0 - units * cost,
            "margin_percent": 0.0,
            "fee_breakdown": {},
        }],
        "units_sold": units,
        "revenue": 200.0,
        "net_accrual": 100.0,
        "commission": 0.0,
        "logistics": 0.0,
        "acquiring": 0.0,
        "other_fees": 0.0,
        "product_cost": units * cost,
        "tax": 0.0,
        "profit": 100.0 - units * cost,
        "margin_percent": 0.0,
        "fee_breakdown": {},
    }


class PeriodProfitSaleQuantityAuthorityTests(unittest.TestCase):
    def service(self, finance, ozon):
        service = PeriodProfitSaleQuantitySummaryService.__new__(
            PeriodProfitSaleQuantitySummaryService
        )
        service.finance_service = finance
        service.sale_quantity_ozon_client = ozon
        service._realization_quantity_cache = {}
        service._posting_quantity_cache = {}
        return service

    def test_multi_unit_realization_row_reconciles_cogs(self):
        finance = FakeFinance({
            "2026-05-01": {
                "error": False,
                "complete": True,
                "records": [
                    sale_record("0131043464-0056-7", "3921245627"),
                    sale_record("single-1", "3921245627"),
                ],
            }
        })
        ozon = FakeOzon(realization={
            (2026, 5): {
                "rows": [
                    realization_row("0131043464-0056-7", "3921245627", 4),
                    realization_row("single-1", "3921245627", 1),
                ]
            }
        })
        service = self.service(finance, ozon)

        result = service._reconcile_sale_quantities(
            result_fixture(units=2),
            "2026-05-01",
            "2026-05-01",
        )

        self.assertFalse(result["error"])
        self.assertEqual(result["units_sold"], 5)
        self.assertEqual(result["product_cost"], 105.0)
        self.assertEqual(result["profit"], -5.0)
        self.assertEqual(result["products"][0]["units_sold"], 5)
        self.assertTrue(result["sale_quantity_reconciled"])

    def test_missing_realization_row_uses_exact_fbo_posting_detail(self):
        finance = FakeFinance({
            "2026-05-01": {
                "error": False,
                "complete": True,
                "records": [sale_record("p-1", "3921245627")],
            }
        })
        ozon = FakeOzon(fbo={
            "p-1": {
                "result": {
                    "posting_number": "p-1",
                    "products": [{
                        "sku": "3921245627",
                        "quantity": 3,
                    }],
                }
            }
        })
        service = self.service(finance, ozon)

        result = service._reconcile_sale_quantities(
            result_fixture(units=1),
            "2026-05-01",
            "2026-05-01",
        )

        self.assertEqual(result["units_sold"], 3)
        self.assertEqual(result["product_cost"], 63.0)
        self.assertEqual(ozon.fbo_calls, ["p-1"])

    def test_unresolved_quantity_fails_closed(self):
        finance = FakeFinance({
            "2026-05-01": {
                "error": False,
                "complete": True,
                "records": [sale_record("missing", "3921245627")],
            }
        })
        service = self.service(finance, FakeOzon())

        result = service._reconcile_sale_quantities(
            result_fixture(units=1),
            "2026-05-01",
            "2026-05-01",
        )

        self.assertTrue(result["error"])
        self.assertEqual(
            result["code"],
            "PERIOD_PROFIT_SALE_QUANTITY_EVIDENCE_UNAVAILABLE",
        )
        self.assertTrue(result["read_only"])
        self.assertFalse(result["executed"])

    def test_negative_return_quantity_is_not_used_for_standard_sales(self):
        parsed = PeriodProfitSaleQuantitySummaryService._parse_realization({
            "rows": [{
                "order": {"posting_number": "p-1"},
                "item": {"sku": "3921245627"},
                "delivery_commission": {"quantity": 1},
                "return_commission": {"quantity": 7},
            }]
        })

        self.assertEqual(parsed[("p-1", "3921245627")], 1)

    def test_duplicate_positive_sale_evidence_fails_closed(self):
        record = sale_record("p-1", "3921245627")
        finance = FakeFinance({
            "2026-05-01": {
                "error": False,
                "complete": True,
                "records": [record, dict(record)],
            }
        })
        service = self.service(finance, FakeOzon())

        result = service._reconcile_sale_quantities(
            result_fixture(units=2),
            "2026-05-01",
            "2026-05-01",
        )

        self.assertEqual(
            result["code"],
            "PERIOD_PROFIT_SALE_QUANTITY_DUPLICATE_SALE_EVIDENCE",
        )


if __name__ == "__main__":
    unittest.main()
