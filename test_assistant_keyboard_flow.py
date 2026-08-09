import sys
import unittest
from pathlib import Path


sys.path.insert(
    0,
    str(Path(__file__).parent / "app")
)


from services.assistant_keyboard_service import (
    AssistantKeyboardService
)



class TestAssistantKeyboardFlow(
    unittest.TestCase
):


    def test_build_main_keyboard(
        self
    ):

        service = (
            AssistantKeyboardService()
        )


        result = (
            service.build_main_keyboard()
        )


        self.assertFalse(
            result["error"]
        )


        self.assertEqual(
            result["type"],
            "inline_keyboard"
        )


        self.assertEqual(
            len(
                result["buttons"]
            ),
            4
        )


        self.assertEqual(
            result["buttons"][0]["callback"],
            "analyze"
        )


        self.assertEqual(
            result["buttons"][1]["callback"],
            "plan"
        )


        self.assertEqual(
            result["buttons"][2]["callback"],
            "history"
        )


        self.assertEqual(
            result["buttons"][3]["callback"],
            "memory"
        )



if __name__ == "__main__":
    unittest.main()