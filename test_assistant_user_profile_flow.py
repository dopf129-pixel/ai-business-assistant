import sys
import unittest
from pathlib import Path


sys.path.insert(
    0,
    str(Path(__file__).parent / "app")
)


from services.assistant_user_profile_service import (
    AssistantUserProfileService
)



class TestAssistantUserProfileFlow(
    unittest.TestCase
):


    def test_users_have_separate_memory(
        self
    ):

        service = (
            AssistantUserProfileService()
        )


        service.save_memory(
            1001,
            "имя",
            "Алекс"
        )


        service.save_memory(
            2002,
            "имя",
            "Мария"
        )


        alex = (
            service.get_memory(
                1001,
                "имя"
            )
        )


        maria = (
            service.get_memory(
                2002,
                "имя"
            )
        )


        self.assertFalse(
            alex["error"]
        )


        self.assertFalse(
            maria["error"]
        )


        self.assertEqual(
            alex["value"],
            "Алекс"
        )


        self.assertEqual(
            maria["value"],
            "Мария"
        )



    def test_new_user_created(
        self
    ):

        service = (
            AssistantUserProfileService()
        )


        result = (
            service.get_user(
                3003
            )
        )


        self.assertFalse(
            result["error"]
        )


        self.assertEqual(
            result["user"]["user_id"],
            3003
        )


        self.assertEqual(
            result["user"]["memory"],
            {}
        )



if __name__ == "__main__":
    unittest.main()