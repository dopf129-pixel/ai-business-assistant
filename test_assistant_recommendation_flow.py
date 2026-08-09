import sys
import unittest
from pathlib import Path


sys.path.insert(
    0,
    str(Path(__file__).parent / "app")
)


from services.assistant_recommendation_service import (
    AssistantRecommendationService
)



class TestAssistantRecommendationFlow(
    unittest.TestCase
):


    def test_generate_recommendations(
        self
    ):

        service = (
            AssistantRecommendationService()
        )


        report = {
            "sales_down": True,
            "low_stock": True
        }


        result = (
            service.analyze(
                report
            )
        )


        self.assertFalse(
            result["error"]
        )


        self.assertEqual(
            result["count"],
            2
        )


        messages = [
            item["message"]
            for item in result["recommendations"]
        ]


        self.assertIn(
            "Проверить причины падения продаж",
            messages
        )


        self.assertIn(
            "Проверить остатки товара",
            messages
        )


    def test_no_problems(
        self
    ):

        service = (
            AssistantRecommendationService()
        )


        result = (
            service.analyze(
                {}
            )
        )


        self.assertFalse(
            result["error"]
        )


        self.assertEqual(
            result["count"],
            1
        )


if __name__ == "__main__":
    unittest.main()