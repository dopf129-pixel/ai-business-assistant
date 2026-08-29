class AssistantDevelopmentDecisionService:
    """
    Evaluates development execution results
    and decides next workflow action.
    """

    def __init__(self):
        self.name = "AssistantDevelopmentDecisionService"


    def evaluate(self, report):
        """
        Analyzes development report.
        """

        verification = report.get("verification")
        if isinstance(verification, dict):
            if verification.get("current_suite_verified") is not True:
                return {
                    "decision": "blocked",
                    "next_action": "review_required",
                    "reason": "current_suite_not_verified",
                }

            if verification.get("current_suite_passed") is not True:
                return {
                    "decision": "blocked",
                    "next_action": "review_required",
                    "reason": "current_suite_failed",
                }

        if report["status"] == "completed":

            return {
                "decision": "complete",
                "next_action": "checkpoint_ready",
                "reason": "workflow_completed",
            }


        return {
            "decision": "blocked",
            "next_action": "review_required",
            "reason": "workflow_failed",
        }
