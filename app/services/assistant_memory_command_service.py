class AssistantMemoryCommandService:


    def __init__(
        self,
        memory_service
    ):

        self.memory_service = (
            memory_service
        )


    def handle(
        self,
        user_id,
        text
    ):

        text = (
            text.strip()
        )

        prefix = (
            "запомни "
        )

        if text.lower().startswith(
            prefix
        ):

            data = (
                text[len(prefix):]
            )

            parsed = None

            if "=" in data:

                parsed = (
                    data.split(
                        "=",
                        1
                    )
                )

            elif " " in data:

                parsed = (
                    data.split(
                        " ",
                        1
                    )
                )

            if parsed is not None:

                key, value = parsed

                try:

                    result = (
                        self.memory_service
                        .remember(
                            user_id,
                            key.strip(),
                            value.strip()
                        )
                    )

                except Exception:

                    return {
                        "error": True,
                        "handled": True,
                        "message":
                            "MEMORY_COMMAND_SAVE_FAILED"
                    }

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

                    return {
                        "error": True,
                        "handled": True,
                        "message":
                            "INVALID_MEMORY_COMMAND_RESULT"
                    }

                response = dict(
                    result
                )

                response[
                    "handled"
                ] = True

                return response

        return {
            "error": False,
            "handled": False
        }
