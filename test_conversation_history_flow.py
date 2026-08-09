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



class TestConversationHistoryFlow(
    unittest.TestCase
):


    def test_history_persists_messages(
        self
    ):

        with tempfile.TemporaryDirectory() as folder:

            file_path = (
                Path(folder)
                /
                "conversation_history.json"
            )


            storage = (
                ConversationHistoryStorageService(
                    file_path=file_path
                )
            )


            history = (
                ConversationHistoryService(
                    storage_service=storage
                )
            )


            history.add_message(
                "user",
                "Покажи отчёт"
            )


            history.add_message(
                "assistant",
                "Отчёт готов"
            )


            new_storage = (
                ConversationHistoryStorageService(
                    file_path=file_path
                )
            )


            new_history = (
                ConversationHistoryService(
                    storage_service=new_storage
                )
            )


            result = (
                new_history
                .get_history()
            )


            self.assertEqual(
                result["count"],
                2
            )


            self.assertEqual(
                result["history"][0]["role"],
                "user"
            )


            self.assertEqual(
                result["history"][0]["message"],
                "Покажи отчёт"
            )


            self.assertEqual(
                result["history"][1]["role"],
                "assistant"
            )


            self.assertEqual(
                result["history"][1]["message"],
                "Отчёт готов"
            )


if __name__ == "__main__":
    unittest.main()