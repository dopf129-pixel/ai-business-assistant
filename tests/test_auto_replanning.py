import sys

sys.path.insert(
    0,
    "app"
)


from telegram_core_factory import create_telegram_core



USER_ID = 1000



def test_failed_action_creates_replan_request():


    core = create_telegram_core()


    task_service = (
        core["task_service"]
    )


    task_service.create_task(

        USER_ID,

        "Replan test",

        [

            {

                "title":
                    "Получить данные",

                "type":
                    "sales",

                "status":
                    "FAILED",

                "error":
                    "API unavailable"

            }

        ]

    )


    assert hasattr(
        task_service,
        "request_replan"
    )