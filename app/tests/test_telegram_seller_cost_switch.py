import os
import sqlite3
import sys
import tempfile
import unittest
from datetime import date


APP_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if APP_ROOT not in sys.path:
    sys.path.insert(0, APP_ROOT)

from services.period_profit_effective_cost_sale_quantity_summary_service import (  # noqa: E402
    PeriodProfitEffectiveCostSaleQuantitySummaryService,
)
from services.period_profit_effective_cost_service import (  # noqa: E402
    PeriodProfitEffectiveCostService,
)
from services.telegram_seller_cost_update_service import (  # noqa: E402
    TelegramSellerCostUpdateService,
)


class TempCostService(PeriodProfitEffectiveCostService):
    def __init__(self, path):
        self.path = path
        super().__init__()

    def get_connection(self):
        return sqlite3.connect(self.path)


class FakeProducts:
    def __init__(self, rows=None):
        self.rows = rows or [("p1", "offer-1", "sku-1")]

    def load_products(self):
        return list(self.rows)


class FinanceForReaccrual:
    def __init__(self, days):
        self.days = list(days)

    def get_daily_sale_posting_evidence(self, day):
        if day in self.days:
            return {
                "error": False,
                "complete": True,
                "records": [{
                    "posting_number": "posting-1",
                    "sku": "sku-1",
                    "accrual_date": day,
                    "source": "OZON_FINANCE_ACCRUAL_BY_DAY",
                }],
            }
        return {"error": False, "complete": True, "records": []}


class FakeOzon:
    def get_realization_posting(self, year, month):
        return {
            "rows": [{
                "order": {"posting_number": "posting-1"},
                "item": {"sku": "sku-1"},
                "delivery_commission": {"quantity": 1},
            }]
        }

    def get_fbo_postings(self, *args, **kwargs):
        return {"result": [], "has_next": False}

    def get_fbo_posting(self, posting_number):
        return {"error": True}

    def get_fbs_posting(self, posting_number):
        return {"error": True}


def summary_fixture():
    return {
        "error": False,
        "status": "PERIOD_PROFIT_SUMMARY_READY",
        "products": [{
            "product_id": "p1",
            "sku": "sku-1",
            "offer_id": "offer-1",
            "cost_per_unit": 21.0,
            "units_sold": 2,
            "revenue": 100.0,
            "net_accrual": 80.0,
            "commission": 0.0,
            "logistics": 0.0,
            "acquiring": 0.0,
            "other_fees": 0.0,
            "product_cost": 42.0,
            "tax": 0.0,
            "profit": 38.0,
            "margin_percent": 38.0,
            "fee_breakdown": {},
        }],
        "units_sold": 2,
        "revenue": 100.0,
        "net_accrual": 80.0,
        "commission": 0.0,
        "logistics": 0.0,
        "acquiring": 0.0,
        "other_fees": 0.0,
        "product_cost": 42.0,
        "tax": 0.0,
        "profit": 38.0,
        "margin_percent": 38.0,
        "fee_breakdown": {},
    }


class SellerCostSwitchTests(unittest.TestCase):
    def test_switch_overrides_bounded_history_only_from_switch_date(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = TempCostService(os.path.join(tmp, "costs.db"))
            history = service.record_historical_cost(
                "p1",
                "sku-1",
                "offer-1",
                21.0,
                "2026-01-01",
                effective_through="2026-12-31",
            )
            switch = service.record_cost_switch(
                "p1", "sku-1", "offer-1", 25.0, "2026-09-10"
            )
            self.assertFalse(history["error"])
            self.assertFalse(switch["error"])

            before = service.get_effective_cost_evidence(
                "2026-09-09", product_id="p1", sku="sku-1", offer_id="offer-1"
            )
            after = service.get_effective_cost_evidence(
                "2026-09-10", product_id="p1", sku="sku-1", offer_id="offer-1"
            )

            self.assertEqual(before["cost_price"], 21.0)
            self.assertEqual(before["cost_basis"], "SELLER_CONFIRMED_BOUNDED_PERIOD")
            self.assertEqual(after["cost_price"], 25.0)
            self.assertEqual(after["cost_basis"], "SELLER_CONFIRMED_OPERATIONAL_SWITCH")
            self.assertEqual(after["effective_from"], "2026-09-10")

    def test_second_switch_supersedes_first_without_rewriting_past(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = TempCostService(os.path.join(tmp, "costs.db"))
            service.record_cost_switch(
                "p1", "sku-1", "offer-1", 25.0, "2026-09-10"
            )
            service.record_cost_switch(
                "p1", "sku-1", "offer-1", 27.5, "2026-10-01"
            )

            september = service.get_effective_cost_evidence(
                "2026-09-20", product_id="p1"
            )
            october = service.get_effective_cost_evidence(
                "2026-10-01", product_id="p1"
            )
            self.assertEqual(september["cost_price"], 25.0)
            self.assertEqual(october["cost_price"], 27.5)

    def test_telegram_input_records_switch_for_next_calendar_date(self):
        with tempfile.TemporaryDirectory() as tmp:
            costs = TempCostService(os.path.join(tmp, "costs.db"))
            flow = TelegramSellerCostUpdateService(
                FakeProducts(),
                costs,
                date_provider=lambda: date(2026, 9, 8),
            )

            selected = flow.select_sku(123, "sku-1")
            self.assertFalse(selected["error"])
            result = flow.handle_text(123, "24,70")

            self.assertFalse(result["error"])
            self.assertTrue(result["handled"])
            self.assertEqual(result["cost_price"], 24.7)
            self.assertEqual(result["effective_from"], "2026-09-09")
            evidence = costs.get_effective_cost_evidence(
                "2026-09-09", product_id="p1"
            )
            self.assertEqual(evidence["cost_price"], 24.7)
            self.assertEqual(
                evidence["cost_basis"], "SELLER_CONFIRMED_OPERATIONAL_SWITCH"
            )

    def test_invalid_telegram_price_keeps_pending_and_does_not_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            costs = TempCostService(os.path.join(tmp, "costs.db"))
            flow = TelegramSellerCostUpdateService(
                FakeProducts(),
                costs,
                date_provider=lambda: date(2026, 9, 8),
            )
            flow.select_sku(123, "sku-1")

            invalid = flow.handle_text(123, "не цена")
            self.assertFalse(invalid["error"])
            self.assertTrue(invalid["handled"])
            conn = costs.get_connection()
            count = conn.execute(
                "SELECT COUNT(*) FROM product_cost_switch_history"
            ).fetchone()[0]
            conn.close()
            self.assertEqual(count, 0)

            valid = flow.handle_text(123, "25")
            self.assertFalse(valid["error"])
            self.assertEqual(valid["cost_price"], 25.0)

    def test_reaccrual_crossing_switch_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            costs = TempCostService(os.path.join(tmp, "costs.db"))
            costs.record_historical_cost(
                "p1",
                "sku-1",
                "offer-1",
                21.0,
                "2026-01-01",
                effective_through="2026-12-31",
            )
            costs.record_cost_switch(
                "p1", "sku-1", "offer-1", 25.0, "2026-09-10"
            )
            service = PeriodProfitEffectiveCostSaleQuantitySummaryService.__new__(
                PeriodProfitEffectiveCostSaleQuantitySummaryService
            )
            service.finance_service = FinanceForReaccrual(
                ["2026-09-09", "2026-09-10"]
            )
            service.cost_service = costs
            service.sale_quantity_ozon_client = FakeOzon()
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

    def test_reaccrual_inside_one_switch_counts_one_quantity_and_one_cogs(self):
        with tempfile.TemporaryDirectory() as tmp:
            costs = TempCostService(os.path.join(tmp, "costs.db"))
            costs.record_cost_switch(
                "p1", "sku-1", "offer-1", 25.0, "2026-09-10"
            )
            service = PeriodProfitEffectiveCostSaleQuantitySummaryService.__new__(
                PeriodProfitEffectiveCostSaleQuantitySummaryService
            )
            service.finance_service = FinanceForReaccrual(
                ["2026-09-10", "2026-09-11"]
            )
            service.cost_service = costs
            service.sale_quantity_ozon_client = FakeOzon()
            service._realization_quantity_cache = {}
            service._posting_quantity_cache = {}
            service._fbo_list_quantity_cache = {}

            result = service._reconcile_sale_quantities(
                summary_fixture(), "2026-09-10", "2026-09-11"
            )
            self.assertFalse(result["error"])
            self.assertEqual(result["units_sold"], 1)
            self.assertEqual(result["product_cost"], 25.0)
            self.assertEqual(result["sale_quantity_positive_event_count"], 2)
            self.assertEqual(result["sale_quantity_reaccrued_event_count"], 1)


if __name__ == "__main__":
    unittest.main()
