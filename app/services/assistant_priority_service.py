class AssistantPriorityService:


    def resolve(
        self,
        action
    ):


        existing_priority = (
            action.get(
                "priority"
            )
        )


        if existing_priority:


            return {

                "error":
                    False,

                "action":
                    action

            }


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


        elif action_type == "marketing":


            priority = "MEDIUM"


        elif action_type == "general":


            priority = "LOW"


        action["priority"] = (
            priority
        )


        return {

            "error":
                False,

            "action":
                action

        }