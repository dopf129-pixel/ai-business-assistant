from api.ozon_client import OzonClient
from product_returns_finance_impact_factory import (
    create_product_returns_finance_impact_query
)

from services.cost_service import ProductCostService
from services.current_product_economics_source import (
    CurrentProductEconomicsSource
)
from services.finance_service import FinanceService
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

    current_source = CurrentProductEconomicsSource(
        ozon_client=ozon_client,
        finance_service=FinanceService()
    )

    returns_finance_impact_query = (
        create_product_returns_finance_impact_query(
            core_components=core_components,
            ozon_client=ozon_client
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
        )
    )
