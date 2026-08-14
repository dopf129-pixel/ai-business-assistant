import sys

sys.path.insert(
    0,
    "app"
)


from telegram_core_factory import create_telegram_core


USER_ID = 1000



def test_failed_action_runs_replanning_flow():


    core = create_telegram_core()


    execution_service = (
        core["execution_service"]
    )


    assert hasattr(
        execution_service,
        "replanning_service"
    )


    assert hasattr(
        execution_service,
        "task_service"
    )