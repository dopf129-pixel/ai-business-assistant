import os
import sqlite3
import sys
import tempfile
import unittest
from datetime import date, timedelta


APP_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if APP_ROOT not in sys.path:
    sys.path.insert(0, APP_ROOT)

from services.period_profit_effective_cost_service import (  # noqa: E402
    PeriodProfitEffectiveCostService,
)


class TempCostService(PeriodProfitEffectiveCostService):
    def __init__(self, path, today_provider=None):
        self.path = path
        super().__init__(today_provider=today_provider)

    def get_connection(self):
        conn = sqlite3.connect(self.path)
        self._ensure_schema(conn)
        return conn


class PeriodProfitEffectiveCostCurrentProjectionTests(unittest.TestCase):
    def _service(self, tmp, today_provider=None):
        return TempCostService(os.path.join(tmp, "costs.db"), today_provider)

    @staticmethod
    def _set_legacy_timestamp(service, timestamp):
        conn = service.get_connection()
        conn.execute(
            "UPDATE product_costs SET updated_at = ? WHERE product_id = ?",
            (timestamp, "p1"),
        )
        conn.commit()
        conn.close()

    @staticmethod
    def _switch(service, cost, effective_from):
        result = service.record_cost_switch(
            product_id="p1",
            sku="sku-1",
            offer_id="offer-1",
            cost_price=cost,
            effective_from=effective_from.isoformat(),
        )
        if result.get("error") is not False:
            raise AssertionError(result)
        return result

    def test_future_single_switch_does_not_replace_current_or_legacy_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            today = date.today()
            service = self._service(tmp)
            service.set_cost("p1", "sku-1", "offer-1", 20.0)
            self._set_legacy_timestamp(
                service,
                (today - timedelta(days=2)).isoformat() + " 12:00:00",
            )

            future = self._switch(service, 25.0, today + timedelta(days=1))

            current = service.get_cost("p1")
            current_evidence = service.get_effective_cost_evidence(
                today.isoformat(), product_id="p1", sku="sku-1", offer_id="offer-1"
            )
            future_evidence = service.get_effective_cost_evidence(
                (today + timedelta(days=1)).isoformat(),
                product_id="p1",
                sku="sku-1",
                offer_id="offer-1",
            )

            self.assertEqual(current[3], 20.0)
            self.assertEqual(current_evidence["cost_price"], 20.0)
            self.assertEqual(current_evidence["source"], "SELLER_CONFIRMED_LEGACY_CURRENT_TIMESTAMP")
            self.assertEqual(future_evidence["cost_price"], 25.0)
            self.assertEqual(future["effective_from"], (today + timedelta(days=1)).isoformat())

    def test_legacy_row_matching_future_projection_timestamp_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            today = date.today()
            service = self._service(tmp)
            service.set_cost("p1", "sku-1", "offer-1", 20.0)
            future = self._switch(service, 25.0, today + timedelta(days=1))

            projection_timestamp = today.isoformat() + " 12:00:00"
            self._set_legacy_timestamp(service, projection_timestamp)
            conn = service.get_connection()
            conn.execute(
                "UPDATE product_costs SET cost_price = ?, updated_at = ? WHERE product_id = ?",
                (25.0, projection_timestamp, "p1"),
            )
            conn.execute(
                "UPDATE product_cost_switch_history SET recorded_at = ? WHERE id = ?",
                (projection_timestamp, future["switch_id"]),
            )
            conn.commit()
            conn.close()

            current = service.get_effective_cost_evidence(
                today.isoformat(), product_id="p1", sku="sku-1", offer_id="offer-1"
            )

            self.assertTrue(current["error"])
            self.assertEqual(
                current["code"],
                "PERIOD_PROFIT_COST_LEGACY_PROVENANCE_AMBIGUOUS",
            )
            self.assertIsNone(service.get_cost("p1"))

    def test_future_only_switch_is_not_misreported_as_current(self):
        with tempfile.TemporaryDirectory() as tmp:
            today = date.today()
            service = self._service(tmp)

            self._switch(service, 25.0, today + timedelta(days=1))

            self.assertIsNone(service.get_cost("p1"))
            current = service.get_effective_cost_evidence(
                today.isoformat(), product_id="p1", sku="sku-1", offer_id="offer-1"
            )
            self.assertTrue(current["error"])
            self.assertIsNone(current["cost_price"])

    def test_late_past_switch_does_not_roll_back_current_or_future_projection(self):
        with tempfile.TemporaryDirectory() as tmp:
            today = date.today()
            service = self._service(tmp)
            self._switch(service, 20.0, today)
            self._switch(service, 25.0, today + timedelta(days=1))

            self._switch(service, 18.0, today - timedelta(days=2))

            self.assertEqual(service.get_cost("p1")[3], 20.0)
            self.assertEqual(
                service.get_effective_cost_evidence(
                    today.isoformat(), product_id="p1", sku="sku-1", offer_id="offer-1"
                )["cost_price"],
                20.0,
            )
            self.assertEqual(
                service.get_effective_cost_evidence(
                    (today + timedelta(days=2)).isoformat(),
                    product_id="p1",
                    sku="sku-1",
                    offer_id="offer-1",
                )["cost_price"],
                25.0,
            )

    def test_batch_projects_latest_switch_effective_today_not_future_maximum(self):
        with tempfile.TemporaryDirectory() as tmp:
            today = date.today()
            service = self._service(tmp)

            result = service.record_cost_switches([
                {
                    "product_id": "p1",
                    "sku": "sku-1",
                    "offer_id": "offer-1",
                    "cost_price": 20.0,
                    "effective_from": today.isoformat(),
                    "source": "CSV_TEST",
                },
                {
                    "product_id": "p1",
                    "sku": "sku-1",
                    "offer_id": "offer-1",
                    "cost_price": 25.0,
                    "effective_from": (today + timedelta(days=1)).isoformat(),
                    "source": "CSV_TEST",
                },
            ])

            self.assertFalse(result["error"])
            self.assertEqual(service.get_cost("p1")[3], 20.0)

    def test_effective_cost_advances_after_date_boundary_without_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            today = date.today()
            current_day = [today]
            service = self._service(tmp, today_provider=lambda: current_day[0])
            self._switch(service, 20.0, today)
            self._switch(service, 25.0, today + timedelta(days=1))

            self.assertEqual(service.get_cost("p1")[3], 20.0)
            self.assertEqual(service.get_all_costs()[0][3], 20.0)

            current_day[0] = today + timedelta(days=1)
            self.assertEqual(service.get_cost("p1")[3], 25.0)
            self.assertEqual(service.get_all_costs()[0][3], 25.0)


if __name__ == "__main__":
    unittest.main()
