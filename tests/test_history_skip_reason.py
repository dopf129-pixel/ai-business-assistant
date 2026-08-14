import sys

sys.path.insert(
    0,
    "app"
)

from telegram_core_factory import create_telegram_core


USER_ID = 505204945



def test_history_shows_skip_reason():


    core = create_telegram_core()


    core["task_service"].create_task(
        USER_ID,
        "История пропуска",
        [

            {
                "title":
                    "Запустить рекламу",

                "type":
                    "marketing",

                "status":
                    "SKIPPED",

                "skip_reason":
                    "Условие не выполнено"

            }

        ]
    )


    result = (
        core["task_service"]
        .get_task_history(
            USER_ID
        )
    )


    item = (
        result["history"][0]
    )


    assert (
        item["status"]
        ==
        "SKIPPED"
    )


    assert (
        item.get(
            "message"
        )
        ==
        "Условие не выполнено"
    )