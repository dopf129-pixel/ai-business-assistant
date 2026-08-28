from copy import deepcopy


class ProductDecisionActionProposalService:

    PROPOSAL_REVIEW_REPLENISHMENT = "REVIEW_REPLENISHMENT"
    PROPOSAL_REVIEW_UNIT_ECONOMICS = "REVIEW_UNIT_ECONOMICS"
    PROPOSAL_REVIEW_MARGIN = "REVIEW_MARGIN"
    PROPOSAL_MONITOR_ONLY = "MONITOR_ONLY"

    DECISION_PROPOSALS = {
        "REPLENISH_HIGH_PRIORITY": (
            PROPOSAL_REVIEW_REPLENISHMENT,
            True,
        ),
        "REPLENISH_NORMAL": (
            PROPOSAL_REVIEW_REPLENISHMENT,
            True,
        ),
        "INVESTIGATE_LOW_PROFIT": (
            PROPOSAL_REVIEW_UNIT_ECONOMICS,
            True,
        ),
        "WATCH_LOW_MARGIN": (
            PROPOSAL_REVIEW_MARGIN,
            True,
        ),
        "HOLD_STOCK": (
            PROPOSAL_MONITOR_ONLY,
            False,
        ),
    }

    def propose(self, decision):
        source = deepcopy(decision or {})
        mapping = self.DECISION_PROPOSALS.get(
            source.get("decision_type")
        )
        if mapping is None or source.get("error"):
            return self._unavailable(source)

        proposal_type, action_required = mapping
        return {
            "available": True,
            "proposal_type": proposal_type,
            "action_required": action_required,
            "requires_confirmation": action_required,
            "execution_allowed": False,
            "automation_status": "PROHIBITED",
            "sku": source.get("sku"),
            "priority": source.get("priority"),
            "decision_type": source.get("decision_type"),
            "reasons": list(source.get("reasons") or []),
        }

    def _unavailable(self, source):
        return {
            "available": False,
            "proposal_type": None,
            "action_required": False,
            "requires_confirmation": False,
            "execution_allowed": False,
            "automation_status": "PROHIBITED",
            "sku": source.get("sku"),
            "priority": source.get("priority"),
            "decision_type": source.get("decision_type"),
            "reasons": list(source.get("reasons") or []),
        }
