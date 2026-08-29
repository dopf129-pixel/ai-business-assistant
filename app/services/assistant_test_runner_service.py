import re


class AssistantTestRunnerService:
    """
    Provides project test validation.

    Test results can be bound to an exact commit SHA so downstream
    project-status logic cannot attribute an older green run to a newer
    revision.
    """

    def __init__(self):
        self.command = "python -m pytest"

    def create_test_report(
        self,
        passed,
        failed,
        total,
        commit_sha=None,
    ):
        """
        Creates a deterministic test execution report.

        commit_sha is optional for backward compatibility. An unbound
        report may describe a test run, but it must not verify any
        repository revision.
        """

        counts = self._counts(passed, failed, total)
        if counts is None:
            return {
                "error": True,
                "status": "invalid",
                "code": "TEST_REPORT_COUNTS_INVALID",
                "command": self.command,
                "commit_sha": self._sha(commit_sha),
                "sha_bound": bool(self._sha(commit_sha)),
            }

        passed_count, failed_count, total_count = counts
        status = "passed" if failed_count == 0 else "failed"
        sha = self._sha(commit_sha)

        result = {
            "error": False,
            "status": status,
            "command": self.command,
            "passed": passed_count,
            "failed": failed_count,
            "total": total_count,
            "commit_sha": sha,
            "sha_bound": bool(sha),
        }

        if sha:
            result["test_report_id"] = (
                "pytest:"
                + sha
                + ":"
                + str(passed_count)
                + ":"
                + str(failed_count)
                + ":"
                + str(total_count)
            )

        return result

    def _counts(self, passed, failed, total):
        try:
            passed_count = int(passed)
            failed_count = int(failed)
            total_count = int(total)
        except (TypeError, ValueError):
            return None

        if min(passed_count, failed_count, total_count) < 0:
            return None

        if passed_count + failed_count != total_count:
            return None

        return passed_count, failed_count, total_count

    def _sha(self, value):
        text = str(value or "").strip().lower()
        if not text:
            return None
        if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", text):
            return None
        return text
