from services.returns_finance_attribution_query_service import (
    ReturnsFinanceAttributionQueryService,
)


class StubFactsSource:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def get(self, **kwargs):
        self.calls.append(dict(kwargs))
        return dict(self.result)


class StubAnalyticsService:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def analyze(self, facts):
        self.calls.append(dict(facts))
        return dict(self.result)


def test_orchestrates_facts_and_analytics_without_mutation():
    facts = {
        "error": False,
        "sku": "hook-2",
        "complete": False,
    }
    expected_facts = dict(facts)
    source = StubFactsSource(facts)
    analytics = StubAnalyticsService({
        "error": False,
        "sku": "hook-2",
        "complete": False,
    })
    service = ReturnsFinanceAttributionQueryService(
        source,
        analytics,
    )

    result = service.query(
        sku="hook-2",
        finance_sku="3921245627",
        since="2026-08-01T00:00:00Z",
        to="2026-08-25T00:00:00Z",
    )

    assert source.calls == [{
        "sku": "hook-2",
        "finance_sku": "3921245627",
        "since": "2026-08-01T00:00:00Z",
        "to": "2026-08-25T00:00:00Z",
    }]
    assert analytics.calls == [expected_facts]
    assert result["complete"] is False
    assert facts == expected_facts


def test_preserves_analytics_error_result():
    source = StubFactsSource({
        "error": True,
        "code": "FINANCE_UNAVAILABLE",
    })
    analytics = StubAnalyticsService({
        "error": True,
        "code": "FINANCE_UNAVAILABLE",
        "message": "Финансы недоступны",
    })
    service = ReturnsFinanceAttributionQueryService(
        source,
        analytics,
    )

    result = service.query(
        "hook-2",
        "3921245627",
        "2026-08-01",
        "2026-08-25",
    )

    assert result == {
        "error": True,
        "code": "FINANCE_UNAVAILABLE",
        "message": "Финансы недоступны",
    }
