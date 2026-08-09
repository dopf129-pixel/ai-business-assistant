import sys
import unittest
from pathlib import Path
import tempfile


sys.path.insert(
    0,
    str(Path(__file__).parent / "app")
)


from services.action_history_service import (
    ActionHistoryService
)

from services.action_storage_service import (
    ActionStorageService
)


class TestActionHistoryUpdate(
    unittest.TestCase
):


    def test_update_action_and_persist(
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


            history = (
                ActionHistoryService(
                    storage_service=storage
                )
            )


            history.save_action(
                {
                    "title": "Проверить товары",
                    "status": "NEW"
                }
            )


            result = (
                history.update_action(
                    0,
                    {
                        "title": "Проверить товары",
                        "status": "DONE"
                    }
                )
            )


            self.assertFalse(
                result["error"]
            )


            self.assertEqual(
                result["action"]["status"],
                "DONE"
            )


            restored = (
                ActionHistoryService(
                    storage_service=storage
                )
            )


            actions = (
                restored.list_actions()
            )


            self.assertEqual(
                actions["actions"][0]["status"],
                "DONE"
            )


    def test_update_missing_action(
        self
    ):

        history = (
            ActionHistoryService()
        )


        result = (
            history.update_action(
                10,
                {
                    "status": "DONE"
                }
            )
        )


        self.assertTrue(
            result["error"]
        )


if __name__ == "__main__":
    unittest.main()