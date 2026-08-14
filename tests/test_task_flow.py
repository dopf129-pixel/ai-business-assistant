import sys

sys.path.insert(
    0,
    "app"
)

from telegram_core_factory import create_telegram_core



USER_ID = 505204945



def create_test_task():

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
            },
            {
                "title": "Проверить остатки товара",
                "type": "stock",
                "status": "NEW",
                "priority": "HIGH"
            }
        ]
    )

    return core





def test_execute_two_actions():


    core = create_test_task()



    result = core["core"].ask(
        "что дальше",
        USER_ID
    )


    assert (
        "Проверить причины падения продаж"
        in
        result["message"]
    )



    result = core["core"].ask(
        "да",
        USER_ID
    )


    assert (
        result["error"]
        is
        False
    )



    result = core["core"].ask(
        "что дальше",
        USER_ID
    )


    assert (
        "Проверить остатки товара"
        in
        result["message"]
    )