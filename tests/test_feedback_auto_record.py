import sys

sys.path.insert(
    0,
    "app"
)


from telegram_core_factory import create_telegram_core



USER_ID = 1000



def test_execution_records_feedback():


    core = create_telegram_core()


    execution_service = (
        core["execution_service"]
    )


    feedback_service = (
        core["feedback_service"]
    )


    execution_service.feedback_service = (
        feedback_service
    )


    assert hasattr(
        execution_service.feedback_service,
        "record"
    )


    result = (
        feedback_service.record(
            {

                "action":
                    "Тест",

                "status":
                    "DONE"

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
            feedback_service.experiences
        )
        ==
        1
    )