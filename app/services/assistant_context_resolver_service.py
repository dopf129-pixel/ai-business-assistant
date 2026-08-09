class AssistantContextResolverService:


    def __init__(
        self,
        memory_service
    ):

        self.memory_service = (
            memory_service
        )



    def resolve(
        self,
        text
    ):

        text = (
            text.lower()
            .strip()
        )


        if (
            "дней" in text
            or
            "день" in text
            or
            "месяц" in text
        ):

            last_command = (
                self.memory_service
                .get(
                    "last_command"
                )
            )


            if not last_command["error"]:

                return {
                    "error": False,
                    "command": (
                        last_command["value"]
                    ),
                    "period": text
                }


        return {
            "error": True,
            "message": "Контекст не найден"
        }