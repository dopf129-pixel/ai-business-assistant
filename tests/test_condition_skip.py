import sys

sys.path.insert(
    0,
    "app"
)

from telegram_core_factory import create_telegram_core


USER_ID = 505204945



def test_condition_skips_action_with_reason():


    core = create_telegram_core()


    core["task_service"].create_task(
        USER_ID,
        "Проверка пропуска",
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


    action = (
        core["task_service"]
        .tasks[str(USER_ID)]
        ["actions"][0]
    )


    assert (
        action["status"]
        ==
        "SKIPPED"
    )


    assert (
        "Условие"
        in
        action.get(
            "skip_reason",
            ""
        )
    )