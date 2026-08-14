import sys
sys.path.insert(0, "app")

from telegram_core_factory import create_telegram_core


USER_ID = 505204945


def test_full_task_lifecycle():

    core = create_telegram_core()


    core["task_service"].create_task(
        USER_ID,
        "Полный цикл задачи",
        [
            {
                "title": "Первый шаг",
                "type": "test",
                "status": "NEW",
                "priority": "HIGH"
            }
        ]
    )


    pause = (
        core["task_service"]
        .pause_task(
            USER_ID
        )
    )


    assert (
        pause["status"]
        ==
        "PAUSED"
    )


    blocked = (
        core["core"]
        .ask(
            "да",
            USER_ID
        )
    )


    assert (
        "пауз"
        in
        blocked["message"].lower()
    )


    resume = (
        core["task_service"]
        .resume_task(
            USER_ID
        )
    )


    assert (
        resume["status"]
        ==
        "ACTIVE"
    )


    executed = (
        core["core"]
        .ask(
            "да",
            USER_ID
        )
    )


    assert (
        executed["error"]
        is
        False
    )