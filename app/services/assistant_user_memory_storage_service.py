import json

from services.tenant_storage import ensure_storage_parent, tenant_storage_path


class AssistantUserMemoryStorageService:


    def __init__(
        self,
        file_path=None
    ):

        self._file_path = file_path

    @property
    def file_path(self):
        return (
            self._file_path
            if self._file_path is not None
            else tenant_storage_path("assistant_user_memory.json")
        )


    def save(
        self,
        memory
    ):

        ensure_storage_parent(self.file_path)

        with open(
            self.file_path,
            "w",
            encoding="utf-8"
        ) as file:

            json.dump(
                memory,
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

            return {}