from app.services.assistant_development_workflow_service import (
    AssistantDevelopmentWorkflowService,
)


def test_workflow_initialization():

    service = AssistantDevelopmentWorkflowService()

    result = service.start_workflow(
        "new service change"
    )

    assert result["status"] == "started"

    assert "change_analysis" in result["steps"]
    assert "test_validation" in result["steps"]
    assert "documentation_validation" in result["steps"]
    assert "checkpoint_preparation" in result["steps"]


def test_complete_workflow_step():

    service = AssistantDevelopmentWorkflowService()

    service.start_workflow(
        "change"
    )

    result = service.complete_step(
        "test_validation"
    )

    assert result["status"] == "completed"