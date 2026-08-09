import sys
import unittest
from pathlib import Path


sys.path.insert(
    0,
    str(Path(__file__).parent / "app")
)


from telegram_core_factory import (
    create_telegram_core
)



class TestTelegramUserMemoryFlow(
    unittest.TestCase
):


    def test_users_have_separate_memory(
        self
    ):

        system = (
            create_telegram_core()
        )


        profiles = (
            system["profiles"]
        )


        profiles.save_memory(
            1001,
            "имя",
            "Алекс"
        )


        profiles.save_memory(
            2002,
            "имя",
            "Мария"
        )


        user1 = (
            profiles.get_user(
                1001
            )
        )


        user2 = (
            profiles.get_user(
                2002
            )
        )


        self.assertEqual(
            user1["user"]["memory"]["имя"],
            "Алекс"
        )


        self.assertEqual(
            user2["user"]["memory"]["имя"],
            "Мария"
        )


if __name__ == "__main__":
    unittest.main()