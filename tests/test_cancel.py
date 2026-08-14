import sys

sys.path.insert(
    0,
    "app"
)

from telegram_core_factory import create_telegram_core



USER_ID = 505204945



def test_cancel_task():


    core = create_telegram_core()



    core["task_service"].create_task(
        USER_ID,
        "Создание плана действий",
        [
            {
                "title": "Проверить продажи",
                "type": "sales",
                "status": "NEW",
                "priority": "HIGH"
            }
        ]
    )



    result = core["core"].ask(
        "отмени задачу",
        USER_ID
    )



    assert (
        "Задача отменена"
        in
        result["message"]
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
        "CANCELLED"
    )