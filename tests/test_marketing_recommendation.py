import sys

sys.path.insert(
    0,
    "app"
)

from telegram_core_factory import create_telegram_core



def test_marketing_recommendation_creates_marketing_action():


    core = create_telegram_core()


    service = (
        core["core"]
        .orchestrator_service
        .entry_service
        .main_flow_service
        .business_service
        .business_flow_service
        .planner_service
        .recommendation_service
    )


    result = (
        service.analyze(
            {
                "marketing_problem": True
            }
        )
    )


    assert (
        result["error"]
        is
        False
    )


    assert (
        result["recommendations"][0]["type"]
        ==
        "marketing"
    )


    assert (
        "рекламных каналов"
        in
        result["recommendations"][0]["message"]
    )