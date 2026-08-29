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
        verification_service=None,
    ):
        self.name = "AssistantDevelopmentAgent"

        self.workflow = workflow
        self.brain_manager = brain_manager
        self.checkpoint_service = checkpoint_service
        self.verification_service = verification_service

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
        canonical_verification = self._verify_revision(
            current_sha,
            test_report,
        )

        result = {
            "agent": self.name,
            "task": task,
            "status": "workflow_started",
            "steps": plan["steps"],
        }

        if canonical_verification is not None:
            result["verification"] = canonical_verification

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
            canonical_verification=canonical_verification,
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
        canonical_verification=None,
    ):
        """
        Creates development execution report.
        """

        workflow_verification = (
            workflow.get("verification")
            if isinstance(workflow, dict)
            else None
        )
        checkpoint_verification = (
            checkpoint.get("verification")
            if isinstance(checkpoint, dict)
            else None
        )
        verification = (
            canonical_verification
            if verification_required
            else workflow_verification
        )

        status = "completed"
        if verification_required:
            if not self._verification_passed(verification):
                status = "blocked"

            if not self._verification_matches(
                verification,
                workflow_verification,
            ):
                status = "blocked"

            if (
                not isinstance(checkpoint, dict)
                or checkpoint.get("status") != "ready"
                or checkpoint.get("checkpoint_ready") is not True
                or not self._verification_matches(
                    verification,
                    checkpoint_verification,
                )
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

    def _verify_revision(self, current_sha, test_report):
        if current_sha is None:
            return None
        if self.verification_service is None:
            return {
                "error": True,
                "status": "VERIFICATION_SERVICE_REQUIRED",
                "current_sha": current_sha,
                "current_suite_verified": False,
                "current_suite_passed": False,
                "baseline": None,
                "baseline_is_current": False,
            }
        return self.verification_service.evaluate(
            current_sha,
            test_report,
        )

    def _verification_passed(self, verification):
        return (
            isinstance(verification, dict)
            and verification.get("error") is False
            and verification.get("current_suite_verified") is True
            and verification.get("current_suite_passed") is True
        )

    def _verification_matches(self, expected, actual):
        if not isinstance(expected, dict) or not isinstance(actual, dict):
            return False
        fields = (
            "status",
            "current_sha",
            "current_suite_verified",
            "current_suite_passed",
            "baseline_is_current",
        )
        return all(
            expected.get(field) == actual.get(field)
            for field in fields
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
