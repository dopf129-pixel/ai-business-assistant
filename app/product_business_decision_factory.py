from services.metrics_service import MetricsService
from services.stock_intelligence_service import StockIntelligenceService
from services.product_decision_metrics_source import (
    ProductDecisionMetricsSource
)
from services.product_decision_input_provider import (
    ProductDecisionInputProvider
)
from services.product_business_decision_service import (
    ProductBusinessDecisionService
)
from services.product_business_decision_query_service import (
    ProductBusinessDecisionQueryService
)
from services.product_decision_history_service import (
    ProductDecisionHistoryService
)
from services.product_decision_history_storage_service import (
    ProductDecisionHistoryStorageService
)
from services.product_decision_action_proposal_service import (
    ProductDecisionActionProposalService
)
from services.product_action_proposal_confirmation_service import (
    ProductActionProposalConfirmationService
)


def create_product_decision_history(
    file_path="data/product_decision_history.json"
):
    return ProductDecisionHistoryService(
        storage_service=ProductDecisionHistoryStorageService(
            file_path=file_path
        )
    )


def create_product_business_decision_query(
    core_components=None,
    metrics_service=None,
    stock_intelligence_service=None,
    unit_economics_query=None,
    decision_history_service=None,
    action_proposal_service=None,
    action_proposal_confirmation_service=None
):
    if core_components is None:
        from telegram_core_factory import create_telegram_core
        components = create_telegram_core()
    else:
        components = core_components

    economics_query = (
        unit_economics_query
        or components.get("unit_economics_query")
    )

    if economics_query is None:
        raise RuntimeError(
            "Product Unit Economics production wiring is required"
        )

    product_service = economics_query.product_service
    analytics_service = economics_query.analytics_service

    prepared_source = ProductDecisionMetricsSource(
        product_service=product_service,
        analytics_service=analytics_service,
        metrics_service=(
            metrics_service or MetricsService()
        ),
        stock_intelligence_service=(
            stock_intelligence_service
            or StockIntelligenceService()
        )
    )

    proposal_service = (
        action_proposal_service
        or ProductDecisionActionProposalService()
    )
    confirmation_service = action_proposal_confirmation_service
    if confirmation_service is None and decision_history_service is not None:
        confirmation_service = ProductActionProposalConfirmationService(
            history_service=decision_history_service,
            proposal_service=proposal_service,
        )

    return ProductBusinessDecisionQueryService(
        product_service=product_service,
        sales_metrics_source=prepared_source.sales,
        stock_metrics_source=prepared_source.stock,
        unit_economics_query_service=economics_query,
        decision_input_provider=ProductDecisionInputProvider(),
        decision_service=ProductBusinessDecisionService(),
        decision_history_service=decision_history_service,
        action_proposal_service=proposal_service,
        action_proposal_confirmation_service=confirmation_service,
    )
