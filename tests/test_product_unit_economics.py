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
    margin_percent=30,
    discount_points=0,
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
        "discount_points": discount_points,
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
            "discount_points": 0.0,
            "revenue_tax_base": 1000.0,
            "tax_base": 1000.0,
            "product_cost": 400.0,
            "marketplace_fees": 300.0,
            "tax": 60.0,
            "tax_effective_percent": 6.0,
            "net_profit": 240.0,
            "profit_per_unit": 48.0,
            "margin_percent": 24.0
        }
    ]


def test_product_unit_economics_subtracts_points_and_reports_actual_tax_percent():
    result = ProductUnitEconomicsProvider(
        tax_service=TaxService(),
        tax_mode="USN_INCOME",
        tax_rate=6,
    ).build([
        _profit_record(discount_points=100),
    ])[0]

    assert result["tax_base"] == 900.0
    assert result["revenue_tax_base"] == 900.0
    assert result["tax"] == 54.0
    assert result["tax_effective_percent"] == 5.4
    assert result["net_profit"] == 246.0


def test_current_economics_subtracts_cross_docking_without_changing_income_tax_base():
    provider = ProductUnitEconomicsProvider(
        tax_service=TaxService(),
        tax_mode="USN_INCOME",
        tax_rate=6,
    )
    facts = {
        "product_id": "p1",
        "sku": "sku-1",
        "seller_price": 1000,
        "discount_points_per_unit": 100,
        "commission_amount": 100,
        "logistics": 0,
        "last_mile": 0,
        "acquiring_average": 0,
        "cross_docking_per_unit": 12,
        "cross_docking": {
            "status": "SKU_SUPPLY_PERIOD_AVERAGE",
            "reason": None,
        },
    }

    result = provider.build_current(facts, product_cost=300)

    assert result["cross_docking_per_unit"] == 12.0
    assert result["cross_docking_included"] is True
    assert result["marketplace_fees"] == 100.0
    assert result["tax_base"] == 900.0
    assert result["tax"] == 54.0
    assert result["net_profit_per_unit"] == 534.0


def test_current_economics_excludes_unconfirmed_cross_docking_without_zeroing_result():
    provider = ProductUnitEconomicsProvider(
        tax_service=TaxService(),
        tax_mode="USN_INCOME",
        tax_rate=6,
    )
    facts = {
        "seller_price": 100,
        "commission_amount": 10,
        "logistics": 10,
        "last_mile": 1,
        "acquiring_average": 1,
        "cross_docking_per_unit": None,
        "cross_docking": {
            "status": "UNAVAILABLE",
            "reason": "CROSSDOCK_WINDOW_INCOMPLETE",
        },
    }

    result = provider.build_current(facts, product_cost=20)

    assert result["net_profit_per_unit"] == 52.0
    assert result["cross_docking_included"] is False
    assert result["cross_docking_status"] == "UNAVAILABLE"


def test_cross_docking_is_deductible_expense_for_income_minus_expenses_mode():
    provider = ProductUnitEconomicsProvider(
        tax_service=TaxService(),
        tax_mode="USN_INCOME_MINUS_EXPENSES",
        tax_rate=15,
        minimum_tax_rate=1,
    )
    facts = {
        "seller_price": 1000,
        "discount_points_per_unit": 100,
        "commission_amount": 100,
        "logistics": 0,
        "last_mile": 0,
        "acquiring_average": 0,
        "cross_docking_per_unit": 100,
        "cross_docking": {"evidence_complete": True},
    }

    result = provider.build_current(facts, product_cost=300)

    assert result["tax_base"] == 400.0
    assert result["tax"] == 60.0
    assert result["net_profit_per_unit"] == 440.0


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
