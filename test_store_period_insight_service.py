import sys
import unittest
from pathlib import Path


sys.path.insert(
    0,
    str(Path(__file__).parent / "app")
)


from services.store_period_insight_service import (
    StorePeriodInsightService
)


class TestStorePeriodInsightService(
    unittest.TestCase
):


    def test_growth_insights(
        self
    ):

        service = (
            StorePeriodInsightService()
        )


        summary = {
            "error": False,
            "comparison": {
                "status": "🟢 Бизнес растёт",
                "comparison": {
                    "revenue": {
                        "change_percent": 20
                    },
                    "business_profit": {
                        "change_percent": 35
                    },
                    "margin": {
                        "trend": "Рост"
                    }
                }
            }
        }


        result = (
            service.analyze(
                summary
            )
        )


        self.assertFalse(
            result["error"]
        )


        self.assertGreater(
            len(result["insights"]),
            0
        )


        self.assertGreater(
            len(result["recommendations"]),
            0
        )


    def test_error_summary(
        self
    ):

        service = (
            StorePeriodInsightService()
        )


        result = (
            service.analyze(
                {
                    "error": True
                }
            )
        )


        self.assertTrue(
            result["error"]
        )


        self.assertEqual(
            result["insights"],
            []
        )


if __name__ == "__main__":
    unittest.main()