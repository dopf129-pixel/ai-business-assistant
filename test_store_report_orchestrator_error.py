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


class ErrorSummaryService:

    def build(
        self,
        period_code,
        date_to,
        products
    ):

        return {
            "error": True,
            "message": "Ошибка построения отчёта"
        }



class FailingInsightService:

    def analyze(
        self,
        summary
    ):

        raise Exception(
            "Insight не должен был запускаться"
        )



class FailingFormatter:

    def format(
        self,
        summary
    ):

        raise Exception(
            "Formatter не должен был запускаться"
        )



class TestStoreReportOrchestratorError(
    unittest.TestCase
):


    def test_summary_error_stops_flow(
        self
    ):

        orchestrator = (
            StoreReportOrchestrator(
                summary_service=(
                    ErrorSummaryService()
                ),
                insight_service=(
                    FailingInsightService()
                ),
                formatter=(
                    FailingFormatter()
                )
            )
        )


        result = (
            orchestrator.build(
                period_code="28D",
                date_to="2026-08-09",
                products=[]
            )
        )


        self.assertTrue(
            result["error"]
        )


        self.assertEqual(
            result["message"],
            "Ошибка построения отчёта"
        )


        self.assertIn(
            "period_summary",
            result
        )


if __name__ == "__main__":
    unittest.main()