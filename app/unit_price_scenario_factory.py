from services.period_profit_finance_service import PeriodProfitFinanceService
from services.tax_configuration_service import TaxConfigurationService
from services.tax_service import TaxService
from services.telegram_unit_price_calculator_runtime_service import (
    TelegramUnitPriceCalculatorRuntimeService,
)
from services.unit_price_scenario_service import UnitPriceScenarioService
from services.unit_price_scenario_source import UnitPriceScenarioSource


def create_unit_price_scenario_runtime(core_components, unit_economics_query, keyboard_service):
    """Compose the planning-only calculator from existing tenant sources."""
    tax_configuration_service = (
        core_components.get("tax_configuration") or TaxConfigurationService()
    )
    source = UnitPriceScenarioSource(
        product_service=unit_economics_query.product_service,
        current_economics_source=unit_economics_query.current_economics_source,
        finance_service=PeriodProfitFinanceService(),
        cost_service=unit_economics_query.cost_service,
        tax_configuration_service=tax_configuration_service,
    )
    return TelegramUnitPriceCalculatorRuntimeService(
        source=source,
        scenario_service=UnitPriceScenarioService(TaxService()),
        keyboard_service=keyboard_service,
    )
