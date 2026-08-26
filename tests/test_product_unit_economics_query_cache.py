from services.product_unit_economics_query_service import (
    ProductUnitEconomicsQueryService,
)


class FakeClock:
    def __init__(self):
        self.value = 100.0

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += seconds


class FakeProductService:
    def load_products(self):
        return [{
            "product_id": "1",
            "offer_id": "hook-2",
            "sku": "3921245627",
        }]


class FakeCurrentSource:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def get(self, **kwargs):
        index = min(
            self.calls,
            len(self.responses) - 1,
        )
        self.calls += 1
        return dict(self.responses[index])


class FakeProvider:
    def build_current(self, facts, cost):
        price = facts.get("seller_price")
        return {
            "product_id": facts.get("product_id"),
            "sku": facts.get("sku"),
            "unit_price": price,
            "cost": cost,
            "commission": 10.0,
            "logistics": 10.0,
            "last_mile": 1.0,
            "acquiring": 1.0,
            "marketplace_fees": 22.0,
            "tax": 5.0,
            "net_profit_per_unit": price - 48.0,
            "margin_percent": 50.0,
            "missing_fields": [],
        }


class FakeCostService:
    def get_cost(self, product_id):
        return (
            str(product_id),
            "hook-2",
            "hook",
            21.0,
        )


def _success(price=96.0):
    return {
        "error": False,
        "product_id": "1",
        "sku": "hook-2",
        "seller_price": price,
        "finance_sample_sales": 10,
        "finance_sample_days": 2,
        "missing_data": [],
    }


def _service(responses, clock, ttl=10):
    source = FakeCurrentSource(responses)
    service = ProductUnitEconomicsQueryService(
        product_service=FakeProductService(),
        period_profit_service=None,
        analytics_service=None,
        unit_economics_provider=FakeProvider(),
        current_economics_source=source,
        cost_service=FakeCostService(),
        cache_ttl_seconds=ttl,
        cache_clock=clock,
        cache_timestamp_provider=(
            lambda: "2026-08-26T12:00:00+00:00"
        ),
    )
    return service, source


def test_second_query_uses_cache_for_offer_or_internal_sku():
    clock = FakeClock()
    service, source = _service([_success()], clock)

    first = service.query("hook-2")
    second = service.query("3921245627")

    assert source.calls == 1
    assert first["cache"]["status"] == "miss"
    assert second["cache"]["status"] == "hit"
    assert second["cache"]["hit"] is True
    assert second["cache"]["stale"] is False
    assert second["unit_price"] == 96.0


def test_cached_result_is_isolated_from_caller_mutation():
    clock = FakeClock()
    service, _ = _service([_success()], clock)

    first = service.query("hook-2")
    first["unit_price"] = 1.0
    second = service.query("hook-2")

    assert second["unit_price"] == 96.0


def test_expired_entry_refreshes_and_replaces_value():
    clock = FakeClock()
    service, source = _service(
        [_success(96.0), _success(101.0)],
        clock,
    )

    first = service.query("hook-2")
    clock.advance(11)
    refreshed = service.query("hook-2")

    assert source.calls == 2
    assert first["unit_price"] == 96.0
    assert refreshed["unit_price"] == 101.0
    assert refreshed["cache"]["status"] == "miss"


def test_failed_refresh_returns_last_success_as_explicit_stale():
    clock = FakeClock()
    service, source = _service(
        [
            _success(),
            {
                "error": True,
                "message": "Ozon unavailable",
            },
        ],
        clock,
    )

    service.query("hook-2")
    clock.advance(11)
    result = service.query("hook-2")

    assert source.calls == 2
    assert result["error"] is False
    assert result["unit_price"] == 96.0
    assert result["cache"]["status"] == "stale"
    assert result["cache"]["stale"] is True
    assert (
        result["cache"]["refresh_error"]
        == "CURRENT_DATA_UNAVAILABLE"
    )


def test_errors_are_not_cached_without_previous_success():
    clock = FakeClock()
    service, source = _service(
        [{
            "error": True,
            "message": "Ozon unavailable",
        }],
        clock,
    )

    first = service.query("hook-2")
    second = service.query("hook-2")

    assert source.calls == 2
    assert first["error"] is True
    assert second["error"] is True
    assert first["cache"]["status"] == "miss"
    assert second["cache"]["status"] == "miss"


def test_zero_ttl_preserves_uncached_behavior():
    clock = FakeClock()
    service, source = _service(
        [_success(), _success()],
        clock,
        ttl=0,
    )

    first = service.query("hook-2")
    second = service.query("hook-2")

    assert source.calls == 2
    assert "cache" not in first
    assert "cache" not in second
