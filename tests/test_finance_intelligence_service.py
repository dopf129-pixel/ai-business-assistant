import sys

sys.path.insert(
    0,
    "app"
)

from services.finance_intelligence_service import (
    FinanceIntelligenceService
)


def test_positive_profit():

    service = FinanceIntelligenceService()

    result = service.analyze(
        {
            "revenue": 1000,
            "expenses": 600
        }
    )

    assert result["error"] is False
    assert result["metrics"] == {
        "revenue": 1000.0,
        "expenses": 600.0,
        "profit": 400.0,
        "margin": 40.0
    }
    assert any(
        item["type"] == "finance_profitable"
        for item in result["insights"]
    )


def test_profit_decline():

    service = FinanceIntelligenceService()

    result = service.analyze(
        {
            "revenue": 1000,
            "expenses": 700,
            "profit": 300
        },
        previous_data={
            "revenue": 1000,
            "expenses": 500,
            "profit": 500
        }
    )

    decline = next(
        item
        for item in result["insights"]
        if item["type"] == "profit_decline"
    )

    assert decline["severity"] == "attention"
    assert decline["change_percent"] == -40.0


def test_expenses_growth():

    service = FinanceIntelligenceService()

    result = service.analyze(
        {
            "revenue": 1200,
            "expenses": 600
        },
        previous_data={
            "revenue": 1000,
            "expenses": 400
        }
    )

    growth = next(
        item
        for item in result["insights"]
        if item["type"] == "expenses_growth"
    )

    assert growth["severity"] == "attention"
    assert growth["change_percent"] == 50.0


def test_missing_finance_data():

    service = FinanceIntelligenceService()

    result = service.analyze({})

    assert result["error"] is True
    assert result["metrics"] == {
        "revenue": None,
        "expenses": None,
        "profit": None,
        "margin": None
    }
    assert result["insights"] == []
