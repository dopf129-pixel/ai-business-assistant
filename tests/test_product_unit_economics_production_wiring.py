from services.product_unit_economics_provider import (
    ProductUnitEconomicsProvider
)
from services.product_unit_economics_query_service import (
    ProductUnitEconomicsQueryService
)
from telegram_core_factory import create_telegram_core


class FakeTaxConfigurationService:

    def __init__(self, policy=None):
        self.policy = policy

    def get_policy(self):
        if self.policy is None:
            return {
                "error": False,
                "configured": False,
                "policy": None
            }

        return {
            "error": False,
            "configured": True,
            "policy": self.policy
        }


class FakeProductService:

    def load_products(self):
        return [(101, "hook", "hook-2")]


class FakeAnalyticsService:

    def get_period(self):
        return {
            "error": False,
            "date_from": "2026-08-01",
            "date_to": "2026-08-07"
        }


class FakePeriodProfitService:

    def calculate_period_profit(
        self,
        date_from,
        date_to,
        products
    ):
        return {
            "error": False,
            "profits": [
                {
                    "error": False,
                    "product_id": "101",
                    "sku": "hook-2",
                    "sales_count": 2,
                    "gross_sales": 2980.0,
                    "net_accrual": 2240.0,
                    "total_cost": 1040.0,
                    "gross_profit": 1200.0
                }
            ]
        }


def _make_core(policy):
    return create_telegram_core(
        tax_configuration_service=(
            FakeTaxConfigurationService(policy)
        ),
        product_service=FakeProductService(),
        period_profit_service=FakePeriodProfitService(),
        analytics_service=FakeAnalyticsService()
    )


def test_production_wiring_exposes_unit_economics_query():
    core = _make_core(
        {
            "mode": "USN_INCOME",
            "tax_rate": 6.0,
            "minimum_tax_rate": 1.0
        }
    )

    query_service = core["unit_economics_query"]

    assert isinstance(
        query_service,
        ProductUnitEconomicsQueryService
    )
    assert isinstance(
        query_service.unit_economics_provider,
        ProductUnitEconomicsProvider
    )


def test_query_uses_usn_income_policy():
    core = _make_core(
        {
            "mode": "USN_INCOME",
            "tax_rate": 6.0,
            "minimum_tax_rate": 1.0
        }
    )

    result = core["unit_economics_query"].query(
        "hook-2"
    )

    assert result["tax"] == 89.4
    assert result["net_profit_per_unit"] == 510.6
    assert result["margin_percent"] == 34.27


def test_query_uses_usn_income_minus_expenses_policy():
    core = _make_core(
        {
            "mode": "USN_INCOME_MINUS_EXPENSES",
            "tax_rate": 15.0,
            "minimum_tax_rate": 1.0
        }
    )

    result = core["unit_economics_query"].query(
        "hook-2"
    )

    assert result["tax"] == 90.0
    assert result["net_profit_per_unit"] == 510.0


def test_query_uses_explicit_none_policy():
    core = _make_core(
        {
            "mode": "NONE",
            "tax_rate": 0.0,
            "minimum_tax_rate": 0.0
        }
    )

    result = core["unit_economics_query"].query(
        "hook-2"
    )

    assert result["tax"] == 0.0
    assert result["net_profit_per_unit"] == 600.0
    assert "tax" not in result["missing_fields"]


def test_query_keeps_unknown_tax_as_none():
    core = _make_core(None)

    result = core["unit_economics_query"].query(
        "hook-2"
    )

    assert result["tax"] is None
    assert result["net_profit_per_unit"] is None
    assert result["margin_percent"] is None
    assert "tax" in result["missing_fields"]


def test_existing_executor_registry_is_preserved():
    core = _make_core(None)
    router = core["action_router"]

    assert "sales" in router.executors
    assert "stock" in router.executors
    assert "finance" in router.executors
