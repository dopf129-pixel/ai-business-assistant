class AssistantTelegramMemoryService:


    def __init__(
        self,
        storage_service
    ):

        self.storage_service = (
            storage_service
        )


    def remember(
        self,
        user_id,
        key,
        value
    ):

        return (
            self.storage_service
            .save_memory(
                user_id,
                key,
                value
            )
        )


    def get_memory(
        self,
        user_id
    ):

        return (
            self.storage_service
            .get_memory(
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
                "TELEGRAM_MEMORY_USER_READ_FAILED"
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
                "INVALID_TELEGRAM_MEMORY_USER_RESULT"
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
                "INVALID_TELEGRAM_MEMORY_USER_RESULT"
            )

        memory = user.get(
            "memory"
        )

        if not isinstance(
            memory,
            dict
        ):

            return self._failure(
                "INVALID_TELEGRAM_MEMORY_DATA"
            )

        previous_memory = memory

        user["memory"] = {}

        try:

            save_result = (
                self.storage_service
                .save()
            )

        except Exception:

            return {
                "error": True,
                "message":
                    "TELEGRAM_MEMORY_SAVE_FAILED",
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
                    "INVALID_TELEGRAM_MEMORY_SAVE_RESULT",
                "cleared": False,
                "persistence_state_unknown":
                    True
            }

        if save_result.get(
            "error"
        ) is True:

            user["memory"] = (
                previous_memory
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
                    "INVALID_TELEGRAM_MEMORY_SAVE_RESULT",
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
