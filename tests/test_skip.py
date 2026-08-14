import sys

sys.path.insert(
    0,
    "app"
)

from telegram_core_factory import create_telegram_core


USER_ID = 505204945



def test_skip_action():


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



    result = core["core"].ask(
        "пропусти этот шаг",
        USER_ID
    )



    assert (
        "Шаг пропущен"
        in
        result["message"]
    )



    status = (
        core["task_service"]
        .get_task_status(
            USER_ID
        )
    )



    first_action = (
        status["actions"][0]
    )


    assert (
        first_action["status"]
        ==
        "SKIPPED"
    )



    next_result = core["core"].ask(
        "что дальше",
        USER_ID
    )


    assert (
        "Проверить остатки товара"
        in
        next_result["message"]
    )