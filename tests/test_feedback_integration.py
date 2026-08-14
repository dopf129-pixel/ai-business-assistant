import sys

sys.path.insert(
    0,
    "app"
)


from telegram_core_factory import create_telegram_core



def test_execution_service_has_feedback_service():


    core = create_telegram_core()


    execution_service = (
        core["execution_service"]
    )


    assert hasattr(
        execution_service,
        "feedback_service"
    )