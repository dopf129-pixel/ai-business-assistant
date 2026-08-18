from app.services.assistant_git_checkpoint_service import (
    AssistantGitCheckpointService,
)


def test_prepare_checkpoint():

    service = AssistantGitCheckpointService()

    result = service.prepare_checkpoint(
        [
            "app/service.py",
            "tests/test_service.py",
        ],
        "Add new service",
    )

    assert result["status"] == "ready"
    assert result["files_changed"] == 2
    assert result["message"] == "Add new service"


def test_changed_files():

    service = AssistantGitCheckpointService()

    files = service.get_changed_files(
        [
            "file1.py",
            "file2.py",
        ]
    )

    assert len(files) == 2