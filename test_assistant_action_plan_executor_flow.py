import sys
import unittest
from pathlib import Path


sys.path.insert(
    0,
    str(Path(__file__).parent / "app")
)


from services.assistant_action_plan_executor_service import (
    AssistantActionPlanExecutorService
)

from services.assistant_priority_service import (
    AssistantPriorityService
)

from services.assistant_action_generator_service import (
    AssistantActionGeneratorService
)

from services.assistant_action_execution_service import (
    AssistantActionExecutionService
)

from services.action_history_service import (
    ActionHistoryService
)



class TestAssistantActionPlanExecutorFlow(
    unittest.TestCase
):


    def test_execute_full_plan(
        self
    ):

        history = (
            ActionHistoryService()
        )


        service = (
            AssistantActionPlanExecutorService(
                priority_service=(
                    AssistantPriorityService()
                ),
                action_generator_service=(
                    AssistantActionGeneratorService()
                ),
                execution_service=(
                    AssistantActionExecutionService(
                        history
                    )
                )
            )
        )


        plan = [
            {
                "step": 1,
                "type": "stock",
                "action": (
                    "Проверить остатки товара"
                )
            },
            {
                "step": 2,
                "type": "sales",
                "action": (
                    "Проверить падение продаж"
                )
            }
        ]


        result = (
            service.execute_plan(
                plan
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
            result["actions"][0]["priority"],
            "HIGH"
        )


        history_result = (
            history.list_actions()
        )


        self.assertEqual(
            history_result["count"],
            2
        )


if __name__ == "__main__":
    unittest.main()