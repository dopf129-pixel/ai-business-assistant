import sys

sys.path.insert(0, "app")

from services.finance_context_provider import FinanceContextProvider
from services.product_profitability_provider import ProductProfitabilityProvider
from services.store_period_profit_service import StorePeriodProfitService


def test_product_profitability_provider_builds_product_metrics():
    metrics = ProductProfitabilityProvider().build(
        [
            {
                "error": False,
                "product_id": 101,
                "sku": "sku-101",
                "sales_count": 5,
                "gross_sales": 1000,
                "total_cost": 400,
                "gross_profit": 300,
                "margin_percent": 30
            }
        ]
    )

    assert metrics == [
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


def test_product_profitability_provider_returns_empty_for_missing_data():
    assert ProductProfitabilityProvider().build(None) == []
    assert ProductProfitabilityProvider().build([]) == []


def test_product_profitability_provider_skips_incomplete_product_data():
    metrics = ProductProfitabilityProvider().build(
        [
            {
                "error": False,
                "product_id": 101,
                "sku": "sku-101",
                "sales_count": None,
                "gross_sales": 1000,
                "total_cost": 400,
                "gross_profit": 300,
                "margin_percent": 30
            },
            {
                "error": False,
                "product_id": 102,
                "sku": "sku-102",
                "sales_count": 5,
                "gross_sales": 1000,
                "total_cost": None,
                "gross_profit": 300,
                "margin_percent": 30
            }
        ]
    )

    assert metrics == []


class FakeFinanceAnalytics:
    def get_period_finance(
        self,
        date_from,
        date_to,
        sku
    ):
        return {
            "error": False,
            "sales_count": 5,
            "gross_sales": 1000,
            "net_accrual": 700
        }


class FakeCostService:
    def get_cost(self, product_id):
        return (
            product_id,
            None,
            None,
            80
        )


class FakeProfitService:
    def calculate(
        self,
        finance,
        cost_price
    ):
        return {
            "error": False,
            "sales_count": 5,
            "gross_sales": 1000.0,
            "cost_price": 80.0,
            "total_cost": 400.0,
            "net_accrual": 700.0,
            "gross_profit": 300.0,
            "profit_per_unit": 60.0,
            "margin_percent": 30.0
        }


class UnusedFinanceService:
    pass


def test_store_period_profit_preserves_product_identity_with_existing_profit_fields():
    service = StorePeriodProfitService(
        finance_service=UnusedFinanceService(),
        cost_service=FakeCostService(),
        profit_service=FakeProfitService()
    )
    service.finance_analytics = FakeFinanceAnalytics()

    result = service.calculate_period_profit(
        "2026-08-18",
        "2026-08-24",
        [
            {
                "product_id": 101,
                "sku": "sku-101"
            }
        ]
    )

    assert result["products_count"] == 1
    assert result["profits"] == [
        {
            "error": False,
            "sales_count": 5,
            "gross_sales": 1000.0,
            "cost_price": 80.0,
            "total_cost": 400.0,
            "net_accrual": 700.0,
            "gross_profit": 300.0,
            "profit_per_unit": 60.0,
            "margin_percent": 30.0,
            "product_id": 101,
            "sku": "sku-101"
        }
    ]


def test_finance_context_contract_remains_unchanged():
    result = FinanceContextProvider().build(
        {
            "current_profits": [
                {
                    "error": False,
                    "product_id": 101,
                    "sku": "sku-101",
                    "gross_sales": 1000,
                    "gross_profit": 300
                }
            ],
            "previous_profits": [
                {
                    "error": False,
                    "product_id": 101,
                    "sku": "sku-101",
                    "gross_sales": 800,
                    "gross_profit": 200
                }
            ]
        }
    )

    assert result == {
        "finance_context": {
            "finance_data": {
                "revenue": 1000.0,
                "expenses": 700.0,
                "profit": 300.0,
                "margin": 30.0
            },
            "previous_data": {
                "revenue": 800.0,
                "expenses": 600.0,
                "profit": 200.0,
                "margin": 25.0
            }
        }
    }
