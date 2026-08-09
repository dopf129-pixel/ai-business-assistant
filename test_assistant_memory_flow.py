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


class TestAssistantMemoryFlow(
    unittest.TestCase
):


    def test_save_and_restore_context(
        self
    ):

        memory = (
            AssistantMemoryService()
        )


        first_request = {
            "command": "report",
            "period": "30D"
        }


        save = (
            memory.save(
                "last_request",
                first_request
            )
        )


        self.assertFalse(
            save["error"]
        )


        restored = (
            memory.get(
                "last_request"
            )
        )


        self.assertFalse(
            restored["error"]
        )


        self.assertEqual(
            restored["value"]["command"],
            "report"
        )


        self.assertEqual(
            restored["value"]["period"],
            "30D"
        )


    def test_context_update(
        self
    ):

        memory = (
            AssistantMemoryService()
        )


        memory.save(
            "period",
            "30D"
        )


        memory.save(
            "period",
            "90D"
        )


        result = (
            memory.get(
                "period"
            )
        )


        self.assertEqual(
            result["value"],
            "90D"
        )


if __name__ == "__main__":
    unittest.main()