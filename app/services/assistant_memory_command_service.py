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


            if "=" in data:

                key, value = (
                    data.split(
                        "=",
                        1
                    )
                )


                return (
                    self.memory_service
                    .remember(
                        user_id,
                        key.strip(),
                        value.strip()
                    )
                )


            if " " in data:

                key, value = (
                    data.split(
                        " ",
                        1
                    )
                )


                return (
                    self.memory_service
                    .remember(
                        user_id,
                        key.strip(),
                        value.strip()
                    )
                )


        return {
            "error": True,
            "message": "Команда памяти не распознана"
        }