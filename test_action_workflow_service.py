import sys
import unittest
from pathlib import Path


sys.path.insert(
    0,
    str(Path(__file__).parent / "app")
)


from services.action_workflow_service import (
    ActionWorkflowService
)

from services.action_status_service import (
    ActionStatusService
)


class FakeHistoryService:

    def __init__(
        self
    ):

        self.actions = [
            {
                "title": "Проверить товары",
                "status": "NEW"
            }
        ]


    def get_action(
        self,
        index
    ):

        if index >= len(
            self.actions
        ):

            return {
                "error": True
            }


        return {
            "error": False,
            "action": self.actions[index]
        }


    def update_action(
        self,
        index,
        action
    ):

        self.actions[index] = action

        return {
            "error": False,
            "action": action
        }



class TestActionWorkflowService(
    unittest.TestCase
):


    def setUp(
        self
    ):

        self.history = (
            FakeHistoryService()
        )


        self.service = (
            ActionWorkflowService(
                history_service=self.history,
                status_service=ActionStatusService()
            )
        )


    def test_update_status(
        self
    ):

        result = (
            self.service
            .update_status(
                0,
                "IN_PROGRESS"
            )
        )


        self.assertFalse(
            result["error"]
        )


        self.assertEqual(
            result["action"]["status"],
            "IN_PROGRESS"
        )


    def test_complete_action(
        self
    ):

        result = (
            self.service
            .complete(
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


    def test_invalid_status(
        self
    ):

        result = (
            self.service
            .update_status(
                0,
                "WRONG"
            )
        )


        self.assertTrue(
            result["error"]
        )


if __name__ == "__main__":
    unittest.main()