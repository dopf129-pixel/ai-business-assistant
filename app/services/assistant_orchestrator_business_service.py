class AssistantOrchestratorBusinessService:


    def __init__(
        self,
        business_flow_service,
        task_service=None,
        execution_service=None
    ):

        self.business_flow_service = (
            business_flow_service
        )

        self.task_service = (
            task_service
        )

        self.execution_service = (
            execution_service
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



        if result.get(
            "error"
        ):

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



        if command == "confirm_execute":


            execution = (
                result.get(
                    "execution",
                    {}
                )
            )


            return {

                "error": False,

                "message":
                    execution.get(
                        "message",
                        "Действие выполнено"
                    ),

                "action":
                    execution.get(
                        "action"
                    ),

                "execution":
                    execution.get(
                        "execution"
                    ),

                "next_action":
                    execution.get(
                        "next_action"
                    ),

                "completed":
                    execution.get(
                        "completed",
                        False
                    ),

                "progress":
                    execution.get(
                        "progress",
                        {
                            "done": 0,
                            "total": 0
                        }
                    )
            }






        if command == "execute":


            return result






        if command == "task_status":


            return {

                "error": False,

                "task_status":
                    result.get(
                        "task_status",
                        {}
                    ),

                "message":
                    "Статус задачи"
            }






        if command == "task_history":


            return {

                "error": False,

                "task_history":
                    result.get(
                        "task_history",
                        {}
                    ),

                "message":
                    "История задачи"
            }
        if command == "task_details":


            return {

                "error": False,

                "task_details":
                    result.get(
                        "task_details",
                        {}
                    ),

                "message":
                    "Детали задачи"
            }






        if command == "task_next":


            next_data = (
                result.get(
                    "task_next",
                    {}
                )
            )


            return {

                "error": False,

                "message":
                    "Следующий шаг",

                "next_action":
                    next_data.get(
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



            return {

                "error": False,

                "message":
                    "Продолжаем работу",

                "task":
                    task,

                "next_step":
                    result.get(
                        "next_action"
                    )
            }






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