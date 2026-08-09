class ConversationHistoryService:


    def __init__(
        self,
        storage_service=None
    ):

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



    def add_message(
        self,
        role,
        message
    ):

        self.history.append(
            {
                "role": role,
                "message": message
            }
        )


        if self.storage_service:

            self.storage_service.save(
                self.history
            )


        return {
            "error": False,
            "saved": True,
            "count": len(
                self.history
            )
        }



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



    def clear(
        self
    ):

        self.history = []


        if self.storage_service:

            self.storage_service.save(
                self.history
            )


        return {
            "error": False,
            "cleared": True
        }