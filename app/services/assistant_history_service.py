import json
import os



class AssistantHistoryService:


    def __init__(
        self,
        file_path="data/history.json"
    ):

        self.file_path = (
            file_path
        )


        self.history = {}


        self.load()



    def load(
        self
    ):


        if not os.path.exists(
            self.file_path
        ):

            self.history = {}

            return



        try:

            with open(
                self.file_path,
                "r",
                encoding="utf-8"
            ) as file:

                self.history = (
                    json.load(
                        file
                    )
                )


        except Exception:

            self.history = {}



    def save(
        self
    ):


        folder = (
            os.path.dirname(
                self.file_path
            )
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
                self.history,
                file,
                ensure_ascii=False,
                indent=4
            )



    def add(
        self,
        user_id,
        action
    ):


        user_id = str(
            user_id
        )


        if user_id not in self.history:

            self.history[user_id] = []



        self.history[user_id].append(
            action
        )


        self.save()



        return {
            "error": False,
            "saved": True
        }



    def get(
        self,
        user_id
    ):


        user_id = str(
            user_id
        )


        return {
            "error": False,
            "history": self.history.get(
                user_id,
                []
            )
        }



    def clear(
        self,
        user_id
    ):


        user_id = str(
            user_id
        )


        if user_id in self.history:

            del self.history[user_id]


            self.save()



        return {
            "error": False,
            "cleared": True
        }