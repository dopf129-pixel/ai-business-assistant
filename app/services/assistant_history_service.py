class AssistantHistoryService:


    def __init__(
        self,
        storage_service
    ):

        self.storage_service = (
            storage_service
        )


    def add(
        self,
        user_id,
        event
    ):

        return (
            self.storage_service
            .add_history(
                user_id,
                event
            )
        )


    def get(
        self,
        user_id
    ):

        return (
            self.storage_service
            .get_history(
                user_id
            )
        )


    def clear(
        self,
        user_id
    ):

        try:

            user_result = (
                self.storage_service
                .get_user(
                    user_id
                )
            )

        except Exception:

            return self._failure(
                "ASSISTANT_HISTORY_USER_READ_FAILED"
            )

        if (
            not isinstance(
                user_result,
                dict
            )
            or type(
                user_result.get(
                    "error"
                )
            )
            is not bool
        ):

            return self._failure(
                "INVALID_ASSISTANT_HISTORY_USER_RESULT"
            )

        if user_result.get(
            "error"
        ) is True:

            return user_result

        user = user_result.get(
            "user"
        )

        if not isinstance(
            user,
            dict
        ):

            return self._failure(
                "INVALID_ASSISTANT_HISTORY_USER_RESULT"
            )

        history = user.get(
            "history"
        )

        if not isinstance(
            history,
            list
        ):

            return self._failure(
                "INVALID_ASSISTANT_HISTORY_DATA"
            )

        previous_history = history

        user["history"] = []

        try:

            save_result = (
                self.storage_service
                .save()
            )

        except Exception:

            return {
                "error": True,
                "message":
                    "ASSISTANT_HISTORY_SAVE_FAILED",
                "cleared": False,
                "persistence_state_unknown":
                    True
            }

        if (
            not isinstance(
                save_result,
                dict
            )
            or type(
                save_result.get(
                    "error"
                )
            )
            is not bool
        ):

            return {
                "error": True,
                "message":
                    "INVALID_ASSISTANT_HISTORY_SAVE_RESULT",
                "cleared": False,
                "persistence_state_unknown":
                    True
            }

        if save_result.get(
            "error"
        ) is True:

            user["history"] = (
                previous_history
            )

            failure = dict(
                save_result
            )
            failure[
                "cleared"
            ] = False
            failure[
                "rolled_back"
            ] = True

            return failure

        if save_result.get(
            "saved"
        ) is not True:

            return {
                "error": True,
                "message":
                    "INVALID_ASSISTANT_HISTORY_SAVE_RESULT",
                "cleared": False,
                "persistence_state_unknown":
                    True
            }

        result = {
            "error": False,
            "cleared": True
        }

        durability_warning = (
            save_result.get(
                "durability_warning"
            )
        )

        if durability_warning is not None:

            result[
                "durability_warning"
            ] = durability_warning

        return result


    @staticmethod
    def _failure(
        code
    ):

        return {
            "error": True,
            "message": code,
            "cleared": False
        }
