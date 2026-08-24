from services.product_profitability_provider import (
    ProductProfitabilityProvider
)
from services.product_unit_economics_provider import (
    ProductUnitEconomicsProvider
)
from services.product_unit_economics_query_service import (
    ProductUnitEconomicsQueryService
)
from services.tax_service import TaxService


class FakeProductService:

    def __init__(self, products):
        self.products = products

    def load_products(self):
        return self.products


class FakeAnalyticsService:

    def get_period(self):
        return {
            "error": False,
            "date_from": "2026-08-01",
            "date_to": "2026-08-07"
        }


class FakePeriodProfitService:

    def __init__(self, profits):
        self.profits = profits
        self.calls = []

    def calculate_period_profit(
        self,
        date_from,
        date_to,
        products
    ):
        self.calls.append(
            {
                "date_from": date_from,
                "date_to": date_to,
                "products": products
            }
        )
        target_skus = {
            str(product.get("sku"))
            for product in products
        }
        return {
            "error": False,
            "profits": [
                item
                for item in self.profits
                if str(item.get("sku"))
                in target_skus
            ]
        }


def make_profit(
    product_id="101",
    sku="hook-2",
    sales_count=2
):
    return {
        "error": False,
        "product_id": product_id,
        "sku": sku,
        "sales_count": sales_count,
        "gross_sales": 2980.0,
        "net_accrual": 2240.0,
        "total_cost": 1040.0,
        "gross_profit": 1200.0,
        "margin_percent": 40.27
    }


def make_query_service(
    products,
    profits,
    tax_mode="USN_INCOME"
):
    unit_provider = ProductUnitEconomicsProvider(
        tax_service=TaxService(),
        tax_mode=tax_mode,
        tax_rate=6.0
    )
    period_profit_service = (
        FakePeriodProfitService(profits)
    )

    return (
        ProductUnitEconomicsQueryService(
            product_service=(
                FakeProductService(products)
            ),
            period_profit_service=(
                period_profit_service
            ),
            analytics_service=(
                FakeAnalyticsService()
            ),
            unit_economics_provider=(
                unit_provider
            )
        ),
        period_profit_service
    )


def test_query_finds_sku_and_returns_unit_economics():
    service, period_profit_service = (
        make_query_service(
            products=[
                (101, "hook", "hook-2")
            ],
            profits=[make_profit()]
        )
    )

    result = service.query("hook-2")

    assert result["error"] is False
    assert result["available"] is True
    assert result["sku"] == "hook-2"
    assert result["unit_price"] == 1490.0
    assert result["cost"] == 520.0
    assert result["marketplace_fees"] == 370.0
    assert result["tax"] == 89.4
    assert result["net_profit_per_unit"] == 510.6
    assert result["margin_percent"] == 34.27
    assert result["missing_fields"] == [
        "advertising",
        "storage",
        "returns"
    ]
    assert period_profit_service.calls[0][
        "products"
    ][0]["sku"] == "hook-2"


def test_query_returns_not_found_for_unknown_sku():
    service, _ = make_query_service(
        products=[
            {
                "product_id": "101",
                "sku": "hook-2"
            }
        ],
        profits=[make_profit()]
    )

    result = service.query("missing-sku")

    assert result == {
        "error": True,
        "code": "SKU_NOT_FOUND",
        "sku": "missing-sku",
        "message": "SKU не найден"
    }


def test_query_exposes_missing_expenses_without_zero_fill():
    service, _ = make_query_service(
        products=[
            {
                "product_id": "101",
                "sku": "hook-2"
            }
        ],
        profits=[make_profit()],
        tax_mode=None
    )

    result = service.query("hook-2")

    assert result["tax"] is None
    assert result["net_profit_per_unit"] is None
    assert result["margin_percent"] is None
    assert result["missing_fields"] == [
        "advertising",
        "storage",
        "returns",
        "tax"
    ]
    assert "без учёта отсутствующих расходов" in (
        result["note"]
    )

    response = service.format_response(result)

    assert "Налог:\n—" in response
    assert "Реклама:\n—" in response
    assert "Хранение:\n—" in response
    assert "Возвраты:\n—" in response


def test_query_returns_safe_empty_result_when_finance_data_missing():
    service, _ = make_query_service(
        products=[
            {
                "product_id": "101",
                "sku": "hook-2"
            }
        ],
        profits=[]
    )

    result = service.query("hook-2")

    assert result["error"] is False
    assert result["available"] is False
    assert result["unit_price"] is None
    assert result["net_profit_per_unit"] is None
    assert "cost" in result["missing_fields"]
    assert "advertising" in result[
        "missing_fields"
    ]


def test_query_selects_only_requested_sku():
    service, period_profit_service = (
        make_query_service(
            products=[
                (101, "hook", "hook-2"),
                (202, "case", "case-9")
            ],
            profits=[
                make_profit(),
                make_profit(
                    product_id="202",
                    sku="case-9"
                )
            ]
        )
    )

    result = service.query("case-9")

    assert result["sku"] == "case-9"
    assert period_profit_service.calls[0][
        "products"
    ] == [
        {
            "product_id": 202,
            "offer_id": "case",
            "sku": "case-9"
        }
    ]


def test_query_treats_zero_sales_as_unavailable_unit_data():
    service, _ = make_query_service(
        products=[
            {
                "product_id": "101",
                "sku": "hook-2"
            }
        ],
        profits=[
            make_profit(
                sales_count=0
            )
        ]
    )

    result = service.query("hook-2")

    assert result["available"] is False
    assert result["unit_price"] is None
    assert result["net_profit_per_unit"] is None


def test_existing_product_profitability_provider_contract_is_preserved():
    result = ProductProfitabilityProvider().build(
        [make_profit()]
    )

    assert result == [
        {
            "product_id": "101",
            "sku": "hook-2",
            "sales_count": 2,
            "revenue": 2980.0,
            "cost": 1040.0,
            "profit": 1200.0,
            "margin": 40.27
        }
    ]
