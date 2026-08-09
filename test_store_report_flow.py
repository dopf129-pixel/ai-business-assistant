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

from services.store_report_manager import (
    StoreReportManager
)


class FakeSummaryService:

    def build(
        self,
        period_code,
        date_to,
        products
    ):

        return {
            "period_code": period_code,
            "date_to": date_to,
            "products": products,
            "profit": 1000
        }



class FakeInsightService:

    def analyze(
        self,
        summary
    ):

        return {
            "growth": True,
            "message": "Продажи растут"
        }



class FakeFormatter:

    def format(
        self,
        summary
    ):

        return "Итоговый отчёт магазина"



class TestStoreReportFlow(
    unittest.TestCase
):

    def test_full_store_report_flow(
        self
    ):

        orchestrator = (
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


        manager = (
            StoreReportManager(
                orchestrator=(
                    orchestrator
                )
            )
        )


        result = (
            manager.build_store_report(
                period_code="28D",
                date_to="2026-08-09",
                products=[]
            )
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
            "Итоговый отчёт магазина"
        )



if __name__ == "__main__":
    unittest.main()