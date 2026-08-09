import sys
import unittest
from pathlib import Path
import tempfile


sys.path.insert(
    0,
    str(Path(__file__).parent / "app")
)


from services.store_report_storage_service import (
    StoreReportStorageService
)


class TestStoreReportStorageService(
    unittest.TestCase
):


    def test_save_and_load(
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


            reports = [
                {
                    "period": "28D",
                    "profit": 1000
                }
            ]


            result = (
                storage.save(
                    reports
                )
            )


            self.assertTrue(
                result
            )


            loaded = (
                storage.load()
            )


            self.assertEqual(
                loaded,
                reports
            )


    def test_load_empty_storage(
        self
    ):

        with tempfile.TemporaryDirectory() as folder:

            file_path = (
                Path(folder)
                /
                "empty.json"
            )


            storage = (
                StoreReportStorageService(
                    file_path=file_path
                )
            )


            result = (
                storage.load()
            )


            self.assertEqual(
                result,
                []
            )


if __name__ == "__main__":
    unittest.main()