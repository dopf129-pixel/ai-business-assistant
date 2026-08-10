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


            task = (
                result.get(
                    "continued_task",
                    ""
                )
            )



            if not task and context:


                if "context" in context:

                    task = (
                        context["context"]
                        .get(
                            "current_task",
                            ""
                        )
                    )


                else:

                    task = (
                        context
                        .get(
                            "current_task",
                            ""
                        )
                    )



            return {
                "error": False,

                "message":
                    "Продолжаем работу",

                "task":
                    task,

                "next_step":
                    f"Следующий шаг по задаче: {task}"
                    if task
                    else
                    "Задача не определена"
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