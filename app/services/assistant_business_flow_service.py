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



        command = (
            intent.get(
                "command"
            )
        )



        if (
            command == "execute"
            or
            command == "confirm_execute"
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
                        {

                            "error":
                                result.get(
                                    "error",
                                    False
                                ),

                            "message":
                                result.get(
                                    "message",
                                    "Действие выполнено"
                                ),

                            "action":
                                result.get(
                                    "action"
                                ),

                            "execution":
                                result.get(
                                    "execution"
                                ),

                            "next_action":
                                result.get(
                                    "next_action"
                                ),

                            "completed":
                                result.get(
                                    "completed",
                                    False
                                ),

                            "progress":
                                result.get(
                                    "progress",
                                    {
                                        "done": 0,
                                        "total": 0
                                    }
                                )
                        }
                }



            return {

                "error": True,

                "message":
                    "Сервис выполнения не подключён"
            }






        if command == "task_status":


            if (
                self.task_service
                and user_id
            ):


                status = (
                    self.task_service
                    .get_task_status(
                        user_id
                    )
                )


                return {

                    "error":
                        status.get(
                            "error",
                            False
                        ),

                    "intent":
                        intent,

                    "task_status":
                        status
                }



            return {

                "error": True,

                "message":
                    "Task service не подключён"
            }






        if command == "task_history":


            if (
                self.task_service
                and user_id
            ):


                history = (
                    self.task_service
                    .get_task_history(
                        user_id
                    )
                )


                return {

                    "error":
                        history.get(
                            "error",
                            False
                        ),

                    "intent":
                        intent,

                    "task_history":
                        history
                }



            return {

                "error": True,

                "message":
                    "Task service не подключён"
            }
        if command == "task_details":


            if (
                self.task_service
                and user_id
            ):


                details = (
                    self.task_service
                    .get_task_history(
                        user_id
                    )
                )


                return {

                    "error":
                        details.get(
                            "error",
                            False
                        ),

                    "intent":
                        intent,

                    "task_details":
                        details
                }



            return {

                "error": True,

                "message":
                    "Task service не подключён"
            }







        if command == "continue":


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


                    self.task_service.set_pending_action(
                        user_id,
                        next_action
                    )



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
                    ),

                "next_action":
                    next_action
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