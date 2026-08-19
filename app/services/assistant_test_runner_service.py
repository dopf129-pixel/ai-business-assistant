class AssistantTestRunnerService:
    """
    Provides project test validation.

    Executes test command information
    and returns verification result.
    """

    def __init__(self):
        self.command = "python -m pytest"

    def create_test_report(
        self,
        passed,
        failed,
        total,
    ):
        """
        Creates test execution report.
        """

        if failed == 0:
            status = "passed"
        else:
            status = "failed"

        return {
            "status": status,
            "command": self.command,
            "passed": passed,
            "failed": failed,
            "total": total,
        }
