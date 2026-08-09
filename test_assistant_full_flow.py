import sys
import unittest
from pathlib import Path


sys.path.insert(
    0,
    str(Path(__file__).parent / "app")
)


from services.assistant_response_service import (
    AssistantResponseService
)


class TestAssistantFullFlow(
    unittest.TestCase
):


    def test_full_assistant_response(
        self
    ):

        report = {
            "period": "28D",
            "status": "🟢 Бизнес растёт"
        }


        action_dashboard = {
            "total": 4,
            "active": 3,
            "completed": 1,
            "actions": [
                {
                    "title": "Проверить товары",
                    "status": "NEW"
                }
            ]
        }


        service = (
            AssistantResponseService()
        )


        result = (
            service.build(
                report,
                action_dashboard
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
            result["actions"]["active"],
            3
        )


        self.assertEqual(
            result["message"],
            "Есть активных задач: 3"
        )


    def test_assistant_without_actions(
        self
    ):

        result = (
            AssistantResponseService()
            .build(
                {
                    "period": "28D"
                },
                {
                    "total": 0,
                    "active": 0,
                    "completed": 0,
                    "actions": []
                }
            )
        )


        self.assertEqual(
            result["message"],
            "Активных задач нет"
        )


if __name__ == "__main__":
    unittest.main()