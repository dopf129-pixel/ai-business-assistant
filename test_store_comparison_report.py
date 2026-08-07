import sys
import unittest
from pathlib import Path


sys.path.insert(
    0,
    str(Path(__file__).parent / "app")
)


from services.store_comparison_report_service import (
    StoreComparisonReportService
)


class FakeComparisonService:

    def compare(
        self,
        current,
        previous
    ):

        return {
            "error": False,
            "status": "🟢 Бизнес растёт",
            "comparison": {
                "revenue": {
                    "name": "Выручка",
                    "current": 12000,
                    "previous": 10000,
                    "change_percent": 20,
                    "trend": "Рост"
                },

                "business_profit": {
                    "name": "Прибыль после расходов",
                    "current": 4000,
                    "previous": 3000,
                    "change_percent": 33.33,
                    "trend": "Рост"
                }
            }
        }



class TestStoreComparisonReportService(
    unittest.TestCase
):


    def test_build_report(
        self
    ):

        service = (
            StoreComparisonReportService(
                comparison_service=(
                    FakeComparisonService()
                )
            )
        )


        current = {
            "business_profit": {
                "business_profit": 4000
            }
        }


        previous = {
            "business_profit": {
                "business_profit": 3000
            }
        }


        result = (
            service.build_report(
                current_result=current,
                previous_result=previous,
                current_period={
                    "code": "28D"
                },
                previous_period={
                    "code": "28D"
                }
            )
        )


        self.assertFalse(
            result["error"]
        )


        self.assertIn(
            "comparison",
            result
        )


        self.assertEqual(
            result["comparison"]["status"],
            "🟢 Бизнес растёт"
        )


    def test_without_previous_result(
        self
    ):

        service = (
            StoreComparisonReportService()
        )


        result = (
            service.build_report(
                current_result={
                    "test": True
                },
                previous_result=None
            )
        )


        self.assertTrue(
            result["error"]
        )


if __name__ == "__main__":
    unittest.main()