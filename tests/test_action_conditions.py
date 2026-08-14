import sys

sys.path.insert(
    0,
    "app"
)

from telegram_core_factory import create_telegram_core


USER_ID = 505204945



def test_action_condition_blocks_when_result_not_match():


    core = create_telegram_core()


    core["task_service"].create_task(
        USER_ID,
        "Проверка условий",
        [

            {
                "title":
                    "Запустить рекламу",

                "type":
                    "marketing",

                "status":
                    "NEW",

                "condition":
                    {
                        "contains":
                            "падение"
                    }
            },

            {
                "title":
                    "Проверить продажи",

                "type":
                    "sales",

                "status":
                    "DONE",

                "result":
                    {
                        "message":
                            "Продажи стабильны"
                    }
            }

        ]
    )


    current = (
        core["task_service"]
        .get_current_action(
            USER_ID
        )
    )


    assert (
        current["action"]
        is
        None
    )