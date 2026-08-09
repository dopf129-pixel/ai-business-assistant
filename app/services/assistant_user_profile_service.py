import json
import os



class AssistantUserProfileService:


    def __init__(
        self,
        file_path="data/profiles.json"
    ):

        self.file_path = file_path

        self.users = {}

        self.load()



    def load(
        self
    ):


        if not os.path.exists(
            self.file_path
        ):

            return


        try:

            with open(
                self.file_path,
                "r",
                encoding="utf-8"
            ) as file:

                self.users = json.load(
                    file
                )


        except Exception:

            self.users = {}



    def save(
        self
    ):


        folder = os.path.dirname(
            self.file_path
        )


        if folder and not os.path.exists(
            folder
        ):

            os.makedirs(
                folder
            )


        with open(
            self.file_path,
            "w",
            encoding="utf-8"
        ) as file:

            json.dump(
                self.users,
                file,
                ensure_ascii=False,
                indent=4
            )



    def create_user(
        self,
        user_id
    ):

        user_id = str(
            user_id
        )


        if user_id not in self.users:

            self.users[user_id] = {
                "user_id": user_id,
                "memory": {}
            }

            self.save()


        return {
            "error": False,
            "user": self.users[user_id]
        }



    def get_user(
        self,
        user_id
    ):

        user_id = str(
            user_id
        )


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


        self.save()


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