import sys

sys.path.insert(
    0,
    "app"
)

from telegram_core_factory import create_telegram_core


USER_ID = 505204945



def test_execution_response_contains_executor_details():


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


    result = (
        core["core"]
        .ask(
            "да",
            USER_ID
        )
    )


    assert (
        result["error"]
        is
        False
    )


    assert (
        "Действие выполнено"
        in
        result["message"]
    )


    assert (
        "Анализ продаж выполнен"
        in
        result["message"]
    )


    assert (
        "Продажи снизились"
        in
        result["message"]
    )