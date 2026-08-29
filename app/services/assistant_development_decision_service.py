class AssistantDevelopmentDecisionService:
    """
    Evaluates development execution results
    and decides next workflow action.
    """

    def __init__(self, verification_service=None):
        self.name = "AssistantDevelopmentDecisionService"
        self.verification_service = verification_service

    def evaluate(
        self,
        report,
        current_sha=None,
        test_report=None,
    ):
        """
        Analyzes development report.

        Legacy calls without current_sha preserve the previous behavior.
        SHA-aware calls recompute verification through the injected
        canonical verification service instead of trusting report fields.
        """

        if current_sha is not None:
            if self.verification_service is None:
                return self._blocked(
                    "verification_service_required"
                )

            verification = self.verification_service.evaluate(
                current_sha,
                test_report,
            )

            if verification.get("current_suite_verified") is not True:
                return self._blocked(
                    "current_suite_not_verified"
                )

            if verification.get("current_suite_passed") is not True:
                return self._blocked(
                    "current_suite_failed"
                )

        if report["status"] == "completed":
            return {
                "decision": "complete",
                "next_action": "checkpoint_ready",
                "reason": "workflow_completed",
            }

        return self._blocked("workflow_failed")

    def _blocked(self, reason):
        return {
            "decision": "blocked",
            "next_action": "review_required",
            "reason": reason,
        }
