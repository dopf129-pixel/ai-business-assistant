class AssistantOrchestratorBusinessService:

    def __init__(
        self,
        business_flow_service,
        task_service=None,
        execution_service=None
    ):

        self.business_flow_service = business_flow_service
        self.task_service = task_service
        self.execution_service = execution_service


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


        execution = (
            result.get(
                "execution",
                {}
            )
        )


        if (
            execution
            and
            execution.get(
                "error"
            )
        ):

            message = (
                execution.get(
                    "message",
                    "Ошибка выполнения"
                )
            )


            if (
                "отменена"
                in
                message.lower()
            ):

                return {

                    "error": False,

                    "message":
                        message

                }


            return {

                "error": True,

                "message":
                    message,

                "execution":
                    execution

            }


        if result.get(
            "error"
        ):

            return result



        intent = (
            result.get(
                "intent",
                {}
            )
        )


        command = (
            intent.get(
                "command"
            )
        )



        if (
            command == "confirm_execute"
            or
            command == "execute"
        ):

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



        if command == "cancel_task":

            return {

                "error": False,

                "message":
                    result.get(
                        "message",
                        "Задача отменена"
                    ),

                "cancelled_task":
                    result.get(
                        "cancelled_task"
                    )

            }



        if command == "pause_task":

            return {

                "error": False,

                "message":
                    result.get(
                        "message",
                        "Задача поставлена на паузу"
                    ),

                "status":
                    result.get(
                        "status"
                    )

            }



        if command == "resume_task":

            return {

                "error": False,

                "message":
                    result.get(
                        "message",
                        "Задача возобновлена"
                    ),

                "status":
                    result.get(
                        "status"
                    )

            }



        if command == "skip_action":

            return {

                "error": False,

                "message":
                    result.get(
                        "message",
                        "Шаг пропущен"
                    ),

                "action":
                    result.get(
                        "action"
                    ),

                "next_action":
                    result.get(
                        "next_action"
                    )

            }



        if command == "task_status":

            return {

                "error": False,

                "message":
                    "Статус задачи",

                "task_status":
                    result.get(
                        "task_status",
                        {}
                    )

            }



        if command == "task_history":

            return {

                "error": False,

                "message":
                    "История задачи",

                "task_history":
                    result.get(
                        "task_history",
                        {}
                    )

            }



        if command == "task_details":

            return {

                "error": False,

                "message":
                    "Детали задачи",

                "task_details":
                    result.get(
                        "task_details",
                        {}
                    )

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

            return {

                "error": False,

                "message":
                    "Продолжаем работу",

                "task":
                    result.get(
                        "continued_task",
                        ""
                    ),

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