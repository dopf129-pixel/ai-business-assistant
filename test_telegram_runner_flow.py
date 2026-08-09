import sys
import unittest
from pathlib import Path


sys.path.insert(
    0,
    str(Path(__file__).parent / "app")
)


from telegram.telegram_runner import (
    TelegramRunner
)



class FakeBotService:


    def on_start(
        self
    ):

        return {
            "event": "start"
        }



    def on_message(
        self,
        text
    ):

        return {
            "event": "message",
            "text": text
        }



    def on_callback(
        self,
        callback
    ):

        return {
            "event": "callback",
            "callback": callback
        }



class TestTelegramRunnerFlow(
    unittest.TestCase
):


    def test_start_flow(
        self
    ):

        runner = (
            TelegramRunner(
                FakeBotService()
            )
        )


        result = (
            runner.start()
        )


        self.assertEqual(
            result["event"],
            "start"
        )



    def test_message_flow(
        self
    ):

        runner = (
            TelegramRunner(
                FakeBotService()
            )
        )


        result = (
            runner.receive_message(
                "Привет"
            )
        )


        self.assertEqual(
            result["event"],
            "message"
        )


        self.assertEqual(
            result["text"],
            "Привет"
        )



    def test_callback_flow(
        self
    ):

        runner = (
            TelegramRunner(
                FakeBotService()
            )
        )


        result = (
            runner.receive_callback(
                "analyze"
            )
        )


        self.assertEqual(
            result["event"],
            "callback"
        )


        self.assertEqual(
            result["callback"],
            "analyze"
        )



if __name__ == "__main__":
    unittest.main()