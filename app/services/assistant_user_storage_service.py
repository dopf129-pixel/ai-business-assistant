import json
import os



class AssistantUserStorageService:


    def __init__(
        self,
        file_path=None
    ):

        if file_path is None:

            file_path = os.path.join(
                os.getcwd(),
                "data",
                "users.json"
            )


        self.file_path = file_path

        self.users = {}

        self.load()



    def normalize_id(
        self,
        user_id
    ):

        return str(
            user_id
        )



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


        if folder and not os.path.exists(folder):

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

        user_id = self.normalize_id(
            user_id
        )


        if user_id not in self.users:

            self.users[user_id] = {
                "user_id": user_id,
                "memory": {},
                "history": []
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

        return (
            self.create_user(
                user_id
            )
        )



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
        user_id
    ):

        user = (
            self.create_user(
                user_id
            )
        )


        return {
            "error": False,
            "memory": user["user"]["memory"]
        }



    def add_history(
        self,
        user_id,
        event
    ):

        user = (
            self.create_user(
                user_id
            )
        )


        user["user"]["history"].append(
            event
        )


        self.save()


        return {
            "error": False,
            "saved": True
        }



    def get_history(
        self,
        user_id
    ):

        user = (
            self.create_user(
                user_id
            )
        )


        return {
            "error": False,
            "history": user["user"]["history"]
        }