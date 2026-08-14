import sys

sys.path.insert(
    0,
    "app"
)


from telegram_core_factory import create_telegram_core


USER_ID = 1000



def test_dependency_chain_blocks_failed_parent():


    core = create_telegram_core()


    task_service = (
        core["task_service"]
    )


    task_service.create_task(

        USER_ID,

        "Цепочка зависимостей",

        [

            {

                "title":
                    "Первый шаг",

                "type":
                    "sales",

                "status":
                    "DONE"

            },

            {

                "title":
                    "Второй шаг",

                "type":
                    "sales",

                "status":
                    "FAILED",

                "depends_on":
                    [
                        "Первый шаг"
                    ]

            },

            {

                "title":
                    "Третий шаг",

                "type":
                    "sales",

                "status":
                    "NEW",

                "depends_on":
                    [
                        "Второй шаг"
                    ]

            }

        ]

    )


    result = (
        task_service
        .get_next_action(
            USER_ID
        )
    )


    action = (
        result.get(
            "action"
        )
    )


    assert (
        action is None
        or
        action["title"]
        !=
        "Третий шаг"
    )