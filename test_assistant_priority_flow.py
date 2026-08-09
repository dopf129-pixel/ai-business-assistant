import sys
import unittest
from pathlib import Path


sys.path.insert(
    0,
    str(Path(__file__).parent / "app")
)


from services.assistant_priority_service import (
    AssistantPriorityService
)



class TestAssistantPriorityFlow(
    unittest.TestCase
):


    def test_stock_action_gets_high_priority(
        self
    ):

        service = (
            AssistantPriorityService()
        )


        action = {
            "title": "Проверить остатки товара",
            "type": "stock",
            "status": "NEW"
        }


        result = (
            service.resolve(
                action
            )
        )


        self.assertFalse(
            result["error"]
        )


        self.assertEqual(
            result["action"]["priority"],
            "HIGH"
        )


    def test_general_action_gets_low_priority(
        self
    ):

        service = (
            AssistantPriorityService()
        )


        action = {
            "title": "Проверить систему",
            "type": "general",
            "status": "NEW"
        }


        result = (
            service.resolve(
                action
            )
        )


        self.assertEqual(
            result["action"]["priority"],
            "LOW"
        )


if __name__ == "__main__":
    unittest.main()