from pathlib import Path


class AssistantGitCheckpointService:
    """
    Prepares Git checkpoint information.

    Does not execute git operations.
    Only analyzes project state.
    """

    def __init__(self, project_root="."):
        self.project_root = Path(project_root)

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