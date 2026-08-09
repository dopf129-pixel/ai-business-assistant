import sys
import unittest
from pathlib import Path


sys.path.insert(
    0,
    str(Path(__file__).parent / "app")
)


from services.assistant_planning_service import (
    AssistantPlanningService
)


class TestAssistantPlanningFlow(
    unittest.TestCase
):


    def test_build_action_plan(
        self
    ):

        service = (
            AssistantPlanningService()
        )


        recommendations = [
            {
                "type": "stock",
                "message": "Проверить остатки товара"
            },
            {
                "type": "sales",
                "message": "Проверить падение продаж"
            }
        ]


        result = (
            service.build_plan(
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
            result["plan"][0]["step"],
            1
        )


        self.assertEqual(
            result["plan"][0]["type"],
            "stock"
        )


        self.assertEqual(
            result["plan"][1]["step"],
            2
        )


if __name__ == "__main__":
    unittest.main()