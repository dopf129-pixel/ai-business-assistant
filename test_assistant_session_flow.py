import sys
import unittest
from pathlib import Path


sys.path.insert(
    0,
    str(Path(__file__).parent / "app")
)


from services.assistant_session_service import (
    AssistantSessionService
)


class FakeAssistant:


    def ask(
        self,
        text
    ):

        return {
            "error": False,
            "message": "Ответ получен",
            "text": text
        }



class TestAssistantSessionFlow(
    unittest.TestCase
):


    def test_session_stores_conversation(
        self
    ):

        assistant = (
            FakeAssistant()
        )


        session = (
            AssistantSessionService(
                assistant
            )
        )


        result = (
            session.ask(
                "Покажи отчёт"
            )
        )


        self.assertFalse(
            result["error"]
        )


        history = (
            session.get_history()
        )


        self.assertEqual(
            history["count"],
            1
        )


        self.assertEqual(
            history["history"][0]["user"],
            "Покажи отчёт"
        )


        self.assertEqual(
            history["history"][0]["assistant"]["message"],
            "Ответ получен"
        )



    def test_multiple_messages(
        self
    ):

        session = (
            AssistantSessionService(
                FakeAssistant()
            )
        )


        session.ask(
            "Первый запрос"
        )

        session.ask(
            "Второй запрос"
        )


        history = (
            session.get_history()
        )


        self.assertEqual(
            history["count"],
            2
        )



if __name__ == "__main__":
    unittest.main()