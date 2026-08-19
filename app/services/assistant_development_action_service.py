class AssistantDevelopmentActionService:
    """
    Executes actions based on development decisions.
    """

    def __init__(self):
        self.name = "AssistantDevelopmentActionService"


    def execute(self, decision):
        """
        Converts decision into next action.
        """

        if decision["decision"] == "complete":

            return {
                "action": "continue",
                "next_step": "checkpoint_ready",
                "status": "ready",
            }


        if decision["decision"] == "blocked":

            return {
                "action": "stop",
                "next_step": "review_required",
                "status": "blocked",
            }


        return {
            "action": "wait",
            "next_step": "unknown",
            "status": "unknown",
        }
