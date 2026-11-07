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
from services.seller_cost_table_service import SellerCostTableService  # noqa: E402


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

    def test_batch_expected_revision_is_checked_inside_the_atomic_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = self._service(tmp)
            initial = service.get_cost_history_snapshot()
            self.assertFalse(initial["error"])
            first = service.record_cost_switches(
                [{
                    "product_id": "p1", "sku": "sku-1", "offer_id": "offer-1",
                    "cost_price": 20.0, "effective_from": date.today().isoformat(),
                    "source": "CSV_TEST",
                }],
                expected_revision=initial["revision"],
            )
            self.assertFalse(first["error"])
            stale = service.record_cost_switches(
                [{
                    "product_id": "p2", "sku": "sku-2", "offer_id": "offer-2",
                    "cost_price": 30.0, "effective_from": date.today().isoformat(),
                    "source": "CSV_TEST",
                }],
                expected_revision=initial["revision"],
            )
            self.assertTrue(stale["error"])
            self.assertEqual(stale["code"], "PRODUCT_COST_SWITCH_REVISION_STALE")
            current = service.get_cost_history_snapshot()
            self.assertEqual(current["row_count"], 1)

    def test_csv_import_persists_safe_source_reference_and_revision(self):
        with tempfile.TemporaryDirectory() as tmp:
            costs = self._service(tmp)

            class Products:
                def load_products(self):
                    return [("p1", "offer-1", "sku-1")]

            table = SellerCostTableService(Products(), costs)
            preview = table.import_csv(
                "Артикул;Ozon SKU;Себестоимость, ₽;Действует с (ГГГГ-ММ-ДД)\n"
                "offer-1;sku-1;20.00;2026-11-01\n"
            )
            self.assertFalse(preview["error"], preview)
            saved = table.commit_import(
                preview["rows"],
                expected_source_revision=preview["source_revision"],
                expected_history_revision=preview["history_revision"],
                source_reference=preview["source_reference"],
                source_revision=preview["source_revision"],
            )
            self.assertFalse(saved["error"], saved)
            evidence = costs.get_effective_cost_evidence(
                "2026-11-06", product_id="p1", sku="sku-1", offer_id="offer-1",
            )
            self.assertEqual(evidence["source"], "SELLER_CONFIRMED_COST_TABLE")
            self.assertEqual(evidence["source_reference"], preview["source_reference"])
            self.assertEqual(evidence["source_revision"], preview["source_revision"])
            exported = table.export_history_csv()
            self.assertIn(preview["source_reference"], exported["file_content"])
            self.assertIn(preview["source_revision"], exported["file_content"])

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
