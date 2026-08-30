import sys

sys.path.insert(
    0,
    "app"
)

from telegram_core_factory import create_telegram_core


USER_ID = 505204945



def test_cancelled_task_cannot_execute():


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



    cancel_result = core["core"].ask(
        "отмени задачу",
        USER_ID
    )


    assert (
        "Задача отменена"
        in
        cancel_result["message"]
    )



    execute_result = core["core"].ask(
        "да",
        USER_ID
    )



    assert (
        execute_result["error"]
        is
        True
    )



    assert (
        "отмен"
        in
        execute_result["message"].lower()
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