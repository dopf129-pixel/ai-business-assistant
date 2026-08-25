from app.services.product_business_decision_service import (
    ProductBusinessDecisionService,
)


def _metrics(**overrides):
    data = {
        "product_id": "101",
        "sku": "hook-2",
        "sales_velocity": 4.0,
        "sales_trend": "GROWING",
        "current_stock": 20,
        "days_of_stock": 5.0,
        "stock_priority": "HIGH",
        "profit_per_unit": 500.0,
        "margin_percent": 30.0,
        "missing_data": [],
    }
    data.update(overrides)
    return data


def test_critical_stock_and_positive_profit_is_high_priority_replenishment():
    service = ProductBusinessDecisionService()

    result = service.decide(
        _metrics(
            current_stock=4,
            days_of_stock=1.0,
            stock_priority="CRITICAL",
        )
    )

    assert result == {
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
    }


def test_low_stock_and_positive_profit_is_normal_replenishment():
    service = ProductBusinessDecisionService()

    result = service.decide(_metrics())

    assert result["decision_type"] == "REPLENISH_NORMAL"
    assert result["priority"] == "HIGH"
    assert "DAYS_OF_STOCK_LOW" in result["reasons"]
    assert "POSITIVE_UNIT_PROFIT" in result["reasons"]


def test_healthy_stock_and_low_margin_is_watch_low_margin():
    service = ProductBusinessDecisionService(low_margin_percent=10.0)

    result = service.decide(
        _metrics(
            stock_priority="MEDIUM",
            days_of_stock=10.0,
            margin_percent=5.0,
            profit_per_unit=20.0,
        )
    )

    assert result["decision_type"] == "WATCH_LOW_MARGIN"
    assert result["priority"] == "NORMAL"
    assert result["reasons"] == ["LOW_MARGIN", "LOW_UNIT_PROFIT"]


def test_zero_profit_is_investigate_low_profit():
    service = ProductBusinessDecisionService()

    result = service.decide(
        _metrics(
            stock_priority="MEDIUM",
            days_of_stock=10.0,
            profit_per_unit=0.0,
        )
    )

    assert result["decision_type"] == "INVESTIGATE_LOW_PROFIT"
    assert "LOW_UNIT_PROFIT" in result["reasons"]


def test_negative_profit_economics_guard_wins_over_critical_stock():
    service = ProductBusinessDecisionService()

    result = service.decide(
        _metrics(
            stock_priority="CRITICAL",
            days_of_stock=1.0,
            current_stock=2,
            profit_per_unit=-100.0,
        )
    )

    assert result["decision_type"] == "INVESTIGATE_LOW_PROFIT"
    assert result["priority"] == "HIGH"
    assert result["reasons"] == [
        "DAYS_OF_STOCK_CRITICAL",
        "NEGATIVE_UNIT_PROFIT",
    ]


def test_excess_stock_and_no_sales_is_hold_stock():
    service = ProductBusinessDecisionService()

    result = service.decide(
        _metrics(
            sales_velocity=0.0,
            sales_trend="DECLINING",
            stock_priority="LOW",
            days_of_stock=40.0,
            current_stock=100,
        )
    )

    assert result["decision_type"] == "HOLD_STOCK"
    assert result["priority"] == "LOW"
    assert result["reasons"] == [
        "POSITIVE_UNIT_PROFIT",
        "SALES_DECLINING",
    ]


def test_missing_required_data_is_insufficient_without_zero_fallback():
    service = ProductBusinessDecisionService()

    result = service.decide(
        _metrics(
            profit_per_unit=None,
            margin_percent=None,
            missing_data=["tax"],
        )
    )

    assert result["decision_type"] == "INSUFFICIENT_DATA"
    assert result["priority"] == "NONE"
    assert result["confidence"] == "LOW"
    assert result["reasons"] == ["ECONOMICS_INCOMPLETE"]
    assert result["missing_data"] == [
        "tax",
        "profit_per_unit",
        "margin_percent",
    ]


def test_identity_mismatch_is_insufficient_data():
    service = ProductBusinessDecisionService()

    result = service.decide(
        _metrics(missing_data=["IDENTITY_MISMATCH"])
    )

    assert result == {
        "product_id": "101",
        "sku": "hook-2",
        "decision_type": "INSUFFICIENT_DATA",
        "priority": "NONE",
        "reasons": ["IDENTITY_MISMATCH"],
        "confidence": "LOW",
        "missing_data": ["IDENTITY_MISMATCH"],
    }


def test_incomplete_non_required_costs_reduce_confidence_but_keep_decision():
    service = ProductBusinessDecisionService()

    result = service.decide(
        _metrics(
            stock_priority="CRITICAL",
            days_of_stock=1.0,
            missing_data=["advertising", "storage", "returns"],
        )
    )

    assert result["decision_type"] == "REPLENISH_HIGH_PRIORITY"
    assert result["confidence"] == "MEDIUM"
    assert result["missing_data"] == [
        "advertising",
        "storage",
        "returns",
    ]


def test_same_input_always_produces_same_output():
    service = ProductBusinessDecisionService()
    input_data = _metrics(
        stock_priority="CRITICAL",
        days_of_stock=2.0,
    )

    first = service.decide(input_data)
    second = service.decide(input_data)

    assert first == second
    assert input_data == _metrics(
        stock_priority="CRITICAL",
        days_of_stock=2.0,
    )
