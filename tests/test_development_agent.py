from app.services.assistant_development_agent import (
    AssistantDevelopmentAgent,
)


def test_create_development_plan():

    agent = AssistantDevelopmentAgent()

    result = agent.create_plan(
        "Add new service"
    )

    assert result["agent"] == "AssistantDevelopmentAgent"

    assert "change_analysis" in result["steps"]
    assert "test_validation" in result["steps"]
    assert "documentation_validation" in result["steps"]
    assert "checkpoint_preparation" in result["steps"]



def test_create_report():

    agent = AssistantDevelopmentAgent()

    result = agent.create_report(
        "Add new service",
        "completed",
    )

    assert result["status"] == "completed"