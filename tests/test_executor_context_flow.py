import sys

sys.path.insert(
    0,
    "app"
)

from telegram_core_factory import create_telegram_core


USER_ID = 505204945



def test_sales_executor_keeps_context_in_history():


    core = create_telegram_core()


    core["task_service"].create_task(
        USER_ID,
        "Создание плана действий",
        [
            {
                "title":
                    "Проверить причины падения продаж",

                "type":
                    "sales",

                "status":
                    "NEW",

                "priority":
                    "HIGH",

                "context":
                    {
                        "reason":
                            "Продажи снизились"
                    }
            }
        ]
    )


    next_result = (
        core["core"]
        .ask(
            "что дальше",
            USER_ID
        )
    )


    assert (
        "Проверить причины падения продаж"
        in
        next_result["message"]
    )


    execute_result = (
        core["core"]
        .ask(
            "да",
            USER_ID
        )
    )


    assert (
        execute_result["error"]
        is
        False
    )


    assert (
        execute_result["message"]
        .startswith(
            "Действие выполнено"
        )
    )


    history = (
        core["task_service"]
        .get_task_history(
            USER_ID
        )
    )


    action = (
        history["history"][0]
    )


    assert (
        action["result"]["result"]["type"]
        ==
        "sales"
    )


    assert (
        action["result"]["result"]["priority"]
        ==
        "HIGH"
    )


    assert (
        "Продажи снизились"
        in
        action["result"]["result"]["details"]
        [-1]
    )