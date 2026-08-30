import json
from pathlib import Path

from ci_verification_manifest import main as manifest_cli_main
from services.assistant_ci_verification_manifest_service import (
    AssistantCiVerificationManifestService,
)
from services.assistant_project_verification_service import (
    AssistantProjectVerificationService,
)


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "verify.yml"
CURRENT_SHA = "a" * 40
OLD_SHA = "b" * 40


def _write_junit(
    path,
    tests=10,
    failures=0,
    errors=0,
    skipped=0,
):
    path.write_text(
        (
            '<testsuites>'
            '<testsuite name="pytest" '
            f'tests="{tests}" '
            f'failures="{failures}" '
            f'errors="{errors}" '
            f'skipped="{skipped}">'
            '</testsuite>'
            '</testsuites>'
        ),
        encoding="utf-8",
    )


def _build(path, sha=CURRENT_SHA):
    return AssistantCiVerificationManifestService().build_from_junit(
        junit_path=str(path),
        commit_sha=sha,
        workflow="Verify",
        event="push",
        run_id=123456,
        run_number=42,
    )


def test_v418_junit_parser_builds_canonical_sha_bound_green_report(tmp_path):
    junit = tmp_path / "pytest-junit.xml"
    _write_junit(junit, tests=10)

    manifest = _build(junit)

    assert manifest["error"] is False
    assert manifest["status"] == "passed"
    assert manifest["passed"] == 10
    assert manifest["failed"] == 0
    assert manifest["total"] == 10
    assert manifest["skipped"] == 0
    assert manifest["commit_sha"] == CURRENT_SHA
    assert manifest["sha_bound"] is True
    assert manifest["test_report_id"] == (
        "pytest:" + CURRENT_SHA + ":10:0:10"
    )


def test_v419_junit_failures_errors_and_skips_are_normalized_without_count_forgery(tmp_path):
    junit = tmp_path / "pytest-junit.xml"
    _write_junit(
        junit,
        tests=12,
        failures=2,
        errors=1,
        skipped=3,
    )

    manifest = _build(junit)

    assert manifest["status"] == "failed"
    assert manifest["junit_tests"] == 12
    assert manifest["junit_failures"] == 2
    assert manifest["junit_errors"] == 1
    assert manifest["skipped"] == 3
    assert manifest["failed"] == 3
    assert manifest["total"] == 9
    assert manifest["passed"] == 6
    assert manifest["passed"] + manifest["failed"] == manifest["total"]


def test_v420_manifest_identity_is_deterministic_and_validation_recomputes_test_report(tmp_path):
    junit = tmp_path / "pytest-junit.xml"
    _write_junit(junit, tests=7)

    service = AssistantCiVerificationManifestService()
    first = _build(junit)
    second = _build(junit)

    assert first == second
    assert first["verification_manifest_id"].startswith(
        "ci-verification:"
    )

    validation = service.validate(first)
    assert validation["status"] == "CI_VERIFICATION_MANIFEST_VALID"
    assert validation["test_report_id"] == first["test_report_id"]
    assert validation["verification_manifest_id"] == (
        first["verification_manifest_id"]
    )


def test_v421_tampered_counts_or_manifest_id_fail_closed(tmp_path):
    junit = tmp_path / "pytest-junit.xml"
    _write_junit(junit, tests=7)
    service = AssistantCiVerificationManifestService()
    manifest = _build(junit)

    forged_count = dict(manifest)
    forged_count["passed"] = 6
    rejected_count = service.validate(forged_count)
    assert rejected_count["error"] is True
    assert rejected_count["code"] in {
        "CI_VERIFICATION_MANIFEST_COUNTS_INVALID",
        "CI_VERIFICATION_MANIFEST_TEST_REPORT_MISMATCH",
    }

    forged_id = dict(manifest)
    forged_id["verification_manifest_id"] = (
        "ci-verification:" + ("0" * 64)
    )
    rejected_id = service.validate(forged_id)
    assert rejected_id["error"] is True
    assert rejected_id["code"] == "CI_VERIFICATION_MANIFEST_ID_MISMATCH"


def test_v422_missing_or_malformed_junit_writes_invalid_evidence_not_false_green(tmp_path):
    service = AssistantCiVerificationManifestService()
    missing = service.build_from_junit(
        junit_path=str(tmp_path / "missing.xml"),
        commit_sha=CURRENT_SHA,
        workflow="Verify",
        event="push",
        run_id=1,
        run_number=1,
    )

    assert missing["error"] is True
    assert missing["status"] == "invalid"
    assert missing["code"] == "CI_VERIFICATION_JUNIT_INVALID"
    assert missing["commit_sha"] == CURRENT_SHA
    assert missing["sha_bound"] is True
    assert missing["business_execution"] is False
    assert missing["ozon_mutation"] is False

    malformed_path = tmp_path / "bad.xml"
    malformed_path.write_text("<broken>", encoding="utf-8")
    malformed = _build(malformed_path)
    assert malformed["error"] is True
    assert malformed["code"] == "CI_VERIFICATION_JUNIT_INVALID"


def test_v423_cli_writes_canonical_json_and_returns_nonzero_for_invalid_junit(tmp_path):
    junit = tmp_path / "pytest-junit.xml"
    output = tmp_path / "test-report.json"
    _write_junit(junit, tests=5)

    code = manifest_cli_main([
        "--junit",
        str(junit),
        "--output",
        str(output),
        "--commit-sha",
        CURRENT_SHA,
        "--workflow",
        "Verify",
        "--event",
        "push",
        "--run-id",
        "88",
        "--run-number",
        "9",
    ])

    assert code == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["passed"] == 5
    assert payload["commit_sha"] == CURRENT_SHA

    invalid_output = tmp_path / "invalid-report.json"
    invalid_code = manifest_cli_main([
        "--junit",
        str(tmp_path / "missing.xml"),
        "--output",
        str(invalid_output),
        "--commit-sha",
        CURRENT_SHA,
        "--workflow",
        "Verify",
        "--event",
        "push",
        "--run-id",
        "88",
        "--run-number",
        "9",
    ])

    assert invalid_code == 1
    invalid_payload = json.loads(
        invalid_output.read_text(encoding="utf-8")
    )
    assert invalid_payload["error"] is True
    assert invalid_payload["status"] == "invalid"


def test_v424_workflow_generates_manifest_after_pytest_with_always_semantics():
    text = WORKFLOW.read_text(encoding="utf-8")

    pytest_index = text.index("python -m pytest -q")
    manifest_index = text.index(
        "python -m ci_verification_manifest"
    )
    upload_index = text.index("actions/upload-artifact@v4")

    assert pytest_index < manifest_index < upload_index
    block_start = text.index(
        "- name: Generate SHA-bound test report"
    )
    block_end = text.index(
        "- name: Upload verification artifacts"
    )
    block = text[block_start:block_end]
    assert "if: always()" in block


def test_v425_workflow_binds_manifest_to_exact_github_metadata_and_uploads_json():
    text = WORKFLOW.read_text(encoding="utf-8")

    assert '--commit-sha "$GITHUB_SHA"' in text
    assert '--workflow "$GITHUB_WORKFLOW"' in text
    assert '--event "$GITHUB_EVENT_NAME"' in text
    assert '--run-id "$GITHUB_RUN_ID"' in text
    assert '--run-number "$GITHUB_RUN_NUMBER"' in text
    assert "verification-artifacts/test-report.json" in text
    assert "verification-${{ github.sha }}" in text


def test_v426_project_verification_accepts_current_manifest_and_rejects_stale_one(tmp_path):
    current_junit = tmp_path / "current.xml"
    _write_junit(current_junit, tests=11)
    current_manifest = _build(current_junit, sha=CURRENT_SHA)

    service = AssistantProjectVerificationService()
    current = service.evaluate_manifest(
        CURRENT_SHA,
        current_manifest,
    )

    assert current["status"] == "CURRENT_VERIFIED"
    assert current["current_suite_verified"] is True
    assert current["current_suite_passed"] is True

    stale_manifest = _build(current_junit, sha=OLD_SHA)
    stale = service.evaluate_manifest(
        CURRENT_SHA,
        stale_manifest,
    )

    assert stale["status"] == "STALE_BASELINE"
    assert stale["current_suite_verified"] is False
    assert stale["current_suite_passed"] is False


def test_v426_project_verification_rejects_tampered_manifest_before_test_report_evaluation(tmp_path):
    junit = tmp_path / "pytest-junit.xml"
    _write_junit(junit, tests=3)
    manifest = _build(junit)
    manifest["verification_manifest_id"] = (
        "ci-verification:" + ("f" * 64)
    )

    result = AssistantProjectVerificationService().evaluate_manifest(
        CURRENT_SHA,
        manifest,
    )

    assert result["status"] == "CI_VERIFICATION_MANIFEST_INVALID"
    assert result["current_suite_verified"] is False
    assert result["current_suite_passed"] is False


def test_v427_manifest_and_workflow_remain_development_evidence_only(tmp_path):
    junit = tmp_path / "pytest-junit.xml"
    _write_junit(junit, tests=2)
    manifest = _build(junit)

    assert manifest["read_only_evidence"] is True
    assert manifest["business_execution"] is False
    assert manifest["ozon_mutation"] is False

    text = WORKFLOW.read_text(encoding="utf-8")
    assert 'OZON_CLIENT_ID: ""' in text
    assert 'OZON_API_KEY: ""' in text
    assert "secrets.OZON" not in text
    assert "permissions:\n  contents: read" in text
