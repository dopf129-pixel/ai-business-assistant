from pathlib import Path


class AssistantGitCheckpointService:
    """
    Prepares Git checkpoint information.

    Does not execute git operations.
    Only analyzes project state.
    """

    def __init__(
        self,
        project_root=".",
        verification_service=None,
    ):
        self.project_root = Path(project_root)
        self.verification_service = verification_service

    def get_changed_files(self, files):
        """
        Returns changed files list.
        """

        return list(files)

    def prepare_checkpoint(
        self,
        files,
        message,
    ):
        """
        Creates checkpoint preparation data.
        """

        changed_files = self.get_changed_files(files)

        return {
            "status": "ready",
            "files_changed": len(changed_files),
            "files": changed_files,
            "message": message,
        }

    def prepare_verified_checkpoint(
        self,
        files,
        message,
        current_sha,
        test_report=None,
    ):
        """
        Prepares checkpoint metadata only when the exact current SHA has
        a verified passing full-suite report.
        """

        if self.verification_service is None:
            return self._blocked(
                "VERIFICATION_SERVICE_REQUIRED"
            )

        verification = self.verification_service.evaluate(
            current_sha,
            test_report,
        )

        if verification.get("current_suite_verified") is not True:
            return self._blocked(
                "CURRENT_SUITE_NOT_VERIFIED",
                verification,
            )

        if verification.get("current_suite_passed") is not True:
            return self._blocked(
                "CURRENT_SUITE_FAILED",
                verification,
            )

        result = self.prepare_checkpoint(
            files,
            message,
        )
        result["checkpoint_ready"] = True
        result["verification"] = verification
        result["current_sha"] = verification.get("current_sha")
        return result

    def _blocked(self, code, verification=None):
        return {
            "status": "blocked",
            "code": code,
            "checkpoint_ready": False,
            "verification": verification,
            "files_changed": 0,
            "files": [],
        }
