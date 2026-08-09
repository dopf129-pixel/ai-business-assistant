import sys
import unittest
from pathlib import Path


sys.path.insert(
    0,
    str(Path(__file__).parent / "app")
)


from services.assistant_business_planner_service import (
    AssistantBusinessPlannerService
)

from services.assistant_recommendation_service import (
    AssistantRecommendationService
)

from services.assistant_planning_service import (
    AssistantPlanningService
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



class TestAssistantBusinessPlannerFlow(
    unittest.TestCase
):


    def test_full_business_plan_flow(
        self
    ):

        history = (
            ActionHistoryService()
        )


        executor = (
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


        service = (
            AssistantBusinessPlannerService(
                recommendation_service=(
                    AssistantRecommendationService()
                ),
                planning_service=(
                    AssistantPlanningService()
                ),
                executor_service=executor
            )
        )


        report = {
            "sales_down": True,
            "low_stock": True
        }


        result = (
            service.build_plan(
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
            len(
                result["recommendations"]
            ),
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