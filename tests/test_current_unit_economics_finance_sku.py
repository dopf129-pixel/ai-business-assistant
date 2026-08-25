from services.product_unit_economics_provider import ProductUnitEconomicsProvider
from services.product_unit_economics_query_service import ProductUnitEconomicsQueryService
from services.tax_service import TaxService


class FakeProductService:
    def load_products(self):
        return [("4108512640", "hook-2", "3921245627")]


class FakeCurrentSource:
    def __init__(self):
        self.calls = []

    def get(self, **kwargs):
        self.calls.append(dict(kwargs))
        return {
            "error": False,
            "product_id": "4108512640",
            "sku": "hook-2",
            "seller_price": 96.0,
            "commission_rate": 14.0,
            "commission_amount": 13.44,
            "logistics": 19.32,
            "last_mile": 1.76,
            "acquiring_average": 1.27,
            "finance_sample_sales": 50,
            "finance_sample_days": 2,
            "as_of": "2026-08-25T07:00:00+00:00",
            "missing_data": []
        }


class FakeCostService:
    def get_cost(self, product_id):
        return (str(product_id), "hook-2", "hook", 21.0, "RUB", "2026-08-25")


class Unused:
    def __getattr__(self, name):
        raise AssertionError(name)


def test_query_uses_offer_id_for_price_and_internal_sku_for_finance():
    source = FakeCurrentSource()
    query = ProductUnitEconomicsQueryService(
        product_service=FakeProductService(),
        period_profit_service=Unused(),
        analytics_service=Unused(),
        unit_economics_provider=ProductUnitEconomicsProvider(
            tax_service=TaxService(),
            tax_mode="USN_INCOME",
            tax_rate=6.0
        ),
        current_economics_source=source,
        cost_service=FakeCostService()
    )

    result = query.query("hook-2")

    assert result["error"] is False
    assert source.calls[0]["sku"] == "hook-2"
    assert source.calls[0]["finance_sku"] == "3921245627"
    assert source.calls[0]["product_id"] == "4108512640"
