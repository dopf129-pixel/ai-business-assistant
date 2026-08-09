import sys
import unittest
from pathlib import Path
import tempfile


sys.path.insert(
    0,
    str(Path(__file__).parent / "app")
)


from services.action_storage_service import (
    ActionStorageService
)


class TestActionStorageService(
    unittest.TestCase
):


    def test_save_and_load_actions(
        self
    ):

        with tempfile.TemporaryDirectory() as folder:

            file_path = (
                Path(folder)
                /
                "actions.json"
            )


            storage = (
                ActionStorageService(
                    file_path=file_path
                )
            )


            actions = [
                {
                    "title": "Проверить товары",
                    "status": "NEW"
                },
                {
                    "title": "Проверить рекламу",
                    "status": "NEW"
                }
            ]


            result = (
                storage.save(
                    actions
                )
            )


            self.assertTrue(
                result
            )


            loaded = (
                storage.load()
            )


            self.assertEqual(
                loaded,
                actions
            )


    def test_load_empty_storage(
        self
    ):

        with tempfile.TemporaryDirectory() as folder:

            file_path = (
                Path(folder)
                /
                "actions.json"
            )


            storage = (
                ActionStorageService(
                    file_path=file_path
                )
            )


            result = (
                storage.load()
            )


            self.assertEqual(
                result,
                []
            )


if __name__ == "__main__":
    unittest.main()