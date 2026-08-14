import sys

sys.path.insert(
    0,
    "app"
)


from telegram_core_factory import create_telegram_core



def test_planner_can_access_memory():


    core = create_telegram_core()


    memory_service = (
        core["memory_service"]
    )


    planner = (
        core.get(
            "planner"
        )
    )


    assert (
        memory_service
        is not None
    )


    memory_service.remember(

        {

            "action":
                "Получить данные",

            "status":
                "DONE"

        }

    )


    result = (
        memory_service.recall(
            "Получить данные"
        )
    )


    assert len(
        result
    ) == 1