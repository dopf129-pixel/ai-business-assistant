from copy import deepcopy

from app.services.assistant_button_handler_service import (
    AssistantButtonHandlerService,
)
from app.services.product_business_decision_query_service import (
    ProductBusinessDecisionQueryService,
)
from app.services.product_business_decision_service import (
    ProductBusinessDecisionService,
)
from app.services.product_decision_action_proposal_service import (
    ProductDecisionActionProposalService,
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


class _Proposal:
    def __init__(self, transform=None, raises=None):
        self.transform = transform
        self.raises = raises
        self.calls = 0
        self.real = ProductDecisionActionProposalService()

    def propose(self, decision):
        self.calls += 1
        if self.raises is not None:
            raise self.raises
        proposal = self.real.propose(decision)
        if self.transform is None:
            return proposal
        return self.transform(deepcopy(proposal))


class _Assistant:
    pass


def _service(proposal_service):
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
        decision_service=ProductBusinessDecisionService(),
        action_proposal_service=proposal_service,
    )


def _invalid_code(result):
    assert result["error"] is True
    assert result["code"] == (
        "PRODUCT_DECISION_ACTION_PROPOSAL_RESULT_INVALID"
    )
    assert result.get("action_proposal") is None


def test_v951_non_mapping_proposal_fails_closed_before_cache():
    proposal = _Proposal(transform=lambda value: ["not", "a", "mapping"])
    service = _service(proposal)

    first = service.query("hook-2")
    second = service.query("hook-2")

    _invalid_code(first)
    _invalid_code(second)
    assert proposal.calls == 2


def test_v952_proposal_exception_fails_closed_without_runtime_escape():
    service = _service(_Proposal(raises=ValueError("secret detail")))

    result = service.query("hook-2")

    _invalid_code(result)
    assert "secret detail" not in str(result)


def test_v953_missing_explicit_available_marker_is_not_trusted():
    def malformed(value):
        value.pop("available")
        return value

    result = _service(_Proposal(transform=malformed)).query("hook-2")

    _invalid_code(result)


def test_v954_execution_permission_overclaim_blocks_decision_card():
    def unsafe(value):
        value["execution_allowed"] = True
        return value

    result = _service(_Proposal(transform=unsafe)).query("hook-2")

    _invalid_code(result)


def test_v955_proposal_sku_must_match_decision():
    def wrong_sku(value):
        value["sku"] = "other"
        return value

    result = _service(_Proposal(transform=wrong_sku)).query("hook-2")

    _invalid_code(result)


def test_v956_proposal_type_must_match_decision_semantics():
    def wrong_type(value):
        value["proposal_type"] = "REVIEW_MARGIN"
        return value

    result = _service(_Proposal(transform=wrong_type)).query("hook-2")

    _invalid_code(result)


def test_v957_reasons_must_remain_exact_canonical_list():
    def wrong_reasons(value):
        value["reasons"] = "DAYS_OF_STOCK_CRITICAL"
        return value

    result = _service(_Proposal(transform=wrong_reasons)).query("hook-2")

    _invalid_code(result)


def test_v958_confirmation_flags_cannot_contradict_proposal_type():
    def wrong_confirmation(value):
        value["requires_confirmation"] = False
        return value

    result = _service(
        _Proposal(transform=wrong_confirmation)
    ).query("hook-2")

    _invalid_code(result)


def test_v959_assortment_query_fails_closed_on_malformed_proposal():
    def malformed(value):
        value["automation_status"] = "ALLOWED"
        return value

    result = _service(_Proposal(transform=malformed)).query_all()

    assert result == {
        "error": True,
        "code": "PRODUCT_DECISION_ACTION_PROPOSAL_RESULT_INVALID",
    }


def test_v960_valid_proposal_remains_non_executable_and_telegram_safe():
    service = _service(_Proposal())
    result = service.query("hook-2")

    assert result["error"] is False
    assert result["action_proposal"]["available"] is True
    assert result["action_proposal"]["proposal_type"] == (
        "REVIEW_REPLENISHMENT"
    )
    assert result["action_proposal"]["action_required"] is True
    assert result["action_proposal"]["requires_confirmation"] is True
    assert result["action_proposal"]["execution_allowed"] is False
    assert result["action_proposal"]["automation_status"] == "PROHIBITED"

    broken_query = type(
        "_Query",
        (),
        {
            "query": lambda self, sku: {
                "error": True,
                "code": "PRODUCT_DECISION_ACTION_PROPOSAL_RESULT_INVALID",
                "sku": sku,
                "decision_type": "REPLENISH_HIGH_PRIORITY",
                "priority": "CRITICAL",
                "reasons": ["DAYS_OF_STOCK_CRITICAL"],
                "confidence": "HIGH",
                "missing_data": [],
            },
        },
    )()

    response = AssistantButtonHandlerService(
        assistant=_Assistant(),
        product_business_decision_query=broken_query,
    ).handle("product_decision:hook-2")

    assert response["error"] is True
    assert response["message"] == (
        "Не удалось подготовить безопасный следующий шаг"
    )
    assert "keyboard" not in response
