import sys

sys.path.insert(
    0,
    "app"
)


from telegram_core_factory import create_telegram_core


USER_ID = 1000



def test_multi_level_dependencies_block_execution():


    core = create_telegram_core()


    task_service = (
        core["task_service"]
    )


    task_service.create_task(

        USER_ID,

        "Многоуровневые зависимости",

        [

            {

                "title":
                    "Подготовить данные",

                "type":
                    "sales",

                "status":
                    "DONE"

            },


            {

                "title":
                    "Создать отчёт",

                "type":
                    "sales",

                "status":
                    "NEW",

                "depends_on":
                    [
                        "Подготовить данные"
                    ]

            },


            {

                "title":
                    "Отправить отчёт",

                "type":
                    "sales",

                "status":
                    "NEW",

                "depends_on":
                    [
                        "Создать отчёт"
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
        action["title"]
        ==
        "Создать отчёт"
    )