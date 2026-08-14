import sys

sys.path.insert(
    0,
    "app"
)


from services.assistant_replanning_service import (
    AssistantReplanningService
)



def test_replanning_service_creates_new_plan():


    service = (
        AssistantReplanningService()
    )


    failed_action = {

        "title":
            "Получить данные",

        "error":
            "API unavailable"

    }


    result = (
        service.replan(
            failed_action
        )
    )


    assert (
        result["error"]
        ==
        False
    )


    assert (
        "plan"
        in result
    )