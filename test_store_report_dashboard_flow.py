import sys
import unittest
from pathlib import Path


sys.path.insert(
    0,
    str(Path(__file__).parent / "app")
)


from services.store_report_presentation_service import (
    StoreReportPresentationService
)


class FakeDashboardService:

    def build(
        self,
        report
    ):

        return {
            "error": False,
            "period": "28D",
            "status": "🟢 Бизнес растёт",
            "insights": [
                "Прибыль растёт"
            ],
            "recommendations": [
                "Проверить товары роста"
            ]
        }



class TestStoreReportDashboardFlow(
    unittest.TestCase
):


    def test_full_dashboard_flow(
        self
    ):

        presentation = (
            StoreReportPresentationService(
                dashboard_service=(
                    FakeDashboardService()
                )
            )
        )


        result = (
            presentation.build(
                {
                    "error": False,
                    "period_summary": {},
                    "period_insights": {}
                }
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


if __name__ == "__main__":
    unittest.main()