import sys
import unittest
from pathlib import Path


sys.path.insert(
    0,
    str(Path(__file__).parent / "app")
)


from services.assistant_memory_service import (
    AssistantMemoryService
)


class TestAssistantMemoryService(
    unittest.TestCase
):


    def setUp(
        self
    ):

        self.service = (
            AssistantMemoryService()
        )


    def test_save_and_get_context(
        self
    ):

        save_result = (
            self.service
            .save(
                "last_command",
                "report"
            )
        )


        self.assertFalse(
            save_result["error"]
        )


        result = (
            self.service
            .get(
                "last_command"
            )
        )


        self.assertFalse(
            result["error"]
        )


        self.assertEqual(
            result["value"],
            "report"
        )


    def test_missing_context(
        self
    ):

        result = (
            self.service
            .get(
                "unknown"
            )
        )


        self.assertTrue(
            result["error"]
        )


    def test_clear_memory(
        self
    ):

        self.service.save(
            "period",
            "30D"
        )


        result = (
            self.service
            .clear()
        )


        self.assertFalse(
            result["error"]
        )


        context = (
            self.service
            .get(
                "period"
            )
        )


        self.assertTrue(
            context["error"]
        )


if __name__ == "__main__":
    unittest.main()