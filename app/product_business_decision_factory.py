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
    decision_history_service=None
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

    return ProductBusinessDecisionQueryService(
        product_service=product_service,
        sales_metrics_source=prepared_source.sales,
        stock_metrics_source=prepared_source.stock,
        unit_economics_query_service=economics_query,
        decision_input_provider=ProductDecisionInputProvider(),
        decision_service=ProductBusinessDecisionService(),
        decision_history_service=decision_history_service
    )
