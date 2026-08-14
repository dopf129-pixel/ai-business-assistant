import sys

sys.path.insert(
    0,
    "app"
)


from telegram_core_factory import create_telegram_core


USER_ID = 1000



def test_retry_limit_blocks_after_max_attempts():


    core = create_telegram_core()


    execution_service = (
        core["execution_service"]
    )


    assert hasattr(
        execution_service,
        "retry_policy"
    )


    execution_service.retry_policy.max_attempts = 3


    result = (
        execution_service
        .retry_policy
        .can_retry(
            4
        )
    )


    assert (
        result
        ==
        False
    )