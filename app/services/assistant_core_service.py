class AssistantCoreService:


    def __init__(
        self,
        orchestrator_service,
        memory_service=None,
        request_context_service=None,
        user_context_service=None,
        task_context_service=None
    ):

        self.orchestrator_service = (
            orchestrator_service
        )

        self.memory_service = (
            memory_service
        )

        self.request_context_service = (
            request_context_service
        )

        self.user_context_service = (
            user_context_service
        )

        self.task_context_service = (
            task_context_service
        )



    def ask(
        self,
        text,
        user_id=None
    ):


        context = None



        if (
            self.user_context_service
            and user_id is not None
        ):

            context = (
                self.user_context_service
                .get_context(
                    user_id
                )
            )

            if not self._valid_context_result(
                context
            ):

                return {
                    "error": True,
                    "message":
                        "INVALID_USER_CONTEXT_RESULT"
                }



        elif (
            self.request_context_service
            and user_id is not None
        ):

            context = (
                self.request_context_service
                .build(
                    user_id,
                    text
                )
            )



        result = (
            self.orchestrator_service
            .process(
                text,
                context,
                user_id
            )
        )


        if not self._valid_result(
            result
        ):

            result = {
                "error": True,
                "message":
                    "INVALID_ORCHESTRATOR_RESULT"
            }



        if (
            self.user_context_service
            and user_id is not None
        ):

            update_result = (
                self.user_context_service
                .update(
                    user_id,
                    "last_message",
                    text
                )
            )

            if not self._valid_update_result(
                update_result
            ):
                return self._context_failure(
                    result,
                    "INVALID_USER_CONTEXT_UPDATE_RESULT"
                )

            context = (
                self.user_context_service
                .get_context(
                    user_id
                )
            )

            if not self._valid_context_result(
                context
            ):
                return self._context_failure(
                    result,
                    "INVALID_USER_CONTEXT_REFRESH_RESULT"
                )



        if context:

            result["context"] = context



        return result

    @staticmethod
    def _valid_result(
        result
    ):

        return (
            isinstance(
                result,
                dict
            )
            and
            type(
                result.get(
                    "error"
                )
            )
            is bool
        )


    @staticmethod
    def _valid_context_result(
        result
    ):

        return (
            isinstance(
                result,
                dict
            )
            and result.get(
                "error"
            )
            is False
            and isinstance(
                result.get(
                    "context"
                ),
                dict
            )
            and isinstance(
                result.get(
                    "memory"
                ),
                dict
            )
        )


    @staticmethod
    def _valid_update_result(
        result
    ):

        return (
            isinstance(
                result,
                dict
            )
            and result.get(
                "error"
            )
            is False
            and result.get(
                "updated"
            )
            is True
        )


    @staticmethod
    def _context_failure(
        result,
        code
    ):

        if result.get(
            "error"
        ):
            return result

        failed = dict(
            result
        )

        failed[
            "context_persistence_error"
        ] = code

        return failed
