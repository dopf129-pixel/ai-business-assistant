class AssistantActionExecutionService:


    def __init__(
        self,
        task_service,
        history_service=None,
        action_router=None,
        action_runner_service=None,
        retry_policy=None,
        replanning_service=None,
        feedback_service=None
    ):


        self.task_service = task_service

        self.history_service = history_service

        self.action_router = action_router

        self.action_runner_service = action_runner_service

        self.retry_policy = retry_policy

        self.replanning_service = replanning_service

        self.feedback_service = feedback_service



    def execute(
        self,
        actions
    ):


        executed = []


        for action in actions:


            try:


                if self.action_runner_service:


                    result = (
                        self.action_runner_service
                        .run(
                            action
                        )
                    )


                else:


                    result = {

                        "error":
                            False,

                        "result":
                            {

                                "type":
                                    action.get(
                                        "type"
                                    ),

                                "message":
                                    "Действие выполнено"

                            }

                    }



                executed.append(

                    {

                        "action":
                            action,

                        "result":
                            result

                    }

                )


            except Exception as error:


                executed.append(

                    {

                        "action":
                            action,

                        "result":
                            {

                                "error":
                                    True,

                                "result":
                                    {

                                        "status":
                                            "FAILED",

                                        "message":
                                            str(
                                                error
                                            )

                                    }

                            }

                    }

                )



        return {

            "error":
                False,

            "executed":
                executed,

            "count":
                len(
                    executed
                )

        }



    def execute_current_action(
        self,
        user_id
    ):


        task_result = (
            self.task_service
            .get_task(
                user_id
            )
        )


        task = (
            task_result.get(
                "task"
            )
        )


        if not task:


            return {

                "error":
                    True,

                "message":
                    "Задача не найдена"

            }
        if task.get(
            "status"
        ) == "CANCELLED":


            return {

                "error":
                    True,

                "message":
                    "Задача отменена"

            }



        if task.get(
            "status"
        ) == "PAUSED":


            return {

                "error":
                    True,

                "message":
                    "Задача находится на паузе"

            }



        current = (
            self.task_service
            .get_current_action(
                user_id
            )
        )


        action = (
            current.get(
                "action"
            )
        )



        if not action:


            next_action = (
                self.task_service
                .get_next_action(
                    user_id
                )
            )


            action = (
                next_action.get(
                    "action"
                )
            )



        if not action:


            return {

                "error":
                    True,

                "message":
                    "Нет доступного действия"

            }



        if action.get(
            "status"
        ) != "NEW":


            return {

                "error":
                    False,

                "message":
                    "Действие уже обработано",

                "action":
                    action

            }



        self.task_service.start_action(

            user_id,

            action.get(
                "title"
            )

        )



        try:


            if self.action_runner_service:


                result = (
                    self.action_runner_service
                    .run(
                        action
                    )
                )


            else:


                result = {

                    "error":
                        False,

                    "result":
                        {

                            "type":
                                action.get(
                                    "type"
                                ),

                            "message":
                                "Действие выполнено"

                        }

                }
        except Exception as error:


            error_text = str(
                error
            )


            retry_allowed = False



            if self.retry_policy:


                retry_allowed = (
                    self.retry_policy
                    .should_retry(
                        error_text
                    )
                )



            if hasattr(
                self.task_service,
                "fail_action"
            ):


                self.task_service.fail_action(

                    user_id,

                    action.get(
                        "title"
                    ),

                    error_text

                )



            failed_action = action.copy()


            failed_action["status"] = "FAILED"


            failed_action["error"] = (
                error_text
            )


            failed_action["retry_allowed"] = (
                retry_allowed
            )


            failed_action["attempt"] = 1



            if self.feedback_service:


                try:


                    self.feedback_service.record(

                        {

                            "action":
                                action.get(
                                    "title"
                                ),

                            "status":
                                "FAILED",

                            "error":
                                error_text

                        }

                    )


                except Exception:

                    pass



            if self.history_service:


                try:


                    self.history_service.save_action(

                        {

                            "action":
                                failed_action,


                            "status":
                                "FAILED",


                            "error":
                                error_text,


                            "attempt":
                                1,


                            "retry_allowed":
                                retry_allowed,


                            "event":
                                "execution_failed"

                        }

                    )


                except Exception:

                    pass



            return {

                "error":
                    False,

                "message":
                    "Действие завершилось ошибкой",

                "action":
                    failed_action

            }



        completed = (
            self.task_service
            .complete_action(
                user_id,

                action.get(
                    "title"
                ),

                result
            )
        )
        if completed.get(
            "error"
        ):


            return completed



        if self.feedback_service:


            try:


                self.feedback_service.record(

                    {

                        "action":
                            action.get(
                                "title"
                            ),

                        "status":
                            "DONE",

                        "result":
                            result

                    }

                )


            except Exception:

                pass



        if self.history_service:


            try:


                self.history_service.save_action(

                    {

                        "action":
                            action,


                        "status":
                            "DONE",


                        "result":
                            result,


                        "event":
                            "execution_completed"

                    }

                )


            except Exception:

                pass



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



        progress = (
            self.task_service
            .get_task_progress(
                user_id
            )
        )



        completed_task = (

            progress.get(
                "total",
                0
            )
            ==
            progress.get(
                "done",
                0
            )

            and

            progress.get(
                "total",
                0
            )
            >
            0

        )



        return {

            "error":
                False,

            "message":
                "Действие выполнено",

            "action":
                completed.get(
                    "action"
                ),

            "next_action":
                next_action,

            "completed":
                completed_task,

            "progress":
                progress

        }



    def retry_action(
        self,
        user_id
    ):
        task_result = (
            self.task_service
            .get_task(
                user_id
            )
        )


        task = (
            task_result.get(
                "task"
            )
        )


        if not task:


            return {

                "error":
                    True,

                "message":
                    "Задача не найдена"

            }



        failed_action = None


        for action in task.get(
            "actions",
            []
        ):


            if action.get(
                "status"
            ) == "FAILED":


                failed_action = action

                break



        if not failed_action:


            return {

                "error":
                    True,

                "message":
                    "Нет FAILED действия"

            }



        attempt = (
            failed_action.get(
                "attempt",
                1
            )
        )



        if self.retry_policy:


            if not self.retry_policy.can_retry(
                attempt
            ):


                if self.history_service:


                    self.history_service.save_action(

                        {

                            "event":
                                "retry_blocked",

                            "reason":
                                "maximum retry attempts reached",

                            "attempt":
                                attempt

                        }

                    )


                return {

                    "error":
                        True,

                    "message":
                        "Повторное выполнение заблокировано"

                }



        prepare_retry = getattr(
            self.task_service,
            "prepare_retry_action",
            None
        )


        if callable(
            prepare_retry
        ):


            prepared = prepare_retry(
                user_id,
                failed_action.get(
                    "title"
                ),
                attempt + 1
            )


            if prepared.get(
                "error"
            ):


                return prepared


            failed_action = prepared.get(
                "action"
            )


        else:


            failed_action["status"] = "NEW"


            failed_action["attempt"] = (
                attempt + 1
            )


            failed_action.pop(
                "error",
                None
            )


            failed_action.pop(
                "retry_allowed",
                None
            )


            save = getattr(
                self.task_service,
                "save",
                None
            )


            if callable(
                save
            ):


                save()



        return {

            "error":
                False,

            "message":
                "Действие подготовлено к повторному выполнению",

            "action":
                failed_action

        }



    def replan_failed_action(
        self,
        user_id
    ):


        if not self.replanning_service:


            return {

                "error":
                    True,

                "message":
                    "Replanning service unavailable"

            }



        task_result = (
            self.task_service
            .get_task(
                user_id
            )
        )


        task = (
            task_result.get(
                "task"
            )
        )


        if not task:


            return {

                "error":
                    True,

                "message":
                    "Task not found"

            }



        failed_action = None



        for action in task.get(
            "actions",
            []
        ):


            if action.get(
                "status"
            ) == "FAILED":


                failed_action = action

                break



        if not failed_action:


            return {

                "error":
                    True,

                "message":
                    "FAILED action not found"

            }



        result = (
            self.replanning_service
            .replan(
                failed_action
            )
        )


        if result.get(
            "error"
        ):


            return result



        plan = (
            result.get(
                "plan",
                []
            )
        )


        apply_replan = getattr(
            self.task_service,
            "apply_replan",
            None
        )


        if callable(
            apply_replan
        ):


            applied = apply_replan(
                user_id,
                plan,
                reason=failed_action.get(
                    "error"
                )
            )


            if applied.get(
                "error"
            ):


                return applied


            plan = applied.get(
                "plan",
                []
            )


        else:


            task["actions"] = plan


            task["replanned"] = True


            task["pending_action"] = None


            save = getattr(
                self.task_service,
                "save",
                None
            )


            if callable(
                save
            ):


                save()



        if self.history_service:


            self.history_service.save_action(

                {

                    "event":
                        "replanned",

                    "reason":
                        failed_action.get(
                            "error"
                        ),

                    "plan":
                        plan

                }

            )



        return {

            "error":
                False,

            "message":
                "Plan updated",

            "plan":
                plan

        }