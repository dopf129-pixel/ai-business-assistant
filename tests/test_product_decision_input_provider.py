from app.services.product_business_decision_service import (
    ProductBusinessDecisionService,
)
from app.services.product_decision_input_provider import (
    ProductDecisionInputProvider,
)


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
        "product_id": "101",
        "sku": "hook-2",
        "net_profit_per_unit": 510.0,
        "margin_percent": 34.0,
        "missing_data": [
            "advertising",
            "storage",
            "returns",
        ],
    }
    data.update(overrides)
    return data


def test_builds_complete_product_decision_input_from_three_sources():
    provider = ProductDecisionInputProvider()

    result = provider.build(
        sales_metrics=_sales(),
        stock_metrics=_stock(),
        unit_economics=_economics(),
    )

    assert result == {
        "product_id": "101",
        "sku": "hook-2",
        "sales_velocity": 4.0,
        "sales_trend": "GROWING",
        "current_stock": 8,
        "days_of_stock": 2.0,
        "stock_priority": "CRITICAL",
        "profit_per_unit": 510.0,
        "margin_percent": 34.0,
        "missing_data": [
            "advertising",
            "storage",
            "returns",
        ],
    }


def test_sales_and_stock_without_economics_preserve_unknown_values():
    provider = ProductDecisionInputProvider()

    result = provider.build(
        sales_metrics=_sales(),
        stock_metrics=_stock(),
    )

    assert result["profit_per_unit"] is None
    assert result["margin_percent"] is None
    assert "profit_per_unit" in result["missing_data"]
    assert "margin_percent" in result["missing_data"]


def test_missing_unit_economics_fields_are_preserved_as_missing():
    provider = ProductDecisionInputProvider()

    result = provider.build(
        sales_metrics=_sales(),
        stock_metrics=_stock(),
        unit_economics=_economics(
            net_profit_per_unit=None,
            margin_percent=None,
            missing_data=["tax", "advertising"],
        ),
    )

    assert result["profit_per_unit"] is None
    assert result["margin_percent"] is None
    assert result["missing_data"] == [
        "tax",
        "advertising",
        "profit_per_unit",
        "margin_percent",
    ]


def test_identity_mismatch_is_not_repaired_automatically():
    provider = ProductDecisionInputProvider()

    result = provider.build(
        sales_metrics=_sales(),
        stock_metrics=_stock(sku="other-sku"),
        unit_economics=_economics(),
    )

    assert result["product_id"] == "101"
    assert result["sku"] == "hook-2"
    assert "IDENTITY_MISMATCH" in result["missing_data"]


def test_missing_source_keeps_its_fields_none_instead_of_zero():
    provider = ProductDecisionInputProvider()

    result = provider.build(
        unit_economics=_economics(),
    )

    assert result["sales_velocity"] is None
    assert result["sales_trend"] is None
    assert result["current_stock"] is None
    assert result["days_of_stock"] is None
    assert result["stock_priority"] is None
    assert result["sales_velocity"] != 0
    assert "sales_velocity" in result["missing_data"]
    assert "current_stock" in result["missing_data"]


def test_missing_sales_trend_is_explicit_but_other_metrics_are_preserved():
    provider = ProductDecisionInputProvider()

    result = provider.build(
        sales_metrics=_sales(sales_trend=None),
        stock_metrics=_stock(),
        unit_economics=_economics(),
    )

    assert result["sales_velocity"] == 4.0
    assert result["sales_trend"] is None
    assert result["current_stock"] == 8
    assert result["profit_per_unit"] == 510.0
    assert "sales_trend" in result["missing_data"]


def test_output_is_directly_compatible_with_business_decision_service():
    provider = ProductDecisionInputProvider()
    decision_service = ProductBusinessDecisionService()

    prepared = provider.build(
        sales_metrics=_sales(),
        stock_metrics=_stock(),
        unit_economics=_economics(missing_data=[]),
    )
    decision = decision_service.decide(prepared)

    assert decision["product_id"] == "101"
    assert decision["sku"] == "hook-2"
    assert decision["decision_type"] == "REPLENISH_HIGH_PRIORITY"
    assert decision["priority"] == "CRITICAL"


def test_provider_does_not_mutate_source_contracts():
    provider = ProductDecisionInputProvider()
    sales = _sales()
    stock = _stock()
    economics = _economics()

    provider.build(
        sales_metrics=sales,
        stock_metrics=stock,
        unit_economics=economics,
    )

    assert sales == _sales()
    assert stock == _stock()
    assert economics == _economics()
