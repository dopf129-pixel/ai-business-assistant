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


    @staticmethod
    def _valid_result(
        payload
    ):

        return (
            isinstance(
                payload,
                dict
            )
            and
            isinstance(
                payload.get(
                    "error"
                ),
                bool
            )
        )


    @staticmethod
    def _safe_message(
        payload,
        fallback
    ):

        message = (
            payload.get(
                "message"
            )
            if isinstance(
                payload,
                dict
            )
            else None
        )

        if (
            isinstance(
                message,
                str
            )
            and message.strip()
        ):

            return message

        return fallback


    @staticmethod
    def _valid_optional_action(
        action
    ):

        return (
            action is None
            or
            isinstance(
                action,
                dict
            )
        )


    @staticmethod
    def _valid_progress(
        progress
    ):

        if not isinstance(
            progress,
            dict
        ):

            return False

        done = progress.get(
            "done"
        )

        total = progress.get(
            "total"
        )

        if (
            isinstance(
                done,
                bool
            )
            or
            isinstance(
                total,
                bool
            )
            or
            not isinstance(
                done,
                int
            )
            or
            not isinstance(
                total,
                int
            )
            or
            done < 0
            or
            total < 0
            or
            done > total
        ):

            return False

        return True


    @staticmethod
    def _invalid(
        message,
        intent=None,
        **extra
    ):

        result = {
            "error": True,
            "message": message
        }

        if intent is not None:

            result["intent"] = intent

        result.update(
            extra
        )

        return result


    def _task_failure(
        self,
        intent,
        payload,
        fallback,
        **extra
    ):

        return self._invalid(
            self._safe_message(
                payload,
                fallback
            ),
            intent=intent,
            **extra
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

        if not self._valid_result(
            intent
        ):

            return self._invalid(
                "INVALID_INTENT_RESULT"
            )

        if intent["error"]:

            return intent

        command = intent.get(
            "command"
        )

        if (
            not isinstance(
                command,
                str
            )
            or
            not command.strip()
        ):

            return self._invalid(
                "INVALID_INTENT_RESULT",
                intent=intent
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

                if not self._valid_result(
                    result
                ):

                    return {
                        "error": True,
                        "intent": intent,
                        "execution": {
                            "error": True,
                            "message": (
                                "INVALID_EXECUTION_RESULT"
                            ),
                            "action": None,
                            "next_action": None,
                            "completed": False,
                            "progress": {
                                "done": 0,
                                "total": 0
                            }
                        }
                    }

                if result["error"]:

                    return {
                        "error": True,
                        "intent": intent,
                        "execution": {
                            "error": True,
                            "message": (
                                self._safe_message(
                                    result,
                                    "EXECUTION_RETURNED_ERROR"
                                )
                            ),
                            "action": (
                                result.get(
                                    "action"
                                )
                                if isinstance(
                                    result.get(
                                        "action"
                                    ),
                                    dict
                                )
                                else None
                            ),
                            "next_action": (
                                result.get(
                                    "next_action"
                                )
                                if isinstance(
                                    result.get(
                                        "next_action"
                                    ),
                                    dict
                                )
                                else None
                            ),
                            "completed": False,
                            "progress": {
                                "done": 0,
                                "total": 0
                            }
                        }
                    }

                message = result.get(
                    "message"
                )

                action = result.get(
                    "action"
                )

                next_action = result.get(
                    "next_action"
                )

                completed = result.get(
                    "completed",
                    False
                )

                progress = result.get(
                    "progress",
                    {
                        "done": 0,
                        "total": 0
                    }
                )

                if (
                    not isinstance(
                        message,
                        str
                    )
                    or
                    not message.strip()
                    or
                    not self._valid_optional_action(
                        action
                    )
                    or
                    not self._valid_optional_action(
                        next_action
                    )
                    or
                    not isinstance(
                        completed,
                        bool
                    )
                    or
                    not self._valid_progress(
                        progress
                    )
                ):

                    return {
                        "error": True,
                        "intent": intent,
                        "execution": {
                            "error": True,
                            "message": (
                                "INVALID_EXECUTION_RESULT"
                            ),
                            "action": None,
                            "next_action": None,
                            "completed": False,
                            "progress": {
                                "done": 0,
                                "total": 0
                            }
                        }
                    }

                return {
                    "error": False,
                    "intent": intent,
                    "execution": {
                        "error": False,
                        "message": message,
                        "action": action,
                        "next_action": next_action,
                        "completed": completed,
                        "progress": progress
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

                if not self._valid_result(
                    cancelled
                ):

                    return self._invalid(
                        "INVALID_TASK_RESULT",
                        intent=intent
                    )

                if cancelled["error"]:

                    return self._task_failure(
                        intent,
                        cancelled,
                        "TASK_CANCEL_FAILED",
                        cancelled_task=(
                            cancelled.get(
                                "task"
                            )
                        )
                    )

                return {
                    "error": False,
                    "intent": intent,
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

                if not self._valid_result(
                    paused
                ):

                    return self._invalid(
                        "INVALID_TASK_RESULT",
                        intent=intent
                    )

                if paused["error"]:

                    return self._task_failure(
                        intent,
                        paused,
                        "TASK_PAUSE_FAILED"
                    )

                return {
                    "error": False,
                    "intent": intent,
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

                if not self._valid_result(
                    resumed
                ):

                    return self._invalid(
                        "INVALID_TASK_RESULT",
                        intent=intent
                    )

                if resumed["error"]:

                    return self._task_failure(
                        intent,
                        resumed,
                        "TASK_RESUME_FAILED"
                    )

                return {
                    "error": False,
                    "intent": intent,
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

                if not self._valid_result(
                    next_result
                ):

                    return self._invalid(
                        "INVALID_TASK_NEXT_RESULT",
                        intent=intent
                    )

                if next_result["error"]:

                    return self._task_failure(
                        intent,
                        next_result,
                        "TASK_NEXT_FAILED"
                    )

                action = next_result.get(
                    "action"
                )

                if action is None:

                    return {
                        "error": False,
                        "intent": intent,
                        "message":
                            "Нет доступного шага для пропуска"
                    }

                if not isinstance(
                    action,
                    dict
                ):

                    return self._invalid(
                        "INVALID_TASK_NEXT_RESULT",
                        intent=intent
                    )

                title = action.get(
                    "title"
                )

                if (
                    not isinstance(
                        title,
                        str
                    )
                    or
                    not title.strip()
                ):

                    return self._invalid(
                        "INVALID_TASK_NEXT_RESULT",
                        intent=intent
                    )

                skipped = (
                    self.task_service
                    .skip_action(
                        user_id,
                        title
                    )
                )

                if not self._valid_result(
                    skipped
                ):

                    return self._invalid(
                        "INVALID_TASK_SKIP_RESULT",
                        intent=intent
                    )

                if skipped["error"]:

                    return self._task_failure(
                        intent,
                        skipped,
                        "TASK_SKIP_FAILED"
                    )

                skipped_action = skipped.get(
                    "action"
                )

                if not isinstance(
                    skipped_action,
                    dict
                ):

                    return self._invalid(
                        "INVALID_TASK_SKIP_RESULT",
                        intent=intent
                    )

                next_after_skip = (
                    self.task_service
                    .get_next_action(
                        user_id
                    )
                )

                if not self._valid_result(
                    next_after_skip
                ):

                    return self._invalid(
                        "INVALID_TASK_NEXT_RESULT",
                        intent=intent,
                        action=skipped_action,
                        next_action=None
                    )

                if next_after_skip["error"]:

                    return self._task_failure(
                        intent,
                        next_after_skip,
                        "TASK_NEXT_FAILED",
                        action=skipped_action,
                        next_action=None
                    )

                next_action = (
                    next_after_skip.get(
                        "action"
                    )
                )

                if not self._valid_optional_action(
                    next_action
                ):

                    return self._invalid(
                        "INVALID_TASK_NEXT_RESULT",
                        intent=intent,
                        action=skipped_action,
                        next_action=None
                    )

                return {
                    "error": False,
                    "intent": intent,
                    "message":
                        "Шаг пропущен",
                    "action":
                        skipped_action,
                    "next_action":
                        next_action
                }

            return {
                "error": True,
                "message":
                    "Task service не подключён"
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

                if not self._valid_result(
                    status
                ):

                    return self._invalid(
                        "INVALID_TASK_RESULT",
                        intent=intent
                    )

                return {
                    "error":
                        status["error"],
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

                if not self._valid_result(
                    history
                ):

                    return self._invalid(
                        "INVALID_TASK_RESULT",
                        intent=intent
                    )

                return {
                    "error":
                        history["error"],
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

                if not self._valid_result(
                    details
                ):

                    return self._invalid(
                        "INVALID_TASK_RESULT",
                        intent=intent
                    )

                return {
                    "error":
                        details["error"],
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

                if not self._valid_result(
                    next_action
                ):

                    return self._invalid(
                        "INVALID_TASK_NEXT_RESULT",
                        intent=intent
                    )

                return {
                    "error":
                        next_action["error"],
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

                if not self._valid_result(
                    next_result
                ):

                    return self._invalid(
                        "INVALID_TASK_NEXT_RESULT",
                        intent=intent
                    )

                if next_result["error"]:

                    return self._task_failure(
                        intent,
                        next_result,
                        "TASK_NEXT_FAILED"
                    )

                next_action = (
                    next_result.get(
                        "action"
                    )
                )

                if not self._valid_optional_action(
                    next_action
                ):

                    return self._invalid(
                        "INVALID_TASK_NEXT_RESULT",
                        intent=intent
                    )

                if next_action:

                    pending_result = (
                        self.task_service
                        .set_pending_action(
                            user_id,
                            next_action
                        )
                    )

                    if not self._valid_result(
                        pending_result
                    ):

                        return self._invalid(
                            "INVALID_PENDING_ACTION_RESULT",
                            intent=intent
                        )

                    if pending_result["error"]:

                        return self._task_failure(
                            intent,
                            pending_result,
                            "SET_PENDING_ACTION_FAILED"
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

        if not self._valid_result(
            result
        ):

            return self._invalid(
                "INVALID_PLANNER_RESULT",
                intent=intent,
                plan=[],
                count=0
            )

        if result["error"]:

            return self._invalid(
                self._safe_message(
                    result,
                    "PLANNER_RETURNED_ERROR"
                ),
                intent=intent,
                plan=[],
                count=0
            )

        plan = result.get(
            "actions"
        )

        count = result.get(
            "count"
        )

        if (
            not isinstance(
                plan,
                list
            )
            or
            not all(
                isinstance(
                    item,
                    dict
                )
                for item in plan
            )
            or
            isinstance(
                count,
                bool
            )
            or
            not isinstance(
                count,
                int
            )
            or
            count < 0
            or
            count
            !=
            len(
                plan
            )
        ):

            return self._invalid(
                "INVALID_PLANNER_RESULT",
                intent=intent,
                plan=[],
                count=0
            )

        return {
            "error": False,
            "intent":
                intent,
            "plan":
                plan,
            "count":
                count
        }
