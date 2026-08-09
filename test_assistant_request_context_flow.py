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

from services.assistant_request_context_service import (
    AssistantRequestContextService
)



class TestAssistantRequestContextFlow(
    unittest.TestCase
):


    def test_request_contains_user_memory(
        self
    ):

        profile = (
            AssistantUserProfileService()
        )


        user_context = (
            AssistantUserContextService(
                profile
            )
        )


        request_context = (
            AssistantRequestContextService(
                user_context
            )
        )


        user_context.remember(
            1001,
            "имя",
            "Алекс"
        )


        result = (
            request_context.build(
                1001,
                "Что нужно сделать?"
            )
        )


        self.assertEqual(
            result["user_id"],
            1001
        )


        self.assertEqual(
            result["text"],
            "Что нужно сделать?"
        )


        self.assertEqual(
            result["memory"]["имя"],
            "Алекс"
        )



    def test_different_users_have_different_context(
        self
    ):

        profile = (
            AssistantUserProfileService()
        )


        user_context = (
            AssistantUserContextService(
                profile
            )
        )


        request_context = (
            AssistantRequestContextService(
                user_context
            )
        )


        user_context.remember(
            1001,
            "имя",
            "Алекс"
        )


        user_context.remember(
            2002,
            "имя",
            "Мария"
        )


        first = (
            request_context.build(
                1001,
                "Привет"
            )
        )


        second = (
            request_context.build(
                2002,
                "Привет"
            )
        )


        self.assertEqual(
            first["memory"]["имя"],
            "Алекс"
        )


        self.assertEqual(
            second["memory"]["имя"],
            "Мария"
        )



if __name__ == "__main__":
    unittest.main()