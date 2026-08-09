import sys
import unittest
from pathlib import Path


sys.path.insert(
    0,
    str(Path(__file__).parent / "app")
)


from services.assistant_business_flow_service import (
    AssistantBusinessFlowService
)

from services.assistant_intent_service import (
    AssistantIntentService
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



class TestAssistantBusinessFlow(
    unittest.TestCase
):


    def test_user_to_business_plan(
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


        planner = (
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


        flow = (
            AssistantBusinessFlowService(
                intent_service=(
                    AssistantIntentService()
                ),
                planner_service=planner
            )
        )


        result = (
            flow.process(
                "Что нужно сделать?",
                {
                    "sales_down": True,
                    "low_stock": True
                }
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
                result["plan"]
            ),
            2
        )


if __name__ == "__main__":
    unittest.main()