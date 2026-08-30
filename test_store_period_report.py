import sys
import unittest
from pathlib import Path


sys.path.insert(
    0,
    str(Path(__file__).parent / "app")
)


from services.store_period_report_service import (
    StorePeriodReportService
)


class FakeProfitService:

    def calculate_period_profit(
        self,
        date_from,
        date_to,
        products
    ):

        return {
            "error": False,
            "business_profit": 3000,
            "gross_sales": 10000,
            "margin_percent": 30
        }



class FakeComparisonReport:

    def build_report(
        self,
        current_result,
        previous_result,
        current_period,
        previous_period
    ):

        return {
            "error": False,
            "comparison": {
                "status": "🟢 Бизнес растёт"
            }
        }



class TestStorePeriodReportService(
    unittest.TestCase
):


    def test_build_report(
        self
    ):

        service = StorePeriodReportService(
            profit_service=FakeProfitService(),
            comparison_report_service=(
                FakeComparisonReport()
            )
        )


        result = (
            service.build(
                current_period={
                    "date_from": "2026-07-11",
                    "date_to": "2026-08-07"
                },
                previous_period={
                    "date_from": "2026-06-13",
                    "date_to": "2026-07-10"
                },
                products=[
                    {
                        "sku": "123"
                    }
                ]
            )
        )


        self.assertFalse(
            result["error"]
        )


        self.assertEqual(
            result["comparison"]["status"],
            "🟢 Бизнес растёт"
        )


    def test_v510_missing_profit_service_fails_closed(
        self
    ):

        service = StorePeriodReportService(
            profit_service=None
        )

        result = service.build(
            current_period={
                "date_from": "2026-07-11",
                "date_to": "2026-08-07"
            },
            previous_period={
                "date_from": "2026-06-13",
                "date_to": "2026-07-10"
            },
            products=[]
        )

        self.assertTrue(result["error"])
        self.assertEqual(
            result["message"],
            "Сервис расчёта прибыли периода недоступен"
        )


    def test_without_current_period(
        self
    ):

        service = StorePeriodReportService(
            profit_service=FakeProfitService()
        )


        result = (
            service.build(
                current_period=None,
                previous_period={
                    "date_from": "2026-06-13"
                },
                products=[]
            )
        )


        self.assertTrue(
            result["error"]
        )


if __name__ == "__main__":
    unittest.main()