import sys
import unittest
from pathlib import Path


sys.path.insert(
    0,
    str(Path(__file__).parent / "app")
)


from services.assistant_intent_service import (
    AssistantIntentService
)

from services.assistant_command_service import (
    AssistantCommandService
)


class FakeOrchestratorService:


    def build_response(
        self,
        period_code,
        date_to,
        products,
        actions
    ):

        return {
            "error": False,
            "report": {
                "period": period_code,
                "products_count": len(products)
            },
            "actions": {
                "total": len(actions),
                "active": 2
            },
            "message": "Анализ готов"
        }



class TestAssistantRealScenarios(
    unittest.TestCase
):


    def setUp(
        self
    ):

        self.intent = (
            AssistantIntentService()
        )


        self.command = (
            AssistantCommandService(
                orchestrator_service=(
                    FakeOrchestratorService()
                )
            )
        )


    def execute_text(
        self,
        text
    ):

        intent = (
            self.intent
            .detect(
                text
            )
        )


        self.assertFalse(
            intent["error"]
        )


        return (
            self.command
            .execute(
                intent["command"],
                {
                    "period_code": "28D",
                    "date_to": "2026-08-09",
                    "products": [
                        "product"
                    ],
                    "actions": [
                        "action1",
                        "action2"
                    ]
                }
            )
        )


    def test_store_status_scenario(
        self
    ):

        result = (
            self.execute_text(
                "Как дела в магазине?"
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
            result["message"],
            "Анализ готов"
        )


    def test_report_scenario(
        self
    ):

        result = (
            self.execute_text(
                "Покажи отчёт"
            )
        )


        self.assertEqual(
            result["report"]["products_count"],
            1
        )


if __name__ == "__main__":
    unittest.main()