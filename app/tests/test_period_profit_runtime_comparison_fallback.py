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
    def __init__(self, current_error=False):
        self.current_error = current_error
        self.calls = []

    def query(self, **kwargs):
        self.calls.append(dict(kwargs))
        if kwargs.get("compare_previous") is True:
            return {
                "error": True,
                "code": "PERIOD_PROFIT_SALE_QUANTITY_EVIDENCE_UNAVAILABLE",
                "status": "PERIOD_PROFIT_SUMMARY_UNAVAILABLE",
                "read_only": True,
                "executed": False,
            }
        if self.current_error:
            return {
                "error": True,
                "code": "PERIOD_PROFIT_SALE_QUANTITY_EVIDENCE_UNAVAILABLE",
                "status": "PERIOD_PROFIT_SUMMARY_UNAVAILABLE",
                "read_only": True,
                "executed": False,
            }
        return {
            "error": False,
            "status": "PERIOD_PROFIT_QUERY_READY",
            "summary": {
                "date_from": "2026-09-08",
                "date_to": "2026-09-14",
                "units_sold": 3,
                "revenue": 100.0,
                "net_accrual": 80.0,
                "product_cost": 51.0,
                "tax": 0.0,
                "profit": 29.0,
                "margin_percent": 29.0,
            },
            "comparison": None,
            "previous_summary": None,
            "text": "full current-period response",
            "read_only": True,
            "executed": False,
        }


class PeriodProfitRuntimeComparisonFallbackTests(unittest.TestCase):
    def test_seven_day_callback_keeps_current_profit_when_previous_comparison_fails(self):
        query = _Query()
        runtime = AssistantPeriodProfitRuntimeService(query)

        result = runtime.handle_callback(
            "period_profit:7D",
            today="2026-09-14",
        )

        self.assertFalse(result["error"])
        self.assertEqual(result["summary"]["profit"], 29.0)
        self.assertEqual(result["comparison_status"], "PERIOD_PROFIT_COMPARISON_UNAVAILABLE")
        self.assertEqual(
            result["comparison_error_code"],
            "PERIOD_PROFIT_SALE_QUANTITY_EVIDENCE_UNAVAILABLE",
        )
        self.assertIn("💰 Прибыль за период", result["text"])
        self.assertEqual(
            [call["compare_previous"] for call in query.calls],
            [True, False],
        )
        self.assertTrue(result["read_only"])
        self.assertFalse(result["executed"])

    def test_current_quantity_failure_stays_fail_closed(self):
        query = _Query(current_error=True)
        runtime = AssistantPeriodProfitRuntimeService(query)

        result = runtime.handle_callback(
            "period_profit:7D",
            today="2026-09-14",
        )

        self.assertTrue(result["error"])
        self.assertEqual(
            result["code"],
            "PERIOD_PROFIT_SALE_QUANTITY_EVIDENCE_UNAVAILABLE",
        )
        self.assertEqual(
            [call["compare_previous"] for call in query.calls],
            [True, False],
        )


if __name__ == "__main__":
    unittest.main()
