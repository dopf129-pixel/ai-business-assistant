from copy import deepcopy

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


class _History:
    def record(self, decision):
        return {
            "decision_history_available": True,
            "decision_changed": False,
            "previous_decision_type": None,
            "previous_priority": None,
            "decision_recorded_at": "current-revision",
            "decision_history_count": 1,
            "previous_feedback": None,
            "decision_outcome": None,
        }


class _Lifecycle:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = 0

    def reconcile(self, **kwargs):
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


def _stale_draft(**overrides):
    result = {
        "sku": "hook-2",
        "proposal_type": "REVIEW_REPLENISHMENT",
        "decision_recorded_at": "previous-revision",
        "status": "STALE",
        "executed": False,
        "execution_allowed": False,
    }
    result.update(overrides)
    return result


def _valid_lifecycle(**overrides):
    result = {
        "error": False,
        "stale_count": 1,
        "stale_drafts": [_stale_draft()],
        "executed": False,
        "execution_allowed": False,
    }
    result.update(overrides)
    return result


def _service(lifecycle, history=None, decision_service=None):
    service = ProductBusinessDecisionQueryService(
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
        decision_service=decision_service or ProductBusinessDecisionService(),
        decision_history_service=history,
        action_proposal_service=ProductDecisionActionProposalService(),
    )
    service.action_task_draft_service = lifecycle
    return service


def _assert_invalid(result):
    assert result["error"] is True
    assert result["code"] == (
        "PRODUCT_DECISION_TASK_DRAFT_LIFECYCLE_RESULT_INVALID"
    )
    assert result["task_draft_lifecycle"] is None


def test_v1001_non_mapping_lifecycle_fails_closed_and_is_not_cached():
    lifecycle = _Lifecycle(["not", "a", "mapping"])
    decision = _CountingDecision()
    service = _service(lifecycle, decision_service=decision)

    first = service.query("hook-2")
    second = service.query("hook-2")

    _assert_invalid(first)
    _assert_invalid(second)
    assert lifecycle.calls == 2
    assert decision.calls == 2


def test_v1002_missing_or_true_error_marker_cannot_become_success():
    missing = _valid_lifecycle()
    missing.pop("error")
    for payload in (missing, _valid_lifecycle(error=True)):
        _assert_invalid(_service(_Lifecycle(payload)).query("hook-2"))


def test_v1003_execution_overclaim_is_rejected():
    for payload in (
        _valid_lifecycle(executed=True),
        _valid_lifecycle(execution_allowed=True),
    ):
        _assert_invalid(_service(_Lifecycle(payload)).query("hook-2"))


def test_v1004_stale_count_and_list_must_be_exact_and_consistent():
    for payload in (
        _valid_lifecycle(stale_count="1"),
        _valid_lifecycle(stale_count=True),
        _valid_lifecycle(stale_count=-1),
        _valid_lifecycle(stale_count=0),
        _valid_lifecycle(stale_drafts="not-a-list"),
    ):
        _assert_invalid(_service(_Lifecycle(payload)).query("hook-2"))


def test_v1005_cross_sku_stale_draft_is_rejected():
    payload = _valid_lifecycle(
        stale_drafts=[_stale_draft(sku="other-sku")]
    )

    _assert_invalid(_service(_Lifecycle(payload)).query("hook-2"))


def test_v1006_current_revision_cannot_be_reported_as_stale():
    payload = _valid_lifecycle(stale_drafts=[_stale_draft(
        decision_recorded_at="current-revision",
    )])

    result = _service(
        _Lifecycle(payload),
        history=_History(),
    ).query("hook-2")

    _assert_invalid(result)


def test_v1007_stale_draft_status_and_proposal_type_are_canonical():
    for draft in (
        _stale_draft(status="DRAFT"),
        _stale_draft(proposal_type="UNKNOWN"),
        _stale_draft(executed=True),
        _stale_draft(execution_allowed=True),
    ):
        payload = _valid_lifecycle(stale_drafts=[draft])
        _assert_invalid(_service(_Lifecycle(payload)).query("hook-2"))


def test_v1008_reconcile_exception_is_sanitized():
    result = _service(
        _Lifecycle(error=ValueError("secret storage detail"))
    ).query("hook-2")

    _assert_invalid(result)
    assert "secret storage detail" not in str(result)


def test_v1009_assortment_query_propagates_lifecycle_integrity_failure():
    result = _service(
        _Lifecycle(_valid_lifecycle(execution_allowed=True))
    ).query_all()

    assert result == {
        "error": True,
        "code": "PRODUCT_DECISION_TASK_DRAFT_LIFECYCLE_RESULT_INVALID",
    }


def test_v1010_valid_lifecycle_is_attached_as_non_executable_copy():
    payload = _valid_lifecycle()
    lifecycle = _Lifecycle(payload)
    result = _service(lifecycle).query("hook-2")

    assert result["error"] is False
    attached = result["task_draft_lifecycle"]
    assert attached["stale_count"] == 1
    assert attached["stale_drafts"][0]["sku"] == "hook-2"
    assert attached["stale_drafts"][0]["status"] == "STALE"
    assert attached["executed"] is False
    assert attached["execution_allowed"] is False
    attached["stale_drafts"][0]["sku"] = "mutated"
    assert payload["stale_drafts"][0]["sku"] == "hook-2"
