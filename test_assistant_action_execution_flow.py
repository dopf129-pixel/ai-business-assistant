import sys
import unittest
from pathlib import Path


sys.path.insert(
    0,
    str(Path(__file__).parent / "app")
)


from services.assistant_action_execution_service import (
    AssistantActionExecutionService
)

from services.action_history_service import (
    ActionHistoryService
)


class TestAssistantActionExecutionFlow(
    unittest.TestCase
):


    def test_execute_generated_actions(
        self
    ):

        history = (
            ActionHistoryService()
        )


        executor = (
            AssistantActionExecutionService(
                history_service=history
            )
        )


        actions = [
            {
                "title": "Проверить остатки товара",
                "type": "stock",
                "status": "NEW"
            },
            {
                "title": "Проверить продажи",
                "type": "sales",
                "status": "NEW"
            }
        ]


        result = (
            executor.execute(
                actions
            )
        )


        self.assertFalse(
            result["error"]
        )


        self.assertEqual(
            result["count"],
            2
        )


        history_result = (
            history.list_actions()
        )


        self.assertEqual(
            history_result["count"],
            2
        )


        self.assertEqual(
            history_result["actions"][0]["type"],
            "stock"
        )


        self.assertEqual(
            history_result["actions"][1]["type"],
            "sales"
        )


if __name__ == "__main__":
    unittest.main()