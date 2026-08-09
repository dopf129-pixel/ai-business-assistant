import sys
import unittest
from pathlib import Path


sys.path.insert(
    0,
    str(Path(__file__).parent / "app")
)


from services.recommendation_service import (
    RecommendationService
)


class TestRecommendationService(
    unittest.TestCase
):


    def setUp(
        self
    ):

        self.service = (
            RecommendationService()
        )


    def test_build_recommendations(
        self
    ):

        result = (
            self.service
            .build(
                [
                    "Проверить товары роста",
                    "Оценить рекламные расходы"
                ]
            )
        )


        self.assertFalse(
            result["error"]
        )


        self.assertEqual(
            len(
                result["recommendations"]
            ),
            2
        )


        self.assertEqual(
            result["recommendations"][0]["title"],
            "Проверить товары роста"
        )


        self.assertEqual(
            result["recommendations"][0]["status"],
            "NEW"
        )


    def test_empty_insights(
        self
    ):

        result = (
            self.service
            .build(
                []
            )
        )


        self.assertFalse(
            result["error"]
        )


        self.assertEqual(
            result["recommendations"],
            []
        )


if __name__ == "__main__":
    unittest.main()