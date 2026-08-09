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


        result = (
            self.profile_service
            .get_user(
                user_id
            )
        )


        user = (
            result["user"]
        )


        if "context" not in user:

            user["context"] = {
                "last_message": "",
                "last_action": "",
                "current_task": ""
            }


            self.profile_service.save()



        return {
            "error": False,
            "user_id": user_id,
            "context": user["context"],
            "memory": user.get(
                "memory",
                {}
            )
        }



    def update(
        self,
        user_id,
        key,
        value
    ):


        result = (
            self.profile_service
            .get_user(
                user_id
            )
        )


        user = (
            result["user"]
        )


        if "context" not in user:

            user["context"] = {}



        user["context"][key] = value


        self.profile_service.save()


        return {
            "error": False,
            "updated": True
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