import sys

sys.path.insert(
    0,
    "app"
)

from telegram_core_factory import create_telegram_core



def test_priority_keeps_existing_priority():


    core = create_telegram_core()


    service = (
        core["core"]
        .orchestrator_service
        .entry_service
        .main_flow_service
        .business_service
        .business_flow_service
        .planner_service
        .executor_service
        .priority_service
    )


    result = (
        service.resolve(
            {
                "type":
                    "marketing",

                "priority":
                    "HIGH"
            }
        )
    )


    assert (
        result["action"]["priority"]
        ==
        "HIGH"
    )



def test_marketing_default_priority():


    core = create_telegram_core()


    service = (
        core["core"]
        .orchestrator_service
        .entry_service
        .main_flow_service
        .business_service
        .business_flow_service
        .planner_service
        .executor_service
        .priority_service
    )


    result = (
        service.resolve(
            {
                "type":
                    "marketing"
            }
        )
    )


    assert (
        result["action"]["priority"]
        ==
        "MEDIUM"
    )