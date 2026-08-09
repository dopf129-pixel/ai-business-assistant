class AssistantSessionService:


    def __init__(
        self,
        assistant,
        storage_service=None
    ):

        self.assistant = (
            assistant
        )

        self.storage_service = (
            storage_service
        )


        if self.storage_service:

            self.history = (
                self.storage_service
                .load()
            )

        else:

            self.history = []



    def ask(
        self,
        text
    ):

        result = (
            self.assistant
            .ask(
                text
            )
        )


        self.history.append(
            {
                "user": text,
                "assistant": result
            }
        )


        if self.storage_service:

            self.storage_service.save(
                self.history
            )


        return result



    def get_history(
        self
    ):

        return {
            "error": False,
            "history": self.history,
            "count": len(
                self.history
            )
        }