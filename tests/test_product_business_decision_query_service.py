from app.services.product_business_decision_query_service import (
    ProductBusinessDecisionQueryService,
)
from app.services.product_business_decision_service import (
    ProductBusinessDecisionService,
)
from app.services.product_decision_input_provider import (
    ProductDecisionInputProvider,
)


class StubProductService:
    def __init__(self, products):
        self.products = products

    def load_products(self):
        return self.products


class StubSource:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def query(self, sku):
        self.calls.append(sku)
        if self.result is None:
            return None
        return dict(self.result)


class StubUnitEconomicsQuery:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def query(self, sku):
        self.calls.append(sku)
        return dict(self.result)


def _sales(**overrides):
    data = {
        "product_id": "101",
        "sku": "hook-2",
        "sales_velocity": 4.0,
        "sales_trend": "GROWING",
    }
    data.update(overrides)
    return data


def _stock(**overrides):
    data = {
        "product_id": "101",
        "sku": "hook-2",
        "current_stock": 8,
        "days_of_stock": 2.0,
        "priority": "CRITICAL",
    }
    data.update(overrides)
    return data


def _economics(**overrides):
    data = {
        "error": False,
        "available": True,
        "product_id": "101",
        "sku": "hook-2",
        "net_profit_per_unit": 510.0,
        "margin_percent": 34.0,
        "missing_fields": [],
    }
    data.update(overrides)
    return data


def _service(
    products=None,
    sales=None,
    stock=None,
    economics=None,
):
    return ProductBusinessDecisionQueryService(
        product_service=StubProductService(
            products
            if products is not None
            else [{"product_id": "101", "sku": "hook-2"}]
        ),
        sales_metrics_source=StubSource(
            _sales() if sales is None else sales
        ),
        stock_metrics_source=StubSource(
            _stock() if stock is None else stock
        ),
        unit_economics_query_service=StubUnitEconomicsQuery(
            _economics() if economics is None else economics
        ),
        decision_input_provider=ProductDecisionInputProvider(),
        decision_service=ProductBusinessDecisionService(),
    )


def test_successful_query_returns_structured_business_decision():
    service = _service()

    result = service.query({"sku": "hook-2"})

    assert result == {
        "error": False,
        "code": None,
        "product_id": "101",
        "sku": "hook-2",
        "decision_type": "REPLENISH_HIGH_PRIORITY",
        "priority": "CRITICAL",
        "reasons": [
            "DAYS_OF_STOCK_CRITICAL",
            "POSITIVE_UNIT_PROFIT",
        ],
        "confidence": "HIGH",
        "missing_data": [],
        "sales_velocity": 4.0,
        "sales_trend": "GROWING",
        "current_stock": 8,
        "days_of_stock": 2.0,
        "stock_priority": "CRITICAL",
        "decision_profit_per_unit": 510.0,
        "decision_margin_percent": 34.0,
    }


def test_unknown_sku_returns_structured_sku_not_found():
    service = _service(products=[])

    result = service.query({"sku": "missing"})

    assert result == {
        "error": True,
        "code": "SKU_NOT_FOUND",
        "product_id": None,
        "sku": "missing",
        "decision_type": "INSUFFICIENT_DATA",
        "priority": "NONE",
        "reasons": [],
        "confidence": "LOW",
        "missing_data": ["sku"],
    }


def test_decision_generation_uses_existing_provider_and_service_contracts():
    service = _service(
        stock=_stock(
            current_stock=30,
            days_of_stock=10.0,
            priority="MEDIUM",
        ),
        economics=_economics(
            net_profit_per_unit=20.0,
            margin_percent=5.0,
        ),
    )

    result = service.query("hook-2")

    assert result["decision_type"] == "WATCH_LOW_MARGIN"
    assert result["priority"] == "NORMAL"
    assert result["reasons"] == ["LOW_MARGIN", "LOW_UNIT_PROFIT"]


def test_missing_metrics_return_insufficient_data_without_zero_fallback():
    service = _service(
        sales={"error": True},
        stock={"error": True},
    )

    result = service.query({"sku": "hook-2"})

    assert result["error"] is False
    assert result["code"] == "INSUFFICIENT_DATA"
    assert result["decision_type"] == "INSUFFICIENT_DATA"
    assert result["confidence"] == "LOW"
    assert "sales_velocity" in result["missing_data"]
    assert "current_stock" in result["missing_data"]


def test_incomplete_economics_remains_none_and_insufficient():
    service = _service(
        economics=_economics(
            net_profit_per_unit=None,
            margin_percent=None,
            missing_fields=["tax", "advertising"],
        )
    )

    result = service.query({"sku": "hook-2"})

    assert result["code"] == "INSUFFICIENT_DATA"
    assert result["decision_type"] == "INSUFFICIENT_DATA"
    assert "tax" in result["missing_data"]
    assert "advertising" in result["missing_data"]
    assert "profit_per_unit" in result["missing_data"]
    assert "margin_percent" in result["missing_data"]


def test_identity_mismatch_is_preserved_as_insufficient_data():
    service = _service(
        stock=_stock(sku="other-sku"),
    )

    result = service.query({"sku": "hook-2"})

    assert result["code"] == "INSUFFICIENT_DATA"
    assert result["decision_type"] == "INSUFFICIENT_DATA"
    assert result["reasons"] == ["IDENTITY_MISMATCH"]
    assert "IDENTITY_MISMATCH" in result["missing_data"]


def test_query_does_not_mutate_prepared_source_data():
    sales = _sales()
    stock = _stock()
    economics = _economics()

    service = _service(
        sales=sales,
        stock=stock,
        economics=economics,
    )

    service.query({"sku": "hook-2"})

    assert sales == _sales()
    assert stock == _stock()
    assert economics == _economics()


def test_missing_sku_is_business_result_not_exception():
    service = _service()

    result = service.query({"sku": None})

    assert result["error"] is True
    assert result["code"] == "SKU_REQUIRED"
    assert result["decision_type"] == "INSUFFICIENT_DATA"
    assert result["missing_data"] == ["sku"]


def test_query_accepts_seller_offer_id_when_internal_sku_differs():
    service = _service(
        products=[{
            "product_id": "101",
            "offer_id": "hook-2",
            "sku": "3921245627",
        }]
    )

    result = service.query("hook-2")

    assert result["error"] is False
    assert result["sku"] == "hook-2"
    assert service.sales_metrics_source.calls == ["hook-2"]
    assert service.stock_metrics_source.calls == ["hook-2"]
    assert (
        service.unit_economics_query_service.calls
        == ["hook-2"]
    )


def test_estimated_returns_profit_drives_decision_and_reduces_confidence():
    service = _service(
        economics=_economics(
            net_profit_per_unit=20.0,
            margin_percent=20.83,
            returns_finance_impact={"error": False},
            returns_estimate_available=True,
            estimated_returns_cost_per_unit=25.0,
            estimated_profit_per_unit=-5.0,
            estimated_margin_percent=-5.21,
            returns_estimate_coverage_percent=91.11,
            missing_fields=["returns"],
        )
    )

    result = service.query("hook-2")

    assert result["decision_type"] == "INVESTIGATE_LOW_PROFIT"
    assert result["confidence"] == "MEDIUM"
    assert result["economics_basis"] == "ESTIMATED_RETURNS"
    assert result["decision_profit_per_unit"] == -5.0
    assert result["decision_margin_percent"] == -5.21
    assert result["returns_reserve_per_unit"] == 25.0
    assert result["returns_coverage_percent"] == 91.11


def test_confirmed_returns_profit_drives_high_confidence_decision():
    service = _service(
        economics=_economics(
            returns_finance_impact={"error": False},
            risk_adjusted_profit_per_unit=15.0,
            risk_adjusted_margin_percent=15.63,
            returns_cost_per_delivered_unit=5.0,
            missing_fields=[],
        )
    )

    result = service.query("hook-2")

    assert result["decision_type"] == "REPLENISH_HIGH_PRIORITY"
    assert result["confidence"] == "HIGH"
    assert result["economics_basis"] == "CONFIRMED_RETURNS"
    assert result["decision_profit_per_unit"] == 15.0
    assert result["returns_reserve_per_unit"] == 5.0


def test_returns_impact_without_reliable_estimate_blocks_base_profit():
    service = _service(
        economics=_economics(
            returns_finance_impact={"error": False},
            returns_estimate_available=False,
            estimated_profit_per_unit=None,
            missing_fields=["returns"],
        )
    )

    result = service.query("hook-2")

    assert result["decision_type"] == "INSUFFICIENT_DATA"
    assert result["confidence"] == "LOW"
    assert result["economics_basis"] == "RETURNS_UNAVAILABLE"
    assert result["decision_profit_per_unit"] is None
    assert "profit_per_unit" in result["missing_data"]


def test_query_exposes_metrics_used_by_decision_card():
    result = _service().query("hook-2")

    assert result["sales_velocity"] == 4.0
    assert result["sales_trend"] == "GROWING"
    assert result["current_stock"] == 8
    assert result["days_of_stock"] == 2.0
    assert result["stock_priority"] == "CRITICAL"
    assert result["decision_profit_per_unit"] == 510.0
    assert result["decision_margin_percent"] == 34.0
