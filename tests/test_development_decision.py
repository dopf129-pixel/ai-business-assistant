from app.services.assistant_development_decision_service import (
    AssistantDevelopmentDecisionService,
)



def test_decision_complete():

    service = AssistantDevelopmentDecisionService()

    result = service.evaluate(
        {
            "status": "completed",
        }
    )

    assert result["decision"] == "complete"

    assert result["next_action"] == "checkpoint_ready"



def test_decision_blocked():

    service = AssistantDevelopmentDecisionService()

    result = service.evaluate(
        {
            "status": "failed",
        }
    )

    assert result["decision"] == "blocked"

    assert result["next_action"] == "review_required"
