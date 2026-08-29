import sys

sys.path.insert(
    0,
    "app"
)


from period_profit_factory import (
    create_period_profit_query
)
from period_profit_mapping_registry_factory import (
    create_period_profit_mapping_registry
)
from return_financial_operation_review_factory import (
    create_return_financial_operation_review_report_service
)

from services.assistant_return_operation_review_runtime_service import (
    AssistantReturnOperationReviewRuntimeService
)
from services.assistant_period_profit_runtime_service import (
    AssistantPeriodProfitRuntimeService
)
from services.assistant_period_profit_mapping_admin_runtime_service import (
    AssistantPeriodProfitMappingAdminRuntimeService
)
from services.assistant_period_profit_mapping_recovery_runtime_service import (
    AssistantPeriodProfitMappingRecoveryRuntimeService
)
from services.period_profit_mapping_admin_service import (
    PeriodProfitMappingAdminService
)
from services.period_profit_mapping_recovery_service import (
    PeriodProfitMappingRecoveryService
)

from services.assistant_core_service import (
    AssistantCoreService
)

from services.assistant_orchestrator_v2_service import (
    AssistantOrchestratorV2Service
)

from services.assistant_entry_service import (
    AssistantEntryService
)

from services.assistant_main_flow_service import (
    AssistantMainFlowService
)

from services.assistant_orchestrator_business_service import (
    AssistantOrchestratorBusinessService
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

from services.assistant_response_builder_service import (
    AssistantResponseBuilderService
)

from services.assistant_user_memory_service import (
    AssistantUserMemoryService
)

from services.assistant_user_memory_storage_service import (
    AssistantUserMemoryStorageService
)

from services.action_history_service import (
    ActionHistoryService
)



def create_assistant():

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


    business_service = (
        AssistantOrchestratorBusinessService(
            business_flow_service=business_flow
        )
    )


    main_flow = (
        AssistantMainFlowService(
            business_service=business_service,

            response_service=(
                AssistantResponseBuilderService()
            )
        )
    )


    mapping_registry = (
        create_period_profit_mapping_registry()
    )

    period_profit_runtime = (
        AssistantPeriodProfitRuntimeService(
            query_service=create_period_profit_query(
                mapping_registry=mapping_registry
            )
        )
    )

    return_operation_review_runtime = (
        AssistantReturnOperationReviewRuntimeService(
            report_service=(
                create_return_financial_operation_review_report_service()
            )
        )
    )

    mapping_admin_runtime = (
        AssistantPeriodProfitMappingAdminRuntimeService(
            admin_service=(
                PeriodProfitMappingAdminService(
                    mapping_registry
                )
            )
        )
    )

    mapping_recovery_runtime = (
        AssistantPeriodProfitMappingRecoveryRuntimeService(
            recovery_service=(
                PeriodProfitMappingRecoveryService(
                    mapping_registry
                )
            )
        )
    )


    entry = (
        AssistantEntryService(
            main_flow_service=main_flow,
            period_profit_runtime_service=(
                period_profit_runtime
            ),
            return_operation_review_runtime_service=(
                return_operation_review_runtime
            ),
            period_profit_mapping_admin_runtime_service=(
                mapping_admin_runtime
            ),
            period_profit_mapping_recovery_runtime_service=(
                mapping_recovery_runtime
            )
        )
    )


    orchestrator = (
        AssistantOrchestratorV2Service(
            entry_service=entry
        )
    )


    memory = (
        AssistantUserMemoryService(
            AssistantUserMemoryStorageService()
        )
    )


    return (
        AssistantCoreService(
            orchestrator_service=orchestrator,

            memory_service=memory
        )
    )



if __name__ == "__main__":

    assistant = create_assistant()


    result = (
        assistant.ask(
            "Что нужно сделать?"
        )
    )


    print(result)
