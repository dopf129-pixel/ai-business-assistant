from copy import deepcopy

from app.services.assistant_button_handler_service import (
    AssistantButtonHandlerService,
)
from app.services.product_business_decision_query_service import (
    ProductBusinessDecisionQueryService,
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
    def __init__(self, result):
        self.result = result

    def query(self, sku):
        result = deepcopy(self.result)
        result["sku"] = sku
        return result


class _Economics:
    def query(self, sku):
        return {
            "error": False,
            "available": True,
            "product_id": "101",
            "sku": sku,
            "net_profit_per_unit": 510.0,
            "margin_percent": 34.0,
            "missing_fields": [],
        }


class _Decision:
    def __init__(self, transform=None, raises=None):
        self.transform = transform
        self.raises = raises
        self.calls = 0

    def decide(self, prepared):
        self.calls += 1
        if self.raises is not None:
            raise self.raises
        result = {
            "product_id": prepared.get("product_id"),
            "sku": prepared.get("sku"),
            "decision_type": "REPLENISH_HIGH_PRIORITY",
            "priority": "CRITICAL",
            "reasons": [
                "DAYS_OF_STOCK_CRITICAL",
                "POSITIVE_UNIT_PROFIT",
            ],
            "confidence": "HIGH",
            "missing_data": [],
        }
        if self.transform is None:
            return result
        return self.transform(deepcopy(result))


class _History:
    def __init__(self):
        self.calls = 0

    def record(self, decision):
        self.calls += 1
        return {
            "decision_history_available": True,
            "decision_changed": False,
            "previous_decision_type": None,
            "previous_priority": None,
            "decision_recorded_at": "2026-09-01T19:00:00+00:00",
            "decision_history_count": 1,
            "previous_feedback": None,
            "decision_outcome": None,
        }


class _Proposal:
    def __init__(self):
        self.calls = 0

    def propose(self, decision):
        self.calls += 1
        return {
            "available": True,
            "proposal_type": "REVIEW_REPLENISHMENT",
            "action_required": True,
            "requires_confirmation": True,
            "execution_allowed": False,
            "automation_status": "PROHIBITED",
            "sku": decision["sku"],
            "priority": decision["priority"],
            "decision_type": decision["decision_type"],
            "reasons": deepcopy(decision["reasons"]),
        }


class _Assistant:
    pass


def _service(decision_service, history=None, proposal=None):
    return ProductBusinessDecisionQueryService(
        product_service=_Products(),
        sales_metrics_source=_Source({
            "product_id": "101",
            "sales_velocity": 4.0,
            "sales_trend": "GROWING",
        }),
        stock_metrics_source=_Source({
            "product_id": "101",
            "current_stock": 8,
            "days_of_stock": 2.0,
            "priority": "CRITICAL",
        }),
        unit_economics_query_service=_Economics(),
        decision_input_provider=ProductDecisionInputProvider(),
        decision_service=decision_service,
        decision_history_service=history,
        action_proposal_service=proposal,
    )


def _assert_invalid(result):
    assert result["error"] is True
    assert result["code"] == "PRODUCT_DECISION_RESULT_INVALID"
    assert result["decision_type"] == "INSUFFICIENT_DATA"
    assert result["priority"] == "NONE"
    assert result["confidence"] == "LOW"
    assert result["missing_data"] == ["decision"]


def test_v981_non_mapping_decision_result_fails_closed():
    service = _service(
        _Decision(transform=lambda result: ["not", "a", "mapping"])
    )

    result = service.query("hook-2")

    _assert_invalid(result)


def test_v982_decision_exception_is_sanitized():
    service = _service(
        _Decision(raises=ValueError("secret decision detail"))
    )

    result = service.query("hook-2")

    _assert_invalid(result)
    assert "secret decision detail" not in str(result)


def test_v983_decision_result_cannot_inject_error_or_code_fields():
    def malformed(result):
        result["error"] = False
        result["code"] = None
        return result

    result = _service(_Decision(transform=malformed)).query("hook-2")

    _assert_invalid(result)


def test_v984_decision_sku_identity_must_match_query():
    def wrong_sku(result):
        result["sku"] = "other"
        return result

    result = _service(_Decision(transform=wrong_sku)).query("hook-2")

    _assert_invalid(result)
    assert result["sku"] == "hook-2"


def test_v985_decision_product_identity_must_match_product():
    def wrong_product(result):
        result["product_id"] = "999"
        return result

    result = _service(_Decision(transform=wrong_product)).query("hook-2")

    _assert_invalid(result)
    assert result["product_id"] == "101"


def test_v986_decision_type_priority_contract_is_exact():
    def wrong_priority(result):
        result["priority"] = "LOW"
        return result

    result = _service(_Decision(transform=wrong_priority)).query("hook-2")

    _assert_invalid(result)


def test_v987_reasons_must_be_canonical_unique_strings():
    for reasons in (
        "DAYS_OF_STOCK_CRITICAL",
        ["DAYS_OF_STOCK_CRITICAL", ""],
        ["DAYS_OF_STOCK_CRITICAL", "DAYS_OF_STOCK_CRITICAL"],
        ["UNKNOWN_REASON"],
    ):
        def malformed(result, reasons=reasons):
            result["reasons"] = reasons
            return result

        result = _service(_Decision(transform=malformed)).query("hook-2")

        _assert_invalid(result)


def test_v988_missing_data_must_be_canonical_unique_strings():
    for missing_data in (
        "sales_velocity",
        ["sales_velocity", ""],
        ["sales_velocity", "sales_velocity"],
    ):
        def malformed(result, missing_data=missing_data):
            result["missing_data"] = missing_data
            result["confidence"] = "MEDIUM"
            return result

        result = _service(_Decision(transform=malformed)).query("hook-2")

        _assert_invalid(result)


def test_v989_invalid_decision_has_no_history_proposal_or_cache_side_effect():
    history = _History()
    proposal = _Proposal()
    decision = _Decision(
        transform=lambda result: {
            **result,
            "decision_type": "UNKNOWN_DECISION",
        }
    )
    service = _service(decision, history=history, proposal=proposal)

    first = service.query("hook-2")
    second = service.query("hook-2")

    _assert_invalid(first)
    _assert_invalid(second)
    assert decision.calls == 2
    assert history.calls == 0
    assert proposal.calls == 0


def test_v990_valid_decision_remains_seller_safe_and_error_has_no_keyboard():
    history = _History()
    proposal = _Proposal()
    service = _service(
        _Decision(),
        history=history,
        proposal=proposal,
    )

    valid = service.query("hook-2")

    assert valid["error"] is False
    assert valid["decision_type"] == "REPLENISH_HIGH_PRIORITY"
    assert valid["priority"] == "CRITICAL"
    assert valid["confidence"] == "HIGH"
    assert valid["action_proposal"]["execution_allowed"] is False
    assert valid["action_proposal"]["automation_status"] == "PROHIBITED"
    assert history.calls == 1
    assert proposal.calls == 1

    broken_query = type(
        "_Query",
        (),
        {
            "query": lambda self, sku: {
                "error": True,
                "code": "PRODUCT_DECISION_RESULT_INVALID",
                "sku": sku,
                "decision_type": "INSUFFICIENT_DATA",
                "priority": "NONE",
                "reasons": [],
                "confidence": "LOW",
                "missing_data": ["decision"],
            },
        },
    )()

    response = AssistantButtonHandlerService(
        assistant=_Assistant(),
        product_business_decision_query=broken_query,
    ).handle("product_decision:hook-2")

    assert response["error"] is True
    assert response["message"] == "Не удалось проверить решение по товару"
    assert "keyboard" not in response
