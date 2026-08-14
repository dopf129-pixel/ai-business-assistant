import sys

sys.path.insert(
    0,
    "app"
)


from telegram_core_factory import create_telegram_core


USER_ID = 1000



def test_failed_execution_contains_retry_decision():


    core = create_telegram_core()


    task_service = (
        core["task_service"]
    )


    task_service.create_task(

        USER_ID,

        "Retry policy integration",

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


    class TimeoutExecutor:


        def execute(
            self,
            action
        ):

            raise Exception(
                "timeout error"
            )


    core["action_router"].executors = {

        "sales":
            TimeoutExecutor()

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


    action = (
        result["action"]
    )


    assert (
        action["status"]
        ==
        "FAILED"
    )


    assert (
        action["retry_allowed"]
        ==
        True
    )