import hashlib
import json


class TaskPersistenceReleaseClosureService:
    """Read-only release-review closure over persistence and verification evidence."""

    REQUIRED_CAPABILITIES = (
        "optimistic_concurrency_guard",
        "kernel_lock_guard",
        "atomic_replace_required",
        "file_fsync_required",
        "directory_fsync_required",
        "coordination_file_ownership_neutral",
    )

    def __init__(
        self,
        release_observability_service,
        workflow_run_evidence_service,
    ):
        self.release_observability_service = release_observability_service
        self.workflow_run_evidence_service = workflow_run_evidence_service

    def build_report(
        self,
        verification_manifest,
        revision_id,
        workflow_run_metadata,
    ):
        try:
            release = self.release_observability_service.build_release_report()
        except Exception:
            return self._error(
                "TASK_PERSISTENCE_RELEASE_CLOSURE_RUNTIME_UNAVAILABLE"
            )
        if not self._valid_release_report(release):
            return self._error(
                "TASK_PERSISTENCE_RELEASE_CLOSURE_RUNTIME_INVALID"
            )

        workflow = self.workflow_run_evidence_service.build_report(
            verification_manifest,
            revision_id,
            workflow_run_metadata,
        )
        if not self._valid_workflow_report(workflow):
            return self._error(
                "TASK_PERSISTENCE_RELEASE_CLOSURE_VERIFICATION_INVALID"
            )

        if workflow.get("revision_id") != revision_id:
            return self._error(
                "TASK_PERSISTENCE_RELEASE_CLOSURE_REVISION_MISMATCH"
            )

        checklist = self._build_checklist(release, workflow)
        blockers = [
            item["id"]
            for item in checklist
            if item["required"] is True
            and item["satisfied"] is not True
        ]
        warnings = self._stable_unique(
            list(release.get("warnings") or [])
        )

        release_review_ready = not blockers and not warnings
        closure_state = (
            "READY_FOR_RELEASE_REVIEW"
            if release_review_ready
            else "BLOCKED"
        )

        evidence = {
            "revision_id": workflow["revision_id"],
            "runtime_release_audit_id": release["audit_receipt_id"],
            "workflow_audit_id": workflow["audit_receipt_id"],
            "verification_manifest_id": workflow[
                "verification_manifest_id"
            ],
            "test_report_id": workflow["test_report_id"],
            "run_id": workflow["run_id"],
            "run_number": workflow["run_number"],
            "checklist": checklist,
            "blockers": blockers,
            "warnings": warnings,
            "closure_state": closure_state,
            "release_review_ready": release_review_ready,
        }
        closure_id = self._digest(
            "task-persistence-release-closure:",
            evidence,
        )

        runbook = self._build_runbook(
            release,
            workflow,
            blockers,
            warnings,
        )

        report = {
            "error": False,
            "status": "TASK_PERSISTENCE_RELEASE_CLOSURE_READY",
            "closure_id": closure_id,
            **evidence,
            "check_count": len(checklist),
            "satisfied_count": sum(
                item["satisfied"] is True
                for item in checklist
            ),
            "blocker_count": len(blockers),
            "warning_count": len(warnings),
            "runbook": runbook,
            "runbook_step_count": len(runbook),
            "completed_workflow_run_bound": True,
            "verification_manifest_bound": True,
            "final_ci_run_success_reported": workflow[
                "final_ci_run_success_reported"
            ],
            "externally_verified": False,
            "deployment_allowed": False,
            "release_approved": False,
            "automatic_retry_allowed": False,
            "automatic_lock_recovery_allowed": False,
            "manual_lock_removal_allowed": False,
            "business_execution_ready": False,
            "mutation_ready": False,
            "read_only": True,
            "deployed": False,
            "executed": False,
        }

        audit = self.build_audit_receipt(report)
        if audit.get("error") is True:
            return audit
        report["closure_audit_receipt_id"] = audit["receipt_id"]
        return report

    def build_audit_receipt(self, report):
        source = dict(report) if isinstance(report, dict) else {}
        if not self._valid_closure_report(source):
            return self._audit_error(
                "TASK_PERSISTENCE_RELEASE_CLOSURE_REPORT_INVALID"
            )

        evidence = {
            "closure_id": source["closure_id"],
            "revision_id": source["revision_id"],
            "runtime_release_audit_id": source[
                "runtime_release_audit_id"
            ],
            "workflow_audit_id": source["workflow_audit_id"],
            "verification_manifest_id": source[
                "verification_manifest_id"
            ],
            "test_report_id": source["test_report_id"],
            "run_id": source["run_id"],
            "run_number": source["run_number"],
            "checklist": list(source["checklist"]),
            "blockers": list(source["blockers"]),
            "warnings": list(source["warnings"]),
            "closure_state": source["closure_state"],
            "release_review_ready": source[
                "release_review_ready"
            ],
            "runbook": list(source["runbook"]),
            "deployment_allowed": False,
            "release_approved": False,
            "deployed": False,
            "executed": False,
        }
        receipt_id = self._digest(
            "task-persistence-release-closure-audit:",
            evidence,
        )

        return {
            "error": False,
            "status": "TASK_PERSISTENCE_RELEASE_CLOSURE_AUDIT_READY",
            "receipt_id": receipt_id,
            **evidence,
            "externally_verified": False,
            "read_only": True,
        }

    def _build_checklist(self, release, workflow):
        capabilities = dict(release["capabilities"])
        checklist = [
            self._check(
                "RUNTIME_RELEASE_READY",
                release.get("release_ready") is True,
                "canonical runtime release report",
            ),
            self._check(
                "NO_RUNTIME_BLOCKERS",
                not release.get("blockers"),
                "runtime blockers",
            ),
            self._check(
                "NO_RUNTIME_WARNINGS",
                not release.get("warnings"),
                "runtime warnings require manual resolution",
            ),
        ]

        for capability in self.REQUIRED_CAPABILITIES:
            checklist.append(
                self._check(
                    "CAPABILITY:" + capability,
                    capabilities.get(capability) is True,
                    "runtime persistence capability",
                )
            )

        checklist.extend([
            self._check(
                "EXACT_REVISION_BOUND",
                bool(workflow.get("revision_id")),
                "workflow provenance exact revision",
            ),
            self._check(
                "VERIFICATION_MANIFEST_BOUND",
                workflow.get("verification_manifest_bound") is True,
                "canonical test manifest",
            ),
            self._check(
                "COMPLETED_WORKFLOW_RUN_BOUND",
                workflow.get("completed_workflow_run_bound") is True,
                "completed workflow-run metadata",
            ),
            self._check(
                "TEST_SUITE_PASSED",
                workflow.get("test_suite_passed") is True,
                "canonical pytest manifest",
            ),
            self._check(
                "FINAL_WORKFLOW_RUN_SUCCESS_REPORTED",
                workflow.get("final_ci_run_success_reported") is True,
                "explicit completed-run metadata",
            ),
            self._check(
                "NO_POST_TEST_FAILURE",
                workflow.get("post_test_failure_possible") is False,
                "test vs completed-run outcome",
            ),
        ])
        return checklist

    def _build_runbook(
        self,
        release,
        workflow,
        blockers,
        warnings,
    ):
        steps = [
            {
                "step": 1,
                "action": "CONFIRM_EXACT_REVISION",
                "instruction": (
                    "Сверьте exact revision с verification manifest "
                    "и completed workflow-run evidence."
                ),
                "automatic": False,
            },
            {
                "step": 2,
                "action": "CONFIRM_RUNTIME_PERSISTENCE_READINESS",
                "instruction": (
                    "Проверьте runtime release report, blockers, warnings "
                    "и шесть persistence capabilities."
                ),
                "automatic": False,
            },
            {
                "step": 3,
                "action": "CONFIRM_TEST_AND_FINAL_RUN_EVIDENCE",
                "instruction": (
                    "Проверьте, что canonical test suite прошёл и completed "
                    "workflow run сообщает success для того же SHA/run."
                ),
                "automatic": False,
            },
        ]

        if "TASK_FILE_WRITE_LOCKED" in (release.get("blockers") or []):
            steps.append({
                "step": len(steps) + 1,
                "action": "WAIT_FOR_ACTIVE_WRITER",
                "instruction": (
                    "Дождитесь завершения активного writer и повторите "
                    "проверку вручную. Coordination file не удалять."
                ),
                "automatic": False,
            })

        if "TASK_DIRECTORY_FSYNC_ERROR" in warnings:
            steps.append({
                "step": len(steps) + 1,
                "action": "INSPECT_DURABILITY_BOUNDARY",
                "instruction": (
                    "Проверьте filesystem/directory durability вручную; "
                    "не трактуйте rename как доказанную crash durability."
                ),
                "automatic": False,
            })

        if blockers or warnings:
            steps.append({
                "step": len(steps) + 1,
                "action": "RESOLVE_AND_REBUILD_CHECKLIST",
                "instruction": (
                    "Устраните явные blockers/warnings и заново соберите "
                    "read-only closure. Автоматического retry нет."
                ),
                "automatic": False,
            })
        else:
            steps.append({
                "step": len(steps) + 1,
                "action": "MANUAL_RELEASE_REVIEW",
                "instruction": (
                    "Checklist готов только к ручному release review. "
                    "Deployment/approval этим отчётом не выполняются."
                ),
                "automatic": False,
            })

        return steps

    def _valid_release_report(self, value):
        expected_capabilities = set(self.REQUIRED_CAPABILITIES)
        capabilities = value.get("capabilities")
        return (
            isinstance(value, dict)
            and value.get("status")
            == "TASK_PERSISTENCE_RELEASE_READINESS"
            and value.get("error") is False
            and isinstance(value.get("release_ready"), bool)
            and isinstance(value.get("blockers"), list)
            and isinstance(value.get("warnings"), list)
            and isinstance(capabilities, dict)
            and set(capabilities) == expected_capabilities
            and all(
                isinstance(capabilities[name], bool)
                for name in expected_capabilities
            )
            and isinstance(value.get("audit_receipt_id"), str)
            and value.get("audit_receipt_id").startswith(
                "task-persistence-release:"
            )
            and value.get("automatic_retry_allowed", False) is False
            and value.get("automatic_lock_recovery_allowed") is False
            and value.get("manual_lock_removal_allowed") is False
            and value.get("business_execution_ready") is False
            and value.get("mutation_ready") is False
            and value.get("read_only") is True
            and value.get("executed") is False
        )

    @staticmethod
    def _valid_workflow_report(value):
        return (
            isinstance(value, dict)
            and value.get("status")
            == "TASK_PERSISTENCE_WORKFLOW_RUN_PROVENANCE_REPORT"
            and value.get("error") is False
            and isinstance(value.get("revision_id"), str)
            and isinstance(value.get("audit_receipt_id"), str)
            and value.get("audit_receipt_id").startswith(
                "task-persistence-workflow-run-audit:"
            )
            and value.get("completed_workflow_run_bound") is True
            and value.get("verification_manifest_bound") is True
            and isinstance(value.get("test_suite_passed"), bool)
            and isinstance(
                value.get("final_ci_run_success_reported"),
                bool,
            )
            and isinstance(
                value.get("post_test_failure_possible"),
                bool,
            )
            and value.get("ci_evidence_bound") is False
            and value.get("externally_verified") is False
            and value.get("network_fetch_performed") is False
            and value.get("business_execution_ready") is False
            and value.get("mutation_ready") is False
            and value.get("read_only") is True
            and value.get("executed") is False
        )

    def _valid_closure_report(self, value):
        if not (
            isinstance(value, dict)
            and value.get("status")
            == "TASK_PERSISTENCE_RELEASE_CLOSURE_READY"
            and value.get("error") is False
            and isinstance(value.get("closure_id"), str)
            and value.get("closure_id").startswith(
                "task-persistence-release-closure:"
            )
            and isinstance(value.get("revision_id"), str)
            and isinstance(value.get("checklist"), list)
            and isinstance(value.get("blockers"), list)
            and isinstance(value.get("warnings"), list)
            and value.get("check_count") == len(value["checklist"])
            and value.get("blocker_count") == len(value["blockers"])
            and value.get("warning_count") == len(value["warnings"])
            and isinstance(value.get("runbook"), list)
            and value.get("runbook_step_count")
            == len(value["runbook"])
            and value.get("closure_state")
            in {"READY_FOR_RELEASE_REVIEW", "BLOCKED"}
            and isinstance(value.get("release_review_ready"), bool)
            and value.get("completed_workflow_run_bound") is True
            and value.get("verification_manifest_bound") is True
            and value.get("externally_verified") is False
            and value.get("deployment_allowed") is False
            and value.get("release_approved") is False
            and value.get("automatic_retry_allowed") is False
            and value.get("automatic_lock_recovery_allowed") is False
            and value.get("manual_lock_removal_allowed") is False
            and value.get("business_execution_ready") is False
            and value.get("mutation_ready") is False
            and value.get("read_only") is True
            and value.get("deployed") is False
            and value.get("executed") is False
        ):
            return False

        if not all(self._valid_check(item) for item in value["checklist"]):
            return False
        expected_blockers = [
            item["id"]
            for item in value["checklist"]
            if item["required"] is True
            and item["satisfied"] is not True
        ]
        if value["blockers"] != expected_blockers:
            return False

        expected_ready = not expected_blockers and not value["warnings"]
        if value["release_review_ready"] is not expected_ready:
            return False
        expected_state = (
            "READY_FOR_RELEASE_REVIEW"
            if expected_ready
            else "BLOCKED"
        )
        if value["closure_state"] != expected_state:
            return False
        if value.get("satisfied_count") != sum(
            item["satisfied"] is True
            for item in value["checklist"]
        ):
            return False
        if not all(
            isinstance(step, dict)
            and step.get("step") == index
            and isinstance(step.get("action"), str)
            and isinstance(step.get("instruction"), str)
            and step.get("automatic") is False
            for index, step in enumerate(value["runbook"], start=1)
        ):
            return False

        evidence = {
            "revision_id": value["revision_id"],
            "runtime_release_audit_id": value[
                "runtime_release_audit_id"
            ],
            "workflow_audit_id": value["workflow_audit_id"],
            "verification_manifest_id": value[
                "verification_manifest_id"
            ],
            "test_report_id": value["test_report_id"],
            "run_id": value["run_id"],
            "run_number": value["run_number"],
            "checklist": value["checklist"],
            "blockers": value["blockers"],
            "warnings": value["warnings"],
            "closure_state": value["closure_state"],
            "release_review_ready": value[
                "release_review_ready"
            ],
        }
        return value["closure_id"] == self._digest(
            "task-persistence-release-closure:",
            evidence,
        )

    @staticmethod
    def _valid_check(item):
        return (
            isinstance(item, dict)
            and isinstance(item.get("id"), str)
            and item.get("required") is True
            and isinstance(item.get("satisfied"), bool)
            and isinstance(item.get("evidence"), str)
        )

    @staticmethod
    def _check(check_id, satisfied, evidence):
        return {
            "id": check_id,
            "required": True,
            "satisfied": bool(satisfied),
            "evidence": evidence,
        }

    @staticmethod
    def _stable_unique(values):
        result = []
        for value in values:
            if value not in result:
                result.append(value)
        return result

    @staticmethod
    def _digest(prefix, value):
        canonical = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return prefix + hashlib.sha256(canonical).hexdigest()

    @staticmethod
    def _error(code):
        return {
            "error": True,
            "code": code,
            "status": "TASK_PERSISTENCE_RELEASE_CLOSURE_UNAVAILABLE",
            "closure_state": "BLOCKED",
            "release_review_ready": False,
            "deployment_allowed": False,
            "release_approved": False,
            "externally_verified": False,
            "automatic_retry_allowed": False,
            "automatic_lock_recovery_allowed": False,
            "manual_lock_removal_allowed": False,
            "business_execution_ready": False,
            "mutation_ready": False,
            "read_only": True,
            "deployed": False,
            "executed": False,
        }

    @classmethod
    def _audit_error(cls, code):
        result = cls._error(code)
        result["status"] = (
            "TASK_PERSISTENCE_RELEASE_CLOSURE_AUDIT_UNAVAILABLE"
        )
        return result
