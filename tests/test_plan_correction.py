import sys

sys.path.insert(
    0,
    "app"
)


from services.assistant_plan_correction_service import (
    AssistantPlanCorrectionService
)



def test_plan_correction_keeps_completed_actions():


    service = (
        AssistantPlanCorrectionService()
    )


    actions = [

        {

            "title":
                "Получить данные",

            "status":
                "DONE"

        },

        {

            "title":
                "Сделать анализ",

            "status":
                "FAILED",

            "error":
                "API unavailable"

        },

        {

            "title":
                "Отправить клиенту",

            "status":
                "NEW"

        }

    ]


    result = (
        service.correct(
            actions
        )
    )


    assert (
        result["error"]
        ==
        False
    )


    corrected = (
        result["plan"]
    )


    assert (
        corrected[0]["status"]
        ==
        "DONE"
    )


    assert len(
        corrected
    ) >= 3