import sys

sys.path.insert(
    0,
    "app"
)


from telegram_core_factory import create_telegram_core



def test_planner_uses_memory_experience():


    core = create_telegram_core()


    memory_service = (
        core["memory_service"]
    )


    memory_service.remember(

        {

            "action":
                "Получить данные из API",

            "status":
                "DONE",

            "solution":
                "Использовать резервный источник"

        }

    )


    memories = (
        memory_service.recall(
            "Получить данные из API"
        )
    )


    assert len(
        memories
    ) == 1


    assert (
        memories[0]["action"]
        ==
        "Получить данные из API"
    )