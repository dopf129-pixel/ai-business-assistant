from app.services.assistant_project_verification_service import (
    AssistantProjectVerificationService,
)
from app.services.assistant_test_runner_service import (
    AssistantTestRunnerService,
)


CURRENT_SHA = "4d1a7e3dde453cb71ca2a64f491c0c7a05562c60"
OLD_SHA = "11883f901d3bb344816735b834392a59185c0c81"


def test_v232_legacy_test_report_remains_unbound():
    report = AssistantTestRunnerService().create_test_report(
        passed=10,
        failed=0,
        total=10,
    )

    assert report["status"] == "passed"
    assert report["sha_bound"] is False
    assert report["commit_sha"] is None
    assert "test_report_id" not in report


def test_v233_sha_bound_report_has_deterministic_identity():
    report = AssistantTestRunnerService().create_test_report(
        passed=982,
        failed=0,
        total=982,
        commit_sha=OLD_SHA,
    )

    assert report["sha_bound"] is True
    assert report["commit_sha"] == OLD_SHA
    assert report["test_report_id"] == (
        "pytest:" + OLD_SHA + ":982:0:982"
    )


def test_v233_invalid_counts_fail_closed():
    report = AssistantTestRunnerService().create_test_report(
        passed=10,
        failed=1,
        total=10,
        commit_sha=CURRENT_SHA,
    )

    assert report["error"] is True
    assert report["status"] == "invalid"
    assert report["code"] == "TEST_REPORT_COUNTS_INVALID"


def test_v234_current_sha_bound_green_report_verifies_current():
    report = AssistantTestRunnerService().create_test_report(
        passed=1000,
        failed=0,
        total=1000,
        commit_sha=CURRENT_SHA,
    )

    result = AssistantProjectVerificationService().evaluate(
        CURRENT_SHA,
        report,
    )

    assert result["status"] == "CURRENT_VERIFIED"
    assert result["current_suite_verified"] is True
    assert result["current_suite_passed"] is True
    assert result["baseline_is_current"] is True


def test_v235_old_green_report_is_stale_baseline_not_current_verification():
    report = AssistantTestRunnerService().create_test_report(
        passed=982,
        failed=0,
        total=982,
        commit_sha=OLD_SHA,
    )

    result = AssistantProjectVerificationService().evaluate(
        CURRENT_SHA,
        report,
    )

    assert result["status"] == "STALE_BASELINE"
    assert result["current_suite_verified"] is False
    assert result["current_suite_passed"] is False
    assert result["baseline_is_current"] is False
    assert result["baseline"]["passed"] == 982
    assert result["baseline"]["commit_sha"] == OLD_SHA


def test_v235_unbound_green_report_cannot_verify_any_sha():
    report = AssistantTestRunnerService().create_test_report(
        passed=10,
        failed=0,
        total=10,
    )

    result = AssistantProjectVerificationService().evaluate(
        CURRENT_SHA,
        report,
    )

    assert result["status"] == "UNBOUND_TEST_REPORT"
    assert result["current_suite_verified"] is False
    assert result["current_suite_passed"] is False


def test_v236_current_failed_report_is_verified_failure_not_green():
    report = AssistantTestRunnerService().create_test_report(
        passed=999,
        failed=1,
        total=1000,
        commit_sha=CURRENT_SHA,
    )

    result = AssistantProjectVerificationService().evaluate(
        CURRENT_SHA,
        report,
    )

    assert result["status"] == "CURRENT_FAILED"
    assert result["current_suite_verified"] is True
    assert result["current_suite_passed"] is False


def test_v236_forged_report_id_fails_closed():
    report = AssistantTestRunnerService().create_test_report(
        passed=1000,
        failed=0,
        total=1000,
        commit_sha=CURRENT_SHA,
    )
    report["test_report_id"] = "pytest:forged:1000:0:1000"

    result = AssistantProjectVerificationService().evaluate(
        CURRENT_SHA,
        report,
    )

    assert result["status"] == "TEST_REPORT_ID_MISMATCH"
    assert result["current_suite_verified"] is False
    assert result["current_suite_passed"] is False


def test_v237_markdown_explicitly_marks_stale_baseline():
    report = AssistantTestRunnerService().create_test_report(
        passed=982,
        failed=0,
        total=982,
        commit_sha=OLD_SHA,
    )
    service = AssistantProjectVerificationService()
    evaluation = service.evaluate(CURRENT_SHA, report)

    text = service.render_markdown(evaluation)

    assert "State: STALE_BASELINE" in text
    assert "Current full suite verified: no" in text
    assert "Passed: 982" in text
    assert OLD_SHA in text
    assert CURRENT_SHA in text


def test_v237_manually_forged_inconsistent_counts_fail_closed():
    report = {
        "error": False,
        "status": "passed",
        "passed": 999,
        "failed": 0,
        "total": 1000,
        "commit_sha": CURRENT_SHA,
        "sha_bound": True,
        "test_report_id": "pytest:" + CURRENT_SHA + ":999:0:1000",
    }

    result = AssistantProjectVerificationService().evaluate(
        CURRENT_SHA,
        report,
    )

    assert result["status"] == "TEST_REPORT_COUNTS_INVALID"
    assert result["current_suite_verified"] is False
    assert result["current_suite_passed"] is False


def test_v237_manually_forged_status_contradiction_fails_closed():
    report = {
        "error": False,
        "status": "passed",
        "passed": 999,
        "failed": 1,
        "total": 1000,
        "commit_sha": CURRENT_SHA,
        "sha_bound": True,
        "test_report_id": "pytest:" + CURRENT_SHA + ":999:1:1000",
    }

    result = AssistantProjectVerificationService().evaluate(
        CURRENT_SHA,
        report,
    )

    assert result["status"] == "TEST_REPORT_STATUS_CONTRADICTORY"
    assert result["current_suite_verified"] is False
    assert result["current_suite_passed"] is False


def test_v237_non_sha_identifier_cannot_bind_report():
    report = AssistantTestRunnerService().create_test_report(
        passed=10,
        failed=0,
        total=10,
        commit_sha="main",
    )

    assert report["commit_sha"] is None
    assert report["sha_bound"] is False
    assert "test_report_id" not in report

    result = AssistantProjectVerificationService().evaluate(
        "main",
        report,
    )

    assert result["error"] is True
    assert result["code"] == "CURRENT_SHA_REQUIRED"
