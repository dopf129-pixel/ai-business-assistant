import sys
import unittest
from pathlib import Path
import tempfile


sys.path.insert(
    0,
    str(Path(__file__).parent / "app")
)


from services.assistant_memory_integration_service import (
    AssistantMemoryIntegrationService
)

from services.assistant_memory_service import (
    AssistantMemoryService
)

from services.assistant_memory_storage_service import (
    AssistantMemoryStorageService
)

from services.assistant_intent_service import (
    AssistantIntentService
)


class TestAssistantMemoryIntegration(
    unittest.TestCase
):


    def test_memory_persists_user_context(
        self
    ):

        with tempfile.TemporaryDirectory() as folder:

            file_path = (
                Path(folder)
                /
                "memory.json"
            )


            storage = (
                AssistantMemoryStorageService(
                    file_path=file_path
                )
            )


            memory = (
                AssistantMemoryService(
                    storage_service=storage
                )
            )


            integration = (
                AssistantMemoryIntegrationService(
                    memory_service=memory,
                    intent_service=(
                        AssistantIntentService()
                    )
                )
            )


            result = (
                integration.process(
                    "Покажи отчёт по магазину"
                )
            )


            self.assertFalse(
                result["error"]
            )


            self.assertTrue(
                result["memory_saved"]
            )


            new_storage = (
                AssistantMemoryStorageService(
                    file_path=file_path
                )
            )


            new_memory = (
                AssistantMemoryService(
                    storage_service=new_storage
                )
            )


            command = (
                new_memory.get(
                    "last_command"
                )
            )


            text = (
                new_memory.get(
                    "last_text"
                )
            )


            self.assertEqual(
                command["value"],
                "report"
            )


            self.assertEqual(
                text["value"],
                "Покажи отчёт по магазину"
            )


if __name__ == "__main__":
    unittest.main()