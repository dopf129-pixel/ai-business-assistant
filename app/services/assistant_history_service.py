class AssistantHistoryService:


    def __init__(
        self
    ):

        self.history = {}



    def add(
        self,
        user_id,
        action
    ):


        if user_id not in self.history:

            self.history[user_id] = []


        self.history[user_id].append(
            action
        )


        return {
            "error": False,
            "saved": True
        }



    def get(
        self,
        user_id
    ):


        return {
            "error": False,
            "history":
                self.history.get(
                    user_id,
                    []
                )
        }