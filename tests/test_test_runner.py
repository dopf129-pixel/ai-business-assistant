from app.services.assistant_test_runner_service import (
    AssistantTestRunnerService,
)


def test_create_test_report():

    service = AssistantTestRunnerService()

    result = service.create_test_report(
        passed=10,
        failed=0,
        total=10,
    )

    assert result["status"] == "passed"

    assert result["passed"] == 10

    assert result["failed"] == 0


def test_failed_test_report():

    service = AssistantTestRunnerService()

    result = service.create_test_report(
        passed=9,
        failed=1,
        total=10,
    )

    assert result["status"] == "failed"
