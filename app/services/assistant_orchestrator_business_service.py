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

        if not self._valid_result(result):
            return self._invalid()

        if result["error"]:
            return result

        intent = result.get("intent")

        if not isinstance(intent, dict):
            return self._invalid()

        command = intent.get("command")

        if (
            not isinstance(command, str)
            or not command.strip()
        ):
            return self._invalid()

        if (
            command == "confirm_execute"
            or command == "execute"
        ):

            execution = result.get("execution")

            if not self._valid_execution(execution):
                return self._invalid(
                    "INVALID_EXECUTION_RESULT",
                    execution=execution
                )

            if execution["error"]:
                return {
                    "error": True,
                    "message": self._safe_message(
                        execution,
                        "EXECUTION_RETURNED_ERROR"
                    ),
                    "execution": execution
                }

            return {
                "error": False,
                "message": execution["message"],
                "action": execution.get("action"),
                "next_action": execution.get("next_action"),
                "completed": execution.get("completed", False),
                "progress": execution.get(
                    "progress",
                    {
                        "done": 0,
                        "total": 0
                    }
                )
            }

        if command == "cancel_task":

            message = result.get("message")

            if not self._valid_message(message):
                return self._invalid()

            return {
                "error": False,
                "message": message,
                "cancelled_task": result.get("cancelled_task")
            }

        if command == "pause_task":

            message = result.get("message")

            if not self._valid_message(message):
                return self._invalid()

            return {
                "error": False,
                "message": message,
                "status": result.get("status")
            }

        if command == "resume_task":

            message = result.get("message")

            if not self._valid_message(message):
                return self._invalid()

            return {
                "error": False,
                "message": message,
                "status": result.get("status")
            }

        if command == "skip_action":

            message = result.get("message")
            action = result.get("action")
            next_action = result.get("next_action")

            if (
                not self._valid_message(message)
                or not self._valid_optional_dict(action)
                or not self._valid_optional_dict(next_action)
            ):
                return self._invalid()

            return {
                "error": False,
                "message": message,
                "action": action,
                "next_action": next_action
            }

        if command == "task_status":

            task_status = result.get("task_status")

            if not self._valid_nested_result(task_status):
                return self._invalid(
                    "INVALID_TASK_RESULT"
                )

            return {
                "error": False,
                "message": "Статус задачи",
                "task_status": task_status
            }

        if command == "task_history":

            task_history = result.get("task_history")

            if not self._valid_nested_result(task_history):
                return self._invalid(
                    "INVALID_TASK_RESULT"
                )

            return {
                "error": False,
                "message": "История задачи",
                "task_history": task_history
            }

        if command == "task_details":

            task_details = result.get("task_details")

            if not self._valid_nested_result(task_details):
                return self._invalid(
                    "INVALID_TASK_RESULT"
                )

            return {
                "error": False,
                "message": "Детали задачи",
                "task_details": task_details
            }

        if command == "task_next":

            next_data = result.get("task_next")

            if not self._valid_nested_result(next_data):
                return self._invalid(
                    "INVALID_TASK_NEXT_RESULT"
                )

            return {
                "error": False,
                "message": "Следующий шаг",
                "next_action": next_data.get("action")
            }

        if command == "continue":

            next_action = result.get("next_action")
            continued_task = result.get(
                "continued_task",
                ""
            )

            if (
                not self._valid_optional_dict(next_action)
                or not isinstance(continued_task, str)
            ):
                return self._invalid()

            return {
                "error": False,
                "message": "Продолжаем работу",
                "task": continued_task,
                "next_step": next_action
            }

        plan = result.get("plan")
        count = result.get("count")

        if (
            not isinstance(plan, list)
            or not all(
                isinstance(item, dict)
                for item in plan
            )
            or isinstance(count, bool)
            or not isinstance(count, int)
            or count < 0
            or count != len(plan)
        ):
            return self._invalid(
                "INVALID_BUSINESS_PLAN_RESULT"
            )

        return {
            "error": False,
            "message": "Бизнес-план создан",
            "actions": plan,
            "count": count
        }


    @staticmethod
    def _valid_result(result):

        return (
            isinstance(result, dict)
            and type(result.get("error")) is bool
        )


    @staticmethod
    def _valid_message(message):

        return (
            isinstance(message, str)
            and bool(message.strip())
        )


    @classmethod
    def _valid_execution(cls, execution):

        if (
            not isinstance(execution, dict)
            or type(execution.get("error")) is not bool
        ):
            return False

        if execution["error"]:
            return True

        if not cls._valid_message(
            execution.get("message")
        ):
            return False

        return (
            cls._valid_optional_dict(
                execution.get("action")
            )
            and cls._valid_optional_dict(
                execution.get("next_action")
            )
            and isinstance(
                execution.get(
                    "completed",
                    False
                ),
                bool
            )
            and cls._valid_progress(
                execution.get(
                    "progress",
                    {
                        "done": 0,
                        "total": 0
                    }
                )
            )
        )


    @staticmethod
    def _valid_progress(progress):

        if not isinstance(progress, dict):
            return False

        done = progress.get("done")
        total = progress.get("total")

        return (
            not isinstance(done, bool)
            and isinstance(done, int)
            and done >= 0
            and not isinstance(total, bool)
            and isinstance(total, int)
            and total >= 0
            and done <= total
        )


    @staticmethod
    def _valid_optional_dict(value):

        return (
            value is None
            or isinstance(value, dict)
        )


    @classmethod
    def _valid_nested_result(cls, value):

        return (
            cls._valid_result(value)
            and value["error"] is False
        )


    @classmethod
    def _safe_message(
        cls,
        result,
        fallback
    ):

        message = result.get("message")

        if cls._valid_message(message):
            return message

        return fallback


    @staticmethod
    def _invalid(
        message="INVALID_BUSINESS_FLOW_RESULT",
        **extra
    ):

        result = {
            "error": True,
            "message": message
        }

        result.update(extra)

        return result
