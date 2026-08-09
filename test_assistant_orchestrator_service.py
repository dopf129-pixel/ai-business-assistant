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
            "active": 1,
            "completed": 0,
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
            "actions": dashboard
        }



class TestAssistantOrchestratorService(
    unittest.TestCase
):


    def setUp(
        self
    ):

        self.service = (
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


    def test_build_response(
        self
    ):

        result = (
            self.service
            .build_response(
                period_code="28D",
                date_to="2026-08-09",
                products=[
                    "Product A"
                ],
                actions=[
                    {
                        "title": "Проверить товар",
                        "status": "NEW"
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
            result["actions"]["total"],
            1
        )


    def test_report_error(
        self
    ):

        class ErrorReportService:

            def build(
                self,
                **kwargs
            ):

                return {
                    "error": True,
                    "message": "Ошибка отчёта"
                }


        service = (
            AssistantOrchestratorService(
                report_service=(
                    ErrorReportService()
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
            service.build_response(
                "28D",
                "2026-08-09",
                [],
                []
            )
        )


        self.assertTrue(
            result["error"]
        )


if __name__ == "__main__":
    unittest.main()