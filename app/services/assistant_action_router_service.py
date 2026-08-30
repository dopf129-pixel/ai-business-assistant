class AssistantActionRouterService:


    def __init__(
        self,
        executors=None
    ):

        self.executors = (
            executors
            or {}
        )



    def execute(
        self,
        action
    ):


        action_type = (
            action.get(
                "type"
            )
        )


        executor = (
            self.executors
            .get(
                action_type
            )
        )


        if not executor:


            return {

                "error": True,

                "message":
                    f"Исполнитель для типа {action_type} не найден"

            }


        return (
            executor.execute(
                action
            )
        )



    def run(
        self,
        action
    ):

        result = (
            self.execute(
                action
            )
        )


        if not isinstance(
            result,
            dict
        ):

            raise RuntimeError(
                "INVALID_EXECUTOR_RESULT"
            )


        error = result.get(
            "error"
        )


        if error is True:

            message = result.get(
                "message"
            )

            if (
                not isinstance(
                    message,
                    str
                )
                or not message.strip()
            ):

                message = (
                    "EXECUTOR_RETURNED_ERROR"
                )

            raise RuntimeError(
                message
            )


        if error not in (
            None,
            False
        ):

            raise RuntimeError(
                "INVALID_EXECUTOR_RESULT"
            )


        return result
