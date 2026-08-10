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



        command = (
            result.get(
                "intent",
                {}
            )
            .get(
                "command"
            )
        )



        if command == "execute":


            execution = (
                result.get(
                    "execution",
                    {}
                )
            )


            return {

                "error":
                    execution.get(
                        "error",
                        False
                    ),

                "message":
                    execution.get(
                        "message",
                        "Действие выполнено"
                    ),

                "action":
                    execution.get(
                        "action"
                    )
            }





        if command == "continue":


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



            last_action = None
            next_action = None



            if (
                self.task_service
                and user_id
            ):


                last_result = (
                    self.task_service
                    .get_last_completed_action(
                        user_id
                    )
                )


                last_action = (
                    last_result
                    .get(
                        "action"
                    )
                )



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



            response = {

                "error": False,

                "message":
                    "Продолжаем работу",

                "task":
                    task
            }



            if last_action:


                response["last_completed"] = (
                    last_action
                )


                response["result"] = (
                    last_action
                    .get(
                        "result"
                    )
                )



            if next_action:


                response["next_step"] = {

                    "title":
                        next_action.get(
                            "title"
                        ),

                    "action":
                        next_action
                }


            else:

                response["next_step"] = (
                    "Все действия выполнены"
                )



            return response





        return {

            "error": False,

            "message":
                "Бизнес-план создан",

            "actions":
                result.get(
                    "plan",
                    []
                ),

            "count":
                result.get(
                    "count",
                    0
                )
        }