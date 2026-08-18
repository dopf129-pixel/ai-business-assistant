from pathlib import Path

from app.services.assistant_documentation_manager import (
    AssistantDocumentationManager,
)


def test_append_changelog(tmp_path):
    brain = tmp_path / "project_brain"
    brain.mkdir()

    changelog = brain / "CHANGELOG.md"
    changelog.write_text(
        "# Changelog\n\nOld history",
        encoding="utf-8",
    )

    manager = AssistantDocumentationManager(tmp_path)

    manager.append_changelog(
        "Test Change",
        "New documentation entry",
    )

    content = changelog.read_text(
        encoding="utf-8"
    )

    assert "Old history" in content
    assert "Test Change" in content
    assert "New documentation entry" in content


def test_append_decision(tmp_path):
    brain = tmp_path / "project_brain"
    brain.mkdir()

    decisions = brain / "DECISIONS.md"
    decisions.write_text(
        "# Decisions\n\nOld decision",
        encoding="utf-8",
    )

    manager = AssistantDocumentationManager(tmp_path)

    manager.append_decision(
        "Documentation Layer",
        "New decision",
    )

    content = decisions.read_text(
        encoding="utf-8"
    )

    assert "Old decision" in content
    assert "Documentation Layer" in content
    assert "New decision" in content