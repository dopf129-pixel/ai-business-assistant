import sys
import unittest
from pathlib import Path

sys.path.insert(
    0,
    str(Path(__file__).parent / "app")
)

from services.store_period_analytics_service import (
    StorePeriodAnalyticsService
)


class FakePeriodService:

    def get_period(
        self,
        period_code,
        date_to
    ):

        return {
            "error": False,
            "code": period_code,
            "date_from": "2026-07-11",
            "date_to": date_to,
            "label": "Последние 28 дней"
        }


    def get_previous_period(
        self,
        period_code,
        date_to
    ):

        return {
            "error": False,
            "code": period_code,
            "date_from": "2026-06-13",
            "date_to": "2026-07-10",
            "label": "Предыдущие 28 дней"
        }


class FakeAnalytics:

    def __init__(
        self,
        result
    ):

        self.result = result

    def analyze(
        self,
        profits
    ):

        return self.result


class FakeComparison:

    def compare(
        self,
        current,
        previous
    ):

        return {
            "error": False,
            "status": "🟢 Бизнес растёт"
        }


class TestStorePeriodAnalyticsService(
    unittest.TestCase
):

    def test_period_analysis_without_previous(
        self
    ):

        def factory(
            period
        ):

            return FakeAnalytics(
                {
                    "business_profit": {
                        "business_profit": 1000
                    }
                }
            )


        service = StorePeriodAnalyticsService(
            factory
        )

        service.period_service = (
            FakePeriodService()
        )

        result = (
            service.analyze_periods(
                period_code="28D",
                date_to="2026-08-07",
                current_profits=[
                    {
                        "profit": 100
                    }
                ]
            )
        )

        self.assertFalse(
            result["error"]
        )

        self.assertTrue(
            result["comparison"]["error"]
        )


    def test_period_analysis_with_comparison(
        self
    ):

        counter = {
            "value": 0
        }


        def factory(
            period
        ):

            counter["value"] += 1

            return FakeAnalytics(
                {
                    "store_profit": {
                        "gross_sales": (
                            10000
                            *
                            counter["value"]
                        ),
                        "gross_profit": 5000
                    },
                    "business_profit": {
                        "business_profit": (
                            3000
                            *
                            counter["value"]
                        ),
                        "margin_percent": 30
                    }
                }
            )


        service = StorePeriodAnalyticsService(
            factory
        )

        service.period_service = (
            FakePeriodService()
        )

        service.comparison_service = (
            FakeComparison()
        )

        result = (
            service.analyze_periods(
                period_code="28D",
                date_to="2026-08-07",
                current_profits=[
                    {}
                ],
                previous_profits=[
                    {}
                ]
            )
        )

        self.assertFalse(
            result["error"]
        )

        self.assertIn(
            "current",
            result
        )

        self.assertIn(
            "previous",
            result
        )

        self.assertFalse(
            result["comparison"]["error"]
        )

        self.assertEqual(
            result["comparison"]["status"],
            "🟢 Бизнес растёт"
        )


if __name__ == "__main__":
    unittest.main()