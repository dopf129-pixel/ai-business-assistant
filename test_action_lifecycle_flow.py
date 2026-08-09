import sys
import unittest
from pathlib import Path
import tempfile


sys.path.insert(
    0,
    str(Path(__file__).parent / "app")
)


from services.action_service import (
    ActionService
)

from services.action_history_service import (
    ActionHistoryService
)

from services.action_storage_service import (
    ActionStorageService
)

from services.action_status_service import (
    ActionStatusService
)

from services.action_workflow_service import (
    ActionWorkflowService
)


class TestActionLifecycleFlow(
    unittest.TestCase
):


    def test_full_action_lifecycle(
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


            action_service = (
                ActionService()
            )


            action_result = (
                action_service.build(
                    [
                        {
                            "title": "Проверить товары роста"
                        }
                    ]
                )
            )


            self.assertFalse(
                action_result["error"]
            )


            action = (
                action_result["actions"][0]
            )


            history.save_action(
                action
            )


            workflow = (
                ActionWorkflowService(
                    history_service=history,
                    status_service=ActionStatusService()
                )
            )


            result = (
                workflow.complete(
                    0
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


            saved = (
                restored.list_actions()
            )


            self.assertEqual(
                saved["count"],
                1
            )


            self.assertEqual(
                saved["actions"][0]["status"],
                "DONE"
            )


if __name__ == "__main__":
    unittest.main()