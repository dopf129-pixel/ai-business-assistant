import sys

sys.path.insert(
    0,
    "app"
)


from telegram_core_factory import create_telegram_core



USER_ID = 999



def test_action_execution_failure():


    core = create_telegram_core()


    task_service = (
        core["task_service"]
    )


    task_service.create_task(

        USER_ID,

        "Ошибка выполнения",

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


    execution_service = (
        core["execution_service"]
    )


    class BrokenExecutor:


        def execute(
            self,
            action
        ):

            raise Exception(
                "Ошибка тестового исполнителя"
            )



    core["action_router"].executors = {

        "sales":
            BrokenExecutor()

    }



    result = (
        execution_service
        .execute_current_action(
            USER_ID
        )
    )


    assert (
        result["error"]
        ==
        False
    )


    task = (
        task_service
        .get_task(
            USER_ID
        )
    )


    action = (
        task["task"]["actions"][0]
    )


    assert (
        action["status"]
        ==
        "FAILED"
    )


    assert (
        "Ошибка"
        in
        action["error"]
    )