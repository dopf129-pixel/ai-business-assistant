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


class FakeReportManager:

    def build_store_report(
        self,
        period_code,
        date_to,
        products
    ):

        return {
            "error": False,
            "period": period_code
        }



class FakeHistoryService:

    def __init__(
        self
    ):

        self.saved = []


    def save_report(
        self,
        report
    ):

        self.saved.append(
            report
        )

        return {
            "error": False
        }



class TestStoreReportPipelineService(
    unittest.TestCase
):


    def test_build_and_save(
        self
    ):

        history = (
            FakeHistoryService()
        )


        pipeline = (
            StoreReportPipelineService(
                report_manager=(
                    FakeReportManager()
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


        self.assertFalse(
            result["error"]
        )


        self.assertEqual(
            len(history.saved),
            1
        )


        self.assertEqual(
            history.saved[0]["period"],
            "28D"
        )


if __name__ == "__main__":
    unittest.main()