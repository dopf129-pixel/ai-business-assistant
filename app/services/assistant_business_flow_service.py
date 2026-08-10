class AssistantBusinessFlowService:


    def __init__(
        self,
        intent_service,
        planner_service,
        task_service=None,
        execution_service=None
    ):

        self.intent_service = (
            intent_service
        )

        self.planner_service = (
            planner_service
        )

        self.task_service = (
            task_service
        )

        self.execution_service = (
            execution_service
        )



    def process(
        self,
        text,
        report,
        context=None,
        user_id=None
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
            "execute"
        ):


            if (
                self.execution_service
                and user_id
            ):


                result = (
                    self.execution_service
                    .execute_current_action(
                        user_id
                    )
                )


                return {

                    "error":
                        result.get(
                            "error",
                            False
                        ),

                    "intent":
                        intent,

                    "execution":
                        result
                }



            return {

                "error": True,

                "message":
                    "Сервис выполнения не подключён"
            }



        if (
            intent.get("command")
            ==
            "continue"
        ):


            return {

                "error": False,

                "intent":
                    intent,

                "plan":
                    [],

                "count":
                    0,

                "continued_task":
                    intent.get(
                        "task",
                        ""
                    )
            }



        result = (
            self.planner_service
            .build_plan(
                report,
                user_id
            )
        )



        return {

            "error": False,

            "intent":
                intent,

            "plan":
                result["actions"],

            "count":
                result["count"]
        }