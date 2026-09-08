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
    def __init__(self, by_day):
        self.by_day = by_day

    def get_daily_sale_posting_evidence(self, day):
        return self.by_day.get(
            day,
            {"error": False, "complete": True, "records": []},
        )


class FakeOzon:
    def __init__(self, postings):
        self.postings = list(postings)

    def get_realization_posting(self, year, month):
        if (year, month) != (2026, 9):
            return {"rows": []}
        return {
            "rows": [
                {
                    "order": {"posting_number": posting_number},
                    "item": {"sku": sku},
                    "delivery_commission": {"quantity": quantity},
                }
                for posting_number, sku, quantity in self.postings
            ]
        }

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
        if at_date <= "2026-09-09":
            return {
                "error": False,
                "effective_cost_confirmed": True,
                "historical_cost_confirmed": True,
                "history_id": 1,
                "cost_price": 21.0,
                "effective_from": "2026-05-03",
                "effective_through": "2026-09-09",
                "source": "SELLER_CONFIRMED",
            }
        return {
            "error": False,
            "effective_cost_confirmed": True,
            "historical_cost_confirmed": True,
            "history_id": 2,
            "cost_price": 25.0,
            "effective_from": "2026-09-10",
            "effective_through": "2026-12-31",
            "source": "SELLER_CONFIRMED",
        }


class FakeSameVersionCost:
    def get_effective_cost_evidence(
        self,
        at_date,
        product_id=None,
        sku=None,
        offer_id=None,
    ):
        return {
            "error": False,
            "effective_cost_confirmed": True,
            "historical_cost_confirmed": True,
            "history_id": 7,
            "cost_price": 21.0,
            "effective_from": "2026-09-01",
            "effective_through": "2026-09-30",
            "source": "SELLER_CONFIRMED",
        }


def sale_record(posting_number, day):
    return {
        "posting_number": posting_number,
        "sku": "sku-1",
        "accrual_date": day,
        "source": "OZON_FINANCE_ACCRUAL_BY_DAY",
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
    def test_bounded_history_preserves_old_cost_and_applies_later_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = TempCostService(os.path.join(tmp, "costs.db"))
            first = service.record_historical_cost(
                "p1",
                "sku-1",
                "offer-1",
                21.0,
                "2026-05-03",
                effective_through="2026-09-09",
            )
            second = service.record_historical_cost(
                "p1",
                "sku-1",
                "offer-1",
                25.0,
                "2026-09-10",
                effective_through="2026-12-31",
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
            self.assertEqual(may["effective_through"], "2026-09-09")
            self.assertEqual(may["cost_basis"], "SELLER_CONFIRMED_BOUNDED_PERIOD")
            self.assertEqual(september["cost_price"], 25.0)
            self.assertEqual(september["effective_from"], "2026-09-10")

    def test_bounded_history_fails_closed_before_first_confirmed_interval(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = TempCostService(os.path.join(tmp, "costs.db"))
            service.record_historical_cost(
                "p1",
                "sku-1",
                "offer-1",
                21.0,
                "2026-05-03",
                effective_through="2026-08-31",
            )

            evidence = service.get_effective_cost_evidence(
                "2026-05-02", product_id="p1", sku="sku-1", offer_id="offer-1"
            )

            self.assertTrue(evidence["error"])
            self.assertEqual(
                evidence["code"], "PERIOD_PROFIT_COST_HISTORY_NOT_EFFECTIVE"
            )
            self.assertIsNone(evidence["cost_price"])

    def test_bounded_history_fails_closed_after_confirmed_interval(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = TempCostService(os.path.join(tmp, "costs.db"))
            service.record_historical_cost(
                "p1",
                "sku-1",
                "offer-1",
                21.0,
                "2026-05-03",
                effective_through="2026-08-31",
            )

            evidence = service.get_effective_cost_evidence(
                "2026-09-01", product_id="p1", sku="sku-1", offer_id="offer-1"
            )

            self.assertTrue(evidence["error"])
            self.assertEqual(
                evidence["code"], "PERIOD_PROFIT_COST_HISTORY_NOT_EFFECTIVE"
            )
            self.assertIsNone(evidence["cost_price"])

    def test_open_ended_history_is_not_period_profit_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = TempCostService(os.path.join(tmp, "costs.db"))
            service.record_historical_cost(
                "p1", "sku-1", "offer-1", 21.0, "2026-05-01"
            )

            evidence = service.get_effective_cost_evidence(
                "2026-08-31", product_id="p1", sku="sku-1", offer_id="offer-1"
            )

            self.assertTrue(evidence["error"])
            self.assertEqual(
                evidence["code"], "PERIOD_PROFIT_COST_HISTORY_UNBOUNDED"
            )
            self.assertIsNone(evidence["cost_price"])

    def test_current_cost_without_history_fails_closed_for_period_profit(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = TempCostService(os.path.join(tmp, "costs.db"))
            service.set_cost("p1", "sku-1", "offer-1", 21.0)

            evidence = service.get_effective_cost_evidence(
                "2026-05-03", product_id="p1", sku="sku-1", offer_id="offer-1"
            )

            self.assertTrue(evidence["error"])
            self.assertEqual(
                evidence["code"], "PERIOD_PROFIT_COST_HISTORY_MISSING"
            )
            self.assertIsNone(evidence["cost_price"])

    def test_invalid_reversed_bound_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = TempCostService(os.path.join(tmp, "costs.db"))
            result = service.record_historical_cost(
                "p1",
                "sku-1",
                "offer-1",
                21.0,
                "2026-09-10",
                effective_through="2026-09-09",
            )
            self.assertTrue(result["error"])
            self.assertEqual(result["code"], "PRODUCT_COST_HISTORY_INPUT_INVALID")

    def test_quantity_cogs_uses_bounded_cost_for_each_distinct_physical_sale(self):
        service = PeriodProfitEffectiveCostSaleQuantitySummaryService.__new__(
            PeriodProfitEffectiveCostSaleQuantitySummaryService
        )
        service.finance_service = FakeFinance({
            "2026-09-09": {
                "error": False,
                "complete": True,
                "records": [sale_record("before-change", "2026-09-09")],
            },
            "2026-09-10": {
                "error": False,
                "complete": True,
                "records": [sale_record("after-change", "2026-09-10")],
            },
        })
        service.cost_service = FakeVersionedCost()
        service.sale_quantity_ozon_client = FakeOzon([
            ("before-change", "sku-1", 1),
            ("after-change", "sku-1", 1),
        ])
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

    def test_reaccrual_within_one_cost_version_counts_physical_quantity_once(self):
        service = PeriodProfitEffectiveCostSaleQuantitySummaryService.__new__(
            PeriodProfitEffectiveCostSaleQuantitySummaryService
        )
        service.finance_service = FakeFinance({
            "2026-09-05": {
                "error": False,
                "complete": True,
                "records": [sale_record("same-posting", "2026-09-05")],
            },
            "2026-09-08": {
                "error": False,
                "complete": True,
                "records": [sale_record("same-posting", "2026-09-08")],
            },
        })
        service.cost_service = FakeSameVersionCost()
        service.sale_quantity_ozon_client = FakeOzon([
            ("same-posting", "sku-1", 1),
        ])
        service._realization_quantity_cache = {}
        service._posting_quantity_cache = {}
        service._fbo_list_quantity_cache = {}

        result = service._reconcile_sale_quantities(
            summary_fixture(), "2026-09-05", "2026-09-08"
        )

        self.assertFalse(result["error"])
        self.assertEqual(result["units_sold"], 1)
        self.assertEqual(result["product_cost"], 21.0)
        self.assertEqual(result["sale_quantity_record_count"], 1)
        self.assertEqual(result["sale_quantity_positive_event_count"], 2)
        self.assertEqual(result["sale_quantity_reaccrued_event_count"], 1)

    def test_reaccrual_crossing_cost_versions_fails_closed(self):
        service = PeriodProfitEffectiveCostSaleQuantitySummaryService.__new__(
            PeriodProfitEffectiveCostSaleQuantitySummaryService
        )
        service.finance_service = FakeFinance({
            "2026-09-09": {
                "error": False,
                "complete": True,
                "records": [sale_record("same-posting", "2026-09-09")],
            },
            "2026-09-10": {
                "error": False,
                "complete": True,
                "records": [sale_record("same-posting", "2026-09-10")],
            },
        })
        service.cost_service = FakeVersionedCost()
        service.sale_quantity_ozon_client = FakeOzon([
            ("same-posting", "sku-1", 1),
        ])
        service._realization_quantity_cache = {}
        service._posting_quantity_cache = {}
        service._fbo_list_quantity_cache = {}

        result = service._reconcile_sale_quantities(
            summary_fixture(), "2026-09-09", "2026-09-10"
        )

        self.assertTrue(result["error"])
        self.assertEqual(
            result["code"], "PERIOD_PROFIT_REACCRUAL_COST_VERSION_AMBIGUOUS"
        )
        self.assertTrue(result["read_only"])
        self.assertFalse(result["executed"])

    def test_missing_effective_cost_service_fails_closed(self):
        service = PeriodProfitEffectiveCostSaleQuantitySummaryService.__new__(
            PeriodProfitEffectiveCostSaleQuantitySummaryService
        )
        service.finance_service = FakeFinance({
            "2026-09-05": {
                "error": False,
                "complete": True,
                "records": [sale_record("p1", "2026-09-05")],
            },
        })
        service.cost_service = object()
        service.sale_quantity_ozon_client = FakeOzon([("p1", "sku-1", 1)])
        service._realization_quantity_cache = {}
        service._posting_quantity_cache = {}
        service._fbo_list_quantity_cache = {}

        result = service._reconcile_sale_quantities(
            summary_fixture(), "2026-09-05", "2026-09-05"
        )

        self.assertTrue(result["error"])
        self.assertEqual(result["code"], "PERIOD_PROFIT_EFFECTIVE_COST_UNAVAILABLE")


if __name__ == "__main__":
    unittest.main()
