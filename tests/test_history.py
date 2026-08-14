import sys

sys.path.insert(
    0,
    "app"
)

from telegram_core_factory import create_telegram_core


USER_ID = 505204945



def test_task_history():


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



    execute_result = core["core"].ask(
        "что дальше",
        USER_ID
    )


    assert (
        "Проверить причины падения продаж"
        in
        execute_result["message"]
    )



    done_result = core["core"].ask(
        "да",
        USER_ID
    )


    assert (
        done_result["error"]
        is
        False
    )



    history_result = core["core"].ask(
        "покажи историю",
        USER_ID
    )


    assert (
        "История задачи"
        in
        history_result["message"]
    )


    assert (
        "Проверить причины падения продаж"
        in
        history_result["message"]
    )


    assert (
        "Действие выполнено"
        in
        history_result["message"]
    )