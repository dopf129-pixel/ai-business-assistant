from services.product_unit_economics_provider import (
    ProductUnitEconomicsProvider
)
from services.product_unit_economics_query_service import (
    ProductUnitEconomicsQueryService
)
from services.profit_service import ProfitService
from services.store_period_profit_service import (
    StorePeriodProfitService
)
from services.tax_service import TaxService


class FakeFinanceService:

    def get_daily_finance(self, current_date, sku=None):
        return {
            "error": False,
            "date": current_date,
            "sku": sku,
            "operations": 1,
            "sales_count": 2,
            "gross_sales": 2980.0,
            "net_accrual": 2240.0,
            "commission": -360.0,
            "logistics": -240.0,
            "acquiring": -40.0,
            "other_fees": -100.0,
            "fee_breakdown": {
                "Продажа": -360.0,
                "Логистика": -240.0,
                "Эквайринг": -40.0,
                "Прочее": -100.0
            }
        }


class FakeCostService:

    def get_cost(self, product_id):
        return (
            product_id,
            None,
            None,
            520.0
        )


class FakeProductService:

    def load_products(self):
        return [
            {
                "product_id": "101",
                "sku": "hook-2"
            }
        ]


class FakeAnalyticsService:

    def get_period(self):
        return {
            "error": False,
            "date_from": "2026-08-01",
            "date_to": "2026-08-01"
        }


def _period_profit_service():
    return StorePeriodProfitService(
        finance_service=FakeFinanceService(),
        cost_service=FakeCostService(),
        profit_service=ProfitService()
    )


def _query_service():
    return ProductUnitEconomicsQueryService(
        product_service=FakeProductService(),
        period_profit_service=(
            _period_profit_service()
        ),
        analytics_service=FakeAnalyticsService(),
        unit_economics_provider=(
            ProductUnitEconomicsProvider(
                tax_service=TaxService(),
                tax_mode="USN_INCOME",
                tax_rate=6.0
            )
        )
    )


def test_period_profit_preserves_existing_ozon_fee_fields():
    result = (
        _period_profit_service()
        .calculate_period_profit(
            "2026-08-01",
            "2026-08-01",
            [
                {
                    "product_id": "101",
                    "sku": "hook-2"
                }
            ]
        )
    )

    profit = result["profits"][0]

    assert profit["commission"] == -360.0
    assert profit["logistics"] == -240.0
    assert profit["acquiring"] == -40.0
    assert profit["other_fees"] == -100.0
    assert profit["fee_breakdown"]["Логистика"] == -240.0


def test_provider_adds_breakdown_without_changing_profit_formula():
    result = (
        _period_profit_service()
        .calculate_period_profit(
            "2026-08-01",
            "2026-08-01",
            [
                {
                    "product_id": "101",
                    "sku": "hook-2"
                }
            ]
        )
    )

    metric = ProductUnitEconomicsProvider(
        tax_service=TaxService(),
        tax_mode="USN_INCOME",
        tax_rate=6.0
    ).build(result["profits"])[0]

    assert metric["marketplace_fees"] == 740.0
    assert metric["fee_breakdown"] == {
        "commission": 360.0,
        "logistics": 240.0,
        "acquiring": 40.0,
        "other_fees": 100.0
    }
    assert metric["net_profit"] == 1021.2
    assert metric["profit_per_unit"] == 510.6


def test_query_returns_per_unit_fee_breakdown_matching_total():
    result = _query_service().query("hook-2")

    assert result["marketplace_fees"] == 370.0
    assert result["fee_breakdown"] == {
        "commission": 180.0,
        "logistics": 120.0,
        "acquiring": 20.0,
        "other_fees": 50.0
    }
    assert round(
        sum(result["fee_breakdown"].values()),
        2
    ) == result["marketplace_fees"]
    assert result["net_profit_per_unit"] == 510.6


def test_formatted_response_shows_ozon_breakdown_and_unknown_costs():
    service = _query_service()
    response = service.format_response(
        service.query("hook-2")
    )

    assert "Удержания Ozon:" in response
    assert "Комиссия:\n180.00 ₽" in response
    assert "Логистика:\n120.00 ₽" in response
    assert "Эквайринг:\n20.00 ₽" in response
    assert "Прочие удержания:\n50.00 ₽" in response
    assert "Всего удержания Ozon:\n370.00 ₽" in response
    assert "Реклама:\n—" in response
    assert "Хранение:\n—" in response
    assert "Возвраты:\n—" in response
    assert "Расчётная прибыль с 1 шт:\n510.60 ₽" in response


def test_provider_keeps_legacy_contract_when_fee_details_are_missing():
    result = ProductUnitEconomicsProvider(
        tax_service=TaxService(),
        tax_mode="NONE"
    ).build(
        [
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
    )

    assert "fee_breakdown" not in result[0]
    assert result[0]["marketplace_fees"] == 740.0
    assert result[0]["profit_per_unit"] == 600.0
