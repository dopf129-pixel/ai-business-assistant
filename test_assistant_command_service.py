import sys
import unittest
from pathlib import Path


sys.path.insert(
    0,
    str(Path(__file__).parent / "app")
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
            "period": period_code,
            "date": date_to,
            "products": products,
            "actions": actions
        }



class TestAssistantCommandService(
    unittest.TestCase
):


    def setUp(
        self
    ):

        self.service = (
            AssistantCommandService(
                orchestrator_service=(
                    FakeOrchestratorService()
                )
            )
        )


    def test_execute_report_command(
        self
    ):

        result = (
            self.service
            .execute(
                "report",
                {
                    "period_code": "28D",
                    "date_to": "2026-08-09",
                    "products": [
                        "Product A"
                    ],
                    "actions": [
                        {
                            "title": "Проверить товар"
                        }
                    ]
                }
            )
        )


        self.assertFalse(
            result["error"]
        )


        self.assertEqual(
            result["period"],
            "28D"
        )


        self.assertEqual(
            len(
                result["products"]
            ),
            1
        )


    def test_unknown_command(
        self
    ):

        result = (
            self.service
            .execute(
                "unknown",
                {}
            )
        )


        self.assertTrue(
            result["error"]
        )


        self.assertEqual(
            result["message"],
            "Неизвестная команда"
        )


if __name__ == "__main__":
    unittest.main()