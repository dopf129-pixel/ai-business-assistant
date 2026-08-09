import sys
import unittest
from pathlib import Path


sys.path.insert(
    0,
    str(Path(__file__).parent / "app")
)


from services.store_report_history_service import (
    StoreReportHistoryService
)


class TestStoreReportHistoryService(
    unittest.TestCase
):


    def setUp(
        self
    ):

        self.service = (
            StoreReportHistoryService()
        )


    def test_save_report(
        self
    ):

        result = (
            self.service
            .save_report(
                {
                    "period": "28D",
                    "profit": 1000
                }
            )
        )


        self.assertFalse(
            result["error"]
        )


        self.assertTrue(
            result["saved"]
        )


        self.assertEqual(
            result["count"],
            1
        )


    def test_get_report(
        self
    ):

        report = {
            "period": "28D"
        }


        self.service.save_report(
            report
        )


        result = (
            self.service
            .get_report(
                0
            )
        )


        self.assertFalse(
            result["error"]
        )


        self.assertEqual(
            result["report"],
            report
        )


    def test_list_reports(
        self
    ):

        self.service.save_report(
            {
                "period": "7D"
            }
        )

        self.service.save_report(
            {
                "period": "28D"
            }
        )


        result = (
            self.service
            .list_reports()
        )


        self.assertEqual(
            result["count"],
            2
        )


        self.assertEqual(
            len(
                result["reports"]
            ),
            2
        )


    def test_missing_report(
        self
    ):

        result = (
            self.service
            .get_report(
                100
            )
        )


        self.assertTrue(
            result["error"]
        )


if __name__ == "__main__":
    unittest.main()