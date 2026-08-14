import sys
sys.path.insert(0, "app")

from telegram_core_factory import create_telegram_core


USER_ID = 505204945


def test_cannot_execute_paused_task():

    core = create_telegram_core()


    core["task_service"].create_task(
        USER_ID,
        "Тестовая задача",
        [
            {
                "title": "Шаг 1",
                "type": "test",
                "status": "NEW",
                "priority": "HIGH"
            }
        ]
    )


    pause = (
        core["task_service"]
        .pause_task(USER_ID)
    )


    assert (
        pause["status"]
        ==
        "PAUSED"
    )


    result = (
        core["core"]
        .ask(
            "да",
            USER_ID
        )
    )


    assert (
        result["error"]
        is True
        or
        "пауз"
        in result.get(
            "message",
            ""
        ).lower()
        or
        "нельзя"
        in result.get(
            "message",
            ""
        ).lower()
    )