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

from services.assistant_task_service import (
    AssistantTaskService
)

from services.assistant_action_router_service import (
    AssistantActionRouterService
)

from services.assistant_sales_executor_service import (
    AssistantSalesExecutorService
)

from services.assistant_stock_executor_service import (
    AssistantStockExecutorService
)

from services.assistant_marketing_executor_service import (
    AssistantMarketingExecutorService
)

from services.sales_intelligence_service import (
    SalesIntelligenceService
)

from services.store_analytics_service import (
    StoreAnalyticsService
)

from services.retry_policy_service import (
    RetryPolicyService
)

from services.assistant_replanning_service import (
    AssistantReplanningService
)

from services.assistant_feedback_service import (
    AssistantFeedbackService
)

from services.assistant_memory_service import (
    AssistantMemoryService
)



def create_telegram_core():


    retry_policy = (
        RetryPolicyService()
    )


    replanning_service = (
        AssistantReplanningService()
    )


    memory_service = (
        AssistantMemoryService()
    )


    feedback_service = (
        AssistantFeedbackService(
            memory_service=memory_service
        )
    )


    history = (
        ActionHistoryService()
    )


    task_service = (
        AssistantTaskService()
    )


    store_analytics = (
        StoreAnalyticsService(
            tax_mode="NONE",
            tax_rate=0,
            minimum_tax_rate=0,
            advertising_cost=0
        )
    )


    sales_intelligence = (
        SalesIntelligenceService(
            analytics_service=(
                store_analytics
            )
        )
    )


    sales_executor = (
        AssistantSalesExecutorService(
            sales_intelligence_service=(
                sales_intelligence
            )
        )
    )


    stock_executor = (
        AssistantStockExecutorService()
    )


    marketing_executor = (
        AssistantMarketingExecutorService()
    )


    action_router = (
        AssistantActionRouterService(

            executors={

                "sales":
                    sales_executor,

                "stock":
                    stock_executor,

                "marketing":
                    marketing_executor

            }
        )
    )


    execution_service = (
        AssistantActionExecutionService(

            history_service=history,

            task_service=task_service,

            action_router=action_router,

            action_runner_service=action_router,

            retry_policy=retry_policy,

            replanning_service=replanning_service,

            feedback_service=feedback_service

        )
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
                execution_service
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

            executor_service=(
                executor
            ),

            task_service=(
                task_service
            )
        )
    )


    business_flow = (
        AssistantBusinessFlowService(

            intent_service=(
                AssistantIntentService()
            ),

            planner_service=(
                planner
            ),

            task_service=(
                task_service
            ),

            execution_service=(
                execution_service
            )
        )
    )


    business = (
        AssistantOrchestratorBusinessService(

            business_flow_service=(
                business_flow
            ),

            task_service=(
                task_service
            ),

            execution_service=(
                execution_service
            )
        )
    )


    main_flow = (
        AssistantMainFlowService(

            business_service=(
                business
            ),

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

            orchestrator_service=(
                orchestrator
            ),

            request_context_service=(
                request_context
            ),

            user_context_service=(
                user_context
            ),

            task_context_service=(
                task_context
            )
        )
    )


    return {

        "core":
            core,

        "profiles":
            storage,

        "storage":
            storage,

        "context":
            user_context,

        "task_context":
            task_context,

        "task_service":
            task_service,

        "execution_service":
            execution_service,

        "action_router":
            action_router,

        "retry_policy":
            retry_policy,

        "replanning_service":
            replanning_service,

        "feedback_service":
            feedback_service,

        "memory_service":
            memory_service

    }