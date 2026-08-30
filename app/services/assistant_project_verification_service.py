import re


class AssistantProjectVerificationService:
    """
    Evaluates whether a test report verifies the exact current revision.

    A green report for another SHA is a stale baseline, not proof that
    current main is green.
    """

    def evaluate(self, current_sha, test_report=None):
        current = self._sha(current_sha)
        if current is None:
            return self._blocked("CURRENT_SHA_REQUIRED")

        report = dict(test_report or {})
        if not report:
            return self._result(
                current_sha=current,
                status="NO_TEST_REPORT",
                current_suite_verified=False,
                current_suite_passed=False,
                baseline=None,
            )

        if report.get("error") is not False:
            return self._result(
                current_sha=current,
                status="TEST_REPORT_INVALID",
                current_suite_verified=False,
                current_suite_passed=False,
                baseline=self._baseline(report),
            )

        report_sha = self._sha(report.get("commit_sha"))
        if not report.get("sha_bound") or report_sha is None:
            return self._result(
                current_sha=current,
                status="UNBOUND_TEST_REPORT",
                current_suite_verified=False,
                current_suite_passed=False,
                baseline=self._baseline(report),
            )

        counts = self._counts(report)
        if counts is None:
            return self._result(
                current_sha=current,
                status="TEST_REPORT_COUNTS_INVALID",
                current_suite_verified=False,
                current_suite_passed=False,
                baseline=self._baseline(report),
            )

        passed_count, failed_count, total_count = counts
        expected_status = "passed" if failed_count == 0 else "failed"
        if report.get("status") != expected_status:
            return self._result(
                current_sha=current,
                status="TEST_REPORT_STATUS_CONTRADICTORY",
                current_suite_verified=False,
                current_suite_passed=False,
                baseline=self._baseline(report),
            )

        expected_id = self._expected_report_id(
            report_sha,
            passed_count,
            failed_count,
            total_count,
        )
        report_id = report.get("test_report_id")
        if report_id != expected_id:
            return self._result(
                current_sha=current,
                status="TEST_REPORT_ID_MISMATCH",
                current_suite_verified=False,
                current_suite_passed=False,
                baseline=self._baseline(report),
            )

        same_revision = report_sha == current
        passed = expected_status == "passed"

        if same_revision and passed:
            status = "CURRENT_VERIFIED"
            current_verified = True
            current_passed = True
        elif same_revision:
            status = "CURRENT_FAILED"
            current_verified = True
            current_passed = False
        else:
            status = "STALE_BASELINE"
            current_verified = False
            current_passed = False

        return self._result(
            current_sha=current,
            status=status,
            current_suite_verified=current_verified,
            current_suite_passed=current_passed,
            baseline=self._baseline(report),
        )

    def evaluate_manifest(
        self,
        current_sha,
        manifest,
        manifest_service=None,
    ):
        if manifest_service is None:
            from services.assistant_ci_verification_manifest_service import (
                AssistantCiVerificationManifestService,
            )
            manifest_service = (
                AssistantCiVerificationManifestService()
            )

        validation = manifest_service.validate(manifest)
        if validation.get("error") is not False:
            current = self._sha(current_sha)
            if current is None:
                return self._blocked("CURRENT_SHA_REQUIRED")
            return self._result(
                current_sha=current,
                status="CI_VERIFICATION_MANIFEST_INVALID",
                current_suite_verified=False,
                current_suite_passed=False,
                baseline=self._baseline(
                    dict(manifest)
                    if isinstance(manifest, dict)
                    else {}
                ),
            )

        source = dict(manifest)
        report = {
            "error": source["error"],
            "status": source["status"],
            "command": source["command"],
            "passed": source["passed"],
            "failed": source["failed"],
            "total": source["total"],
            "commit_sha": source["commit_sha"],
            "sha_bound": source["sha_bound"],
            "test_report_id": source["test_report_id"],
        }
        return self.evaluate(current_sha, report)

    def render_markdown(self, evaluation):
        source = dict(evaluation or {})
        if source.get("error") is not False:
            return "# Verification Status\n\nStatus: INVALID\n"

        baseline = source.get("baseline") or {}
        lines = [
            "# Verification Status",
            "",
            "Current SHA: " + str(source.get("current_sha") or ""),
            "State: " + str(source.get("status") or ""),
            "Current full suite verified: "
            + ("yes" if source.get("current_suite_verified") else "no"),
            "Current full suite passed: "
            + ("yes" if source.get("current_suite_passed") else "no"),
            "",
            "## Last supplied test report",
            "",
        ]

        if baseline:
            lines.extend([
                "Report SHA: " + str(baseline.get("commit_sha") or ""),
                "Status: " + str(baseline.get("status") or ""),
                "Passed: " + str(baseline.get("passed")),
                "Failed: " + str(baseline.get("failed")),
                "Total: " + str(baseline.get("total")),
            ])
        else:
            lines.append("No SHA-bound test report supplied.")

        lines.extend([
            "",
            (
                "A report for another SHA is historical evidence only and "
                "must not be presented as verification of the current revision."
            ),
            "",
        ])
        return "\n".join(lines)

    def _expected_report_id(
        self,
        sha,
        passed,
        failed,
        total,
    ):
        return (
            "pytest:"
            + sha
            + ":"
            + str(passed)
            + ":"
            + str(failed)
            + ":"
            + str(total)
        )

    def _counts(self, report):
        try:
            passed = int(report.get("passed"))
            failed = int(report.get("failed"))
            total = int(report.get("total"))
        except (TypeError, ValueError):
            return None

        if min(passed, failed, total) < 0:
            return None
        if passed + failed != total:
            return None

        return passed, failed, total

    def _baseline(self, report):
        if not isinstance(report, dict):
            return None
        return {
            "commit_sha": self._sha(report.get("commit_sha")),
            "status": report.get("status"),
            "passed": report.get("passed"),
            "failed": report.get("failed"),
            "total": report.get("total"),
        }

    def _result(
        self,
        current_sha,
        status,
        current_suite_verified,
        current_suite_passed,
        baseline,
    ):
        return {
            "error": False,
            "status": status,
            "current_sha": current_sha,
            "current_suite_verified": current_suite_verified,
            "current_suite_passed": current_suite_passed,
            "baseline": baseline,
            "baseline_is_current": bool(
                baseline
                and baseline.get("commit_sha") == current_sha
            ),
        }

    def _blocked(self, code):
        return {
            "error": True,
            "code": code,
            "status": "VERIFICATION_BLOCKED",
            "current_suite_verified": False,
            "current_suite_passed": False,
            "baseline": None,
            "baseline_is_current": False,
        }

    def _sha(self, value):
        text = str(value or "").strip().lower()
        if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", text):
            return None
        return text
