from app.services.assistant_development_action_service import (
    AssistantDevelopmentActionService,
)



def test_action_continue():

    service = AssistantDevelopmentActionService()

    result = service.execute(
        {
            "decision": "complete",
        }
    )

    assert result["action"] == "continue"

    assert result["next_step"] == "checkpoint_ready"

    assert result["status"] == "ready"



def test_action_stop():

    service = AssistantDevelopmentActionService()

    result = service.execute(
        {
            "decision": "blocked",
        }
    )

    assert result["action"] == "stop"

    assert result["next_step"] == "review_required"

    assert result["status"] == "blocked"
