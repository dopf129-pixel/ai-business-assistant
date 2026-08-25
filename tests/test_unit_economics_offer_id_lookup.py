from services.product_unit_economics_query_service import (
    ProductUnitEconomicsQueryService
)


class FakeProductService:
    def load_products(self):
        return [
            (4108512640, "hook-2", "3921245627")
        ]


class FakeCurrentSource:
    def get(self, **kwargs):
        sku = kwargs["sku"]
        return {
            "error": False,
            "sku": sku,
            "product_id": "4108512640",
            "seller_price": 96.0,
            "commission_rate": 14.0,
            "commission_amount": 13.44,
            "logistics": 19.32,
            "last_mile": 1.8,
            "acquiring_average": 1.2,
            "finance_sample_sales": 5,
            "finance_sample_days": 2,
            "as_of": "2026-08-25T00:00:00+00:00",
            "missing_data": []
        }


class FakeUnitProvider:
    def build_current(self, facts, cost):
        return {
            "product_id": facts["product_id"],
            "sku": facts["sku"],
            "unit_price": facts["seller_price"],
            "cost": cost,
            "commission": facts["commission_amount"],
            "commission_rate": facts["commission_rate"],
            "logistics": facts["logistics"],
            "last_mile": facts["last_mile"],
            "acquiring": facts["acquiring_average"],
            "tax": None,
            "net_profit_per_unit": None,
            "margin_percent": None,
            "missing_fields": ["tax"],
            "finance_sample_sales": 5,
            "finance_sample_days": 2
        }


class FakeCostService:
    def get_cost(self, product_id):
        return (product_id, None, None, 21.0)


def test_query_accepts_offer_id_as_user_product_identifier():
    service = ProductUnitEconomicsQueryService(
        product_service=FakeProductService(),
        period_profit_service=None,
        analytics_service=None,
        unit_economics_provider=FakeUnitProvider(),
        current_economics_source=FakeCurrentSource(),
        cost_service=FakeCostService()
    )

    result = service.query("hook-2")

    assert result["error"] is False
    assert result["source"] == "current"
    assert result["sku"] == "hook-2"
    assert result["product_id"] == "4108512640"
    assert result["unit_price"] == 96.0
    assert result["cost"] == 21.0
