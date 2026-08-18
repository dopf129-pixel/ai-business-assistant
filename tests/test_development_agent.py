from app.services.assistant_development_agent import (
    AssistantDevelopmentAgent,
)


class MockWorkflow:
    pass


class MockBrainManager:
    pass


class MockCheckpointService:
    pass


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



def test_run_development_cycle():

    agent = AssistantDevelopmentAgent()

    result = agent.run_development_cycle(
        "Add new feature"
    )

    assert result["agent"] == "AssistantDevelopmentAgent"

    assert result["status"] == "workflow_ready"

    assert result["project_brain"] == "ready"

    assert result["checkpoint"] == "ready"



def test_run_development_cycle_with_tools():

    agent = AssistantDevelopmentAgent(
        workflow=MockWorkflow(),
        brain_manager=MockBrainManager(),
        checkpoint_service=MockCheckpointService(),
    )

    result = agent.run_development_cycle(
        "Add new feature"
    )

    assert result["agent"] == "AssistantDevelopmentAgent"

    assert result["status"] == "workflow_ready"

    assert result["workflow"] == "connected"

    assert result["project_brain"] == "connected"

    assert result["checkpoint"] == "connected"
