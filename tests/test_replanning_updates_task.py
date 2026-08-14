import sys

sys.path.insert(
    0,
    "app"
)


from telegram_core_factory import create_telegram_core


USER_ID = 1000



def test_replanning_updates_task_actions():


    core = create_telegram_core()


    task_service = (
        core["task_service"]
    )


    replanning_service = (
        core["replanning_service"]
    )


    task_service.create_task(

        USER_ID,

        "Update plan test",

        [

            {

                "title":
                    "FAILED действие",

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
        replanning_service.replan(
            {
                "title":
                    "FAILED действие",

                "error":
                    "API unavailable"
            }
        )
    )


    assert (
        result["error"]
        ==
        False
    )


    assert (
        len(
            result["plan"]
        )
        >
        0
    )