from app.services.assistant_button_handler_service import (
    AssistantButtonHandlerService,
)
from app.services.product_action_proposal_confirmation_service import (
    ProductActionProposalConfirmationService,
)
from app.services.product_decision_action_proposal_service import (
    ProductDecisionActionProposalService,
)
from app.services.product_decision_history_service import (
    ProductDecisionHistoryService,
)


class SequenceStorage:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.persisted = []

    def load(self):
        return []

    def save(self, records):
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        if outcome is True:
            self.persisted = [dict(item) for item in records]
        return outcome


def _decision():
    return {
        "error": False,
        "sku": "hook-2",
        "decision_type": "REPLENISH_NORMAL",
        "priority": "HIGH",
        "reasons": ["DAYS_OF_STOCK_LOW"],
    }


def _history(outcomes):
    storage = SequenceStorage(outcomes)
    service = ProductDecisionHistoryService(
        storage_service=storage,
        clock=lambda: "now",
    )
    service.record(_decision())
    return service, storage


class DraftSpy:
    def __init__(self):
        self.create_calls = []
        self.dismiss_calls = []

    def create_from_confirmation(self, decision, proposal):
        self.create_calls.append((dict(decision), dict(proposal)))
        return {
            "error": False,
            "code": None,
            "task_draft": {
                "draft_id": "d1",
                "sku": decision["sku"],
                "proposal_type": proposal["proposal_type"],
                "status": "DRAFT",
                "executed": False,
                "execution_allowed": False,
            },
            "saved": True,
            "executed": False,
            "execution_allowed": False,
        }

    def dismiss(self, sku, proposal_type, decision_recorded_at):
        self.dismiss_calls.append((sku, proposal_type, decision_recorded_at))
        return {
            "error": False,
            "code": None,
            "task_draft": None,
            "saved": False,
            "executed": False,
            "execution_allowed": False,
        }


class MalformedHistory:
    def latest(self, sku):
        return {
            "sku": sku,
            "decision_type": "REPLENISH_NORMAL",
            "priority": "HIGH",
            "recorded_at": "now",
        }

    def record_proposal_status(self, **kwargs):
        return {
            "error": False,
            "saved": True,
        }


class StubAssistant:
    pass


class ConfirmationResultStub:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def decide(self, sku, expected_proposal_type, status):
        self.calls.append((sku, expected_proposal_type, status))
        return self.result


class FeedbackResultStub:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def record_feedback(self, sku, feedback):
        self.calls.append((sku, feedback))
        return self.result


class QueryStub:
    def __init__(self, confirmation=None, history=None):
        self.action_proposal_confirmation_service = confirmation
        self.decision_history_service = history


def _handler(confirmation=None, history=None):
    return AssistantButtonHandlerService(
        assistant=StubAssistant(),
        product_business_decision_query=QueryStub(
            confirmation=confirmation,
            history=history,
        ),
    )


def test_v743_feedback_false_save_rolls_back_only_explicit_rejection():
    history, _ = _history([True, False])

    result = history.record_feedback("hook-2", "USEFUL")

    assert result["error"] is True
    assert result["code"] == "DECISION_HISTORY_SAVE_REJECTED"
    assert result["saved"] is False
    assert result["persistence_state"] == "NOT_COMMITTED"
    assert history.latest("hook-2")["feedback"] is None


def test_v744_feedback_exception_is_unknown_without_fabricated_rollback():
    history, _ = _history([True, OSError("disk detail")])

    result = history.record_feedback("hook-2", "USEFUL")

    assert result["error"] is True
    assert result["code"] == "DECISION_HISTORY_SAVE_STATE_UNKNOWN"
    assert result["saved"] is None
    assert result["persistence_state"] == "UNKNOWN"
    assert history.latest("hook-2")["feedback"] == "USEFUL"
    assert "disk detail" not in str(result)


def test_v745_feedback_malformed_save_result_is_unknown():
    history, _ = _history([True, {"ok": True}])

    result = history.record_feedback("hook-2", "NOT_RELEVANT")

    assert result["error"] is True
    assert result["saved"] is None
    assert result["persistence_state"] == "UNKNOWN"
    assert history.latest("hook-2")["feedback"] == "NOT_RELEVANT"


def test_v746_proposal_false_save_rolls_back_and_blocks_task_draft():
    history, _ = _history([True, False])
    drafts = DraftSpy()
    service = ProductActionProposalConfirmationService(
        history_service=history,
        proposal_service=ProductDecisionActionProposalService(),
        task_draft_service=drafts,
    )

    result = service.decide(
        "hook-2",
        "REVIEW_REPLENISHMENT",
        "CONFIRMED",
    )

    assert result["error"] is True
    assert result["code"] == "DECISION_HISTORY_SAVE_REJECTED"
    assert result["saved"] is False
    assert result["executed"] is False
    assert result["execution_allowed"] is False
    assert history.latest("hook-2")["proposal_status"] is None
    assert drafts.create_calls == []


def test_v747_proposal_exception_is_unknown_and_blocks_task_draft():
    history, _ = _history([True, OSError("secret storage detail")])
    drafts = DraftSpy()
    service = ProductActionProposalConfirmationService(
        history_service=history,
        proposal_service=ProductDecisionActionProposalService(),
        task_draft_service=drafts,
    )

    result = service.decide(
        "hook-2",
        "REVIEW_REPLENISHMENT",
        "CONFIRMED",
    )

    assert result["error"] is True
    assert result["saved"] is None
    assert result["persistence_state"] == "UNKNOWN"
    assert history.latest("hook-2")["proposal_status"] == "CONFIRMED"
    assert drafts.create_calls == []
    assert "secret storage detail" not in str(result)


def test_v748_confirmation_rejects_malformed_history_success_before_draft():
    drafts = DraftSpy()
    service = ProductActionProposalConfirmationService(
        history_service=MalformedHistory(),
        proposal_service=ProductDecisionActionProposalService(),
        task_draft_service=drafts,
    )

    result = service.decide(
        "hook-2",
        "REVIEW_REPLENISHMENT",
        "CONFIRMED",
    )

    assert result["error"] is True
    assert result["code"] == "INVALID_DECISION_HISTORY_RESULT"
    assert result["saved"] is None
    assert result["persistence_state"] == "UNKNOWN"
    assert drafts.create_calls == []


def test_v749_valid_confirmation_keeps_non_execution_contract():
    history, _ = _history([True, True])
    drafts = DraftSpy()
    service = ProductActionProposalConfirmationService(
        history_service=history,
        proposal_service=ProductDecisionActionProposalService(),
        task_draft_service=drafts,
    )

    result = service.decide(
        "hook-2",
        "REVIEW_REPLENISHMENT",
        "CONFIRMED",
    )

    assert result["error"] is False
    assert result["saved"] is True
    assert result["executed"] is False
    assert result["execution_allowed"] is False
    assert result["task_draft"]["status"] == "DRAFT"
    assert len(drafts.create_calls) == 1


def test_v750_telegram_confirmation_rejects_non_dict_result():
    confirmation = ConfirmationResultStub(None)

    result = _handler(confirmation=confirmation).handle(
        "product_proposal:yes:r:hook-2"
    )

    assert result == {
        "error": True,
        "message": "Не удалось сохранить статус шага",
        "executed": False,
        "execution_allowed": False,
    }
    assert len(confirmation.calls) == 1


def test_v751_telegram_confirmation_rejects_missing_error_contract():
    confirmation = ConfirmationResultStub({"saved": True})

    result = _handler(confirmation=confirmation).handle(
        "product_proposal:yes:r:hook-2"
    )

    assert result["error"] is True
    assert result["executed"] is False
    assert "сохранён" not in result["message"].lower()


def test_v752_telegram_confirmation_requires_identity_and_non_execution():
    confirmation = ConfirmationResultStub({
        "error": False,
        "code": None,
        "sku": "other",
        "proposal_type": "REVIEW_REPLENISHMENT",
        "proposal_status": "CONFIRMED",
        "saved": True,
        "executed": False,
        "execution_allowed": False,
        "task_draft": None,
    })

    result = _handler(confirmation=confirmation).handle(
        "product_proposal:yes:r:hook-2"
    )

    assert result["error"] is True
    assert result["executed"] is False


def test_v753_telegram_feedback_rejects_malformed_or_mismatched_success():
    malformed = FeedbackResultStub({"saved": True})
    mismatch = FeedbackResultStub({
        "error": False,
        "code": None,
        "sku": "hook-2",
        "feedback": "NOT_RELEVANT",
        "saved": True,
    })

    malformed_result = _handler(history=malformed).handle(
        "product_decision_feedback:useful:hook-2"
    )
    mismatch_result = _handler(history=mismatch).handle(
        "product_decision_feedback:useful:hook-2"
    )

    assert malformed_result["error"] is True
    assert mismatch_result["error"] is True
    assert "неактуально" not in mismatch_result["message"].lower()


def test_v754_telegram_valid_idempotent_feedback_remains_success():
    history = FeedbackResultStub({
        "error": False,
        "code": None,
        "sku": "hook-2",
        "feedback": "USEFUL",
        "saved": False,
    })

    result = _handler(history=history).handle(
        "product_decision_feedback:useful:hook-2"
    )

    assert result["error"] is False
    assert result["message"] == "Оценка сохранена: решение полезно."
    assert history.calls == [("hook-2", "useful")]
