import sys
import unittest
from pathlib import Path


sys.path.insert(
    0,
    str(Path(__file__).parent / "app")
)


from services.assistant_action_generator_service import (
    AssistantActionGeneratorService
)



class TestAssistantActionGeneratorFlow(
    unittest.TestCase
):


    def test_generate_actions_from_recommendations(
        self
    ):

        service = (
            AssistantActionGeneratorService()
        )


        recommendations = [
            {
                "type": "stock",
                "message": (
                    "Проверить остатки товара"
                )
            },
            {
                "type": "sales",
                "message": (
                    "Проверить причины падения продаж"
                )
            }
        ]


        result = (
            service.generate(
                recommendations
            )
        )


        self.assertFalse(
            result["error"]
        )


        self.assertEqual(
            result["count"],
            2
        )


        self.assertEqual(
            result["actions"][0]["status"],
            "NEW"
        )


        self.assertEqual(
            result["actions"][0]["type"],
            "stock"
        )


        self.assertEqual(
            result["actions"][1]["type"],
            "sales"
        )



    def test_empty_recommendations(
        self
    ):

        service = (
            AssistantActionGeneratorService()
        )


        result = (
            service.generate(
                []
            )
        )


        self.assertFalse(
            result["error"]
        )


        self.assertEqual(
            result["count"],
            0
        )


if __name__ == "__main__":
    unittest.main()