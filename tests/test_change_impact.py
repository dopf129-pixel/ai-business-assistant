from app.services.assistant_change_impact_service import (
    AssistantChangeImpactService,
)


def test_analyze_service_change():

    service = AssistantChangeImpactService()

    result = service.analyze_change(
        [
            "app/services/user_service.py"
        ]
    )

    assert (
        "tests/test_user_service.py"
        in result["tests_required"]
    )

    assert (
        "project_brain/TEST_MAP.md"
        in result["documentation_required"]
    )


def test_analyze_empty_change():

    service = AssistantChangeImpactService()

    result = service.analyze_change(
        []
    )

    assert result["files"] == []
