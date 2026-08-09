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

from services.action_query_service import (
    ActionQueryService
)

from services.action_dashboard_service import (
    ActionDashboardService
)



class TestActionDashboardFlow(
    unittest.TestCase
):


    def test_full_dashboard_flow(
        self
    ):

        history = (
            ActionHistoryService()
        )


        history.save_action(
            {
                "title": "Проверить товары",
                "status": "NEW"
            }
        )


        history.save_action(
            {
                "title": "Проверить рекламу",
                "status": "IN_PROGRESS"
            }
        )


        history.save_action(
            {
                "title": "Закрытый отчёт",
                "status": "DONE"
            }
        )


        stored = (
            history.list_actions()
        )


        dashboard = (
            ActionDashboardService(
                query_service=(
                    ActionQueryService()
                )
            )
        )


        result = (
            dashboard.build(
                stored["actions"]
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


if __name__ == "__main__":
    unittest.main()