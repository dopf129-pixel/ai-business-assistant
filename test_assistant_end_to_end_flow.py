import sys
import unittest
from pathlib import Path


sys.path.insert(
    0,
    str(Path(__file__).parent / "app")
)


from services.assistant_orchestrator_service import (
    AssistantOrchestratorService
)


class FakeReportService:

    def build(
        self,
        period_code,
        date_to,
        products
    ):

        return {
            "error": False,
            "period": period_code,
            "date": date_to,
            "products": products
        }



class FakeActionDashboardService:

    def build(
        self,
        actions
    ):

        return {
            "error": False,
            "total": len(actions),
            "active": 2,
            "completed": 1,
            "actions": actions
        }



class FakeResponseService:

    def build(
        self,
        report,
        dashboard
    ):

        return {
            "error": False,
            "report": report,
            "dashboard": dashboard,
            "message": "Готово"
        }



class TestAssistantEndToEndFlow(
    unittest.TestCase
):


    def test_full_assistant_flow(
        self
    ):

        assistant = (
            AssistantOrchestratorService(
                report_service=(
                    FakeReportService()
                ),
                action_dashboard_service=(
                    FakeActionDashboardService()
                ),
                response_service=(
                    FakeResponseService()
                )
            )
        )


        result = (
            assistant.build_response(
                period_code="28D",
                date_to="2026-08-09",
                products=[
                    {
                        "name": "Product A"
                    }
                ],
                actions=[
                    {
                        "title": "Проверить товар",
                        "status": "NEW"
                    },
                    {
                        "title": "Проверить рекламу",
                        "status": "IN_PROGRESS"
                    }
                ]
            )
        )


        self.assertFalse(
            result["error"]
        )


        self.assertEqual(
            result["report"]["period"],
            "28D"
        )


        self.assertEqual(
            result["dashboard"]["active"],
            2
        )


        self.assertEqual(
            result["message"],
            "Готово"
        )


if __name__ == "__main__":
    unittest.main()