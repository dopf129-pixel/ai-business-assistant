import sys
import unittest
from pathlib import Path


sys.path.insert(
    0,
    str(Path(__file__).parent / "app")
)


from services.action_query_service import (
    ActionQueryService
)


class TestActionQueryService(
    unittest.TestCase
):


    def setUp(
        self
    ):

        self.service = (
            ActionQueryService()
        )


        self.actions = [
            {
                "title": "Товары",
                "status": "NEW"
            },
            {
                "title": "Реклама",
                "status": "IN_PROGRESS"
            },
            {
                "title": "Отчёт",
                "status": "DONE"
            }
        ]


    def test_filter_by_status(
        self
    ):

        result = (
            self.service
            .filter_by_status(
                self.actions,
                "NEW"
            )
        )


        self.assertFalse(
            result["error"]
        )


        self.assertEqual(
            result["count"],
            1
        )


        self.assertEqual(
            result["actions"][0]["title"],
            "Товары"
        )


    def test_filter_done_actions(
        self
    ):

        result = (
            self.service
            .filter_by_status(
                self.actions,
                "DONE"
            )
        )


        self.assertEqual(
            result["count"],
            1
        )


        self.assertEqual(
            result["actions"][0]["title"],
            "Отчёт"
        )


    def test_get_active_actions(
        self
    ):

        result = (
            self.service
            .get_active(
                self.actions
            )
        )


        self.assertFalse(
            result["error"]
        )


        self.assertEqual(
            result["count"],
            2
        )


        titles = [
            item["title"]
            for item
            in result["actions"]
        ]


        self.assertNotIn(
            "Отчёт",
            titles
        )


if __name__ == "__main__":
    unittest.main()