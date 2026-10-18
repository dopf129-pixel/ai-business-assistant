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
        if self.current_error:
            return {
                "error": True,
                "code": "PERIOD_PROFIT_SALE_QUANTITY_EVIDENCE_UNAVAILABLE",
                "status": "PERIOD_PROFIT_SUMMARY_UNAVAILABLE",
                "read_only": True,
                "executed": False,
            }
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
    def test_current_quantity_failure_is_returned_without_retrying_whole_query(self):
        query = _Query()
        query.current_error = True
        runtime = AssistantPeriodProfitRuntimeService(query)

        result = runtime.handle_callback(
            "period_profit:7D",
            today="2026-09-14",
        )

        self.assertTrue(result["error"])
        self.assertEqual(result["code"], "PERIOD_PROFIT_SALE_QUANTITY_EVIDENCE_UNAVAILABLE")
        self.assertEqual([call["compare_previous"] for call in query.calls], [True])
        self.assertTrue(result["read_only"])
        self.assertFalse(result["executed"])

    def test_optional_previous_error_is_presented_when_service_preserves_current(self):
        query = _Query(current_error=True)
        query.current_error = False

        def query_with_optional_error(**kwargs):
            query.calls.append(dict(kwargs))
            result = _Query(current_error=False).query(compare_previous=False)
            result["comparison_status"] = "PERIOD_PROFIT_COMPARISON_UNAVAILABLE"
            result["comparison_error_code"] = "TEST_PREVIOUS_RETURN_UNAVAILABLE"
            return result

        query.query = query_with_optional_error
        runtime = AssistantPeriodProfitRuntimeService(query)

        result = runtime.handle_callback(
            "period_profit:7D",
            today="2026-09-14",
        )

        self.assertFalse(result["error"])
        self.assertEqual(result["summary"]["profit"], 29.0)
        self.assertEqual(result["comparison_status"], "PERIOD_PROFIT_COMPARISON_UNAVAILABLE")
        self.assertEqual(len(query.calls), 1)
        self.assertTrue(query.calls[0]["compare_previous"])
        self.assertIn("💰 Прибыль за период", result["text"])


if __name__ == "__main__":
    unittest.main()
