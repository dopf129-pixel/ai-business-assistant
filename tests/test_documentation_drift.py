from app.services.assistant_documentation_drift_service import (
    AssistantDocumentationDriftService,
)


def test_detect_missing_documentation(tmp_path):

    services = (
        tmp_path
        / "app"
        / "services"
    )

    services.mkdir(
        parents=True
    )

    (services / "assistant_test_service.py").write_text(
        "",
        encoding="utf-8"
    )


    brain = (
        tmp_path
        / "project_brain"
    )

    brain.mkdir()

    (
        brain / "TEST_MAP.md"
    ).write_text(
        "# Tests",
        encoding="utf-8"
    )


    service = AssistantDocumentationDriftService(
        tmp_path
    )

    result = service.get_missing_documentation()


    assert "assistant_test_service" in result