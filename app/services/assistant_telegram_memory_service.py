class AssistantTelegramMemoryService:


    def __init__(
        self,
        profile_service
    ):

        self.profile_service = (
            profile_service
        )



    def remember(
        self,
        user_id,
        key,
        value
    ):

        return (
            self.profile_service
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

        user = (
            self.profile_service
            .get_user(
                user_id
            )
        )


        return {
            "error": False,

            "memory": (
                user["user"]["memory"]
            )
        }