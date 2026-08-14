import sys

sys.path.insert(
    0,
    "app"
)


from telegram_core_factory import create_telegram_core



USER_ID = 1000



def test_history_contains_failed_execution():


    core = create_telegram_core()


    task_service = (
        core["task_service"]
    )


    task_service.create_task(

        USER_ID,

        "Ошибка истории",

        [

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


    class BrokenExecutor:


        def execute(
            self,
            action
        ):

            raise Exception(
                "Ошибка исполнителя"
            )



    core["action_router"].executors = {

        "sales":
            BrokenExecutor()

    }



    result = (
        core["execution_service"]
        .execute_current_action(
            USER_ID
        )
    )


    assert (
        result["error"]
        ==
        False
    )


    history = (
        core["execution_service"]
        .history_service
        .actions
    )


    found = False


    for item in history:

        if (
            item.get(
                "status"
            )
            ==
            "FAILED"
        ):

            found = True



    assert found