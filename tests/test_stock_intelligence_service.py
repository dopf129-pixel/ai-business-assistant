from app.services.stock_intelligence_service import (
    StockIntelligenceService,
)


def test_stock_intelligence_critical_stock():

    service = StockIntelligenceService()

    result = service.analyze(
        stock_data={
            "product_id": "101",
            "current_stock": 3,
        },
        sales_data={
            "product_id": "101",
            "sales_count": 21,
        },
        period_days=7,
    )

    assert result == {
        "error": False,
        "product_id": "101",
        "current_stock": 3,
        "sales_velocity": 3.0,
        "days_of_stock": 1.0,
        "priority": "CRITICAL",
    }


def test_stock_intelligence_high_priority():

    service = StockIntelligenceService()

    result = service.analyze(
        stock_data={
            "product_id": "102",
            "current_stock": 10,
        },
        sales_data={
            "product_id": "102",
            "sales_count": 20,
        },
        period_days=10,
    )

    assert result["sales_velocity"] == 2.0
    assert result["days_of_stock"] == 5.0
    assert result["priority"] == "HIGH"


def test_stock_intelligence_sufficient_stock():

    service = StockIntelligenceService()

    result = service.analyze(
        stock_data={
            "product_id": "103",
            "current_stock": 100,
        },
        sales_data={
            "product_id": "103",
            "sales_count": 14,
        },
        period_days=7,
    )

    assert result["days_of_stock"] == 50.0
    assert result["priority"] == "LOW"


def test_stock_intelligence_no_sales():

    service = StockIntelligenceService()

    result = service.analyze(
        stock_data={
            "product_id": "104",
            "current_stock": 20,
        },
        sales_data={
            "product_id": "104",
            "sales_count": 0,
        },
        period_days=7,
    )

    assert result["error"] is False
    assert result["sales_velocity"] == 0
    assert result["days_of_stock"] is None
    assert result["priority"] == "NO_SALES"


def test_stock_intelligence_empty_data():

    service = StockIntelligenceService()

    result = service.analyze(
        stock_data=None,
        sales_data=None,
        period_days=7,
    )

    assert result["error"] is True
    assert result["product_id"] is None
    assert result["current_stock"] is None
    assert result["sales_velocity"] is None
    assert result["days_of_stock"] is None
    assert result["priority"] == "UNKNOWN"
