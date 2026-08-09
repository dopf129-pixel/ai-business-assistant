class AssistantPriorityService:


    def resolve(
        self,
        action
    ):

        action_type = (
            action.get(
                "type"
            )
        )


        priority = "MEDIUM"


        if action_type == "stock":

            priority = "HIGH"


        elif action_type == "sales":

            priority = "HIGH"


        elif action_type == "general":

            priority = "LOW"



        action["priority"] = (
            priority
        )


        return {
            "error": False,
            "action": action
        }