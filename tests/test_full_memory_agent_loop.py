import sys

sys.path.insert(
    0,
    "app"
)


from telegram_core_factory import create_telegram_core



def test_full_agent_memory_loop():


    core = create_telegram_core()


    memory_service = (
        core["memory_service"]
    )


    feedback_service = (
        core["feedback_service"]
    )


    # прошлый опыт

    memory_service.remember(

        {

            "action":
                "Получить данные",

            "status":
                "DONE",

            "solution":
                "Использовать резервный источник"

        }

    )


    # новое выполнение

    feedback_service.record(

        {

            "action":
                "Новая задача",

            "status":
                "DONE"

        }

    )


    memories = (
        memory_service.recall()
    )


    assert len(
        memories
    ) == 2


    assert (
        memories[0]["action"]
        ==
        "Получить данные"
    )


    assert (
        memories[1]["action"]
        ==
        "Новая задача"
    )