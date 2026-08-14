import sys

sys.path.insert(
    0,
    "app"
)

from telegram_core_factory import create_telegram_core


USER_ID = 505204945



def test_action_keeps_context():


    core = create_telegram_core()


    recommendations = [
        {
            "type": "sales",
            "message": "Проверить причины падения продаж",
            "priority": "HIGH",
            "reason": "Продажи снизились"
        }
    ]


    result = (
        core["core"]
        .orchestrator_service
        .entry_service
        .main_flow_service
        .business_service
        .business_flow_service
        .planner_service
        .executor_service
        .action_generator_service
        .generate(
            recommendations
        )
    )


    assert (
        result["error"]
        is
        False
    )


    action = (
        result["actions"][0]
    )


    assert (
        action["title"]
        ==
        "Проверить причины падения продаж"
    )


    assert (
        action["type"]
        ==
        "sales"
    )



def test_action_keeps_priority_and_context():


    core = create_telegram_core()


    recommendations = [
        {
            "type": "sales",
            "message": "Проверить причины падения продаж",
            "priority": "HIGH",
            "reason": "Продажи снизились"
        }
    ]


    result = (
        core["core"]
        .orchestrator_service
        .entry_service
        .main_flow_service
        .business_service
        .business_flow_service
        .planner_service
        .executor_service
        .action_generator_service
        .generate(
            recommendations
        )
    )


    action = (
        result["actions"][0]
    )


    assert (
        action["priority"]
        ==
        "HIGH"
    )


    assert (
        action["context"]["reason"]
        ==
        "Продажи снизились"
    )