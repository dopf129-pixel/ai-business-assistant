import sys
import unittest
from pathlib import Path

sys.path.insert(
    0,
    str(Path(__file__).parent / "app")
)

from services.analysis_period_service import (
    AnalysisPeriodService
)


class TestAnalysisPeriodService(unittest.TestCase):

    def setUp(self):

        self.service = (
            AnalysisPeriodService()
        )

    def test_today_period(self):

        result = (
            self.service
            .get_period(
                "TODAY",
                "2026-08-07"
            )
        )

        self.assertFalse(
            result["error"]
        )

        self.assertEqual(
            result["date_from"],
            "2026-08-07"
        )

        self.assertEqual(
            result["date_to"],
            "2026-08-07"
        )

        self.assertEqual(
            result["days"],
            1
        )

    def test_7_days_period(self):

        result = (
            self.service
            .get_period(
                "7D",
                "2026-08-07"
            )
        )

        self.assertEqual(
            result["date_from"],
            "2026-08-01"
        )

        self.assertEqual(
            result["date_to"],
            "2026-08-07"
        )

        self.assertEqual(
            result["days"],
            7
        )

    def test_28_days_period(self):

        result = (
            self.service
            .get_period(
                "28D",
                "2026-08-07"
            )
        )

        self.assertEqual(
            result["date_from"],
            "2026-07-11"
        )

        self.assertEqual(
            result["date_to"],
            "2026-08-07"
        )

        self.assertEqual(
            result["days"],
            28
        )

    def test_56_days_period(self):

        result = (
            self.service
            .get_period(
                "56D",
                "2026-08-07"
            )
        )

        self.assertEqual(
            result["date_from"],
            "2026-06-13"
        )

        self.assertEqual(
            result["date_to"],
            "2026-08-07"
        )

        self.assertEqual(
            result["days"],
            56
        )

    def test_90_days_period(self):

        result = (
            self.service
            .get_period(
                "90D",
                "2026-08-07"
            )
        )

        self.assertEqual(
            result["date_from"],
            "2026-05-10"
        )

        self.assertEqual(
            result["date_to"],
            "2026-08-07"
        )

        self.assertEqual(
            result["days"],
            90
        )

    def test_all_time_period(self):

        result = (
            self.service
            .get_period(
                "ALL",
                "2026-08-07"
            )
        )

        self.assertFalse(
            result["error"]
        )

        self.assertIsNone(
            result["date_from"]
        )

        self.assertEqual(
            result["date_to"],
            "2026-08-07"
        )

        self.assertIsNone(
            result["days"]
        )

    def test_previous_28_days_period(self):

        result = (
            self.service
            .get_previous_period(
                "28D",
                "2026-08-07"
            )
        )

        self.assertFalse(
            result["error"]
        )

        self.assertEqual(
            result["date_from"],
            "2026-06-13"
        )

        self.assertEqual(
            result["date_to"],
            "2026-07-10"
        )

    def test_previous_today_period(self):

        result = (
            self.service
            .get_previous_period(
                "TODAY",
                "2026-08-07"
            )
        )

        self.assertEqual(
            result["date_from"],
            "2026-08-06"
        )

        self.assertEqual(
            result["date_to"],
            "2026-08-06"
        )

    def test_previous_all_time_not_supported(self):

        result = (
            self.service
            .get_previous_period(
                "ALL",
                "2026-08-07"
            )
        )

        self.assertTrue(
            result["error"]
        )

    def test_unknown_period(self):

        result = (
            self.service
            .get_period(
                "UNKNOWN",
                "2026-08-07"
            )
        )

        self.assertTrue(
            result["error"]
        )

        self.assertEqual(
            result["message"],
            "Неизвестный период анализа"
        )

    def test_available_periods(self):

        periods = (
            self.service
            .get_available_periods()
        )

        codes = [
            item["code"]
            for item in periods
        ]

        self.assertEqual(
            codes,
            [
                "TODAY",
                "7D",
                "28D",
                "56D",
                "90D",
                "ALL"
            ]
        )


if __name__ == "__main__":
    unittest.main()