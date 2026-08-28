from app.services.product_decision_action_proposal_service import (
    ProductDecisionActionProposalService,
)


def _decision(decision_type, **overrides):
    result = {
        "error": False,
        "sku": "hook-2",
        "decision_type": decision_type,
        "priority": "HIGH",
        "reasons": ["POSITIVE_UNIT_PROFIT"],
    }
    result.update(overrides)
    return result


def test_replenishment_decisions_propose_manual_review_only():
    service = ProductDecisionActionProposalService()

    urgent = service.propose(_decision("REPLENISH_HIGH_PRIORITY"))
    normal = service.propose(_decision("REPLENISH_NORMAL"))

    for proposal in (urgent, normal):
        assert proposal["proposal_type"] == "REVIEW_REPLENISHMENT"
        assert proposal["action_required"] is True
        assert proposal["requires_confirmation"] is True
        assert proposal["execution_allowed"] is False
        assert proposal["automation_status"] == "PROHIBITED"


def test_profit_and_margin_decisions_propose_safe_reviews():
    service = ProductDecisionActionProposalService()

    profit = service.propose(_decision("INVESTIGATE_LOW_PROFIT"))
    margin = service.propose(_decision("WATCH_LOW_MARGIN"))

    assert profit["proposal_type"] == "REVIEW_UNIT_ECONOMICS"
    assert margin["proposal_type"] == "REVIEW_MARGIN"
    assert profit["execution_allowed"] is False
    assert margin["execution_allowed"] is False


def test_hold_stock_is_monitoring_not_required_action():
    service = ProductDecisionActionProposalService()

    proposal = service.propose(_decision("HOLD_STOCK", priority="LOW"))

    assert proposal["proposal_type"] == "MONITOR_ONLY"
    assert proposal["available"] is True
    assert proposal["action_required"] is False
    assert proposal["requires_confirmation"] is False
    assert proposal["execution_allowed"] is False


def test_insufficient_or_error_decision_has_no_proposal():
    service = ProductDecisionActionProposalService()

    insufficient = service.propose(_decision("INSUFFICIENT_DATA"))
    error = service.propose(_decision("HOLD_STOCK", error=True))

    for proposal in (insufficient, error):
        assert proposal["available"] is False
        assert proposal["proposal_type"] is None
        assert proposal["execution_allowed"] is False
