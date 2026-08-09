import json
from pathlib import Path


class ConversationHistoryStorageService:


    def __init__(
        self,
        file_path="conversation_history.json"
    ):

        self.file_path = Path(
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
                indent=4
            )


        return True



    def load(
        self
    ):

        if not self.file_path.exists():

            return []


        with open(
            self.file_path,
            "r",
            encoding="utf-8"
        ) as file:

            return json.load(
                file
            )