class AssistantOrchestratorBusinessService:


    def __init__(
        self,
        business_flow_service,
        task_service=None
    ):

        self.business_flow_service = (
            business_flow_service
        )

        self.task_service = (
            task_service
        )



    def handle(
        self,
        text,
        report,
        context=None,
        user_id=None
    ):


        result = (
            self.business_flow_service
            .process(
                text,
                report,
                context,
                user_id
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



            next_action = None



            if (
                self.task_service
                and user_id
            ):

                next_result = (
                    self.task_service
                    .get_next_action(
                        user_id
                    )
                )


                next_action = (
                    next_result
                    .get(
                        "action"
                    )
                )



            if next_action:


                return {

                    "error": False,

                    "message":
                        "Продолжаем работу",

                    "task":
                        task,

                    "next_step":
                        (
                            "Следующий шаг: "
                            +
                            next_action.get(
                                "title",
                                ""
                            )
                        ),

                    "action":
                        next_action
                }



            return {

                "error": False,

                "message":
                    "Продолжаем работу",

                "task":
                    task,

                "next_step":
                    (
                        "Все действия выполнены"
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