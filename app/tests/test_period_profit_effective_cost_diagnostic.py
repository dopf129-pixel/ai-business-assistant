import os
import sys
import unittest


APP_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if APP_ROOT not in sys.path:
    sys.path.insert(0, APP_ROOT)

from services.period_profit_diagnostic_quantity_summary_service import (  # noqa: E402
    PeriodProfitDiagnosticQuantitySummaryService,
)


class _MissingHistoryCost:
    def get_effective_cost_evidence(self, *args, **kwargs):
        return {
            "error": True,
            "code": "PERIOD_PROFIT_COST_HISTORY_NOT_EFFECTIVE",
            "status": "PERIOD_PROFIT_EFFECTIVE_COST_UNAVAILABLE",
            "effective_cost_confirmed": False,
            "historical_cost_confirmed": False,
            "cost_price": None,
        }


class _ReadyCost:
    def get_effective_cost_evidence(self, *args, **kwargs):
        return {
            "error": False,
            "effective_cost_confirmed": True,
            "historical_cost_confirmed": True,
            "cost_price": 10.0,
            "effective_from": "2026-09-01",
            "effective_through": "2026-09-30",
            "source": "SELLER_CONFIRMED",
            "cost_basis": "SELLER_CONFIRMED_BOUNDED_PERIOD",
            "history_id": 1,
        }


class PeriodProfitEffectiveCostDiagnosticTests(unittest.TestCase):
    def _service(self, cost_service):
        service = PeriodProfitDiagnosticQuantitySummaryService.__new__(
            PeriodProfitDiagnosticQuantitySummaryService
        )
        service.cost_service = cost_service
        return service

    def test_exact_safe_cost_blocker_replaces_generic_code(self):
        service = self._service(_MissingHistoryCost())
        evidence = service._effective_cost_evidence(
            {"product_id": "p1", "sku": "sku-1", "offer_id": "offer-1"},
            "2026-09-05",
        )
        self.assertIsNone(evidence)

        result = service._quantity_error(
            "PERIOD_PROFIT_EFFECTIVE_COST_UNAVAILABLE"
        )

        self.assertTrue(result["error"])
        self.assertEqual(
            result["code"],
            "PERIOD_PROFIT_COST_HISTORY_NOT_EFFECTIVE",
        )
        self.assertTrue(result["read_only"])
        self.assertFalse(result["executed"])
        self.assertNotIn("p1", str(result))
        self.assertNotIn("sku-1", str(result))
        self.assertNotIn("offer-1", str(result))

    def test_successful_evidence_clears_previous_diagnostic(self):
        service = self._service(_MissingHistoryCost())
        service._effective_cost_evidence({}, "2026-09-05")
        service.cost_service = _ReadyCost()

        evidence = service._effective_cost_evidence({}, "2026-09-06")
        result = service._quantity_error(
            "PERIOD_PROFIT_EFFECTIVE_COST_UNAVAILABLE"
        )

        self.assertIsInstance(evidence, dict)
        self.assertEqual(evidence["cost_price"], 10.0)
        self.assertEqual(
            result["code"],
            "PERIOD_PROFIT_EFFECTIVE_COST_UNAVAILABLE",
        )

    def test_unrelated_quantity_errors_are_not_rewritten(self):
        service = self._service(_MissingHistoryCost())
        service._effective_cost_evidence({}, "2026-09-05")

        result = service._quantity_error(
            "PERIOD_PROFIT_SALE_QUANTITY_EVIDENCE_UNAVAILABLE"
        )

        self.assertEqual(
            result["code"],
            "PERIOD_PROFIT_SALE_QUANTITY_EVIDENCE_UNAVAILABLE",
        )


if __name__ == "__main__":
    unittest.main()
