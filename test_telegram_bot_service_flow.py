import sys
import unittest
from pathlib import Path


sys.path.insert(
    0,
    str(Path(__file__).parent / "app")
)


from telegram.telegram_bot_service import (
    TelegramBotService
)



class FakeAdapter:


    def get_start_response(
        self
    ):

        return {
            "type": "start"
        }



    def handle_text(
        self,
        text
    ):

        return {
            "type": "text",
            "value": text
        }



    def handle_button(
        self,
        callback
    ):

        return {
            "type": "button",
            "value": callback
        }



class TestTelegramBotServiceFlow(
    unittest.TestCase
):


    def test_start_command(
        self
    ):

        service = (
            TelegramBotService(
                FakeAdapter()
            )
        )


        result = (
            service.on_start()
        )


        self.assertEqual(
            result["type"],
            "start"
        )



    def test_message_handler(
        self
    ):

        service = (
            TelegramBotService(
                FakeAdapter()
            )
        )


        result = (
            service.on_message(
                "Привет"
            )
        )


        self.assertEqual(
            result["type"],
            "text"
        )


        self.assertEqual(
            result["value"],
            "Привет"
        )



    def test_callback_handler(
        self
    ):

        service = (
            TelegramBotService(
                FakeAdapter()
            )
        )


        result = (
            service.on_callback(
                "analyze"
            )
        )


        self.assertEqual(
            result["type"],
            "button"
        )


        self.assertEqual(
            result["value"],
            "analyze"
        )



if __name__ == "__main__":
    unittest.main()