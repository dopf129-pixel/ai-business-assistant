import sys

sys.path.insert(
    0,
    "app"
)


from telegram_core_factory import create_telegram_core


USER_ID = 1000



def test_automatic_replanning_replaces_failed_action():


    core = create_telegram_core()


    task_service = (
        core["task_service"]
    )


    execution_service = (
        core["execution_service"]
    )


    task_service.create_task(

        USER_ID,

        "Automatic replanning",

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


    result = (
        execution_service
        .replan_failed_action(
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


    assert (
        task["task"]
        .get(
            "replanned"
        )
        ==
        True
    )