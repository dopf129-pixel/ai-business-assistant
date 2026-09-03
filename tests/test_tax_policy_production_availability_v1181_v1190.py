import json
from pathlib import Path

from services.product_unit_economics_provider import (
    ProductUnitEconomicsProvider,
)
from services.tax_configuration_service import (
    TaxConfigurationService,
)
from services.tax_service import TaxService
from telegram_core_factory import create_telegram_core


def test_v1181_repository_production_tax_policy_is_explicit_usn_income_6():
    policy_path = (
        Path(__file__).resolve().parents[1]
        / "data"
        / "tax_configuration.json"
    )

    policy = TaxConfigurationService(
        file_path=str(policy_path),
        environment={},
    ).get_policy()

    assert policy == {
        "error": False,
        "configured": True,
        "policy": {
            "mode": "USN_INCOME",
            "tax_rate": 6.0,
            "minimum_tax_rate": 1.0,
        },
    }


def test_v1182_explicit_environment_policy_is_used_when_file_is_absent(
    tmp_path,
):
    result = TaxConfigurationService(
        file_path=str(tmp_path / "missing.json"),
        environment={
            "TAX_MODE": "USN_INCOME",
            "TAX_RATE": "6",
            "MINIMUM_TAX_RATE": "1",
        },
    ).get_policy()

    assert result["configured"] is True
    assert result["policy"] == {
        "mode": "USN_INCOME",
        "tax_rate": 6.0,
        "minimum_tax_rate": 1.0,
    }


def test_v1183_missing_file_and_missing_explicit_environment_stays_unknown(
    tmp_path,
):
    result = TaxConfigurationService(
        file_path=str(tmp_path / "missing.json"),
        environment={},
    ).get_policy()

    assert result == {
        "error": False,
        "configured": False,
        "policy": None,
    }


def test_v1184_invalid_environment_policy_fails_closed(
    tmp_path,
):
    for environment in (
        {
            "TAX_MODE": "BROKEN",
            "TAX_RATE": "6",
        },
        {
            "TAX_MODE": "USN_INCOME",
            "TAX_RATE": "not-a-number",
        },
        {
            "TAX_MODE": "USN_INCOME",
        },
    ):
        result = TaxConfigurationService(
            file_path=str(tmp_path / "missing.json"),
            environment=environment,
        ).get_policy()

        assert result == {
            "error": False,
            "configured": False,
            "policy": None,
        }


def test_v1185_explicit_environment_none_mode_is_real_zero_tax(
    tmp_path,
):
    result = TaxConfigurationService(
        file_path=str(tmp_path / "missing.json"),
        environment={
            "TAX_MODE": "NONE",
        },
    ).get_policy()

    assert result == {
        "error": False,
        "configured": True,
        "policy": {
            "mode": "NONE",
            "tax_rate": 0.0,
            "minimum_tax_rate": 0.0,
        },
    }


def test_v1186_persisted_policy_has_precedence_over_environment(
    tmp_path,
):
    path = tmp_path / "tax.json"
    path.write_text(
        json.dumps({
            "mode": "USN_INCOME",
            "tax_rate": 6.0,
            "minimum_tax_rate": 1.0,
        }),
        encoding="utf-8",
    )

    result = TaxConfigurationService(
        file_path=str(path),
        environment={
            "TAX_MODE": "NONE",
        },
    ).get_policy()

    assert result["configured"] is True
    assert result["policy"]["mode"] == "USN_INCOME"
    assert result["policy"]["tax_rate"] == 6.0


def test_v1187_malformed_persisted_policy_does_not_silently_fallback(
    tmp_path,
):
    path = tmp_path / "tax.json"
    path.write_text(
        '{"mode":"USN_INCOME","tax_rate":',
        encoding="utf-8",
    )

    result = TaxConfigurationService(
        file_path=str(path),
        environment={
            "TAX_MODE": "USN_INCOME",
            "TAX_RATE": "6",
        },
    ).get_policy()

    assert result == {
        "error": False,
        "configured": False,
        "policy": None,
    }


def test_v1188_production_telegram_core_receives_repository_tax_policy():
    core = create_telegram_core()
    provider = (
        core["unit_economics_query"]
        .unit_economics_provider
    )

    assert provider.tax_mode == "USN_INCOME"
    assert provider.tax_rate == 6.0
    assert provider.minimum_tax_rate == 1.0


def test_v1189_hook_like_current_economics_calculates_tax_and_base_profit():
    provider = ProductUnitEconomicsProvider(
        tax_service=TaxService(),
        tax_mode="USN_INCOME",
        tax_rate=6.0,
        minimum_tax_rate=1.0,
    )

    result = provider.build_current(
        facts={
            "product_id": "1",
            "sku": "hook-2",
            "seller_price": 100.0,
            "buyer_price": 100.0,
            "commission_amount": 17.0,
            "commission_rate": 17.0,
            "logistics": 17.54,
            "last_mile": 1.54,
            "acquiring_average": 1.09,
            "tax_base_policy": "OZON_BUYER_PRICE",
        },
        product_cost=21.0,
    )

    assert result["tax_base_policy"] == "OZON_BUYER_PRICE"
    assert result["tax_rate"] == 6.0
    assert result["tax"] == 6.0
    assert result["net_profit_per_unit"] == 35.83
    assert result["margin_percent"] == 35.83
    assert "tax" not in result["missing_fields"]


def test_v1190_unconfigured_tax_still_blocks_profit_instead_of_assuming_zero():
    provider = ProductUnitEconomicsProvider(
        tax_service=TaxService(),
        tax_mode=None,
        tax_rate=None,
    )

    result = provider.build_current(
        facts={
            "product_id": "1",
            "sku": "hook-2",
            "seller_price": 100.0,
            "buyer_price": 100.0,
            "commission_amount": 17.0,
            "commission_rate": 17.0,
            "logistics": 17.54,
            "last_mile": 1.54,
            "acquiring_average": 1.09,
            "tax_base_policy": "OZON_BUYER_PRICE",
        },
        product_cost=21.0,
    )

    assert result["tax"] is None
    assert result["net_profit_per_unit"] is None
    assert "tax" in result["missing_fields"]
