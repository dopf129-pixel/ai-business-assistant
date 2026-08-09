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
            "message": "Отчёт готов",
            "period": period_code
        }



class TestAssistantIntentFlow(
    unittest.TestCase
):


    def setUp(
        self
    ):

        self.intent_service = (
            AssistantIntentService()
        )


        self.command_service = (
            AssistantCommandService(
                orchestrator_service=(
                    FakeOrchestratorService()
                )
            )
        )


    def test_report_text_to_response(
        self
    ):

        intent = (
            self.intent_service
            .detect(
                "Покажи отчёт по магазину"
            )
        )


        self.assertFalse(
            intent["error"]
        )


        self.assertEqual(
            intent["command"],
            "report"
        )


        response = (
            self.command_service
            .execute(
                intent["command"],
                {
                    "period_code": "28D",
                    "date_to": "2026-08-09",
                    "products": [],
                    "actions": []
                }
            )
        )


        self.assertFalse(
            response["error"]
        )


        self.assertEqual(
            response["message"],
            "Отчёт готов"
        )


    def test_unknown_text(
        self
    ):

        intent = (
            self.intent_service
            .detect(
                "Просто поговори со мной"
            )
        )


        self.assertTrue(
            intent["error"]
        )


if __name__ == "__main__":
    unittest.main()