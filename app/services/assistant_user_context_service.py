class AssistantUserContextService:


    def __init__(
        self,
        profile_service
    ):

        self.profile_service = (
            profile_service
        )


    def get_context(
        self,
        user_id
    ):

        result = (
            self.profile_service
            .get_user(
                user_id
            )
        )

        user = self._user_from_result(
            result
        )

        if user is None:

            return self._invalid_result(
                "INVALID_USER_PROFILE_RESULT"
            )

        context = user.get(
            "context"
        )

        if context is None:

            user["context"] = {
                "last_message": "",
                "last_action": "",
                "current_task": ""
            }

            save_result = (
                self.profile_service
                .save()
            )

            if not self._valid_save_result(
                save_result
            ):

                if self._explicit_save_failure(
                    save_result
                ):
                    user.pop(
                        "context",
                        None
                    )

                return self._invalid_result(
                    "INVALID_USER_CONTEXT_SAVE_RESULT"
                )

            context = user["context"]

        elif not isinstance(
            context,
            dict
        ):

            return self._invalid_result(
                "INVALID_USER_CONTEXT_DATA"
            )

        memory = user.get(
            "memory",
            {}
        )

        if not isinstance(
            memory,
            dict
        ):

            return self._invalid_result(
                "INVALID_USER_MEMORY_DATA"
            )

        return {
            "error": False,
            "user_id": user_id,
            "context": context,
            "memory": memory
        }


    def update(
        self,
        user_id,
        key,
        value
    ):

        result = (
            self.profile_service
            .get_user(
                user_id
            )
        )

        user = self._user_from_result(
            result
        )

        if user is None:

            return self._invalid_result(
                "INVALID_USER_PROFILE_RESULT"
            )

        context = user.get(
            "context"
        )
        context_created = (
            context is None
        )

        if context_created:

            user["context"] = {}
            context = user["context"]

        elif not isinstance(
            context,
            dict
        ):

            return self._invalid_result(
                "INVALID_USER_CONTEXT_DATA"
            )

        existed = key in context
        previous = context.get(
            key
        )

        context[key] = value

        save_result = (
            self.profile_service
            .save()
        )

        if not self._valid_save_result(
            save_result
        ):

            if self._explicit_save_failure(
                save_result
            ):

                if context_created:
                    user.pop(
                        "context",
                        None
                    )
                elif existed:
                    context[key] = previous
                else:
                    context.pop(
                        key,
                        None
                    )

            return self._invalid_result(
                "INVALID_USER_CONTEXT_SAVE_RESULT"
            )

        return {
            "error": False,
            "updated": True
        }


    def remember(
        self,
        user_id,
        key,
        value
    ):

        result = (
            self.profile_service
            .save_memory(
                user_id,
                key,
                value
            )
        )

        if (
            not isinstance(
                result,
                dict
            )
            or type(
                result.get(
                    "error"
                )
            )
            is not bool
        ):

            return self._invalid_result(
                "INVALID_USER_MEMORY_SAVE_RESULT"
            )

        return result


    @staticmethod
    def _user_from_result(
        result
    ):

        if (
            not isinstance(
                result,
                dict
            )
            or result.get(
                "error"
            )
            is not False
        ):
            return None

        user = result.get(
            "user"
        )

        if not isinstance(
            user,
            dict
        ):
            return None

        return user


    @staticmethod
    def _valid_save_result(
        result
    ):

        if result is None:
            return True

        return (
            isinstance(
                result,
                dict
            )
            and type(
                result.get(
                    "error"
                )
            )
            is bool
            and result.get(
                "error"
            )
            is False
        )


    @staticmethod
    def _explicit_save_failure(
        result
    ):

        return (
            isinstance(
                result,
                dict
            )
            and type(
                result.get(
                    "error"
                )
            )
            is bool
            and result.get(
                "error"
            )
            is True
        )


    @staticmethod
    def _invalid_result(
        code
    ):

        return {
            "error": True,
            "message": code
        }
