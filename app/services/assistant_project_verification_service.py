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

        expected_id = self._expected_report_id(report, report_sha)
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
        passed = (
            report.get("status") == "passed"
            and report.get("failed") == 0
        )

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

    def render_markdown(self, evaluation):
        source = dict(evaluation or {})
        if source.get("error") is not False:
            return "# Verification Status\\n\\nStatus: INVALID\\n"

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
        return "\\n".join(lines)

    def _expected_report_id(self, report, sha):
        required = ("passed", "failed", "total")
        if any(report.get(field) is None for field in required):
            return None
        return (
            "pytest:"
            + sha
            + ":"
            + str(report.get("passed"))
            + ":"
            + str(report.get("failed"))
            + ":"
            + str(report.get("total"))
        )

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
        return text or None
