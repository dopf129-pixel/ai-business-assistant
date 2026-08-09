class AssistantTelegramMemoryService:


    def __init__(
        self,
        storage_service
    ):

        self.storage_service = (
            storage_service
        )



    def remember(
        self,
        user_id,
        key,
        value
    ):

        return (
            self.storage_service
            .save_memory(
                user_id,
                key,
                value
            )
        )



    def get_memory(
        self,
        user_id
    ):


        return (
            self.storage_service
            .get_memory(
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


        user["memory"] = {}


        self.storage_service.save()


        return {
            "error": False,
            "cleared": True
        }