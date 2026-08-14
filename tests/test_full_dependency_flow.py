import sys

sys.path.insert(
    0,
    "app"
)

from telegram_core_factory import create_telegram_core


USER_ID = 505204945



def test_full_flow_with_dependent_actions():


    core = create_telegram_core()


    result = (
        core["core"]
        .ask(
            "создай план действий",
            USER_ID
        )
    )


    assert (
        result["error"]
        is
        False
    )


    core["task_service"].create_task(
        USER_ID,
        "Маркетинговый план",
        [
            {
                "title":
                    "Проверить продажи",

                "type":
                    "sales",

                "status":
                    "NEW",

                "priority":
                    "HIGH"
            },

            {
                "title":
                    "Запустить рекламу",

                "type":
                    "marketing",

                "status":
                    "NEW",

                "depends_on":
                    [
                        "Проверить продажи"
                    ]
            }
        ]
    )


    first = (
        core["task_service"]
        .get_current_action(
            USER_ID
        )
    )


    assert (
        first["action"]["title"]
        ==
        "Проверить продажи"
    )


    execute = (
        core["core"]
        .ask(
            "да",
            USER_ID
        )
    )


    assert (
        execute["error"]
        is
        False
    )


    second = (
        core["task_service"]
        .get_current_action(
            USER_ID
        )
    )


    assert (
        second["action"]["title"]
        ==
        "Запустить рекламу"
    )