from services.returns_buyout_query_service import ReturnsBuyoutQueryService


class StubFactsSource:
    def __init__(self, facts):
        self.facts = facts
        self.calls = []

    def get(self, **kwargs):
        self.calls.append(dict(kwargs))
        return dict(self.facts)


class StubAnalyticsService:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def analyze(self, facts):
        self.calls.append(dict(facts))
        return dict(self.result)


def test_query_orchestrates_existing_boundaries_without_mutation():
    facts = {
        "error": False,
        "sku": "hook-2",
        "delivered_units": 45,
        "customer_non_buyout_units": 5,
    }
    expected_facts = dict(facts)
    source = StubFactsSource(facts)
    analytics = StubAnalyticsService({
        "error": False,
        "sku": "hook-2",
        "buyout_rate": 90.0,
        "buyout_sample_size": 50,
    })
    service = ReturnsBuyoutQueryService(source, analytics)

    result = service.query(
        "hook-2",
        "2026-08-01T00:00:00Z",
        "2026-08-25T00:00:00Z",
    )

    assert source.calls == [{
        "sku": "hook-2",
        "since": "2026-08-01T00:00:00Z",
        "to": "2026-08-25T00:00:00Z",
    }]
    assert analytics.calls == [expected_facts]
    assert result["buyout_rate"] == 90.0
    assert facts == expected_facts


def test_query_preserves_structured_business_error():
    source = StubFactsSource({
        "error": True,
        "code": "FBO_POSTINGS_UNAVAILABLE",
        "sku": "hook-2",
    })
    analytics = StubAnalyticsService({
        "error": True,
        "code": "FBO_POSTINGS_UNAVAILABLE",
        "sku": "hook-2",
        "message": "FBO postings недоступны",
    })
    service = ReturnsBuyoutQueryService(source, analytics)

    result = service.query("hook-2", "2026-08-01", "2026-08-25")

    assert result["error"] is True
    assert result["code"] == "FBO_POSTINGS_UNAVAILABLE"
