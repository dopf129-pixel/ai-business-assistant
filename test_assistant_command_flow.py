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
            "report": {
                "period": period_code
            },
            "actions": {
                "total": len(actions)
            },
            "message": "Готово"
        }



class TestAssistantCommandFlow(
    unittest.TestCase
):


    def test_full_command_flow(
        self
    ):

        service = (
            AssistantCommandService(
                orchestrator_service=(
                    FakeOrchestratorService()
                )
            )
        )


        result = (
            service.execute(
                "report",
                {
                    "period_code": "28D",
                    "date_to": "2026-08-09",
                    "products": [
                        {
                            "name": "Product A"
                        }
                    ],
                    "actions": [
                        {
                            "title": "Проверить товар",
                            "status": "NEW"
                        }
                    ]
                }
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


        self.assertEqual(
            result["message"],
            "Готово"
        )


if __name__ == "__main__":
    unittest.main()