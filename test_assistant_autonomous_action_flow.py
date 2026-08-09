import sys
import unittest
from pathlib import Path


sys.path.insert(
    0,
    str(Path(__file__).parent / "app")
)


from services.assistant_autonomous_action_service import (
    AssistantAutonomousActionService
)

from services.assistant_recommendation_service import (
    AssistantRecommendationService
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



class TestAssistantAutonomousActionFlow(
    unittest.TestCase
):


    def test_full_autonomous_action_cycle(
        self
    ):

        history = (
            ActionHistoryService()
        )


        service = (
            AssistantAutonomousActionService(
                recommendation_service=(
                    AssistantRecommendationService()
                ),
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


        report = {
            "sales_down": True,
            "low_stock": True
        }


        result = (
            service.execute_plan(
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