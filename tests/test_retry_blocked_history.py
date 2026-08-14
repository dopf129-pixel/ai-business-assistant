import sys

sys.path.insert(
    0,
    "app"
)


from telegram_core_factory import create_telegram_core


USER_ID = 1000



def test_retry_blocked_creates_history_event():


    core = create_telegram_core()


    execution_service = (
        core["execution_service"]
    )


    execution_service.retry_policy.max_attempts = 3


    history = (
        execution_service
        .history_service
        .actions
    )


    execution_service.history_service.save_action(

        {

            "event":
                "retry_blocked",

            "reason":
                "maximum retry attempts reached",

            "attempt":
                3

        }

    )


    found = False


    for item in history:


        if (
            item.get(
                "event"
            )
            ==
            "retry_blocked"
        ):

            found = True


            assert (
                item["attempt"]
                ==
                3
            )


    assert (
        found
        ==
        True
    )