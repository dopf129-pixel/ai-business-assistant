import os
import sys
import unittest


APP_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if APP_ROOT not in sys.path:
    sys.path.insert(0, APP_ROOT)

from services.period_profit_cost_confirmation_runtime_service import (  # noqa: E402
    PeriodProfitCostConfirmationRuntimeService,
)
from services.assistant_period_profit_runtime_service import (  # noqa: E402
    AssistantPeriodProfitRuntimeService,
)


class _FakeCostService:
    def __init__(self, rows, existing=None):
        self.rows = rows
        self.existing = existing
        self.recorded = []

    def get_all_costs(self):
        return list(self.rows)

    def get_effective_cost_evidence(self, *args, **kwargs):
        if self.existing is not None:
            return dict(self.existing)
        return {
            "error": True,
            "code": "PERIOD_PROFIT_COST_HISTORY_MISSING",
            "effective_cost_confirmed": False,
            "historical_cost_confirmed": False,
            "cost_price": None,
        }

    def record_cost_switch(self, **kwargs):
        self.recorded.append(dict(kwargs))
        return {
            "error": False,
            "status": "PRODUCT_COST_SWITCH_RECORDED",
            "seller_confirmed": True,
        }


class _NeverQuery:
    def query(self, **kwargs):
        raise AssertionError("profit query must not run for cost confirmation")


class PeriodProfitCostConfirmationRuntimeTests(unittest.TestCase):
    def test_seller_phrase_records_unique_matching_current_cost_from_start_of_year(self):
        cost = _FakeCostService([
            ("p-1", "sku-1", "offer-1", 21.0, "RUB", "2026-09-10 12:00:00"),
        ])
        confirmation = PeriodProfitCostConfirmationRuntimeService(cost)
        runtime = AssistantPeriodProfitRuntimeService(
            _NeverQuery(),
            cost_confirmation_runtime_service=confirmation,
        )

        result = runtime.handle_text("21р себестоимость была с начала 2026г")

        self.assertFalse(result["error"])
        self.assertEqual(result["code"], "PERIOD_PROFIT_COST_CONFIRMATION_RECORDED")
        self.assertTrue(result["seller_confirmed"])
        self.assertTrue(result["read_only_ozon"])
        self.assertEqual(len(cost.recorded), 1)
        recorded = cost.recorded[0]
        self.assertEqual(recorded["product_id"], "p-1")
        self.assertEqual(recorded["sku"], "sku-1")
        self.assertEqual(recorded["offer_id"], "offer-1")
        self.assertEqual(recorded["cost_price"], 21.0)
        self.assertEqual(recorded["effective_from"], "2026-01-01")
        self.assertEqual(recorded["source"], "SELLER_CONFIRMED_BOT_TEXT")

    def test_same_price_on_multiple_products_fails_closed_without_identity(self):
        cost = _FakeCostService([
            ("p-1", "sku-1", "offer-1", 21.0, "RUB", "2026-09-10 12:00:00"),
            ("p-2", "sku-2", "offer-2", 21.0, "RUB", "2026-09-11 12:00:00"),
        ])
        runtime = PeriodProfitCostConfirmationRuntimeService(cost)

        result = runtime.handle_text("21 ₽ себестоимость с 01.01.2026")

        self.assertTrue(result["error"])
        self.assertEqual(result["code"], "PERIOD_PROFIT_COST_CONFIRMATION_AMBIGUOUS")
        self.assertEqual(cost.recorded, [])

    def test_explicit_offer_disambiguates_same_price(self):
        cost = _FakeCostService([
            ("p-1", "sku-1", "offer-1", 21.0, "RUB", "2026-09-10 12:00:00"),
            ("p-2", "sku-2", "offer-2", 21.0, "RUB", "2026-09-11 12:00:00"),
        ])
        runtime = PeriodProfitCostConfirmationRuntimeService(cost)

        result = runtime.handle_text("offer-2: себестоимость 21 ₽ с 01.01.2026")

        self.assertFalse(result["error"])
        self.assertEqual(len(cost.recorded), 1)
        self.assertEqual(cost.recorded[0]["product_id"], "p-2")

    def test_existing_different_effective_cost_blocks_overwrite(self):
        cost = _FakeCostService(
            [("p-1", "sku-1", "offer-1", 21.0, "RUB", "2026-09-10 12:00:00")],
            existing={
                "error": False,
                "effective_cost_confirmed": True,
                "historical_cost_confirmed": True,
                "cost_price": 19.0,
            },
        )
        runtime = PeriodProfitCostConfirmationRuntimeService(cost)

        result = runtime.handle_text("21р себестоимость была с начала 2026г")

        self.assertTrue(result["error"])
        self.assertEqual(
            result["code"],
            "PERIOD_PROFIT_COST_CONFIRMATION_VERSION_CONFLICT",
        )
        self.assertEqual(cost.recorded, [])

    def test_non_confirmation_text_does_not_match(self):
        runtime = PeriodProfitCostConfirmationRuntimeService(_FakeCostService([]))
        self.assertIsNone(runtime.handle_text("прибыль за 7 дней"))


if __name__ == "__main__":
    unittest.main()
