import sys
import unittest
from pathlib import Path


sys.path.insert(
    0,
    str(Path(__file__).parent)
)


from services.store_period_analytics_service import (
    StorePeriodAnalyticsService
)


class FakeStoreAnalytics:

    def __init__(
        self,
        period
    ):

        self.period = period


    def analyze(
        self,
        profits
    ):

        return {
            "error": False,

            "analysis_period": self.period,

            "store_profit": {
                "gross_sales": 10000,
                "gross_profit": 5000
            },

            "business_profit": {
                "business_profit": 3000,
                "margin_percent": 30
            }
        }



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



class FakePeriodService:

    def get_period(
        self,
        period_code,
        date_to
    ):

        return {
            "error": False,
            "code": period_code,
            "label": "Последние 28 дней",
            "date_from": "2026-07-11",
            "date_to": date_to
        }


    def get_previous_period(
        self,
        period_code,
        date_to
    ):

        return {
            "error": False,
            "code": period_code,
            "label": "Предыдущие 28 дней",
            "date_from": "2026-06-13",
            "date_to": "2026-07-10"
        }



class TestPeriodIntegration(
    unittest.TestCase
):


    def test_full_period_flow(
        self
    ):

        def factory(
            period
        ):

            return FakeStoreAnalytics(
                period
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
                    {
                        "profit": 100
                    }
                ],
                previous_profits=[
                    {
                        "profit": 90
                    }
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