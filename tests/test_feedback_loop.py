import sys

sys.path.insert(
    0,
    "app"
)


from services.assistant_feedback_service import (
    AssistantFeedbackService
)



def test_feedback_service_records_success():


    service = (
        AssistantFeedbackService()
    )


    result = (
        service.record(
            {

                "action":
                    "Создать отчёт",

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
        "experience"
        in result
    )