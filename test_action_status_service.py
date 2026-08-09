import sys
import unittest
from pathlib import Path


sys.path.insert(
    0,
    str(Path(__file__).parent / "app")
)


from services.action_status_service import (
    ActionStatusService
)


class TestActionStatusService(
    unittest.TestCase
):


    def setUp(
        self
    ):

        self.service = (
            ActionStatusService()
        )


    def test_update_status(
        self
    ):

        action = {
            "title": "Проверить товары",
            "status": "NEW"
        }


        result = (
            self.service
            .update_status(
                action,
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

        action = {
            "title": "Проверить рекламу",
            "status": "IN_PROGRESS"
        }


        result = (
            self.service
            .complete(
                action
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

        action = {
            "title": "Тест",
            "status": "NEW"
        }


        result = (
            self.service
            .update_status(
                action,
                "UNKNOWN"
            )
        )


        self.assertTrue(
            result["error"]
        )


if __name__ == "__main__":
    unittest.main()