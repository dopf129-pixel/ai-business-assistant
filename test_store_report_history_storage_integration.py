import sys
import unittest
from pathlib import Path
import tempfile


sys.path.insert(
    0,
    str(Path(__file__).parent / "app")
)


from services.store_report_history_service import (
    StoreReportHistoryService
)

from services.store_report_storage_service import (
    StoreReportStorageService
)


class TestStoreReportHistoryStorageIntegration(
    unittest.TestCase
):


    def test_history_persists_reports(
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


            history.save_report(
                {
                    "period": "28D",
                    "profit": 1000
                }
            )


            new_history = (
                StoreReportHistoryService(
                    storage_service=storage
                )
            )


            result = (
                new_history.list_reports()
            )


            self.assertEqual(
                result["count"],
                1
            )


            self.assertEqual(
                result["reports"][0]["period"],
                "28D"
            )


if __name__ == "__main__":
    unittest.main()