import json
from pathlib import Path

from services.tenant_storage import ensure_storage_parent, tenant_storage_path


class AssistantMemoryStorageService:


    def __init__(
        self,
        file_path=None
    ):

        self._file_path = file_path

    @property
    def file_path(self):
        return Path(
            self._file_path
            if self._file_path is not None
            else tenant_storage_path("assistant_memory.json")
        )


    def save(
        self,
        context
    ):

        ensure_storage_parent(self.file_path)

        with open(
            self.file_path,
            "w",
            encoding="utf-8"
        ) as file:

            json.dump(
                context,
                file,
                ensure_ascii=False,
                indent=4
            )


        return True


    def load(
        self
    ):

        if not self.file_path.exists():

            return {}


        with open(
            self.file_path,
            "r",
            encoding="utf-8"
        ) as file:

            return json.load(
                file
            )