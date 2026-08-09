import sys
import unittest
from pathlib import Path


sys.path.insert(
    0,
    str(Path(__file__).parent / "app")
)


from services.store_report_dashboard_service import (
    StoreReportDashboardService
)


class TestStoreReportDashboardService(
    unittest.TestCase
):


    def setUp(
        self
    ):

        self.service = (
            StoreReportDashboardService()
        )


    def test_build_dashboard(
        self
    ):

        report = {
            "error": False,

            "period_summary": {
                "period": "28D"
            },

            "period_insights": {
                "insights": [
                    "Прибыль растёт быстрее выручки"
                ],

                "recommendations": [
                    "Проверить товары роста"
                ]
            },

            "period_text": (
                "Итоговый отчёт"
            )
        }


        result = (
            self.service
            .build(
                report
            )
        )


        self.assertFalse(
            result["error"]
        )


        self.assertEqual(
            result["period"],
            "28D"
        )


        self.assertEqual(
            len(
                result["insights"]
            ),
            1
        )


        self.assertEqual(
            len(
                result["recommendations"]
            ),
            1
        )


    def test_build_dashboard_error(
        self
    ):

        result = (
            self.service
            .build(
                {
                    "error": True,
                    "message": "Ошибка"
                }
            )
        )


        self.assertTrue(
            result["error"]
        )


        self.assertEqual(
            result["message"],
            "Ошибка"
        )


if __name__ == "__main__":
    unittest.main()