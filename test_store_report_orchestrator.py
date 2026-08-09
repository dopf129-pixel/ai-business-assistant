import sys
import unittest
from pathlib import Path


sys.path.insert(
    0,
    str(Path(__file__).parent / "app")
)


from services.store_report_orchestrator import (
    StoreReportOrchestrator
)


class FakeSummaryService:

    def build(
        self,
        period_code,
        date_to,
        products
    ):

        return {
            "error": False,
            "comparison": {
                "status": "🟢 Бизнес растёт"
            }
        }



class FakeInsightService:

    def analyze(
        self,
        summary
    ):

        return {
            "error": False,
            "insights": [
                "Прибыль растёт"
            ]
        }



class FakeFormatter:

    def format(
        self,
        summary
    ):

        return (
            "Сравнение периодов"
        )



class TestStoreReportOrchestrator(
    unittest.TestCase
):


    def test_build_report(
        self
    ):

        service = (
            StoreReportOrchestrator(
                summary_service=(
                    FakeSummaryService()
                ),
                insight_service=(
                    FakeInsightService()
                ),
                formatter=(
                    FakeFormatter()
                )
            )
        )


        result = (
            service.build(
                period_code="28D",
                date_to="2026-08-09",
                products=[]
            )
        )


        self.assertFalse(
            result["error"]
        )


        self.assertIn(
            "period_summary",
            result
        )


        self.assertIn(
            "period_insights",
            result
        )


        self.assertEqual(
            result["period_text"],
            "Сравнение периодов"
        )


if __name__ == "__main__":
    unittest.main()