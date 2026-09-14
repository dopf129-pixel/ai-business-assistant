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
        conn = sqlite3.connect(self.path)
        self._ensure_schema(conn)
        return conn


class PeriodProfitLegacyCurrentCostTimestampTests(unittest.TestCase):
    def _set_updated_at(self, service, value):
        conn = service.get_connection()
        conn.execute(
            "UPDATE product_costs SET updated_at = ? WHERE product_id = ?",
            (value, "p1"),
        )
        conn.commit()
        conn.close()

    def test_legacy_current_cost_is_valid_only_from_its_stored_timestamp(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = TempCostService(os.path.join(tmp, "costs.db"))
            service.set_cost("p1", "sku-1", "offer-1", 21.0)
            self._set_updated_at(service, "2026-09-01 12:34:56")

            before = service.get_effective_cost_evidence(
                "2026-08-31",
                product_id="p1",
                sku="sku-1",
                offer_id="offer-1",
            )
            after = service.get_effective_cost_evidence(
                "2026-09-05",
                product_id="p1",
                sku="sku-1",
                offer_id="offer-1",
            )

            self.assertTrue(before["error"])
            self.assertEqual(before["code"], "PERIOD_PROFIT_COST_HISTORY_MISSING")
            self.assertIsNone(before["cost_price"])

            self.assertFalse(after["error"])
            self.assertEqual(after["cost_price"], 21.0)
            self.assertEqual(after["effective_from"], "2026-09-01")
            self.assertEqual(
                after["source"],
                "SELLER_CONFIRMED_LEGACY_CURRENT_TIMESTAMP",
            )
            self.assertEqual(
                after["cost_basis"],
                "SELLER_CONFIRMED_BOUNDED_PERIOD",
            )
            self.assertTrue(after["historical_cost_confirmed"])
            self.assertTrue(after["effective_cost_confirmed"])

    def test_later_cost_edit_never_backfills_earlier_sale(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = TempCostService(os.path.join(tmp, "costs.db"))
            service.set_cost("p1", "sku-1", "offer-1", 25.0)
            self._set_updated_at(service, "2026-09-10 08:00:00")

            evidence = service.get_effective_cost_evidence(
                "2026-09-05",
                product_id="p1",
                sku="sku-1",
                offer_id="offer-1",
            )

            self.assertTrue(evidence["error"])
            self.assertEqual(
                evidence["code"],
                "PERIOD_PROFIT_COST_HISTORY_MISSING",
            )
            self.assertIsNone(evidence["cost_price"])

    def test_explicit_bounded_history_stays_authoritative(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = TempCostService(os.path.join(tmp, "costs.db"))
            service.set_cost("p1", "sku-1", "offer-1", 25.0)
            self._set_updated_at(service, "2026-09-10 08:00:00")
            recorded = service.record_historical_cost(
                "p1",
                "sku-1",
                "offer-1",
                17.0,
                "2026-09-01",
                effective_through="2026-09-09",
            )
            self.assertFalse(recorded["error"])

            evidence = service.get_effective_cost_evidence(
                "2026-09-05",
                product_id="p1",
                sku="sku-1",
                offer_id="offer-1",
            )

            self.assertFalse(evidence["error"])
            self.assertEqual(evidence["cost_price"], 17.0)
            self.assertEqual(evidence["source"], "SELLER_CONFIRMED")
            self.assertEqual(evidence["cost_basis"], "SELLER_CONFIRMED_BOUNDED_PERIOD")


if __name__ == "__main__":
    unittest.main()
