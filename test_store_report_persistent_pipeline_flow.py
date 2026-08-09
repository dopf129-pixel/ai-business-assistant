import sys
import unittest
from pathlib import Path
import tempfile


sys.path.insert(
    0,
    str(Path(__file__).parent / "app")
)


from services.store_report_pipeline_service import (
    StoreReportPipelineService
)

from services.store_report_history_service import (
    StoreReportHistoryService
)

from services.store_report_storage_service import (
    StoreReportStorageService
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
            "period": period_code,
            "profit": 1000
        }



class TestPersistentPipelineFlow(
    unittest.TestCase
):


    def test_pipeline_saves_report_to_storage(
        self
    ):

        with tempfile.TemporaryDirectory() as folder:

            file_path = (
                Path(folder)
                /
                "reports.json"
            )


            storage = (
                StoreReportStorageService(
                    file_path=file_path
                )
            )


            history = (
                StoreReportHistoryService(
                    storage_service=storage
                )
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


            new_history = (
                StoreReportHistoryService(
                    storage_service=storage
                )
            )


            reports = (
                new_history.list_reports()
            )


            self.assertEqual(
                reports["count"],
                1
            )


            self.assertEqual(
                reports["reports"][0]["period"],
                "28D"
            )


if __name__ == "__main__":
    unittest.main()