import os
import sys
import unittest


APP_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if APP_ROOT not in sys.path:
    sys.path.insert(0, APP_ROOT)

from services.assistant_period_profit_runtime_service import (  # noqa: E402
    AssistantPeriodProfitRuntimeService,
)


class _Query:
    def query(self, **kwargs):
        return {
            "error": True,
            "code": "PERIOD_PROFIT_SALE_QUANTITY_EVIDENCE_UNAVAILABLE",
            "status": "PERIOD_PROFIT_SALE_QUANTITY_UNAVAILABLE",
            "message": "Данные о количестве проданных товаров недоступны",
            "read_only": True,
            "executed": False,
        }


class PeriodProfitQuantityErrorDiagnosticTests(unittest.TestCase):
    def test_quantity_error_exposes_safe_stage_code_to_seller(self):
        service = AssistantPeriodProfitRuntimeService(_Query())

        result = service.handle_callback("PERIOD_PROFIT:7D", today="2026-09-14")

        self.assertTrue(result["error"])
        self.assertEqual(
            result["quantity_diagnostic_code"],
            "PERIOD_PROFIT_SALE_QUANTITY_EVIDENCE_UNAVAILABLE",
        )
        self.assertEqual(
            result["message"],
            "Данные о количестве проданных товаров недоступны\n"
            "Код диагностики: PERIOD_PROFIT_SALE_QUANTITY_EVIDENCE_UNAVAILABLE",
        )
        self.assertTrue(result["read_only"])
        self.assertFalse(result["executed"])
        self.assertNotIn("posting", result["message"].lower())
        self.assertNotIn("sku", result["message"].lower())


if __name__ == "__main__":
    unittest.main()
