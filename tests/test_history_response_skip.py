import sys

sys.path.insert(
    0,
    "app"
)

from telegram_core_factory import create_telegram_core


USER_ID = 505204945



def test_history_response_shows_skip_reason():


    core = create_telegram_core()


    core["task_service"].create_task(
        USER_ID,
        "История с пропуском",
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
        core["core"]
        .ask(
            "покажи историю",
            USER_ID
        )
    )


    assert (
        "История задачи"
        in
        result["message"]
    )


    assert (
        "Запустить рекламу"
        in
        result["message"]
    )


    assert (
        "Условие не выполнено"
        in
        result["message"]
    )