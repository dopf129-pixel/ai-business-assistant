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


class SuccessSummaryService:

    def build(
        self,
        period_code,
        date_to,
        products
    ):

        return {
            "error": False,
            "period": "28D"
        }


class ErrorInsightService:

    def analyze(
        self,
        summary
    ):

        raise Exception(
            "Insight error"
        )


class ErrorFormatter:

    def format(
        self,
        summary
    ):

        raise Exception(
            "Formatter error"
        )


class SuccessInsightService:

    def analyze(
        self,
        summary
    ):

        return {
            "error": False
        }


class TestStoreReportOrchestratorServiceErrors(
    unittest.TestCase
):


    def test_insight_error(
        self
    ):

        orchestrator = (
            StoreReportOrchestrator(
                summary_service=SuccessSummaryService(),
                insight_service=ErrorInsightService(),
                formatter=ErrorFormatter()
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

        self.assertIn(
            "Insight",
            result["message"]
        )


    def test_formatter_error(
        self
    ):

        orchestrator = (
            StoreReportOrchestrator(
                summary_service=SuccessSummaryService(),
                insight_service=SuccessInsightService(),
                formatter=ErrorFormatter()
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

        self.assertIn(
            "форматирования",
            result["message"]
        )


if __name__ == "__main__":
    unittest.main()