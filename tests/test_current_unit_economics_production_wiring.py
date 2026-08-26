from current_unit_economics_factory import (
    create_current_unit_economics_query
)
from services.current_product_economics_source import (
    CurrentProductEconomicsSource
)
from services.product_unit_economics_provider import (
    ProductUnitEconomicsProvider
)
from services.product_unit_economics_query_service import (
    ProductUnitEconomicsQueryService
)
from services.product_returns_finance_impact_query_service import (
    ProductReturnsFinanceImpactQueryService
)


class HistoricalQuery:
    def __init__(self):
        self.product_service = object()
        self.period_profit_service = object()
        self.analytics_service = object()
        self.unit_economics_provider = (
            ProductUnitEconomicsProvider()
        )


def test_current_query_is_wired_over_existing_core_contract():
    historical = HistoricalQuery()

    query = create_current_unit_economics_query(
        {
            "unit_economics_query": historical
        }
    )

    assert isinstance(
        query,
        ProductUnitEconomicsQueryService
    )
    assert isinstance(
        query.current_economics_source,
        CurrentProductEconomicsSource
    )
    assert query.product_service is historical.product_service
    assert (
        query.period_profit_service
        is historical.period_profit_service
    )
    assert (
        query.analytics_service
        is historical.analytics_service
    )
    assert (
        query.unit_economics_provider
        is historical.unit_economics_provider
    )
    assert query.cost_service is not None
    assert query.current_finance_days == 2
    assert query.cache_ttl_seconds == 600
    assert (
        query.current_tax_base_policy
        == "OZON_BUYER_PRICE"
    )
    assert isinstance(
        query.returns_finance_impact_query,
        ProductReturnsFinanceImpactQueryService
    )
    assert (
        query.returns_finance_impact_query.product_service
        is historical.product_service
    )
