from api.ozon_client import OzonClient
from services.product_returns_finance_impact_query_service import (
    ProductReturnsFinanceImpactQueryService,
)
from services.returns_buyout_facts_source import (
    ReturnsBuyoutFactsSource,
)
from services.returns_finance_attribution_analytics_service import (
    ReturnsFinanceAttributionAnalyticsService,
)
from services.returns_finance_attribution_facts_source import (
    ReturnsFinanceAttributionFactsSource,
)
from services.returns_finance_attribution_query_service import (
    ReturnsFinanceAttributionQueryService,
)


def create_product_returns_finance_impact_query(
    core_components,
    ozon_client=None,
    period_days=30,
    now_provider=None,
):
    unit_economics_query = core_components.get(
        "unit_economics_query"
    )
    if unit_economics_query is None:
        raise RuntimeError(
            "Product Unit Economics production wiring is required"
        )

    client = ozon_client or OzonClient()
    returns_source = ReturnsBuyoutFactsSource(client)
    facts_source = ReturnsFinanceAttributionFactsSource(
        ozon_client=client,
        returns_buyout_facts_source=returns_source,
    )
    attribution_query = ReturnsFinanceAttributionQueryService(
        facts_source=facts_source,
        analytics_service=(
            ReturnsFinanceAttributionAnalyticsService()
        ),
    )

    return ProductReturnsFinanceImpactQueryService(
        product_service=unit_economics_query.product_service,
        attribution_query_service=attribution_query,
        period_days=period_days,
        now_provider=now_provider,
    )
