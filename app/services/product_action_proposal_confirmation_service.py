class ProductActionProposalConfirmationService:

    STATUS_CONFIRMED = "CONFIRMED"
    STATUS_DISMISSED = "DISMISSED"
    ALLOWED_STATUSES = {STATUS_CONFIRMED, STATUS_DISMISSED}

    def __init__(
        self,
        history_service,
        proposal_service,
        task_draft_service=None,
    ):
        self.history_service = history_service
        self.proposal_service = proposal_service
        self.task_draft_service = task_draft_service

    def decide(self, sku, expected_proposal_type, status):
        sku = str(sku or "").strip()
        expected = str(expected_proposal_type or "").strip().upper()
        normalized_status = str(status or "").strip().upper()

        if normalized_status not in self.ALLOWED_STATUSES:
            return self._error("INVALID_PROPOSAL_STATUS", sku, expected)

        latest = self.history_service.latest(sku)
        if latest is None:
            return self._error("DECISION_HISTORY_NOT_FOUND", sku, expected)

        proposal = self.proposal_service.propose(latest)
        if not proposal.get("available") or not proposal.get("action_required"):
            return self._error("PROPOSAL_NOT_CONFIRMABLE", sku, expected)

        actual = str(proposal.get("proposal_type") or "").upper()
        if not expected or expected != actual:
            return self._error("STALE_PROPOSAL", sku, expected, actual=actual)

        saved = self.history_service.record_proposal_status(
            sku=sku,
            proposal_type=actual,
            status=normalized_status,
        )
        if saved.get("error"):
            return {
                **saved,
                "executed": False,
                "execution_allowed": False,
            }
        result = {
            **saved,
            "executed": False,
            "execution_allowed": False,
        }
        result["task_draft"] = self._update_task_draft(
            latest,
            proposal,
            normalized_status,
        )
        return result

    def _update_task_draft(self, decision, proposal, status):
        if self.task_draft_service is None:
            return None
        try:
            if status == self.STATUS_CONFIRMED:
                result = self.task_draft_service.create_from_confirmation(
                    decision,
                    proposal,
                )
            else:
                result = self.task_draft_service.dismiss(
                    sku=decision.get("sku"),
                    proposal_type=proposal.get("proposal_type"),
                    decision_recorded_at=decision.get("recorded_at"),
                )
        except (OSError, ValueError, TypeError):
            return None
        if result.get("error"):
            return None
        return result.get("task_draft")

    def _error(self, code, sku, expected, actual=None):
        return {
            "error": True,
            "code": code,
            "sku": sku or None,
            "proposal_type": actual or expected or None,
            "proposal_status": None,
            "saved": False,
            "executed": False,
            "execution_allowed": False,
        }
