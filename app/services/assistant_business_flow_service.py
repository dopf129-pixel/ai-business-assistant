class AssistantBusinessFlowService:


    def __init__(
        self,
        intent_service,
        planner_service
    ):

        self.intent_service = (
            intent_service
        )

        self.planner_service = (
            planner_service
        )



    def process(
        self,
        text,
        report,
        context=None
    ):


        intent = (
            self.intent_service
            .detect(
                text,
                context
            )
        )



        if intent["error"]:

            return intent



        if (
            intent.get("command")
            ==
            "continue"
        ):


            return {
                "error": False,
                "intent": intent,
                "plan": [],
                "count": 0,
                "continued_task":
                    intent.get(
                        "task",
                        ""
                    )
            }



        result = (
            self.planner_service
            .build_plan(
                report
            )
        )



        return {
            "error": False,
            "intent": intent,
            "plan": result["actions"],
            "count": result["count"]
        }