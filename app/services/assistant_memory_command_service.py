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
        text
    ):


        parts = (
            text.split()
        )


        if len(parts) >= 3:

            if parts[0].lower() == "запомни":

                key = parts[1]

                value = (
                    " ".join(
                        parts[2:]
                    )
                )


                return (
                    self.memory_service
                    .remember(
                        key,
                        value
                    )
                )


        if text.lower() == "кто я":

            return (
                self.memory_service
                .get(
                    "имя"
                )
            )


        return {
            "error": True,
            "message": "Команда памяти не распознана"
        }