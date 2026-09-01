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


class _History:
    def __init__(self, record_result=None, record_error=None, latest=None):
        self.record_result = record_result
        self.record_error = record_error
        self.latest_result = latest
        self.record_calls = 0
        self.latest_calls = 0

    def record(self, decision):
        self.record_calls += 1
        if self.record_error is not None:
            raise self.record_error
        return deepcopy(self.record_result)

    def latest(self, sku):
        self.latest_calls += 1
        return deepcopy(self.latest_result)


class _DraftLifecycle:
    def __init__(self):
        self.calls = 0

    def reconcile(self, **kwargs):
        self.calls += 1
        return {
            "error": False,
            "stale_count": 0,
            "executed": False,
        }


class _DraftLatest:
    def __init__(self, result):
        self.result = result
        self.calls = 0

    def latest_for_sku(self, sku):
        self.calls += 1
        return deepcopy(self.result)


class _Assistant:
    pass


def _valid_context(**values):
    result = {
        "decision_history_available": True,
        "decision_changed": False,
        "previous_decision_type": None,
        "previous_priority": None,
        "decision_recorded_at": "2026-09-01T18:00:00+00:00",
        "decision_history_count": 1,
        "previous_feedback": None,
        "decision_outcome": None,
    }
    result.update(values)
    return result


def _service(history):
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
        decision_history_service=history,
        action_proposal_service=ProductDecisionActionProposalService(),
    )


def test_v961_history_context_cannot_overwrite_decision_identity():
    context = _valid_context(
        sku="other",
        priority="LOW",
        decision_type="HOLD_STOCK",
        error=True,
    )
    result = _service(_History(record_result=context)).query("hook-2")

    assert result["error"] is False
    assert result["sku"] == "hook-2"
    assert result["priority"] == "CRITICAL"
    assert result["decision_type"] == "REPLENISH_HIGH_PRIORITY"
    assert result["decision_history_error"] is True
    assert result["decision_history_code"] == (
        "INVALID_DECISION_HISTORY_CONTEXT"
    )
    assert result["decision_history_count"] is None


def test_v962_non_mapping_history_context_is_unknown_and_not_cached():
    history = _History(record_result=["not", "a", "mapping"])
    service = _service(history)

    first = service.query("hook-2")
    second = service.query("hook-2")

    assert first["decision_history_error"] is True
    assert second["decision_history_error"] is True
    assert first["decision_history_count"] is None
    assert history.record_calls == 2


def test_v963_missing_required_history_booleans_fails_context():
    context = _valid_context()
    context.pop("decision_changed")

    result = _service(_History(record_result=context)).query("hook-2")

    assert result["decision_history_error"] is True
    assert result["decision_history_available"] is False


def test_v964_malformed_history_count_is_not_coerced():
    result = _service(
        _History(
            record_result=_valid_context(decision_history_count="1")
        )
    ).query("hook-2")

    assert result["decision_history_error"] is True
    assert result["decision_history_count"] is None


def test_v965_history_exception_is_sanitized_and_unknown():
    result = _service(
        _History(record_error=OSError("secret history path"))
    ).query("hook-2")

    assert result["error"] is False
    assert result["decision_history_error"] is True
    assert result["decision_history_code"] == "DECISION_HISTORY_RECORD_FAILED"
    assert result["decision_history_count"] is None
    assert "secret history path" not in str(result)


def test_v966_valid_history_context_is_whitelisted_and_cacheable():
    history = _History(
        record_result=_valid_context(
            decision_changed=True,
            previous_decision_type="HOLD_STOCK",
            previous_priority="LOW",
            previous_feedback="USEFUL",
            decision_outcome="PRIORITY_INCREASED",
        )
    )
    service = _service(history)

    first = service.query("hook-2")
    second = service.query("hook-2")

    assert first["decision_history_error"] is False
    assert first["decision_history_available"] is True
    assert first["previous_decision_type"] == "HOLD_STOCK"
    assert first["previous_priority"] == "LOW"
    assert first["previous_feedback"] == "USEFUL"
    assert first["decision_outcome"] == "PRIORITY_INCREASED"
    assert second["decision_history_count"] == 1
    assert history.record_calls == 1


def test_v967_history_context_error_blocks_task_draft_lifecycle():
    history = _History(record_result=None)
    service = _service(history)
    drafts = _DraftLifecycle()
    service.action_task_draft_service = drafts

    result = service.query("hook-2")

    assert result["decision_history_error"] is True
    assert drafts.calls == 0


def test_v968_telegram_skips_latest_reads_when_history_context_failed():
    history = _History(latest={
        "sku": "hook-2",
        "proposal_type": "REVIEW_REPLENISHMENT",
        "proposal_status": "CONFIRMED",
    })
    query = type(
        "_Query",
        (),
        {
            "decision_history_service": history,
            "query": lambda self, sku: {
                "error": False,
                "code": None,
                "sku": sku,
                "decision_type": "REPLENISH_HIGH_PRIORITY",
                "priority": "CRITICAL",
                "reasons": ["DAYS_OF_STOCK_CRITICAL"],
                "confidence": "HIGH",
                "missing_data": [],
                "decision_history_available": False,
                "decision_history_error": True,
                "action_proposal": {
                    "available": True,
                    "proposal_type": "REVIEW_REPLENISHMENT",
                    "action_required": True,
                    "requires_confirmation": True,
                    "execution_allowed": False,
                    "automation_status": "PROHIBITED",
                    "sku": sku,
                    "priority": "CRITICAL",
                    "decision_type": "REPLENISH_HIGH_PRIORITY",
                    "reasons": ["DAYS_OF_STOCK_CRITICAL"],
                },
            },
        },
    )()

    response = AssistantButtonHandlerService(
        assistant=_Assistant(),
        product_business_decision_query=query,
    ).handle("product_decision:hook-2")

    assert response["error"] is False
    assert history.latest_calls == 0
    assert "keyboard" not in response


def test_v969_malformed_or_cross_sku_latest_cannot_enter_card():
    for latest in (
        ["bad"],
        {
            "sku": "other",
            "proposal_type": "REVIEW_REPLENISHMENT",
            "proposal_status": "CONFIRMED",
        },
        {
            "sku": "hook-2",
            "proposal_type": "REVIEW_REPLENISHMENT",
            "proposal_status": "UNKNOWN",
        },
    ):
        history = _History(latest=latest)
        handler = AssistantButtonHandlerService(
            assistant=_Assistant(),
            product_business_decision_query=type(
                "_Query",
                (),
                {"decision_history_service": history},
            )(),
        )
        source = {
            "decision_history_error": False,
            "decision_recorded_at": "now",
            "action_proposal": {
                "proposal_type": "REVIEW_REPLENISHMENT",
            },
        }

        result = handler._with_latest_proposal_status(
            source,
            "hook-2",
        )

        assert "proposal_status" not in result["action_proposal"]


def test_v970_valid_latest_status_and_safe_draft_are_preserved():
    history = _History(latest={
        "sku": "hook-2",
        "proposal_type": "REVIEW_REPLENISHMENT",
        "proposal_status": "CONFIRMED",
    })
    draft = {
        "draft_id": "d1",
        "sku": "hook-2",
        "proposal_type": "REVIEW_REPLENISHMENT",
        "decision_recorded_at": "now",
        "status": "DRAFT",
        "executed": False,
        "execution_allowed": False,
    }
    drafts = _DraftLatest(draft)
    query = type(
        "_Query",
        (),
        {
            "decision_history_service": history,
            "action_task_draft_service": drafts,
        },
    )()
    handler = AssistantButtonHandlerService(
        assistant=_Assistant(),
        product_business_decision_query=query,
    )
    source = {
        "decision_history_error": False,
        "decision_recorded_at": "now",
        "action_proposal": {
            "proposal_type": "REVIEW_REPLENISHMENT",
        },
    }

    result = handler._with_latest_proposal_status(source, "hook-2")

    assert result["action_proposal"]["proposal_status"] == "CONFIRMED"
    assert result["action_task_draft"] == draft
    assert result["action_task_draft"] is not draft
    assert history.latest_calls == 1
    assert drafts.calls == 1
