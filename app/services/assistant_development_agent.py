from datetime import date


class AssistantDevelopmentAgent:
    """
    Development Assistant coordinator.

    Coordinates development workflow,
    Project Brain synchronization,
    Git checkpoint preparation
    and development reporting.

    This service supports GPT + GitHub
    development workflow.
    """

    def __init__(
        self,
        workflow=None,
        brain_manager=None,
        checkpoint_service=None,
    ):
        self.name = "AssistantDevelopmentAgent"

        self.workflow = workflow
        self.brain_manager = brain_manager
        self.checkpoint_service = checkpoint_service

    def create_plan(self, task):
        """
        Creates development workflow plan.
        """

        return {
            "agent": self.name,
            "task": task,
            "steps": [
                "change_analysis",
                "test_validation",
                "documentation_validation",
                "checkpoint_preparation",
            ],
        }

    def create_report(self, task, status):
        """
        Creates simple development report.
        """

        return {
            "agent": self.name,
            "task": task,
            "status": status,
        }

    def run_development_cycle(
        self,
        task,
        current_sha=None,
        test_report=None,
    ):
        """
        Runs development support workflow.

        Does not make autonomous decisions.
        Prepares development information
        for review.
        """

        plan = self.create_plan(task)

        result = {
            "agent": self.name,
            "task": task,
            "status": "workflow_started",
            "steps": plan["steps"],
        }

        if self.workflow:
            result["workflow"] = self.execute_workflow(
                task,
                current_sha=current_sha,
                test_report=test_report,
            )
        else:
            result["workflow"] = "not_connected"

        if self.brain_manager:
            result["project_brain"] = self.update_project_brain(task)
        else:
            result["project_brain"] = "not_connected"

        if self.checkpoint_service:
            result["checkpoint"] = self.prepare_checkpoint(
                current_sha=current_sha,
                test_report=test_report,
            )
        else:
            result["checkpoint"] = "not_connected"

        result["report"] = self.create_development_report(
            task,
            result["workflow"],
            result["project_brain"],
            result["checkpoint"],
            verification_required=(current_sha is not None),
        )

        report_status = result["report"].get("status")
        result["status"] = (
            "workflow_completed"
            if report_status == "completed"
            else "workflow_blocked"
        )

        return result

    def create_development_report(
        self,
        task,
        workflow,
        project_brain,
        checkpoint,
        verification_required=False,
    ):
        """
        Creates development execution report.
        """

        verification = (
            workflow.get("verification")
            if isinstance(workflow, dict)
            else None
        )

        status = "completed"
        if verification_required:
            if (
                not isinstance(verification, dict)
                or verification.get("current_suite_verified") is not True
                or verification.get("current_suite_passed") is not True
            ):
                status = "blocked"

            if (
                not isinstance(checkpoint, dict)
                or checkpoint.get("status") != "ready"
                or checkpoint.get("checkpoint_ready") is not True
            ):
                status = "blocked"
        elif (
            isinstance(checkpoint, dict)
            and checkpoint.get("status") == "blocked"
        ):
            status = "blocked"

        result = {
            "agent": self.name,
            "task": task,
            "status": status,
            "summary": {
                "workflow": workflow,
                "project_brain": project_brain,
                "checkpoint": checkpoint,
            },
        }

        if isinstance(verification, dict):
            result["verification"] = verification

        return result

    def execute_workflow(
        self,
        task,
        current_sha=None,
        test_report=None,
    ):
        """
        Executes workflow service.
        """

        if current_sha is None:
            return self.workflow.start_workflow(
                task
            )

        return self.workflow.start_workflow(
            task,
            current_sha=current_sha,
            test_report=test_report,
        )

    def update_project_brain(self, task):
        """
        Updates Project Brain documentation.
        """

        self.brain_manager.add_changelog_entry(
            "Development Workflow Update",
            f"""
Development task processed by
{self.name}.

Task:

{task}
""",
        )

        return {
            "status": "updated",
            "date": str(date.today()),
        }

    def prepare_checkpoint(
        self,
        current_sha=None,
        test_report=None,
    ):
        """
        Prepares Git checkpoint metadata.
        """

        if current_sha is None:
            return self.checkpoint_service.prepare_checkpoint(
                files=[],
                message="Development workflow checkpoint",
            )

        verified = getattr(
            self.checkpoint_service,
            "prepare_verified_checkpoint",
            None,
        )
        if not callable(verified):
            return {
                "status": "blocked",
                "code": "VERIFIED_CHECKPOINT_CAPABILITY_MISSING",
                "checkpoint_ready": False,
                "files_changed": 0,
                "files": [],
            }

        return verified(
            files=[],
            message="Development workflow checkpoint",
            current_sha=current_sha,
            test_report=test_report,
        )
