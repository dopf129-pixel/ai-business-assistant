from app.services.assistant_project_brain_manager import (
    AssistantProjectBrainManager,
)


def test_append_changelog(tmp_path):

    brain = tmp_path / "project_brain"
    brain.mkdir()

    file = brain / "CHANGELOG.md"

    file.write_text(
        "Old history",
        encoding="utf-8",
    )

    manager = AssistantProjectBrainManager(
        tmp_path
    )

    manager.add_changelog_entry(
        "New Feature",
        "Added by agent",
    )

    result = file.read_text(
        encoding="utf-8"
    )

    assert "Old history" in result
    assert "New Feature" in result
    assert "Added by agent" in result



def test_append_test_map(tmp_path):

    brain = tmp_path / "project_brain"
    brain.mkdir()

    file = brain / "TEST_MAP.md"

    file.write_text(
        "Old tests",
        encoding="utf-8",
    )

    manager = AssistantProjectBrainManager(
        tmp_path
    )

    manager.add_test_map_entry(
        "TestService",
        "test_service.py",
    )

    result = file.read_text(
        encoding="utf-8",
    )

    assert "Old tests" in result
    assert "TestService" in result