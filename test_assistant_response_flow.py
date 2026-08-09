import sys
import unittest
from pathlib import Path


sys.path.insert(
    0,
    str(Path(__file__).parent / "app")
)


from services.assistant_response_builder_service import (
    AssistantResponseBuilderService
)


class TestAssistantResponseFlow(
    unittest.TestCase
):


    def test_build_user_response(
        self
    ):

        service = (
            AssistantResponseBuilderService()
        )


        result = (
            service.build(
                {
                    "count": 2,
                    "actions": [
                        {
                            "title": "Проверить остатки",
                            "priority": "HIGH"
                        },
                        {
                            "title": "Проверить продажи",
                            "priority": "HIGH"
                        }
                    ]
                }
            )
        )


        self.assertFalse(
            result["error"]
        )


        self.assertEqual(
            result["message"],
            "Создано действий: 2"
        )


        self.assertEqual(
            len(
                result["actions"]
            ),
            2
        )


    def test_empty_response(
        self
    ):

        service = (
            AssistantResponseBuilderService()
        )


        result = (
            service.build(
                {
                    "count": 0
                }
            )
        )


        self.assertFalse(
            result["error"]
        )


        self.assertEqual(
            result["message"],
            "Проблем не найдено"
        )


if __name__ == "__main__":
    unittest.main()