class AssistantUserProfileService:


    def __init__(
        self
    ):

        self.users = {}



    def create_user(
        self,
        user_id
    ):

        if user_id not in self.users:

            self.users[user_id] = {
                "user_id": user_id,
                "memory": {}
            }


        return {
            "error": False,
            "user": self.users[user_id]
        }



    def get_user(
        self,
        user_id
    ):

        if user_id not in self.users:

            return self.create_user(
                user_id
            )


        return {
            "error": False,
            "user": self.users[user_id]
        }



    def save_memory(
        self,
        user_id,
        key,
        value
    ):

        user = (
            self.create_user(
                user_id
            )
        )


        user["user"]["memory"][key] = value


        return {
            "error": False,
            "saved": True
        }



    def get_memory(
        self,
        user_id,
        key
    ):

        user = (
            self.get_user(
                user_id
            )
        )


        memory = (
            user["user"]["memory"]
        )


        if key not in memory:

            return {
                "error": True,
                "message": "Память не найдена"
            }


        return {
            "error": False,
            "value": memory[key]
        }