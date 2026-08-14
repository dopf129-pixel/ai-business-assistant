class AssistantBusinessFlowService:


    def __init__(
        self,
        intent_service,
        planner_service,
        task_service=None,
        execution_service=None
    ):

        self.intent_service = intent_service

        self.planner_service = planner_service

        self.task_service = task_service

        self.execution_service = execution_service





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







        if command == "cancel_task":


            if (
                self.task_service
                and user_id
            ):


                cancelled = (
                    self.task_service
                    .cancel_task(
                        user_id
                    )
                )


                return {

                    "error":
                        cancelled.get(
                            "error",
                            False
                        ),

                    "intent":
                        intent,

                    "message":
                        "Задача отменена",

                    "cancelled_task":
                        cancelled.get(
                            "task"
                        )
                }





            return {

                "error": True,

                "message":
                    "Task service не подключён"
            }










        if command == "pause_task":


            if (
                self.task_service
                and user_id
            ):


                paused = (
                    self.task_service
                    .pause_task(
                        user_id
                    )
                )


                return {

                    "error":
                        paused.get(
                            "error",
                            False
                        ),

                    "intent":
                        intent,

                    "message":
                        "Задача поставлена на паузу",

                    "status":
                        paused.get(
                            "status"
                        )

                }



            return {

                "error": True,

                "message":
                    "Task service не подключён"

            }




        if command == "resume_task":


            if (
                self.task_service
                and user_id
            ):


                resumed = (
                    self.task_service
                    .resume_task(
                        user_id
                    )
                )


                return {

                    "error":
                        resumed.get(
                            "error",
                            False
                        ),

                    "intent":
                        intent,

                    "message":
                        "Задача возобновлена",

                    "status":
                        resumed.get(
                            "status"
                        )

                }



            return {

                "error": True,

                "message":
                    "Task service не подключён"

            }


        if command == "skip_action":


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


                action = (
                    next_result.get(
                        "action"
                    )
                )


                if not action:


                    return {

                        "error": False,

                        "intent":
                            intent,

                        "message":
                            "Нет доступного шага для пропуска"
                    }



                skipped = (
                    self.task_service
                    .skip_action(
                        user_id,
                        action.get(
                            "title"
                        )
                    )
                )


                next_action = (
                    self.task_service
                    .get_next_action(
                        user_id
                    )
                )


                return {

                    "error":
                        skipped.get(
                            "error",
                            False
                        ),

                    "intent":
                        intent,

                    "message":
                        "Шаг пропущен",

                    "action":
                        skipped.get(
                            "action"
                        ),

                    "next_action":
                        next_action.get(
                            "action"
                        )
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







        if command == "task_next":


            if (
                self.task_service
                and user_id
            ):


                next_action = (
                    self.task_service
                    .get_next_action(
                        user_id
                    )
                )


                return {

                    "error":
                        next_action.get(
                            "error",
                            False
                        ),

                    "intent":
                        intent,

                    "task_next":
                        next_action
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
                    next_result.get(
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
                result.get(
                    "actions",
                    []
                ),

            "count":
                result.get(
                    "count",
                    0
                )
        }