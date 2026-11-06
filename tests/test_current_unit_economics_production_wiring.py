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
from services.period_profit_finance_service import PeriodProfitFinanceService
from services.fifo_current_unit_cost_adapter import FifoCurrentUnitCostAdapter
from services.fifo_cost_history_service import FifoCostHistoryService
from services.fifo_cost_repository import FifoCostRepository
from unit_price_scenario_factory import create_unit_price_scenario_runtime


class HistoricalQuery:
    def __init__(self):
        self.product_service = object()
        self.period_profit_service = object()
        self.analytics_service = object()
        self.unit_economics_provider = (
            ProductUnitEconomicsProvider()
        )


def test_current_query_is_wired_over_existing_core_contract(tmp_path):
    historical = HistoricalQuery()
    fifo_repository = FifoCostRepository(db_path=tmp_path / "fifo-current-economics.sqlite")

    query = create_current_unit_economics_query(
        {
            "unit_economics_query": historical,
            "fifo_cost_repository": fifo_repository,
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
    assert isinstance(
        query.current_economics_source.finance_service,
        PeriodProfitFinanceService,
    )
    assert query.current_economics_source.cross_docking_source is not None
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
    assert isinstance(query.cost_adapter, FifoCurrentUnitCostAdapter)
    assert isinstance(query.cost_adapter.history_service, FifoCostHistoryService)
    assert query.cost_adapter.history_service.repository is fifo_repository
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
    assert (
        query.returns_finance_impact_query.period_days
        == 30
    )


def test_scenario_factory_reuses_the_current_finance_and_cross_docking_sources(tmp_path):
    fifo_repository = FifoCostRepository(db_path=tmp_path / "fifo-scenario.sqlite")
    query = create_current_unit_economics_query(
        {
            "unit_economics_query": HistoricalQuery(),
            "fifo_cost_repository": fifo_repository,
        }
    )

    runtime = create_unit_price_scenario_runtime(
        {},
        query,
        keyboard_service=object(),
    )

    assert runtime is not None
    assert runtime.source.finance_service is query.current_economics_source.finance_service
    assert runtime.source.cross_docking_source is query.current_economics_source.cross_docking_source
    assert runtime.source.cost_adapter is query.cost_adapter
