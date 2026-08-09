import sys
import unittest
from pathlib import Path


sys.path.insert(
    0,
    str(Path(__file__).parent / "app")
)


from services.assistant_context_resolver_service import (
    AssistantContextResolverService
)

from services.assistant_memory_service import (
    AssistantMemoryService
)



class TestAssistantContextResolverFlow(
    unittest.TestCase
):


    def test_continue_previous_command(
        self
    ):

        memory = (
            AssistantMemoryService()
        )


        memory.save(
            "last_command",
            "report"
        )


        resolver = (
            AssistantContextResolverService(
                memory_service=memory
            )
        )


        result = (
            resolver.resolve(
                "Покажи за 90 дней"
            )
        )


        self.assertFalse(
            result["error"]
        )


        self.assertEqual(
            result["command"],
            "report"
        )


        self.assertEqual(
            result["period"],
            "покажи за 90 дней"
        )


    def test_without_context(
        self
    ):

        memory = (
            AssistantMemoryService()
        )


        resolver = (
            AssistantContextResolverService(
                memory_service=memory
            )
        )


        result = (
            resolver.resolve(
                "за 90 дней"
            )
        )


        self.assertTrue(
            result["error"]
        )


if __name__ == "__main__":
    unittest.main()