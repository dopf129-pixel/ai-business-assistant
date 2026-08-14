import sys

sys.path.insert(
    0,
    "app"
)


from telegram_core_factory import create_telegram_core



def test_feedback_saves_experience_into_memory():


    core = create_telegram_core()


    feedback_service = (
        core["feedback_service"]
    )


    memory_service = (
        core["memory_service"]
    )


    feedback_service.memory_service = (
        memory_service
    )


    feedback_service.record(

        {

            "action":
                "Создать отчёт",

            "status":
                "DONE"

        }

    )


    assert len(
        memory_service.memory
    ) == 1


    assert (
        memory_service.memory[0]["action"]
        ==
        "Создать отчёт"
    )