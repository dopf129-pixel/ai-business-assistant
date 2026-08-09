class AssistantTelegramMemoryService:


    def __init__(
        self,
        profiles,
        file_path="data/profiles.json"
    ):

        self.profiles = profiles

        self.file_path = file_path



    def remember(
        self,
        user_id,
        key,
        value
    ):


        result = (
            self.profiles
            .save_memory(
                user_id,
                key,
                value
            )
        )


        return result



    def get_memory(
        self,
        user_id
    ):


        user = (
            self.profiles
            .get_user(
                user_id
            )
        )


        return {
            "error": False,
            "memory":
                user["user"]
                .get(
                    "memory",
                    {}
                )
        }



    def clear(
        self,
        user_id
    ):


        user = (
            self.profiles
            .get_user(
                user_id
            )
        )


        user["user"]["memory"] = {}


        return {
            "error": False,
            "cleared": True
        }