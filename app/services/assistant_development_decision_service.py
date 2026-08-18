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
