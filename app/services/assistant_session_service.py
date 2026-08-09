class AssistantSessionService:


    def __init__(
        self,
        assistant
    ):

        self.assistant = assistant
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