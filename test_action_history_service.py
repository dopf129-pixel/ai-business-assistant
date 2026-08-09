import sys
import unittest
from pathlib import Path


sys.path.insert(
    0,
    str(Path(__file__).parent / "app")
)


from services.action_history_service import (
    ActionHistoryService
)


class TestActionHistoryService(
    unittest.TestCase
):


    def setUp(
        self
    ):

        self.service = (
            ActionHistoryService()
        )


    def test_save_action(
        self
    ):

        result = (
            self.service
            .save_action(
                {
                    "title": "Проверить товары роста",
                    "status": "NEW"
                }
            )
        )


        self.assertFalse(
            result["error"]
        )


        self.assertTrue(
            result["saved"]
        )


        self.assertEqual(
            result["count"],
            1
        )


    def test_get_action(
        self
    ):

        action = {
            "title": "Проверить рекламу"
        }


        self.service.save_action(
            action
        )


        result = (
            self.service
            .get_action(
                0
            )
        )


        self.assertFalse(
            result["error"]
        )


        self.assertEqual(
            result["action"],
            action
        )


    def test_list_actions(
        self
    ):

        self.service.save_action(
            {
                "title": "Action 1"
            }
        )

        self.service.save_action(
            {
                "title": "Action 2"
            }
        )


        result = (
            self.service
            .list_actions()
        )


        self.assertEqual(
            result["count"],
            2
        )


        self.assertEqual(
            len(
                result["actions"]
            ),
            2
        )


    def test_missing_action(
        self
    ):

        result = (
            self.service
            .get_action(
                100
            )
        )


        self.assertTrue(
            result["error"]
        )


if __name__ == "__main__":
    unittest.main()