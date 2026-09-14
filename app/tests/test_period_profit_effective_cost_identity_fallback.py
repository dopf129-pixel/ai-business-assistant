import os
import sqlite3
import sys
import tempfile
import unittest


APP_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if APP_ROOT not in sys.path:
    sys.path.insert(0, APP_ROOT)

from services.period_profit_effective_cost_service import (  # noqa: E402
    PeriodProfitEffectiveCostService,
)


class TempCostService(PeriodProfitEffectiveCostService):
    def __init__(self, path):
        self.path = path
        super().__init__()

    def get_connection(self):
        return sqlite3.connect(self.path)


class PeriodProfitEffectiveCostIdentityFallbackTests(unittest.TestCase):
    def test_legacy_finance_sku_resolves_historical_cost_via_stable_offer(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = TempCostService(os.path.join(tmp, "costs.db"))

            historical = service.record_historical_cost(
                "legacy-product-id",
                "3398133813",
                "hook-2",
                14.50,
                "2026-05-03",
                effective_through="2026-09-09",
            )
            current = service.record_cost_switch(
                "current-product-id",
                "3921245627",
                "hook-2",
                21.00,
                "2026-09-11",
            )
            self.assertFalse(historical["error"])
            self.assertFalse(current["error"])

            evidence = service.get_effective_cost_evidence(
                "2026-09-05",
                product_id="current-product-id",
                offer_id="hook-2",
                sku="3398133813",
            )

            self.assertFalse(evidence["error"])
            self.assertTrue(evidence["effective_cost_confirmed"])
            self.assertEqual(evidence["product_id"], "legacy-product-id")
            self.assertEqual(evidence["offer_id"], "hook-2")
            self.assertEqual(evidence["sku"], "3398133813")
            self.assertEqual(evidence["cost_price"], 14.50)
            self.assertEqual(evidence["effective_from"], "2026-05-03")
            self.assertEqual(evidence["effective_through"], "2026-09-09")
            self.assertEqual(
                evidence["cost_basis"], "SELLER_CONFIRMED_BOUNDED_PERIOD"
            )
            self.assertNotEqual(evidence["cost_price"], 21.00)

    def test_stronger_identity_not_effective_does_not_fall_through(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = TempCostService(os.path.join(tmp, "costs.db"))

            service.record_historical_cost(
                "legacy-product-id",
                "3398133813",
                "hook-2",
                14.50,
                "2026-05-03",
                effective_through="2026-09-09",
            )
            service.record_historical_cost(
                "current-product-id",
                "3921245627",
                "hook-2",
                21.00,
                "2026-09-11",
                effective_through="2026-12-31",
            )

            evidence = service.get_effective_cost_evidence(
                "2026-09-05",
                product_id="current-product-id",
                offer_id="hook-2",
                sku="3398133813",
            )

            self.assertTrue(evidence["error"])
            self.assertEqual(
                evidence["code"], "PERIOD_PROFIT_COST_HISTORY_NOT_EFFECTIVE"
            )
            self.assertIsNone(evidence["cost_price"])


    def test_identity_index_includes_history_and_switch_without_cost_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = TempCostService(os.path.join(tmp, "costs.db"))
            service.record_historical_cost(
                "legacy-product-id",
                "3398133813",
                "hook-2",
                14.50,
                "2026-05-03",
                effective_through="2026-09-09",
            )
            service.record_cost_switch(
                "current-product-id",
                "3921245627",
                "hook-2",
                21.00,
                "2026-09-11",
            )

            result = service.get_seller_cost_identities()

            self.assertFalse(result["error"])
            self.assertTrue(result["read_only"])
            self.assertFalse(result["executed"])
            self.assertFalse(result["cost_values_included"])
            records = result["records"]
            self.assertTrue(any(
                row["product_id"] == "legacy-product-id"
                and row["sku"] == "3398133813"
                and row["offer_id"] == "hook-2"
                and row["source"] == "product_cost_history"
                for row in records
            ))
            self.assertTrue(any(
                row["product_id"] == "current-product-id"
                and row["sku"] == "3921245627"
                and row["offer_id"] == "hook-2"
                and row["source"] == "product_cost_switch_history"
                for row in records
            ))
            self.assertTrue(all("cost_price" not in row for row in records))


if __name__ == "__main__":
    unittest.main()
