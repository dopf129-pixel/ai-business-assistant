import sys
import unittest
from pathlib import Path
import tempfile


sys.path.insert(
    0,
    str(Path(__file__).parent / "app")
)


from services.assistant_memory_storage_service import (
    AssistantMemoryStorageService
)


class TestAssistantMemoryStorageService(
    unittest.TestCase
):


    def test_save_and_load_context(
        self
    ):

        with tempfile.TemporaryDirectory() as folder:

            file_path = (
                Path(folder)
                /
                "memory.json"
            )


            storage = (
                AssistantMemoryStorageService(
                    file_path=file_path
                )
            )


            context = {
                "last_command": "report",
                "period": "30D"
            }


            result = (
                storage.save(
                    context
                )
            )


            self.assertTrue(
                result
            )


            new_storage = (
                AssistantMemoryStorageService(
                    file_path=file_path
                )
            )


            loaded = (
                new_storage.load()
            )


            self.assertEqual(
                loaded["last_command"],
                "report"
            )


            self.assertEqual(
                loaded["period"],
                "30D"
            )


    def test_load_empty_storage(
        self
    ):

        with tempfile.TemporaryDirectory() as folder:

            file_path = (
                Path(folder)
                /
                "missing.json"
            )


            storage = (
                AssistantMemoryStorageService(
                    file_path=file_path
                )
            )


            result = (
                storage.load()
            )


            self.assertEqual(
                result,
                {}
            )


if __name__ == "__main__":
    unittest.main()