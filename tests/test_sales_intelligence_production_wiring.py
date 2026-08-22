import sys

sys.path.insert(
    0,
    "app"
)

from telegram_core_factory import create_telegram_core
from services.sales_intelligence_service import (
    SalesIntelligenceService
)
from services.store_analytics_service import (
    StoreAnalyticsService
)


def test_production_core_wires_sales_intelligence_service():

    core = create_telegram_core()

    sales_executor = (
        core["action_router"]
        .executors["sales"]
    )

    intelligence = (
        sales_executor
        .sales_intelligence_service
    )

    assert isinstance(
        intelligence,
        SalesIntelligenceService
    )

    assert isinstance(
        intelligence.analytics_service,
        StoreAnalyticsService
    )
