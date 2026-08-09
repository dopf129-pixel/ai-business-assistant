class AssistantUserContextService:


    def __init__(
        self,
        profile_service
    ):

        self.profile_service = (
            profile_service
        )



    def get_context(
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
            "user_id": user_id,
            "memory": (
                user["user"]["memory"]
            )
        }



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