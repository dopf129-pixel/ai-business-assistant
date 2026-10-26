from api.ozon_client import OzonClient
from product_returns_finance_impact_factory import (
    create_product_returns_finance_impact_query
)

from services.cost_service import ProductCostService
from services.cross_docking_unit_rate_source import CrossDockingUnitRateSource
from services.current_product_economics_source import (
    CurrentProductEconomicsSource
)
from services.period_profit_finance_service import PeriodProfitFinanceService
from services.product_unit_economics_query_service import (
    ProductUnitEconomicsQueryService
)


def create_current_unit_economics_query(
    core_components
):
    historical_query = core_components[
        "unit_economics_query"
    ]

    ozon_client = OzonClient()
    finance_service = PeriodProfitFinanceService()
    cross_docking_source = CrossDockingUnitRateSource(
        ozon_client=ozon_client,
        finance_service=finance_service,
    )

    current_source = CurrentProductEconomicsSource(
        ozon_client=ozon_client,
        finance_service=finance_service,
        cross_docking_source=cross_docking_source,
    )

    returns_finance_impact_query = (
        create_product_returns_finance_impact_query(
            core_components=core_components,
            ozon_client=ozon_client,
            period_days=30
        )
    )

    return ProductUnitEconomicsQueryService(
        product_service=(
            historical_query.product_service
        ),
        period_profit_service=(
            historical_query.period_profit_service
        ),
        analytics_service=(
            historical_query.analytics_service
        ),
        unit_economics_provider=(
            historical_query.unit_economics_provider
        ),
        current_economics_source=current_source,
        cost_service=ProductCostService(),
        current_finance_days=2,
        returns_finance_impact_query=(
            returns_finance_impact_query
        ),
        current_tax_base_policy=(
            "OZON_BUYER_PRICE"
        ),
        cache_ttl_seconds=600
    )
