class AssistantHistoryService:


    def __init__(
        self,
        storage_service
    ):

        self.storage_service = (
            storage_service
        )



    def add(
        self,
        user_id,
        event
    ):


        return (
            self.storage_service
            .add_history(
                user_id,
                event
            )
        )



    def get(
        self,
        user_id
    ):


        return (
            self.storage_service
            .get_history(
                user_id
            )
        )



    def clear(
        self,
        user_id
    ):


        user = (
            self.storage_service
            .get_user(
                user_id
            )
        )


        user["history"] = {}


        self.storage_service.save()


        return {
            "error": False,
            "cleared": True
        }