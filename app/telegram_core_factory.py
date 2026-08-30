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

from services.terminal_safe_assistant_task_service import (
    TerminalSafeAssistantTaskService
)

from services.task_persistence_operational_service import (
    TaskPersistenceOperationalService
)

from services.task_persistence_release_observability_service import (
    TaskPersistenceReleaseObservabilityService
)

from services.task_persistence_capability_provenance_service import (
    TaskPersistenceCapabilityProvenanceService
)

from services.task_persistence_operator_access_policy import (
    TaskPersistenceOperatorAccessPolicy
)

from services.task_persistence_operator_presentation_service import (
    TaskPersistenceOperatorPresentationService
)

from services.assistant_task_persistence_operational_runtime_service import (
    AssistantTaskPersistenceOperationalRuntimeService
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

from services.assistant_finance_executor_service import (
    AssistantFinanceExecutorService
)

from services.sales_intelligence_service import (
    SalesIntelligenceService
)

from services.stock_intelligence_service import (
    StockIntelligenceService
)

from services.finance_intelligence_service import (
    FinanceIntelligenceService
)

from services.sales_context_provider import (
    SalesContextProvider
)

from services.stock_context_provider import (
    StockContextProvider
)

from services.finance_context_provider import (
    FinanceContextProvider
)

from services.store_analytics_service import (
    StoreAnalyticsService
)

from services.product_service import (
    ProductService
)

from services.finance_service import (
    FinanceService
)

from services.metrics_service import (
    MetricsService
)

from services.cost_service import (
    ProductCostService
)

from services.profit_service import (
    ProfitService
)

from services.store_period_profit_service import (
    StorePeriodProfitService
)

from services.tax_configuration_service import (
    TaxConfigurationService
)

from services.tax_service import (
    TaxService
)

from services.product_unit_economics_provider import (
    ProductUnitEconomicsProvider
)

from services.product_unit_economics_query_service import (
    ProductUnitEconomicsQueryService
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



def create_telegram_core(
    tax_configuration_service=None,
    product_service=None,
    period_profit_service=None,
    analytics_service=None,
    task_service=None,
    task_persistence_operator_user_ids=None,
    task_persistence_revision_id=None,
    task_persistence_ci_evidence=None
):


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


    planning_service = (
        AssistantPlanningService(
            memory_service=memory_service
        )
    )


    action_generator_service = (
        AssistantActionGeneratorService(
            memory_service=memory_service
        )
    )


    history = (
        ActionHistoryService()
    )


    if (
        task_service is not None
        and not isinstance(
            task_service,
            TerminalSafeAssistantTaskService
        )
    ):
        raise ValueError(
            "UNSAFE_TASK_SERVICE_INJECTION"
        )

    task_service = (
        task_service
        if task_service is not None
        else TerminalSafeAssistantTaskService()
    )


    task_persistence_operator_access_policy = (
        TaskPersistenceOperatorAccessPolicy(
            allowed_user_ids=(
                task_persistence_operator_user_ids
            )
        )
    )

    task_persistence_operational_service = (
        TaskPersistenceOperationalService(
            task_service=task_service
        )
    )

    task_persistence_release_observability_service = (
        TaskPersistenceReleaseObservabilityService(
            task_service=task_service,
            operational_service=(
                task_persistence_operational_service
            )
        )
    )

    task_persistence_capability_provenance_service = (
        TaskPersistenceCapabilityProvenanceService(
            release_observability_service=(
                task_persistence_release_observability_service
            ),
            revision_id=task_persistence_revision_id,
            ci_evidence=task_persistence_ci_evidence,
        )
    )

    task_persistence_operational_runtime = (
        AssistantTaskPersistenceOperationalRuntimeService(
            operational_service=(
                task_persistence_operational_service
            ),
            access_policy=(
                task_persistence_operator_access_policy
            ),
            presentation_service=(
                TaskPersistenceOperatorPresentationService()
            ),
            release_observability_service=(
                task_persistence_release_observability_service
            ),
            capability_provenance_service=(
                task_persistence_capability_provenance_service
            )
        )
    )


    tax_configuration = (
        tax_configuration_service
        or TaxConfigurationService()
    )


    tax_configuration_result = (
        tax_configuration.get_policy()
    )


    tax_policy = (
        tax_configuration_result.get(
            "policy"
        )
        if tax_configuration_result.get(
            "configured"
        )
        else None
    )


    store_analytics = (
        analytics_service
        or StoreAnalyticsService(
            tax_mode=(
                tax_policy.get("mode")
                if tax_policy
                else None
            ),
            tax_rate=(
                tax_policy.get("tax_rate")
                if tax_policy
                else 0
            ),
            minimum_tax_rate=(
                tax_policy.get(
                    "minimum_tax_rate"
                )
                if tax_policy
                else 0
            ),
            advertising_cost=0,
            finance_service=FinanceService()
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


    stock_intelligence = (
        StockIntelligenceService()
    )


    stock_executor = (
        AssistantStockExecutorService(
            stock_intelligence_service=(
                stock_intelligence
            )
        )
    )


    finance_intelligence = (
        FinanceIntelligenceService()
    )


    finance_executor = (
        AssistantFinanceExecutorService(
            finance_intelligence_service=(
                finance_intelligence
            )
        )
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

                "finance":
                    finance_executor,

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
                action_generator_service
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
                planning_service
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


    product_service = (
        product_service
        or ProductService()
    )


    period_profit_service = (
        period_profit_service
        or StorePeriodProfitService(
            finance_service=(
                FinanceService()
            ),
            cost_service=(
                ProductCostService()
            ),
            profit_service=(
                ProfitService()
            )
        )
    )


    unit_economics_provider = (
        ProductUnitEconomicsProvider(
            tax_service=TaxService(),
            tax_mode=(
                tax_policy.get("mode")
                if tax_policy
                else None
            ),
            tax_rate=(
                tax_policy.get("tax_rate")
                if tax_policy
                else None
            ),
            minimum_tax_rate=(
                tax_policy.get(
                    "minimum_tax_rate"
                )
                if tax_policy
                else 1.0
            )
        )
    )


    unit_economics_query = (
        ProductUnitEconomicsQueryService(
            product_service=product_service,
            period_profit_service=(
                period_profit_service
            ),
            analytics_service=store_analytics,
            unit_economics_provider=(
                unit_economics_provider
            )
        )
    )


    metrics_service = (
        MetricsService()
    )


    sales_context_provider = (
        SalesContextProvider(
            product_service=product_service,
            period_profit_service=(
                period_profit_service
            ),
            analytics_service=(
                store_analytics
            )
        )
    )


    stock_context_provider = (
        StockContextProvider(
            product_service=product_service,
            analytics_service=(
                store_analytics
            ),
            metrics_service=(
                metrics_service
            )
        )
    )


    finance_context_provider = (
        FinanceContextProvider()
    )


    entry = (
        AssistantEntryService(
            main_flow_service=main_flow,
            sales_context_provider=(
                sales_context_provider
            ),
            stock_context_provider=(
                stock_context_provider
            ),
            finance_context_provider=(
                finance_context_provider
            ),
            task_persistence_operational_runtime_service=(
                task_persistence_operational_runtime
            )
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

        "task_persistence_operational_runtime_service":
            task_persistence_operational_runtime,

        "task_persistence_release_observability_service":
            task_persistence_release_observability_service,

        "task_persistence_capability_provenance_service":
            task_persistence_capability_provenance_service,

        "task_persistence_operator_access_policy":
            task_persistence_operator_access_policy,

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
            memory_service,

        "planning_service":
            planning_service,

        "action_generator_service":
            action_generator_service,

        "tax_configuration":
            tax_configuration,

        "unit_economics_query":
            unit_economics_query

    }