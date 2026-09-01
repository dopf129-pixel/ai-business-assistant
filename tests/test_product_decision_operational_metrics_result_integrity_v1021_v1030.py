from copy import deepcopy
from math import inf, nan

from app.services.product_business_decision_query_service import (
    ProductBusinessDecisionQueryService,
)
from app.services.product_business_decision_service import (
    ProductBusinessDecisionService,
)
from app.services.product_decision_input_provider import (
    ProductDecisionInputProvider,
)


class _Products:
    def load_products(self):
        return [{
            "product_id": "101",
            "offer_id": "hook-2",
            "sku": "3921245627",
        }]


class _Source:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = 0

    def query(self, sku):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return deepcopy(self.result)


class _Economics:
    def __init__(self):
        self.calls = 0

    def query(self, sku):
        self.calls += 1
        return {
            "error": False,
            "available": True,
            "product_id": "101",
            "sku": sku,
            "net_profit_per_unit": 510.0,
            "margin_percent": 34.0,
            "missing_fields": [],
        }


class _CountingDecision(ProductBusinessDecisionService):
    def __init__(self):
        self.calls = 0

    def decide(self, prepared):
        self.calls += 1
        return super().decide(prepared)


def _sales(**overrides):
    result = {
        "product_id": "101",
        "sku": "hook-2",
        "sales_velocity": 4.0,
        "sales_trend": "GROWING",
        "missing_data": [],
    }
    result.update(overrides)
    return result


def _stock(**overrides):
    result = {
        "product_id": "101",
        "sku": "hook-2",
        "current_stock": 8,
        "days_of_stock": 2.0,
        "priority": "CRITICAL",
        "missing_data": [],
    }
    result.update(overrides)
    return result


def _service(
    sales=None,
    stock=None,
    economics=None,
    decision=None,
    cache_ttl_seconds=600,
):
    return ProductBusinessDecisionQueryService(
        product_service=_Products(),
        sales_metrics_source=sales or _Source(_sales()),
        stock_metrics_source=stock or _Source(_stock()),
        unit_economics_query_service=economics or _Economics(),
        decision_input_provider=ProductDecisionInputProvider(),
        decision_service=decision or ProductBusinessDecisionService(),
        cache_ttl_seconds=cache_ttl_seconds,
    )


def _assert_invalid(result, source):
    assert result == {
        "error": True,
        "code": "PRODUCT_DECISION_OPERATIONAL_METRICS_RESULT_INVALID",
        "product_id": "101",
        "sku": "hook-2",
        "decision_type": "INSUFFICIENT_DATA",
        "priority": "NONE",
        "reasons": [],
        "confidence": "LOW",
        "missing_data": [source + "_metrics"],
    }


def test_v1021_sales_source_exception_is_sanitized_before_decision():
    decision = _CountingDecision()
    result = _service(
        sales=_Source(error=ValueError("secret sales payload")),
        decision=decision,
    ).query("hook-2")

    _assert_invalid(result, "sales")
    assert decision.calls == 0
    assert "secret sales payload" not in str(result)


def test_v1022_stock_source_exception_is_sanitized_before_economics():
    economics = _Economics()
    result = _service(
        stock=_Source(error=KeyError("secret stock payload")),
        economics=economics,
    ).query("hook-2")

    _assert_invalid(result, "stock")
    assert economics.calls == 0
    assert "secret stock payload" not in str(result)


def test_v1023_non_mapping_operational_metrics_fail_closed():
    for source_name in ("sales", "stock"):
        kwargs = {source_name: _Source(["not", "a", "mapping"])}
        _assert_invalid(
            _service(**kwargs).query("hook-2"),
            source_name,
        )


def test_v1024_explicit_error_marker_must_be_boolean_but_true_is_unknown():
    for source_name in ("sales", "stock"):
        kwargs = {source_name: _Source({"error": "false"})}
        _assert_invalid(
            _service(**kwargs).query("hook-2"),
            source_name,
        )

    result = _service(
        sales=_Source({"error": True}),
        stock=_Source({"error": True}),
    ).query("hook-2")
    assert result["error"] is False
    assert result["code"] == "INSUFFICIENT_DATA"
    assert result["sales_velocity"] is None
    assert result["current_stock"] is None


def test_v1025_sales_velocity_rejects_boolean_negative_and_non_finite():
    for value in (True, -0.1, nan, inf):
        result = _service(
            sales=_Source(_sales(sales_velocity=value))
        ).query("hook-2")
        _assert_invalid(result, "sales")


def test_v1026_sales_trend_requires_canonical_producer_value():
    for value in ("DOWN", "UNKNOWN", 1, ""):
        result = _service(
            sales=_Source(_sales(sales_trend=value))
        ).query("hook-2")
        _assert_invalid(result, "sales")


def test_v1027_stock_quantity_and_days_reject_unsafe_numbers():
    payloads = (
        _stock(current_stock=True),
        _stock(current_stock=-1),
        _stock(days_of_stock=nan),
        _stock(days_of_stock=-0.1),
    )
    for payload in payloads:
        result = _service(stock=_Source(payload)).query("hook-2")
        _assert_invalid(result, "stock")


def test_v1028_stock_priority_and_days_relationship_is_canonical():
    payloads = (
        _stock(priority="UNKNOWN"),
        _stock(priority="CRITICAL", days_of_stock=None),
        _stock(priority=None, days_of_stock=2.0),
        _stock(priority="NO_SALES", days_of_stock=2.0),
    )
    for payload in payloads:
        result = _service(stock=_Source(payload)).query("hook-2")
        _assert_invalid(result, "stock")

    no_sales = _stock(
        sales_velocity=0 if False else 0,
        priority="NO_SALES",
        days_of_stock=None,
    )
    valid = _service(stock=_Source(no_sales)).query("hook-2")
    assert valid["error"] is False
    assert valid["code"] == "INSUFFICIENT_DATA"


def test_v1029_missing_data_and_evidence_strings_cannot_be_malformed():
    payloads = (
        ("sales", _sales(missing_data="sales_velocity")),
        ("sales", _sales(sales_observed_at="")),
        ("stock", _stock(missing_data=["days_of_stock", "days_of_stock"])),
        ("stock", _stock(stock_source_recorded_at=123)),
    )
    for source_name, payload in payloads:
        result = _service(
            **{source_name: _Source(payload)}
        ).query("hook-2")
        _assert_invalid(result, source_name)


def test_v1030_invalid_metrics_are_not_cached_and_valid_path_is_preserved():
    bad_sales = _Source(_sales(sales_trend="UNKNOWN"))
    service = _service(
        sales=bad_sales,
        cache_ttl_seconds=600,
    )

    first = service.query("hook-2")
    second = service.query("hook-2")

    _assert_invalid(first, "sales")
    _assert_invalid(second, "sales")
    assert bad_sales.calls == 2

    valid = _service().query("hook-2")
    assert valid["error"] is False
    assert valid["decision_type"] == "REPLENISH_HIGH_PRIORITY"
    assert valid["sales_velocity"] == 4.0
    assert valid["current_stock"] == 8
