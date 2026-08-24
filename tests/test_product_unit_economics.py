import sys

sys.path.insert(0, "app")

from services.product_profitability_provider import (
    ProductProfitabilityProvider
)
from services.product_unit_economics_provider import (
    ProductUnitEconomicsProvider
)
from services.tax_service import TaxService


def _profit_record(
    product_id="101",
    sku="sku-101",
    sales_count=5,
    gross_sales=1000,
    total_cost=400,
    net_accrual=700,
    gross_profit=300,
    margin_percent=30
):
    return {
        "error": False,
        "product_id": product_id,
        "sku": sku,
        "sales_count": sales_count,
        "gross_sales": gross_sales,
        "cost_price": 80,
        "total_cost": total_cost,
        "net_accrual": net_accrual,
        "gross_profit": gross_profit,
        "profit_per_unit": 60,
        "margin_percent": margin_percent
    }


def test_product_unit_economics_includes_existing_tax_calculation():
    result = ProductUnitEconomicsProvider(
        tax_service=TaxService(),
        tax_mode="USN_INCOME",
        tax_rate=6
    ).build([
        _profit_record()
    ])

    assert result == [
        {
            "product_id": "101",
            "sku": "sku-101",
            "units_sold": 5,
            "revenue": 1000.0,
            "product_cost": 400.0,
            "marketplace_fees": 300.0,
            "tax": 60.0,
            "net_profit": 240.0,
            "profit_per_unit": 48.0,
            "margin_percent": 24.0
        }
    ]


def test_product_unit_economics_without_tax_data_is_explicitly_incomplete():
    result = ProductUnitEconomicsProvider().build([
        _profit_record()
    ])

    assert result[0]["tax"] is None
    assert result[0]["net_profit"] is None
    assert result[0]["profit_per_unit"] is None
    assert result[0]["margin_percent"] is None
    assert result[0]["marketplace_fees"] == 300.0


def test_product_unit_economics_skips_record_without_cost():
    record = _profit_record()
    record["total_cost"] = None

    result = ProductUnitEconomicsProvider(
        tax_service=TaxService(),
        tax_mode="USN_INCOME"
    ).build([
        record
    ])

    assert result == []


def test_product_unit_economics_supports_multiple_skus():
    result = ProductUnitEconomicsProvider(
        tax_service=TaxService(),
        tax_mode="NONE"
    ).build([
        _profit_record(),
        _profit_record(
            product_id="202",
            sku="sku-202",
            sales_count=2,
            gross_sales=500,
            total_cost=160,
            net_accrual=380,
            gross_profit=220,
            margin_percent=44
        )
    ])

    assert [
        item["sku"]
        for item in result
    ] == [
        "sku-101",
        "sku-202"
    ]
    assert result[0]["net_profit"] == 300.0
    assert result[1]["net_profit"] == 220.0
    assert result[1]["profit_per_unit"] == 110.0


def test_existing_product_profitability_contract_is_unchanged():
    result = ProductProfitabilityProvider().build([
        _profit_record()
    ])

    assert result == [
        {
            "product_id": "101",
            "sku": "sku-101",
            "sales_count": 5,
            "revenue": 1000.0,
            "cost": 400.0,
            "profit": 300.0,
            "margin": 30.0
        }
    ]
