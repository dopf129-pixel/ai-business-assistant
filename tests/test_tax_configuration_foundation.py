from services.business_profit_service import (
    BusinessProfitService
)
from services.product_unit_economics_provider import (
    ProductUnitEconomicsProvider
)
from services.tax_configuration_service import (
    TaxConfigurationService
)
from services.tax_service import TaxService
from telegram_core_factory import create_telegram_core


def test_tax_configuration_is_persisted(tmp_path):
    file_path = tmp_path / "tax.json"
    service = TaxConfigurationService(
        file_path=str(file_path)
    )

    saved = service.save_policy(
        mode="USN_INCOME",
        tax_rate=6.0
    )
    loaded = TaxConfigurationService(
        file_path=str(file_path)
    ).get_policy()

    assert saved["error"] is False
    assert loaded == {
        "error": False,
        "configured": True,
        "policy": {
            "mode": "USN_INCOME",
            "tax_rate": 6.0,
            "minimum_tax_rate": 1.0
        }
    }


def test_usn_income_policy_configures_tax_service(tmp_path):
    service = TaxConfigurationService(
        file_path=str(tmp_path / "tax.json")
    )
    service.save_policy(
        mode="USN_INCOME",
        tax_rate=6.0
    )
    policy = service.get_policy()["policy"]

    result = TaxService().calculate(
        mode=policy["mode"],
        revenue=1000,
        gross_profit=400,
        tax_rate=policy["tax_rate"],
        minimum_tax_rate=policy[
            "minimum_tax_rate"
        ]
    )

    assert result["error"] is False
    assert result["configured"] is True
    assert result["mode"] == "USN_INCOME"
    assert result["tax_amount"] == 60.0


def test_usn_income_minus_expenses_policy(tmp_path):
    service = TaxConfigurationService(
        file_path=str(tmp_path / "tax.json")
    )
    service.save_policy(
        mode="USN_INCOME_MINUS_EXPENSES",
        tax_rate=15.0,
        minimum_tax_rate=1.0
    )
    policy = service.get_policy()["policy"]

    result = TaxService().calculate(
        mode=policy["mode"],
        revenue=1000,
        gross_profit=400,
        tax_rate=policy["tax_rate"],
        minimum_tax_rate=policy[
            "minimum_tax_rate"
        ]
    )

    assert result["error"] is False
    assert result["configured"] is True
    assert result["mode"] == (
        "USN_INCOME_MINUS_EXPENSES"
    )
    assert result["tax_amount"] == 60.0


def test_none_mode_is_only_explicit_configuration(tmp_path):
    service = TaxConfigurationService(
        file_path=str(tmp_path / "tax.json")
    )

    missing = service.get_policy()
    service.save_policy(mode="NONE")
    configured = service.get_policy()

    assert missing == {
        "error": False,
        "configured": False,
        "policy": None
    }
    assert configured == {
        "error": False,
        "configured": True,
        "policy": {
            "mode": "NONE",
            "tax_rate": 0.0,
            "minimum_tax_rate": 0.0
        }
    }

    explicit_none = TaxService().calculate(
        mode="NONE",
        revenue=1000,
        gross_profit=400
    )

    assert explicit_none["configured"] is True
    assert explicit_none["tax_amount"] == 0.0


def test_missing_tax_configuration_keeps_unit_economics_tax_unknown(
    tmp_path
):
    service = TaxConfigurationService(
        file_path=str(tmp_path / "missing.json")
    )
    configuration = service.get_policy()

    tax = TaxService().calculate(
        mode=None,
        revenue=1000,
        gross_profit=400
    )

    assert tax == {
        "error": False,
        "configured": False,
        "mode": None,
        "mode_name": "Не настроен",
        "tax_base": None,
        "tax_rate": None,
        "tax_amount": None
    }

    provider = ProductUnitEconomicsProvider(
        tax_service=TaxService(),
        tax_mode=(
            configuration["policy"]["mode"]
            if configuration["configured"]
            else None
        )
    )

    result = provider.build(
        [
            {
                "product_id": "101",
                "sku": "hook-2",
                "sales_count": 2,
                "gross_sales": 2980.0,
                "net_accrual": 2240.0,
                "total_cost": 1040.0,
                "gross_profit": 1200.0
            }
        ]
    )[0]

    assert result["tax"] is None
    assert result["net_profit"] is None
    assert result["profit_per_unit"] is None
    assert result["margin_percent"] is None


def test_business_profit_preserves_unknown_tax():
    result = BusinessProfitService().calculate(
        store_profit={
            "gross_sales": 1000.0,
            "gross_profit": 400.0
        },
        tax=TaxService().calculate(
            mode=None,
            revenue=1000,
            gross_profit=400
        )
    )

    assert result["error"] is False
    assert result["configured"] is False
    assert result["tax_amount"] is None
    assert result["business_profit"] is None
    assert result["margin_percent"] is None


class FakeTaxConfigurationService:

    def get_policy(self):
        return {
            "error": False,
            "configured": True,
            "policy": {
                "mode": "USN_INCOME",
                "tax_rate": 6.0,
                "minimum_tax_rate": 1.0
            }
        }


def test_production_factory_uses_tax_configuration_and_keeps_executors():
    configuration = FakeTaxConfigurationService()
    core = create_telegram_core(
        tax_configuration_service=configuration
    )

    router = core["action_router"]
    sales_executor = router.executors["sales"]
    analytics = (
        sales_executor
        .sales_intelligence_service
        .analytics_service
        .business_analytics
    )

    assert core["tax_configuration"] is configuration
    assert analytics.tax_mode == "USN_INCOME"
    assert analytics.tax_rate == 6.0
    assert "sales" in router.executors
    assert "stock" in router.executors
    assert "finance" in router.executors
