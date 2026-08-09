class AssistantPlanningService:


    def build_plan(
        self,
        recommendations
    ):

        plan = []


        for item in recommendations:

            plan.append(
                {
                    "step": len(plan) + 1,
                    "action": item.get(
                        "message"
                    ),
                    "type": item.get(
                        "type"
                    )
                }
            )


        return {
            "error": False,
            "plan": plan,
            "count": len(
                plan
            )
        }