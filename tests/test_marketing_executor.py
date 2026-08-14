import sys

sys.path.insert(
    0,
    "app"
)

from telegram_core_factory import create_telegram_core


def test_marketing_executor_can_be_added_to_router():


    core = create_telegram_core()


    result = (
        core["action_router"]
        .execute(
            {
                "type":
                    "marketing",

                "title":
                    "Проверить рекламные каналы",

                "priority":
                    "HIGH",

                "context":
                    {
                        "reason":
                            "Снизилась эффективность рекламы"
                    }
            }
        )
    )


    assert (
        result["error"]
        is
        False
    )


    assert (
        result["result"]["type"]
        ==
        "marketing"
    )


    assert (
        "Маркетинг"
        in
        result["result"]["message"]
    )