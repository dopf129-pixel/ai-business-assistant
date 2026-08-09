import json


class AssistantSessionStorageService:


    def __init__(
        self,
        file_path="assistant_session.json"
    ):

        self.file_path = (
            file_path
        )


    def save(
        self,
        history
    ):

        with open(
            self.file_path,
            "w",
            encoding="utf-8"
        ) as file:

            json.dump(
                history,
                file,
                ensure_ascii=False,
                indent=2
            )


        return {
            "error": False,
            "saved": True
        }



    def load(
        self
    ):

        try:

            with open(
                self.file_path,
                "r",
                encoding="utf-8"
            ) as file:

                return json.load(
                    file
                )


        except FileNotFoundError:

            return []