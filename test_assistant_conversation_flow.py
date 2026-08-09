import sys
import unittest
from pathlib import Path
import tempfile


sys.path.insert(
    0,
    str(Path(__file__).parent / "app")
)


from services.conversation_history_service import (
    ConversationHistoryService
)

from services.conversation_history_storage_service import (
    ConversationHistoryStorageService
)

from services.assistant_memory_service import (
    AssistantMemoryService
)

from services.assistant_memory_storage_service import (
    AssistantMemoryStorageService
)

from services.assistant_memory_integration_service import (
    AssistantMemoryIntegrationService
)

from services.assistant_intent_service import (
    AssistantIntentService
)



class TestAssistantConversationFlow(
    unittest.TestCase
):


    def test_full_conversation_cycle(
        self
    ):

        with tempfile.TemporaryDirectory() as folder:

            memory_file = (
                Path(folder)
                /
                "memory.json"
            )

            history_file = (
                Path(folder)
                /
                "history.json"
            )


            memory_storage = (
                AssistantMemoryStorageService(
                    file_path=memory_file
                )
            )


            history_storage = (
                ConversationHistoryStorageService(
                    file_path=history_file
                )
            )


            memory = (
                AssistantMemoryService(
                    storage_service=memory_storage
                )
            )


            history = (
                ConversationHistoryService(
                    storage_service=history_storage
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


            user_message = (
                "Покажи отчёт по магазину"
            )


            history.add_message(
                "user",
                user_message
            )


            result = (
                integration.process(
                    user_message
                )
            )


            self.assertFalse(
                result["error"]
            )


            history.add_message(
                "assistant",
                "Отчёт готов"
            )


            restored_history = (
                ConversationHistoryService(
                    storage_service=(
                        ConversationHistoryStorageService(
                            file_path=history_file
                        )
                    )
                )
            )


            conversation = (
                restored_history
                .get_history()
            )


            self.assertEqual(
                conversation["count"],
                2
            )


            self.assertEqual(
                conversation["history"][0]["role"],
                "user"
            )


            self.assertEqual(
                conversation["history"][1]["role"],
                "assistant"
            )


            saved_command = (
                memory.get(
                    "last_command"
                )
            )


            self.assertEqual(
                saved_command["value"],
                "report"
            )


if __name__ == "__main__":
    unittest.main()