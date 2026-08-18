import sys

sys.path.insert(
    0,
    "app"
)

from services.assistant_change_impact_service import (
    AssistantChangeImpactService
)



def test_change_impact_detects_action_generator_dependencies():


    service = (
        AssistantChangeImpactService()
    )


    result = (
        service
        .analyze(
            "assistant_action_generator_service.py"
        )
    )


    assert (
        result["changed_file"]
        ==
        "assistant_action_generator_service.py"
    )


    assert (
        "AssistantActionPlanExecutorService"
        in
        result["affected_services"]
    )


    assert (
        "test_action_context.py"
        in
        result["affected_tests"]
    )


    assert (
        "TEST_MAP.md"
        in
        result["affected_docs"]
    )