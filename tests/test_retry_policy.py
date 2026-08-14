import sys

sys.path.insert(
    0,
    "app"
)


from telegram_core_factory import create_telegram_core



def test_retry_policy_detects_retryable_error():


    core = create_telegram_core()


    execution_service = (
        core["execution_service"]
    )


    assert hasattr(
        execution_service,
        "retry_policy"
    )


    result = (
        execution_service
        .retry_policy
        .should_retry(
            "timeout error"
        )
    )


    assert (
        result
        ==
        True
    )