import sys

sys.path.insert(
    0,
    "app"
)


from telegram_core_factory import create_telegram_core



USER_ID = 1000



def test_retry_history_records_attempts():


    core = create_telegram_core()


    task_service = (
        core["task_service"]
    )


    task_service.create_task(

        USER_ID,

        "История retry",

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
                "Ошибка попытки"
            )



    core["action_router"].executors = {

        "sales":
            BrokenExecutor()

    }


    execution_service = (
        core["execution_service"]
    )


    execution_service.execute_current_action(
        USER_ID
    )


    history = (
        execution_service
        .history_service
        .actions
    )


    found = False


    for item in history:

        if (
            item.get(
                "event"
            )
            ==
            "execution_failed"
        ):

            found = True


            assert (
                "attempt"
                in item
            )



    assert found