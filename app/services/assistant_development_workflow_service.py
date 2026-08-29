class AssistantDevelopmentWorkflowService:
    """
    Development Autopilot workflow orchestrator.

    Coordinates development steps:
    - change analysis
    - test validation
    - documentation validation
    - checkpoint preparation
    """

    def __init__(self, verification_service=None):
        self.steps = []
        self.verification_service = verification_service

    def start_workflow(
        self,
        change,
        current_sha=None,
        test_report=None,
    ):
        self.steps = [
            "change_analysis",
            "test_validation",
            "documentation_validation",
            "checkpoint_preparation",
        ]

        result = {
            "change": change,
            "status": "started",
            "steps": self.steps,
        }

        verification = self._verification(
            current_sha,
            test_report,
        )
        if verification is not None:
            result["verification"] = verification
            result["test_validation_status"] = (
                self._validation_status(verification)
            )

        return result

    def complete_step(
        self,
        step,
        current_sha=None,
        test_report=None,
    ):
        if step not in self.steps:
            return {
                "step": step,
                "status": "unknown",
            }

        if (
            step == "test_validation"
            and self.verification_service is not None
            and current_sha is not None
        ):
            verification = self.verification_service.evaluate(
                current_sha,
                test_report,
            )
            status = self._validation_status(verification)
            if status != "verified":
                return {
                    "step": step,
                    "status": "blocked",
                    "reason": (
                        "current_suite_failed"
                        if status == "failed"
                        else "current_suite_not_verified"
                    ),
                    "verification": verification,
                }

            return {
                "step": step,
                "status": "completed",
                "verification": verification,
            }

        return {
            "step": step,
            "status": "completed",
        }

    def get_workflow_steps(self):
        return self.steps

    def _verification(self, current_sha, test_report):
        if (
            self.verification_service is None
            or current_sha is None
        ):
            return None
        return self.verification_service.evaluate(
            current_sha,
            test_report,
        )

    def _validation_status(self, verification):
        source = dict(verification or {})
        if source.get("current_suite_verified") is not True:
            return "unverified"
        if source.get("current_suite_passed") is not True:
            return "failed"
        return "verified"
