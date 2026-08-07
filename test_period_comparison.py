import sys
import unittest
from pathlib import Path

sys.path.insert(
    0,
    str(Path(__file__).parent / "app")
)

from services.period_comparison_service import (
    PeriodComparisonService
)


class TestPeriodComparisonService(
    unittest.TestCase
):

    def setUp(
        self
    ):

        self.service = (
            PeriodComparisonService()
        )


    def test_business_growth(
        self
    ):

        current = {
            "store_profit": {
                "gross_sales": 12000,
                "gross_profit": 6000
            },
            "business_profit": {
                "business_profit": 4000,
                "margin_percent": 33.3
            }
        }

        previous = {
            "store_profit": {
                "gross_sales": 10000,
                "gross_profit": 5000
            },
            "business_profit": {
                "business_profit": 3000,
                "margin_percent": 30
            }
        }

        result = (
            self.service
            .compare(
                current,
                previous
            )
        )

        self.assertFalse(
            result["error"]
        )

        self.assertEqual(
            result["status"],
            "🟢 Бизнес растёт"
        )

        self.assertEqual(
            result["comparison"]["revenue"]["change_percent"],
            20.0
        )

        self.assertEqual(
            result["comparison"]["business_profit"]["change_percent"],
            33.33
        )


    def test_business_decline(
        self
    ):

        current = {
            "store_profit": {
                "gross_sales": 8000,
                "gross_profit": 3000
            },
            "business_profit": {
                "business_profit": 1000,
                "margin_percent": 12
            }
        }

        previous = {
            "store_profit": {
                "gross_sales": 10000,
                "gross_profit": 5000
            },
            "business_profit": {
                "business_profit": 3000,
                "margin_percent": 30
            }
        }

        result = (
            self.service
            .compare(
                current,
                previous
            )
        )

        self.assertFalse(
            result["error"]
        )

        self.assertEqual(
            result["status"],
            "🔴 Бизнес ухудшается"
        )

        self.assertEqual(
            result["comparison"]["revenue"]["change_percent"],
            -20.0
        )

        self.assertEqual(
            result["comparison"]["business_profit"]["change_percent"],
            -66.67
        )


    def test_stable_business(
        self
    ):

        current = {
            "store_profit": {
                "gross_sales": 10000,
                "gross_profit": 5000
            },
            "business_profit": {
                "business_profit": 3000,
                "margin_percent": 30
            }
        }

        previous = {
            "store_profit": {
                "gross_sales": 10000,
                "gross_profit": 5000
            },
            "business_profit": {
                "business_profit": 3000,
                "margin_percent": 30
            }
        }

        result = (
            self.service
            .compare(
                current,
                previous
            )
        )

        self.assertFalse(
            result["error"]
        )

        self.assertEqual(
            result["status"],
            "🟡 Стабильное состояние"
        )


    def test_zero_previous_value(
        self
    ):

        result = (
            self.service
            .safe_percent_change(
                100,
                0
            )
        )

        self.assertEqual(
            result,
            100.0
        )


    def test_zero_values(
        self
    ):

        result = (
            self.service
            .safe_percent_change(
                0,
                0
            )
        )

        self.assertEqual(
            result,
            0.0
        )


    def test_missing_period_data(
        self
    ):

        result = (
            self.service
            .compare(
                None,
                {}
            )
        )

        self.assertTrue(
            result["error"]
        )


if __name__ == "__main__":
    unittest.main()