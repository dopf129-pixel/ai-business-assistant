from app.services.product_action_proposal_confirmation_service import (
    ProductActionProposalConfirmationService,
)
from app.services.product_decision_action_proposal_service import (
    ProductDecisionActionProposalService,
)
from app.services.product_decision_history_service import (
    ProductDecisionHistoryService,
)


def _service(decision_type="REPLENISH_NORMAL"):
    history = ProductDecisionHistoryService(clock=lambda: "now")
    history.record({
        "error": False,
        "sku": "hook-2",
        "decision_type": decision_type,
        "priority": "HIGH",
        "reasons": ["DAYS_OF_STOCK_LOW"],
    })
    return ProductActionProposalConfirmationService(
        history_service=history,
        proposal_service=ProductDecisionActionProposalService(),
    ), history


def test_confirmation_records_intent_without_execution():
    service, history = _service()

    result = service.decide(
        "hook-2", "REVIEW_REPLENISHMENT", "CONFIRMED"
    )

    assert result["error"] is False
    assert result["saved"] is True
    assert result["executed"] is False
    assert result["execution_allowed"] is False
    assert history.latest("hook-2")["proposal_status"] == "CONFIRMED"


def test_dismissal_and_repeated_status_are_idempotent():
    service, _ = _service()

    first = service.decide(
        "hook-2", "REVIEW_REPLENISHMENT", "DISMISSED"
    )
    repeated = service.decide(
        "hook-2", "REVIEW_REPLENISHMENT", "DISMISSED"
    )

    assert first["saved"] is True
    assert repeated["saved"] is False
    assert repeated["executed"] is False


def test_stale_or_non_actionable_proposal_cannot_be_confirmed():
    service, _ = _service()
    stale = service.decide("hook-2", "REVIEW_MARGIN", "CONFIRMED")

    monitor_service, _ = _service(decision_type="HOLD_STOCK")
    monitor = monitor_service.decide(
        "hook-2", "MONITOR_ONLY", "CONFIRMED"
    )

    assert stale["code"] == "STALE_PROPOSAL"
    assert monitor["code"] == "PROPOSAL_NOT_CONFIRMABLE"
    assert stale["executed"] is False
    assert monitor["executed"] is False


def test_confirmation_validates_status_and_decision_history():
    service, _ = _service()
    invalid = service.decide(
        "hook-2", "REVIEW_REPLENISHMENT", "EXECUTE"
    )
    missing = service.decide(
        "missing", "REVIEW_REPLENISHMENT", "CONFIRMED"
    )

    assert invalid["code"] == "INVALID_PROPOSAL_STATUS"
    assert missing["code"] == "DECISION_HISTORY_NOT_FOUND"
