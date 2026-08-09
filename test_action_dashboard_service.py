import sys
import unittest
from pathlib import Path


sys.path.insert(
    0,
    str(Path(__file__).parent / "app")
)


from services.action_dashboard_service import (
    ActionDashboardService
)


class FakeQueryService:

    def get_active(
        self,
        actions
    ):

        result = [
            action
            for action in actions
            if action["status"] != "DONE"
        ]

        return {
            "error": False,
            "actions": result,
            "count": len(result)
        }


    def filter_by_status(
        self,
        actions,
        status
    ):

        result = [
            action
            for action in actions
            if action["status"] == status
        ]

        return {
            "error": False,
            "actions": result,
            "count": len(result)
        }



class TestActionDashboardService(
    unittest.TestCase
):


    def setUp(
        self
    ):

        self.service = (
            ActionDashboardService(
                query_service=(
                    FakeQueryService()
                )
            )
        )


    def test_build_dashboard(
        self
    ):

        actions = [
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


        result = (
            self.service
            .build(
                actions
            )
        )


        self.assertFalse(
            result["error"]
        )


        self.assertEqual(
            result["total"],
            3
        )


        self.assertEqual(
            result["active"],
            2
        )


        self.assertEqual(
            result["completed"],
            1
        )


        self.assertEqual(
            len(
                result["actions"]
            ),
            3
        )


if __name__ == "__main__":
    unittest.main()