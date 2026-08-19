from app.services.assistant_development_agent import (
    AssistantDevelopmentAgent,
)


class MockWorkflow:

    def start_workflow(self, change):

        return {
            "change": change,
            "status": "started",
            "steps": [
                "change_analysis",
                "test_validation",
                "documentation_validation",
                "checkpoint_preparation",
            ],
        }



class MockBrainManager:

    def add_changelog_entry(
        self,
        title,
        description,
    ):
        return None



class MockCheckpointService:

    def prepare_checkpoint(
        self,
        files,
        message,
    ):

        return {
            "status": "ready",
            "files_changed": len(files),
            "files": files,
            "message": message,
        }







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



def test_create_development_report():

    agent = AssistantDevelopmentAgent()

    result = agent.create_development_report(
        "Add new feature",
        {
            "status": "started",
        },
        {
            "status": "updated",
        },
        {
            "status": "ready",
        },
    )

    assert result["agent"] == "AssistantDevelopmentAgent"

    assert result["status"] == "completed"

    assert result["summary"]["workflow"]["status"] == "started"

    assert result["summary"]["project_brain"]["status"] == "updated"

    assert result["summary"]["checkpoint"]["status"] == "ready"



def test_run_development_cycle():

    agent = AssistantDevelopmentAgent()

    result = agent.run_development_cycle(
        "Add new feature"
    )

    assert result["agent"] == "AssistantDevelopmentAgent"

    assert result["status"] == "workflow_completed"

    assert result["workflow"] == "not_connected"

    assert result["project_brain"] == "not_connected"

    assert result["checkpoint"] == "not_connected"




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

    assert result["status"] == "workflow_completed"

    assert result["workflow"]["status"] == "started"

    assert result["project_brain"]["status"] == "updated"

    assert result["checkpoint"]["status"] == "ready"

    assert result["report"]["status"] == "completed"

    assert result["report"]["summary"]["workflow"]["status"] == "started"

