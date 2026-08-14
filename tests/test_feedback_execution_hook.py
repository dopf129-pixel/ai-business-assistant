import sys

sys.path.insert(
    0,
    "app"
)


from telegram_core_factory import create_telegram_core



USER_ID = 1000



def test_execution_automatically_creates_feedback():


    core = create_telegram_core()


    execution_service = (
        core["execution_service"]
    )


    feedback_service = (
        core["feedback_service"]
    )


    task_service = (
        core["task_service"]
    )


    task_service.create_task(

        USER_ID,

        "Feedback hook test",

        [

            {

                "title":
                    "Проверка продаж",

                "type":
                    "sales",

                "status":
                    "NEW"

            }

        ]

    )


    execution_service.execute_current_action(
        USER_ID
    )


    assert (
        len(
            feedback_service.experiences
        )
        >
        0
    )