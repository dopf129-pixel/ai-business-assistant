import sys
import unittest
from pathlib import Path


sys.path.insert(
    0,
    str(Path(__file__).parent / "app")
)


from services.store_period_runner_service import (
    StorePeriodRunnerService
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
            "date_from": "2026-06-13",
            "date_to": "2026-07-10"
        }



class FakeReportService:

    def build(
        self,
        current_period,
        previous_period,
        products
    ):

        return {
            "error": False,
            "comparison": {
                "status": "🟢 Бизнес растёт"
            }
        }



class TestStorePeriodRunnerService(
    unittest.TestCase
):


    def test_build_store_period_report(
        self
    ):

        service = (
            StorePeriodRunnerService(
                report_service=(
                    FakeReportService()
                )
            )
        )


        service.period_service = (
            FakePeriodService()
        )


        result = (
            service.build_store_period_report(
                period_code="28D",
                date_to="2026-08-07",
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


    def test_without_products(
        self
    ):

        service = (
            StorePeriodRunnerService(
                report_service=(
                    FakeReportService()
                )
            )
        )


        service.period_service = (
            FakePeriodService()
        )


        result = (
            service.build_store_period_report(
                period_code="28D",
                date_to="2026-08-07",
                products=[]
            )
        )


        self.assertFalse(
            result["error"]
        )


if __name__ == "__main__":
    unittest.main()