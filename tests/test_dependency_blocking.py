import sys

sys.path.insert(
    0,
    "app"
)

from telegram_core_factory import create_telegram_core


USER_ID = 505204945



def test_dependency_blocks_action_until_parent_done():


    core = create_telegram_core()


    core["task_service"].create_task(
        USER_ID,
        "Блокировка зависимостей",
        [

            {
                "title":
                    "Запустить рекламу",

                "type":
                    "marketing",

                "status":
                    "NEW",

                "depends_on":
                    [
                        "Проверить продажи"
                    ]
            },


            {
                "title":
                    "Проверить продажи",

                "type":
                    "sales",

                "status":
                    "NEW"
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
        current["action"]["title"]
        ==
        "Проверить продажи"
    )


    assert (
        current["action"]["title"]
        !=
        "Запустить рекламу"
    )