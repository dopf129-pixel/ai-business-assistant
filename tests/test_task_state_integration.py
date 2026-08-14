import sys

sys.path.insert(
    0,
    "app"
)

from telegram_core_factory import create_telegram_core

from core.task_states import TaskStatus



USER_ID = 505204945



def test_pause_and_resume_task():


    core = create_telegram_core()



    core["task_service"].create_task(
        USER_ID,
        "Создание плана действий",
        [
            {
                "title": "Проверить причины падения продаж",
                "type": "sales",
                "status": "NEW",
                "priority": "HIGH"
            }
        ]
    )



    pause_result = (
        core["task_service"]
        .pause_task(
            USER_ID
        )
    )


    assert (
        pause_result["error"]
        is
        False
    )



    status = (
        core["task_service"]
        .get_task_status(
            USER_ID
        )
    )


    assert (
        status["status"]
        ==
        TaskStatus.PAUSED
    )



    resume_result = (
        core["task_service"]
        .resume_task(
            USER_ID
        )
    )


    assert (
        resume_result["error"]
        is
        False
    )



    status = (
        core["task_service"]
        .get_task_status(
            USER_ID
        )
    )


    assert (
        status["status"]
        ==
        TaskStatus.ACTIVE
    )