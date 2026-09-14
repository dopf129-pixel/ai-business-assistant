import os
import sys
import unittest


APP_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if APP_ROOT not in sys.path:
    sys.path.insert(0, APP_ROOT)

from services.period_profit_tax_policy_summary_service import (  # noqa: E402
    PeriodProfitTaxPolicySummaryService,
)


class _ExplodingBase:
    def calculate(self, date_from, date_to, products):
        self._explode()

    @staticmethod
    def _explode():
        raise ValueError("sensitive runtime detail must not be returned")


class _UnusedTaxService:
    def calculate(self, *args, **kwargs):
        raise AssertionError("tax service must not run after base exception")


class PeriodProfitTaxBaseExceptionDiagnosticsTests(unittest.TestCase):
    def test_reports_safe_exception_location_without_exception_message(self):
        service = PeriodProfitTaxPolicySummaryService(
            _ExplodingBase(),
            _UnusedTaxService(),
            {
                "error": False,
                "configured": True,
                "policy": {"mode": "NONE"},
            },
        )

        result = service.calculate("2026-09-01", "2026-09-07", [])

        self.assertTrue(result["error"])
        self.assertEqual(result["code"], "PERIOD_PROFIT_TAX_BASE_EXCEPTION")
        self.assertEqual(result["status"], "PERIOD_PROFIT_SUMMARY_UNAVAILABLE")
        self.assertEqual(result["exception_type"], "ValueError")
        self.assertEqual(result["exception_function"], "_explode")
        self.assertEqual(
            result["exception_file"],
            "test_period_profit_tax_base_exception_diagnostics.py",
        )
        self.assertIsInstance(result["exception_line"], int)
        self.assertNotIn("exception_message", result)
        self.assertNotIn("sensitive runtime detail", str(result))


if __name__ == "__main__":
    unittest.main()
