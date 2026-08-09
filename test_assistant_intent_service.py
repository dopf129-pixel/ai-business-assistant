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


class TestAssistantIntentService(
    unittest.TestCase
):


    def setUp(
        self
    ):

        self.service = (
            AssistantIntentService()
        )


    def test_report_intent(
        self
    ):

        result = (
            self.service
            .detect(
                "Покажи отчёт по магазину"
            )
        )


        self.assertFalse(
            result["error"]
        )


        self.assertEqual(
            result["command"],
            "report"
        )


    def test_actions_intent(
        self
    ):

        result = (
            self.service
            .detect(
                "Какие задачи нужно сделать?"
            )
        )


        self.assertFalse(
            result["error"]
        )


        self.assertEqual(
            result["command"],
            "actions"
        )


    def test_unknown_intent(
        self
    ):

        result = (
            self.service
            .detect(
                "Расскажи что-нибудь"
            )
        )


        self.assertTrue(
            result["error"]
        )


if __name__ == "__main__":
    unittest.main()