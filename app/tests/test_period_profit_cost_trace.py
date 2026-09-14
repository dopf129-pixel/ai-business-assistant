import os
import sys
import unittest

APP_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if APP_ROOT not in sys.path:
    sys.path.insert(0, APP_ROOT)

from services.assistant_period_profit_runtime_service import AssistantPeriodProfitRuntimeService
from services.period_profit_diagnostic_quantity_summary_service import (
    PeriodProfitDiagnosticQuantitySummaryService,
)


class _MissingCost:
    @staticmethod
    def _date(value):
        from datetime import date
        try:
            return date.fromisoformat(str(value))
        except (TypeError, ValueError):
            return None

    def get_effective_cost_evidence(self, at_date, **kwargs):
        return {
            "error": True,
            "code": "PERIOD_PROFIT_COST_HISTORY_MISSING",
            "status": "PERIOD_PROFIT_EFFECTIVE_COST_UNAVAILABLE",
            "effective_cost_confirmed": False,
            "historical_cost_confirmed": False,
        }

    def get_cost(self, product_id):
        return (product_id, "new-sku", "offer", 100.0, "RUB", "2026-09-14 10:00:00")


class PeriodProfitCostTraceTests(unittest.TestCase):
    def test_missing_cost_emits_safe_identity_trace(self):
        service = PeriodProfitDiagnosticQuantitySummaryService.__new__(
            PeriodProfitDiagnosticQuantitySummaryService
        )
        service.cost_service = _MissingCost()

        evidence = service._effective_cost_evidence(
            {
                "product_id": "secret-product",
                "offer_id": "secret-offer",
                "sku": "legacy-secret-sku",
                "catalog_sku": "current-secret-sku",
                "historical_sku_identity_recovered": True,
            },
            "2026-09-10",
        )
        self.assertIsNone(evidence)

        result = service._quantity_error("PERIOD_PROFIT_EFFECTIVE_COST_UNAVAILABLE")
        trace = result["cost_diagnostic_trace"]
        self.assertEqual(result["code"], "PERIOD_PROFIT_COST_HISTORY_MISSING")
        self.assertTrue(trace["product_id_present"])
        self.assertTrue(trace["offer_id_present"])
        self.assertTrue(trace["finance_sku_present"])
        self.assertTrue(trace["catalog_sku_present"])
        self.assertTrue(trace["catalog_sku_differs"])
        self.assertTrue(trace["identity_recovered"])
        self.assertEqual(trace["product_id_lookup_code"], "PERIOD_PROFIT_COST_HISTORY_MISSING")
        self.assertEqual(trace["offer_id_lookup_code"], "PERIOD_PROFIT_COST_HISTORY_MISSING")
        self.assertEqual(trace["finance_sku_lookup_code"], "PERIOD_PROFIT_COST_HISTORY_MISSING")
        self.assertEqual(trace["catalog_sku_lookup_code"], "PERIOD_PROFIT_COST_HISTORY_MISSING")
        self.assertTrue(trace["current_cost_present"])
        self.assertEqual(trace["current_cost_date_relation"], "AFTER_SALE")
        self.assertNotIn("secret-product", str(result))
        self.assertNotIn("secret-offer", str(result))
        self.assertNotIn("legacy-secret-sku", str(result))
        self.assertNotIn("current-secret-sku", str(result))

    def test_runtime_renders_trace_without_identifiers(self):
        result = {
            "error": True,
            "code": "PERIOD_PROFIT_COST_HISTORY_MISSING",
            "status": "PERIOD_PROFIT_SALE_QUANTITY_UNAVAILABLE",
            "cost_diagnostic_trace": {
                "product_id_present": True,
                "catalog_sku_present": True,
                "product_id_lookup_code": "PERIOD_PROFIT_COST_HISTORY_MISSING",
                "current_cost_present": True,
                "current_cost_date_relation": "AFTER_SALE",
            },
            "read_only": True,
            "executed": False,
        }
        presented = AssistantPeriodProfitRuntimeService._present(result)
        self.assertIn("Трассировка:", presented["message"])
        self.assertIn("current_cost_date_relation=AFTER_SALE", presented["message"])
        self.assertTrue(presented["read_only"])
        self.assertFalse(presented["executed"])


if __name__ == "__main__":
    unittest.main()
