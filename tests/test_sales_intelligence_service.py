import sys

sys.path.insert(
    0,
    "app"
)


from services.sales_intelligence_service import (
    SalesIntelligenceService
)


class FakeAnalyticsService:

    def __init__(
        self,
        result
    ):

        self.result = result
        self.calls = []


    def analyze(
        self,
        profits,
        previous_result=None
    ):

        self.calls.append(
            {
                "profits": profits,
                "previous_result": previous_result
            }
        )

        return self.result


def test_sales_intelligence_uses_injected_analytics_service():

    analytics = FakeAnalyticsService(
        {
            "error": False,
            "store_profit": {
                "gross_sales": 1200,
                "gross_profit": 420
            },
            "business_profit": {
                "business_profit": 300,
                "margin_percent": 25
            }
        }
    )

    service = SalesIntelligenceService(
        analytics
    )

    profits = [
        {
            "sku": "SKU-1",
            "profit": 300
        }
    ]

    result = service.analyze(
        profits
    )

    assert result["error"] is False

    assert result["metrics"] == {
        "revenue": 1200,
        "gross_profit": 420,
        "business_profit": 300,
        "margin_percent": 25
    }

    assert analytics.calls == [
        {
            "profits": profits,
            "previous_result": None
        }
    ]


def test_sales_intelligence_builds_decline_insight_from_comparison():

    comparison = {
        "error": False,
        "comparison": {
            "revenue": {
                "change_percent": -12.5,
                "trend": "Снижение"
            }
        }
    }

    analytics = FakeAnalyticsService(
        {
            "error": False,
            "store_profit": {
                "gross_sales": 875,
                "gross_profit": 250
            },
            "business_profit": {
                "business_profit": 150,
                "margin_percent": 17.14
            },
            "comparison": comparison
        }
    )

    service = SalesIntelligenceService(
        analytics
    )

    result = service.analyze(
        [],
        previous_result={
            "store_profit": {
                "gross_sales": 1000
            }
        }
    )

    assert result["comparison"] == comparison

    assert result["insights"] == [
        {
            "type": "sales_decline",
            "severity": "attention",
            "change_percent": -12.5,
            "message": "Продажи снизились относительно предыдущего периода"
        }
    ]


def test_sales_intelligence_propagates_analytics_error():

    analytics = FakeAnalyticsService(
        {
            "error": True,
            "message": "Нет данных для анализа"
        }
    )

    service = SalesIntelligenceService(
        analytics
    )

    result = service.analyze(
        []
    )

    assert result == {
        "error": True,
        "message": "Нет данных для анализа"
    }
