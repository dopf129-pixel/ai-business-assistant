from services.assistant_orchestrator_v2_service import (
    AssistantOrchestratorV2Service
)

from services.assistant_entry_service import (
    AssistantEntryService
)

from services.assistant_main_flow_service import (
    AssistantMainFlowService
)

from services.assistant_business_flow_service import (
    AssistantBusinessFlowService
)

from services.assistant_orchestrator_business_service import (
    AssistantOrchestratorBusinessService
)

from services.assistant_business_planner_service import (
    AssistantBusinessPlannerService
)

from services.assistant_planning_service import (
    AssistantPlanningService
)

from services.assistant_recommendation_service import (
    AssistantRecommendationService
)

from services.assistant_action_plan_executor_service import (
    AssistantActionPlanExecutorService
)

from services.assistant_action_generator_service import (
    AssistantActionGeneratorService
)

from services.assistant_action_execution_service import (
    AssistantActionExecutionService
)

from services.assistant_priority_service import (
    AssistantPriorityService
)

from services.assistant_response_builder_service import (
    AssistantResponseBuilderService
)

from services.assistant_intent_service import (
    AssistantIntentService
)

from services.action_history_service import (
    ActionHistoryService
)

from services.assistant_core_service import (
    AssistantCoreService
)

from services.assistant_user_storage_service import (
    AssistantUserStorageService
)

from services.assistant_user_context_service import (
    AssistantUserContextService
)

from services.assistant_request_context_service import (
    AssistantRequestContextService
)

from services.assistant_task_context_service import (
    AssistantTaskContextService
)



def create_telegram_core():


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



    business_flow = (
        AssistantBusinessFlowService(
            intent_service=(
                AssistantIntentService()
            ),

            planner_service=planner
        )
    )



    business = (
        AssistantOrchestratorBusinessService(
            business_flow_service=business_flow
        )
    )



    main_flow = (
        AssistantMainFlowService(
            business_service=business,

            response_service=(
                AssistantResponseBuilderService()
            )
        )
    )



    entry = (
        AssistantEntryService(
            main_flow_service=main_flow
        )
    )



    orchestrator = (
        AssistantOrchestratorV2Service(
            entry_service=entry
        )
    )



    storage = (
        AssistantUserStorageService()
    )



    user_context = (
        AssistantUserContextService(
            storage
        )
    )



    task_context = (
        AssistantTaskContextService(
            user_context
        )
    )



    request_context = (
        AssistantRequestContextService(
            user_context
        )
    )



    core = (
        AssistantCoreService(
            orchestrator_service=orchestrator,

            request_context_service=request_context,

            user_context_service=user_context,

            task_context_service=task_context
        )
    )



    return {
        "core": core,

        "profiles": storage,

        "storage": storage,

        "context": user_context,

        "task_context": task_context
    }