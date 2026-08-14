import sys

sys.path.insert(
    0,
    "app"
)


from telegram_core_factory import create_telegram_core



USER_ID = 1000



def test_retry_failed_action_execution():


    core = create_telegram_core()


    task_service = (
        core["task_service"]
    )


    task_service.create_task(

        USER_ID,

        "Retry тест",

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
                "Первая ошибка"
            )



    core["action_router"].executors = {

        "sales":
            BrokenExecutor()

    }


    execution_service = (
        core["execution_service"]
    )


    first_result = (
        execution_service
        .execute_current_action(
            USER_ID
        )
    )


    assert (
        first_result["error"]
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


    assert hasattr(
        execution_service,
        "retry_action"
    )