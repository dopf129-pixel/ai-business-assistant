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


class TestActionHistoryPersistence(
    unittest.TestCase
):


    def test_history_restores_actions_from_storage(
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


            new_history = (
                ActionHistoryService(
                    storage_service=storage
                )
            )


            result = (
                new_history
                .list_actions()
            )


            self.assertEqual(
                result["count"],
                1
            )


            self.assertEqual(
                result["actions"][0]["title"],
                "Проверить товары"
            )


if __name__ == "__main__":
    unittest.main()