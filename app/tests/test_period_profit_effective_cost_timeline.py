import os
import sqlite3
import sys
import tempfile
import unittest


APP_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if APP_ROOT not in sys.path:
    sys.path.insert(0, APP_ROOT)

from services.period_profit_effective_cost_sale_quantity_summary_service import (  # noqa: E402
    PeriodProfitEffectiveCostSaleQuantitySummaryService,
)
from services.period_profit_effective_cost_service import (  # noqa: E402
    PeriodProfitEffectiveCostService,
)


class TempCostService(PeriodProfitEffectiveCostService):
    def __init__(self, path):
        self.path = path
        super().__init__()

    def get_connection(self):
        return sqlite3.connect(self.path)


class FakeFinance:
    def __init__(self):
        self.by_day = {
            "2026-09-09": {
                "error": False,
                "complete": True,
                "records": [{
                    "posting_number": "before-change",
                    "sku": "sku-1",
                    "accrual_date": "2026-09-09",
                }],
            },
            "2026-09-10": {
                "error": False,
                "complete": True,
                "records": [{
                    "posting_number": "after-change",
                    "sku": "sku-1",
                    "accrual_date": "2026-09-10",
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
        if (year, month) == (2026, 9):
            return {
                "rows": [
                    {
                        "order": {"posting_number": "before-change"},
                        "item": {"sku": "sku-1"},
                        "delivery_commission": {"quantity": 1},
                    },
                    {
                        "order": {"posting_number": "after-change"},
                        "item": {"sku": "sku-1"},
                        "delivery_commission": {"quantity": 1},
                    },
                ]
            }
        return {"rows": []}

    def get_fbo_postings(self, *args, **kwargs):
        return {"result": [], "has_next": False}

    def get_fbo_posting(self, posting_number):
        return {"error": True}

    def get_fbs_posting(self, posting_number):
        return {"error": True}


class FakeVersionedCost:
    def get_effective_cost_evidence(
        self,
        at_date,
        product_id=None,
        sku=None,
        offer_id=None,
    ):
        cost = 21.0 if at_date < "2026-09-10" else 25.0
        effective_from = "2026-05-01" if cost == 21.0 else "2026-09-10"
        return {
            "error": False,
            "effective_cost_confirmed": True,
            "historical_cost_confirmed": True,
            "cost_price": cost,
            "effective_from": effective_from,
            "source": "SELLER_CONFIRMED",
        }


def summary_fixture():
    return {
        "error": False,
        "status": "PERIOD_PROFIT_SUMMARY_READY",
        "products": [{
            "sku": "sku-1",
            "offer_id": "offer-1",
            "cost_per_unit": 99.0,
            "units_sold": 2,
            "revenue": 100.0,
            "net_accrual": 80.0,
            "commission": 0.0,
            "logistics": 0.0,
            "acquiring": 0.0,
            "other_fees": 0.0,
            "product_cost": 198.0,
            "tax": 0.0,
            "profit": -118.0,
            "margin_percent": -118.0,
            "fee_breakdown": {},
        }],
        "units_sold": 2,
        "revenue": 100.0,
        "net_accrual": 80.0,
        "commission": 0.0,
        "logistics": 0.0,
        "acquiring": 0.0,
        "other_fees": 0.0,
        "product_cost": 198.0,
        "tax": 0.0,
        "profit": -118.0,
        "margin_percent": -118.0,
        "fee_breakdown": {},
    }


class PeriodProfitEffectiveCostTimelineTests(unittest.TestCase):
    def test_history_versions_preserve_old_cost_and_apply_future_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = TempCostService(os.path.join(tmp, "costs.db"))
            service.set_cost("p1", "sku-1", "offer-1", 99.0)
            first = service.record_historical_cost(
                "p1", "sku-1", "offer-1", 21.0, "2026-05-01"
            )
            second = service.record_historical_cost(
                "p1", "sku-1", "offer-1", 25.0, "2026-09-10"
            )
            self.assertFalse(first["error"])
            self.assertFalse(second["error"])

            may = service.get_effective_cost_evidence(
                "2026-05-03", product_id="p1", sku="sku-1", offer_id="offer-1"
            )
            september = service.get_effective_cost_evidence(
                "2026-09-11", product_id="p1", sku="sku-1", offer_id="offer-1"
            )

            self.assertEqual(may["cost_price"], 21.0)
            self.assertEqual(may["cost_basis"], "SELLER_CONFIRMED_EFFECTIVE_DATE")
            self.assertEqual(september["cost_price"], 25.0)
            self.assertEqual(september["effective_from"], "2026-09-10")

    def test_history_timeline_fails_closed_before_first_confirmed_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = TempCostService(os.path.join(tmp, "costs.db"))
            service.set_cost("p1", "sku-1", "offer-1", 99.0)
            service.record_historical_cost(
                "p1", "sku-1", "offer-1", 21.0, "2026-05-01"
            )

            evidence = service.get_effective_cost_evidence(
                "2026-04-30", product_id="p1", sku="sku-1", offer_id="offer-1"
            )

            self.assertTrue(evidence["error"])
            self.assertEqual(
                evidence["code"], "PERIOD_PROFIT_COST_HISTORY_NOT_EFFECTIVE"
            )
            self.assertIsNone(evidence["cost_price"])

    def test_no_history_keeps_unique_current_cost_as_legacy_compatibility(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = TempCostService(os.path.join(tmp, "costs.db"))
            service.set_cost("p1", "sku-1", "offer-1", 21.0)

            evidence = service.get_effective_cost_evidence(
                "2026-05-03", product_id="p1", sku="sku-1", offer_id="offer-1"
            )

            self.assertFalse(evidence["error"])
            self.assertEqual(evidence["cost_price"], 21.0)
            self.assertEqual(evidence["cost_basis"], "LEGACY_CURRENT_COST_NO_HISTORY")
            self.assertFalse(evidence["historical_cost_confirmed"])

    def test_quantity_cogs_uses_cost_effective_on_each_sale_accrual_date(self):
        service = PeriodProfitEffectiveCostSaleQuantitySummaryService.__new__(
            PeriodProfitEffectiveCostSaleQuantitySummaryService
        )
        service.finance_service = FakeFinance()
        service.cost_service = FakeVersionedCost()
        service.sale_quantity_ozon_client = FakeOzon()
        service._realization_quantity_cache = {}
        service._posting_quantity_cache = {}
        service._fbo_list_quantity_cache = {}

        result = service._reconcile_sale_quantities(
            summary_fixture(), "2026-09-09", "2026-09-10"
        )

        self.assertFalse(result["error"])
        self.assertEqual(result["units_sold"], 2)
        self.assertEqual(result["product_cost"], 46.0)
        self.assertEqual(result["profit"], 34.0)
        self.assertEqual(result["products"][0]["cost_per_unit"], 23.0)
        self.assertTrue(result["products"][0]["effective_cost_versioned"])
        self.assertEqual(result["historical_cost_bucket_count"], 2)
        self.assertEqual(result["legacy_current_cost_bucket_count"], 0)


if __name__ == "__main__":
    unittest.main()
