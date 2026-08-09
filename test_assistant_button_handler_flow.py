import sys
import unittest
from pathlib import Path


sys.path.insert(
    0,
    str(Path(__file__).parent / "app")
)


from services.assistant_button_handler_service import (
    AssistantButtonHandlerService
)



class FakeAssistant:


    def ask(
        self,
        text
    ):

        return {
            "error": False,
            "request": text
        }



class TestAssistantButtonHandlerFlow(
    unittest.TestCase
):


    def test_analyze_button(
        self
    ):

        service = (
            AssistantButtonHandlerService(
                FakeAssistant()
            )
        )


        result = (
            service.handle(
                "analyze"
            )
        )


        self.assertFalse(
            result["error"]
        )


        self.assertEqual(
            result["request"],
            "Что нужно сделать с продажами?"
        )



    def test_plan_button(
        self
    ):

        service = (
            AssistantButtonHandlerService(
                FakeAssistant()
            )
        )


        result = (
            service.handle(
                "plan"
            )
        )


        self.assertFalse(
            result["error"]
        )


        self.assertEqual(
            result["request"],
            "Создай план действий"
        )



    def test_history_button(
        self
    ):

        service = (
            AssistantButtonHandlerService(
                FakeAssistant()
            )
        )


        result = (
            service.handle(
                "history"
            )
        )


        self.assertFalse(
            result["error"]
        )


        self.assertEqual(
            result["command"],
            "history"
        )



    def test_memory_button(
        self
    ):

        service = (
            AssistantButtonHandlerService(
                FakeAssistant()
            )
        )


        result = (
            service.handle(
                "memory"
            )
        )


        self.assertFalse(
            result["error"]
        )


        self.assertEqual(
            result["command"],
            "memory"
        )



    def test_unknown_button(
        self
    ):

        service = (
            AssistantButtonHandlerService(
                FakeAssistant()
            )
        )


        result = (
            service.handle(
                "unknown"
            )
        )


        self.assertTrue(
            result["error"]
        )


        self.assertEqual(
            result["message"],
            "Кнопка неизвестна"
        )



if __name__ == "__main__":

    unittest.main()