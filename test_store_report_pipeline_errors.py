import sys
import unittest
from pathlib import Path


sys.path.insert(
    0,
    str(Path(__file__).parent / "app")
)


from services.store_report_pipeline_service import (
    StoreReportPipelineService
)


class ErrorReportManager:

    def build_store_report(
        self,
        period_code,
        date_to,
        products
    ):

        return {
            "error": True,
            "message": "Ошибка отчёта"
        }


class HistoryService:

    def __init__(self):

        self.saved = []


    def save_report(
        self,
        report
    ):

        self.saved.append(report)


class TestStoreReportPipelineErrors(
    unittest.TestCase
):


    def test_report_error_not_saved(
        self
    ):

        history = HistoryService()

        pipeline = (
            StoreReportPipelineService(
                report_manager=(
                    ErrorReportManager()
                ),
                history_service=history
            )
        )


        result = (
            pipeline.build_and_save(
                period_code="28D",
                date_to="2026-08-09",
                products=[]
            )
        )


        self.assertTrue(
            result["error"]
        )


        self.assertEqual(
            len(history.saved),
            0
        )


if __name__ == "__main__":
    unittest.main()