import sys

sys.path.insert(
    0,
    "app"
)


from telegram_core_factory import create_telegram_core



def test_feedback_is_connected_to_memory():


    core = create_telegram_core()


    feedback_service = (
        core["feedback_service"]
    )


    memory_service = (
        core["memory_service"]
    )


    assert (
        feedback_service
        is not None
    )


    assert (
        memory_service
        is not None
    )


    result = (
        memory_service.remember(
            {

                "action":
                    "Тест памяти",

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
            memory_service.memory
        )
        ==
        1
    )