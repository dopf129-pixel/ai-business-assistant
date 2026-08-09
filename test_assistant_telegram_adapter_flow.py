import sys
import unittest
from pathlib import Path


sys.path.insert(
    0,
    str(Path(__file__).parent / "app")
)


from telegram.assistant_telegram_adapter import (
    AssistantTelegramAdapter
)



class FakeAssistant:


    def ask(
        self,
        text
    ):

        return {
            "error": False,
            "message": "Ответ ассистента",
            "request": text
        }



class FakeKeyboard:


    def build_main_keyboard(
        self
    ):

        return {
            "error": False,
            "buttons": [
                {
                    "text": "📊 Анализ",
                    "callback": "analyze"
                }
            ]
        }



class FakeButtonHandler:


    def handle(
        self,
        callback
    ):

        return {
            "error": False,
            "callback": callback
        }



class TestAssistantTelegramAdapterFlow(
    unittest.TestCase
):


    def test_start_response(
        self
    ):

        adapter = (
            AssistantTelegramAdapter(
                FakeAssistant(),
                FakeKeyboard(),
                FakeButtonHandler()
            )
        )


        result = (
            adapter.get_start_response()
        )


        self.assertIn(
            "text",
            result
        )


        self.assertIn(
            "keyboard",
            result
        )



    def test_text_message(
        self
    ):

        adapter = (
            AssistantTelegramAdapter(
                FakeAssistant(),
                FakeKeyboard(),
                FakeButtonHandler()
            )
        )


        result = (
            adapter.handle_text(
                "Привет"
            )
        )


        self.assertFalse(
            result["error"]
        )


        self.assertEqual(
            result["request"],
            "Привет"
        )



    def test_button_callback(
        self
    ):

        adapter = (
            AssistantTelegramAdapter(
                FakeAssistant(),
                FakeKeyboard(),
                FakeButtonHandler()
            )
        )


        result = (
            adapter.handle_button(
                "analyze"
            )
        )


        self.assertFalse(
            result["error"]
        )


        self.assertEqual(
            result["callback"],
            "analyze"
        )



if __name__ == "__main__":
    unittest.main()