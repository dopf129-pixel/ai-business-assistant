class AssistantOrchestratorBusinessService:


    def __init__(
        self,
        business_flow_service
    ):

        self.business_flow_service = (
            business_flow_service
        )



    def handle(
        self,
        text,
        report,
        context=None
    ):


        result = (
            self.business_flow_service
            .process(
                text,
                report,
                context
            )
        )



        if result["error"]:

            return result



        if (
            result.get("intent", {})
            .get("command")
            ==
            "continue"
        ):


            return {
                "error": False,
                "message":
                    "Продолжаем работу",
                "task":
                    result.get(
                        "continued_task",
                        ""
                    )
            }



        return {
            "error": False,
            "message":
                "Бизнес-план создан",
            "actions":
                result["plan"],
            "count":
                result["count"]
        }