from copy import deepcopy

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


class _Metrics:
    def __init__(self, stock=False):
        self.stock = stock

    def query(self, sku):
        if self.stock:
            return {
                "product_id": "101",
                "sku": sku,
                "current_stock": 8,
                "days_of_stock": 2.0,
                "priority": "CRITICAL",
            }
        return {
            "product_id": "101",
            "sku": sku,
            "sales_velocity": 4.0,
            "sales_trend": "GROWING",
        }


class _Economics:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = 0

    def query(self, sku):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return deepcopy(self.result)


class _CountingDecision(ProductBusinessDecisionService):
    def __init__(self):
        self.calls = 0

    def decide(self, prepared):
        self.calls += 1
        return super().decide(prepared)


def _economics(**overrides):
    result = {
        "error": False,
        "available": True,
        "product_id": "101",
        "sku": "hook-2",
        "net_profit_per_unit": 510.0,
        "margin_percent": 34.0,
        "missing_fields": [],
    }
    result.update(overrides)
    return result


def _service(economics, decision_service=None, cache_ttl_seconds=600):
    return ProductBusinessDecisionQueryService(
        product_service=_Products(),
        sales_metrics_source=_Metrics(),
        stock_metrics_source=_Metrics(stock=True),
        unit_economics_query_service=economics,
        decision_input_provider=ProductDecisionInputProvider(),
        decision_service=decision_service or ProductBusinessDecisionService(),
        cache_ttl_seconds=cache_ttl_seconds,
    )


def _assert_invalid(result):
    assert result == {
        "error": True,
        "code": "PRODUCT_DECISION_UNIT_ECONOMICS_RESULT_INVALID",
        "product_id": "101",
        "sku": "hook-2",
        "decision_type": "INSUFFICIENT_DATA",
        "priority": "NONE",
        "reasons": [],
        "confidence": "LOW",
        "missing_data": ["unit_economics"],
    }


def test_v1011_non_mapping_economics_result_fails_closed():
    result = _service(_Economics(["bad"])).query("hook-2")
    _assert_invalid(result)


def test_v1012_missing_or_non_boolean_error_is_not_success():
    missing = _economics()
    missing.pop("error")
    for payload in (missing, _economics(error=0), _economics(error="false")):
        _assert_invalid(_service(_Economics(payload)).query("hook-2"))


def test_v1013_expected_explicit_downstream_error_stays_unknown_not_zero():
    result = _service(_Economics({
        "error": True,
        "code": "CURRENT_DATA_UNAVAILABLE",
    })).query("hook-2")

    assert result["error"] is False
    assert result["code"] == "INSUFFICIENT_DATA"
    assert result["decision_profit_per_unit"] is None
    assert result["decision_margin_percent"] is None
    assert "profit_per_unit" in result["missing_data"]


def test_v1014_query_exception_is_sanitized_and_blocks_decision_service():
    decision = _CountingDecision()
    service = _service(
        _Economics(error=ValueError("secret finance payload")),
        decision_service=decision,
    )

    result = service.query("hook-2")

    _assert_invalid(result)
    assert decision.calls == 0
    assert "secret finance payload" not in str(result)


def test_v1015_unavailable_economics_cannot_claim_profit():
    payload = _economics(
        available=False,
        net_profit_per_unit=500.0,
        margin_percent=20.0,
    )
    _assert_invalid(_service(_Economics(payload)).query("hook-2"))


def test_v1016_missing_fields_must_be_a_unique_string_list():
    for missing in ("tax", [""], ["tax", "tax"], [None]):
        payload = _economics(missing_fields=missing)
        _assert_invalid(_service(_Economics(payload)).query("hook-2"))


def test_v1017_non_finite_or_boolean_finance_values_are_rejected():
    for value in (float("nan"), float("inf"), True):
        payload = _economics(net_profit_per_unit=value)
        _assert_invalid(_service(_Economics(payload)).query("hook-2"))


def test_v1018_confirmed_returns_profit_requires_complete_cost_evidence():
    payload = _economics(
        risk_adjusted_profit_per_unit=450.0,
        risk_adjusted_margin_percent=30.0,
        returns_cost_per_delivered_unit=60.0,
        returns_finance_complete=False,
    )
    _assert_invalid(_service(_Economics(payload)).query("hook-2"))


def test_v1019_estimated_returns_profit_requires_exact_readiness_and_evidence():
    for payload in (
        _economics(
            returns_estimate_available="yes",
            estimated_profit_per_unit=470.0,
            estimated_returns_cost_per_unit=40.0,
            returns_estimate_coverage_percent=90.0,
        ),
        _economics(
            returns_estimate_available=True,
            estimated_profit_per_unit=470.0,
            estimated_returns_cost_per_unit=None,
            returns_estimate_coverage_percent=90.0,
        ),
    ):
        _assert_invalid(_service(_Economics(payload)).query("hook-2"))


def test_v1020_invalid_economics_is_not_cached_and_valid_result_still_works():
    malformed = _economics()
    malformed.pop("error")
    invalid = _Economics(malformed)
    service = _service(invalid, cache_ttl_seconds=600)

    first = service.query("hook-2")
    second = service.query("hook-2")

    _assert_invalid(first)
    _assert_invalid(second)
    assert invalid.calls == 2

    valid = _service(_Economics(_economics())).query("hook-2")
    assert valid["error"] is False
    assert valid["decision_profit_per_unit"] == 510.0
    assert valid["decision_margin_percent"] == 34.0
