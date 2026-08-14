import sys
sys.path.insert(0, "app")

from telegram_core_factory import create_telegram_core


USER_ID = 505204945


def test_resume_task_command():

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

    pause = core["core"].ask(
        "поставь задачу на паузу",
        USER_ID
    )

    assert "пауз" in pause["message"].lower()


    resume = core["core"].ask(
        "продолжи задачу",
        USER_ID
    )

    assert "возобнов" in resume["message"].lower()


    status = core["task_service"].get_task_status(USER_ID)

    assert status["status"] == "ACTIVE"