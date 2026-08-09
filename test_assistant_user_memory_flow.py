import sys
import unittest
from pathlib import Path


sys.path.insert(
    0,
    str(Path(__file__).parent / "app")
)


from services.assistant_user_memory_service import (
    AssistantUserMemoryService
)

from services.assistant_user_memory_storage_service import (
    AssistantUserMemoryStorageService
)



class TestAssistantUserMemoryFlow(
    unittest.TestCase
):


    def test_memory_save_and_read(
        self
    ):

        storage = (
            AssistantUserMemoryStorageService(
                "test_memory.json"
            )
        )


        memory = (
            AssistantUserMemoryService(
                storage
            )
        )


        save_result = (
            memory.remember(
                "name",
                "Алекс"
            )
        )


        self.assertFalse(
            save_result["error"]
        )


        new_memory = (
            AssistantUserMemoryService(
                storage
            )
        )


        read_result = (
            new_memory.get(
                "name"
            )
        )


        self.assertFalse(
            read_result["error"]
        )


        self.assertEqual(
            read_result["value"],
            "Алекс"
        )



if __name__ == "__main__":
    unittest.main()