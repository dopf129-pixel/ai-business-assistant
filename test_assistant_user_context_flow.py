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

from services.assistant_user_context_service import (
    AssistantUserContextService
)



class TestAssistantUserContextFlow(
    unittest.TestCase
):


    def test_users_have_independent_context(
        self
    ):

        profile = (
            AssistantUserProfileService()
        )


        context = (
            AssistantUserContextService(
                profile
            )
        )


        context.remember(
            1001,
            "имя",
            "Алекс"
        )


        context.remember(
            2002,
            "имя",
            "Мария"
        )


        user_1001 = (
            context.get_context(
                1001
            )
        )


        user_2002 = (
            context.get_context(
                2002
            )
        )


        self.assertEqual(
            user_1001["memory"]["имя"],
            "Алекс"
        )


        self.assertEqual(
            user_2002["memory"]["имя"],
            "Мария"
        )



    def test_new_user_has_empty_memory(
        self
    ):

        profile = (
            AssistantUserProfileService()
        )


        context = (
            AssistantUserContextService(
                profile
            )
        )


        result = (
            context.get_context(
                3003
            )
        )


        self.assertEqual(
            result["memory"],
            {}
        )



if __name__ == "__main__":
    unittest.main()