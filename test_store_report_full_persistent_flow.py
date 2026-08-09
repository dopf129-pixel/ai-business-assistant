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

from services.store_report_manager import (
    StoreReportManager
)

from services.store_report_history_service import (
    StoreReportHistoryService
)

from services.store_report_storage_service import (
    StoreReportStorageService
)


class TestStoreReportFullPersistentFlow(
    unittest.TestCase
):


    def test_full_report_persistent_flow(
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


            manager = (
                StoreReportManager(
                    orchestrator=(
                        self.create_orchestrator()
                    )
                )
            )


            pipeline = (
                StoreReportPipelineService(
                    report_manager=manager,
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


            restored_history = (
                StoreReportHistoryService(
                    storage_service=storage
                )
            )


            reports = (
                restored_history
                .list_reports()
            )


            self.assertEqual(
                reports["count"],
                1
            )


    def create_orchestrator(
        self
    ):

        class FakeOrchestrator:

            def build(
                self,
                period_code,
                date_to,
                products
            ):

                return {
                    "error": False,
                    "period_summary": {
                        "period": period_code
                    },
                    "period_insights": {},
                    "period_text": "OK"
                }


        return FakeOrchestrator()


if __name__ == "__main__":
    unittest.main()