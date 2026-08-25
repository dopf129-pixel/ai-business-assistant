from services.product_unit_economics_provider import (
    ProductUnitEconomicsProvider
)
from services.product_unit_economics_query_service import (
    ProductUnitEconomicsQueryService
)
from services.tax_service import TaxService


class FakeProductService:
    def load_products(self):
        return [
            {
                "product_id": "old-id",
                "sku": "hook-2"
            }
        ]


class FakeCurrentSource:
    def __init__(self, facts):
        self.facts = facts
        self.calls = []

    def get(self, **kwargs):
        self.calls.append(dict(kwargs))
        return dict(self.facts)


class FakeCostService:
    def __init__(self, costs):
        self.costs = costs
        self.calls = []

    def get_cost(self, product_id):
        self.calls.append(str(product_id))
        value = self.costs.get(str(product_id))
        if value is None:
            return None
        return (
            str(product_id),
            "hook-2",
            "hook",
            value,
            "RUB",
            "2026-08-25"
        )


class UnusedPeriodProfitService:
    def calculate_period_profit(self, *args, **kwargs):
        raise AssertionError("historical path must not be used")


class UnusedAnalyticsService:
    def get_period(self):
        raise AssertionError("historical path must not be used")


def _facts(**overrides):
    data = {
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
    data.update(overrides)
    return data


def _service(facts=None, tax_mode="USN_INCOME"):
    source = FakeCurrentSource(
        facts or _facts()
    )
    costs = FakeCostService(
        {
            "4108512640": 21.0,
            "old-id": 99.0
        }
    )
    provider = ProductUnitEconomicsProvider(
        tax_service=TaxService(),
        tax_mode=tax_mode,
        tax_rate=6.0
    )
    service = ProductUnitEconomicsQueryService(
        product_service=FakeProductService(),
        period_profit_service=UnusedPeriodProfitService(),
        analytics_service=UnusedAnalyticsService(),
        unit_economics_provider=provider,
        current_economics_source=source,
        cost_service=costs,
        current_finance_days=2
    )
    return service, source, costs


def test_current_query_uses_live_price_and_prepared_expenses():
    service, source, costs = _service()

    result = service.query("hook-2")

    assert result["source"] == "current"
    assert result["unit_price"] == 96.0
    assert result["cost"] == 21.0
    assert result["commission"] == 13.44
    assert result["logistics"] == 19.32
    assert result["last_mile"] == 1.76
    assert result["acquiring"] == 1.27
    assert result["marketplace_fees"] == 35.79
    assert result["tax"] == 5.76
    assert result["net_profit_per_unit"] == 33.45
    assert result["margin_percent"] == 34.84
    assert result["missing_fields"] == []
    assert costs.calls == ["4108512640"]
    assert source.calls[0]["sku"] == "hook-2"
    assert len(source.calls[0]["accrual_dates"]) == 2


def test_current_response_shows_rubles_and_percentages():
    service, _, _ = _service()

    response = service.format_response(
        service.query("hook-2")
    )

    assert "Актуальная цена продавца:\n96.00 ₽ — 100.0%" in response
    assert "Комиссия Ozon:\n13.44 ₽ — 14.0%" in response
    assert "Логистика:\n19.32 ₽ — 20.1%" in response
    assert "Последняя миля:\n1.76 ₽ — 1.8%" in response
    assert "Эквайринг:\n1.27 ₽ — 1.3%" in response
    assert "Себестоимость:\n21.00 ₽ — 21.9%" in response
    assert "Налог:\n5.76 ₽ — 6.0%" in response
    assert "Расчётная прибыль с 1 шт:\n33.45 ₽ — 34.8%" in response
    assert "Реклама" not in response
    assert "Хранение" not in response


def test_missing_logistics_keeps_profit_unknown():
    service, _, _ = _service(
        _facts(
            logistics=None,
            missing_data=["logistics"]
        )
    )

    result = service.query("hook-2")

    assert result["logistics"] is None
    assert result["net_profit_per_unit"] is None
    assert result["margin_percent"] is None
    assert "logistics" in result["missing_fields"]

    response = service.format_response(result)
    assert "Логистика:\n—" in response
    assert "Расчётная прибыль с 1 шт:\n—" in response


def test_missing_tax_keeps_profit_unknown():
    service, _, _ = _service(tax_mode=None)

    result = service.query("hook-2")

    assert result["tax"] is None
    assert result["net_profit_per_unit"] is None
    assert result["margin_percent"] is None
    assert "tax" in result["missing_fields"]


def test_current_product_id_is_preferred_for_cost_lookup():
    service, _, costs = _service()

    result = service.query("hook-2")

    assert result["cost"] == 21.0
    assert costs.calls == ["4108512640"]


def test_missing_current_product_cost_falls_back_to_catalog_id():
    source = FakeCurrentSource(_facts())
    costs = FakeCostService({"old-id": 21.0})
    provider = ProductUnitEconomicsProvider(
        tax_service=TaxService(),
        tax_mode="USN_INCOME",
        tax_rate=6.0
    )
    service = ProductUnitEconomicsQueryService(
        product_service=FakeProductService(),
        period_profit_service=UnusedPeriodProfitService(),
        analytics_service=UnusedAnalyticsService(),
        unit_economics_provider=provider,
        current_economics_source=source,
        cost_service=costs
    )

    result = service.query("hook-2")

    assert result["cost"] == 21.0
    assert costs.calls == ["4108512640", "old-id"]
