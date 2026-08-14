import sys

sys.path.insert(
    0,
    "app"
)

from telegram_core_factory import create_telegram_core


USER_ID = 505204945



def test_pause_task_command():


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



    result = core["core"].ask(
        "поставь задачу на паузу",
        USER_ID
    )


    assert (
        "пауз"
        in
        result["message"].lower()
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
        "PAUSED"
    )