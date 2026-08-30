import hashlib
import json
import re


class TaskPersistenceWorkflowRunEvidenceService:
    """Bind explicit completed GitHub workflow-run metadata to canonical provenance."""

    ALLOWED_EVENTS = {
        "push",
        "pull_request",
        "workflow_dispatch",
    }

    ALLOWED_CONCLUSIONS = {
        "success",
        "failure",
        "cancelled",
        "timed_out",
        "action_required",
        "neutral",
        "skipped",
        "stale",
    }

    def __init__(
        self,
        verification_manifest_service,
        verification_manifest_provenance_service,
    ):
        self.verification_manifest_service = (
            verification_manifest_service
        )
        self.verification_manifest_provenance_service = (
            verification_manifest_provenance_service
        )

    def build_run_evidence(self, value):
        source = dict(value) if isinstance(value, dict) else {}

        head_sha = self._sha(source.get("head_sha"))
        workflow = source.get("workflow")
        event = source.get("event")
        run_id = source.get("run_id")
        run_number = source.get("run_number")
        status = source.get("status")
        conclusion = source.get("conclusion")

        if (
            head_sha is None
            or workflow != "Verify"
            or event not in self.ALLOWED_EVENTS
            or isinstance(run_id, bool)
            or not isinstance(run_id, int)
            or run_id <= 0
            or isinstance(run_number, bool)
            or not isinstance(run_number, int)
            or run_number <= 0
            or status != "completed"
            or conclusion not in self.ALLOWED_CONCLUSIONS
        ):
            return self._error(
                "TASK_PERSISTENCE_WORKFLOW_RUN_EVIDENCE_INVALID"
            )

        evidence = {
            "head_sha": head_sha,
            "workflow": workflow,
            "event": event,
            "run_id": run_id,
            "run_number": run_number,
            "run_status": status,
            "conclusion": conclusion,
            "run_success": conclusion == "success",
            "evidence_source": (
                "CALLER_SUPPLIED_COMPLETED_WORKFLOW_RUN_METADATA"
            ),
            "network_fetch_performed": False,
            "externally_verified": False,
        }
        evidence_id = self._digest(
            "task-persistence-workflow-run:",
            evidence,
        )

        return {
            "error": False,
            "status": "TASK_PERSISTENCE_WORKFLOW_RUN_EVIDENCE_READY",
            "evidence_id": evidence_id,
            **evidence,
            "read_only": True,
            "executed": False,
        }

    def bind_manifest(self, verification_manifest, run_evidence):
        manifest = (
            dict(verification_manifest)
            if isinstance(verification_manifest, dict)
            else {}
        )
        run = (
            dict(run_evidence)
            if isinstance(run_evidence, dict)
            else {}
        )

        validation = self.verification_manifest_service.validate(
            manifest
        )
        if validation.get("error") is not False:
            return self._binding_error(
                "TASK_PERSISTENCE_WORKFLOW_MANIFEST_INVALID"
            )
        if not self._valid_run_evidence(run):
            return self._binding_error(
                "TASK_PERSISTENCE_WORKFLOW_RUN_EVIDENCE_REQUIRED"
            )

        exact_fields = {
            "head_sha": manifest.get("commit_sha"),
            "workflow": manifest.get("workflow"),
            "event": manifest.get("event"),
            "run_id": manifest.get("run_id"),
            "run_number": manifest.get("run_number"),
        }
        if any(
            run.get(field) != expected
            for field, expected in exact_fields.items()
        ):
            return self._binding_error(
                "TASK_PERSISTENCE_WORKFLOW_RUN_MANIFEST_MISMATCH"
            )

        test_suite_passed = manifest.get("status") == "passed"
        final_run_success = run.get("run_success") is True

        if final_run_success and not test_suite_passed:
            return self._binding_error(
                "TASK_PERSISTENCE_WORKFLOW_RUN_STATE_CONTRADICTORY"
            )

        post_test_failure_possible = (
            test_suite_passed and not final_run_success
        )

        evidence = {
            "workflow_run_evidence_id": run["evidence_id"],
            "verification_manifest_id": manifest[
                "verification_manifest_id"
            ],
            "test_report_id": manifest["test_report_id"],
            "revision_id": manifest["commit_sha"],
            "run_id": run["run_id"],
            "run_number": run["run_number"],
            "test_suite_passed": test_suite_passed,
            "final_ci_run_success_reported": final_run_success,
            "post_test_failure_possible": post_test_failure_possible,
        }
        binding_id = self._digest(
            "task-persistence-workflow-manifest-binding:",
            evidence,
        )

        return {
            "error": False,
            "status": (
                "TASK_PERSISTENCE_WORKFLOW_RUN_MANIFEST_BOUND"
            ),
            "binding_id": binding_id,
            **evidence,
            "workflow": run["workflow"],
            "event": run["event"],
            "run_status": run["run_status"],
            "run_conclusion": run["conclusion"],
            "completed_workflow_run_bound": True,
            "verification_manifest_bound": True,
            "ci_evidence_bound": False,
            "network_fetch_performed": False,
            "externally_verified": False,
            "read_only": True,
            "executed": False,
        }

    def build_report(
        self,
        verification_manifest,
        revision_id,
        workflow_run_metadata,
    ):
        manifest = (
            dict(verification_manifest)
            if isinstance(verification_manifest, dict)
            else {}
        )

        provenance = (
            self.verification_manifest_provenance_service
            .build_report(
                manifest,
                revision_id,
            )
        )
        if provenance.get("error") is True:
            return self._report_error(
                "TASK_PERSISTENCE_VERIFICATION_PROVENANCE_UNAVAILABLE"
            )

        run_evidence = self.build_run_evidence(
            workflow_run_metadata
        )
        if run_evidence.get("error") is True:
            return run_evidence

        manifest_binding = self.bind_manifest(
            manifest,
            run_evidence,
        )
        if manifest_binding.get("error") is True:
            return manifest_binding

        if (
            provenance.get("revision_id")
            != manifest_binding.get("revision_id")
            or provenance.get("verification_manifest_id")
            != manifest_binding.get("verification_manifest_id")
            or provenance.get("test_report_id")
            != manifest_binding.get("test_report_id")
            or provenance.get("test_suite_passed")
            is not manifest_binding.get("test_suite_passed")
        ):
            return self._report_error(
                "TASK_PERSISTENCE_WORKFLOW_PROVENANCE_LINEAGE_MISMATCH"
            )

        capabilities = []
        for item in provenance.get("capabilities") or []:
            if not isinstance(item, dict):
                return self._report_error(
                    "TASK_PERSISTENCE_WORKFLOW_CAPABILITY_INVALID"
                )
            enriched = dict(item)
            enriched["completed_workflow_run_bound"] = True
            enriched["final_ci_run_success_reported"] = (
                manifest_binding[
                    "final_ci_run_success_reported"
                ]
            )
            enriched["externally_verified"] = False
            capabilities.append(enriched)

        evidence = {
            "revision_id": provenance["revision_id"],
            "capability_manifest_id": provenance[
                "capability_manifest_id"
            ],
            "verification_manifest_id": provenance[
                "verification_manifest_id"
            ],
            "test_report_id": provenance["test_report_id"],
            "verification_binding_id": provenance["binding_id"],
            "workflow_manifest_binding_id": manifest_binding[
                "binding_id"
            ],
            "workflow_run_evidence_id": run_evidence[
                "evidence_id"
            ],
            "run_id": run_evidence["run_id"],
            "run_number": run_evidence["run_number"],
            "test_suite_passed": provenance["test_suite_passed"],
            "final_ci_run_success_reported": manifest_binding[
                "final_ci_run_success_reported"
            ],
            "post_test_failure_possible": manifest_binding[
                "post_test_failure_possible"
            ],
            "capabilities": capabilities,
        }
        provenance_binding_id = self._digest(
            "task-persistence-workflow-provenance-binding:",
            evidence,
        )

        report = {
            "error": False,
            "status": (
                "TASK_PERSISTENCE_WORKFLOW_RUN_PROVENANCE_REPORT"
            ),
            "provenance_binding_id": provenance_binding_id,
            **evidence,
            "workflow": run_evidence["workflow"],
            "event": run_evidence["event"],
            "run_status": run_evidence["status"],
            "run_conclusion": run_evidence["conclusion"],
            "completed_workflow_run_bound": True,
            "verification_manifest_bound": True,
            "ci_evidence_bound": False,
            "active_probe_performed": False,
            "network_fetch_performed": False,
            "externally_verified": False,
            "automatic_retry_allowed": False,
            "automatic_lock_recovery_allowed": False,
            "manual_lock_removal_allowed": False,
            "business_execution_ready": False,
            "mutation_ready": False,
            "read_only": True,
            "executed": False,
        }

        audit = self.build_audit_receipt(
            provenance,
            manifest,
            run_evidence,
            manifest_binding,
            report,
        )
        if audit.get("error") is True:
            return audit
        report["audit_receipt_id"] = audit["receipt_id"]
        return report

    def build_audit_receipt(
        self,
        verification_provenance,
        verification_manifest,
        run_evidence,
        manifest_binding,
        report,
    ):
        provenance = (
            dict(verification_provenance)
            if isinstance(verification_provenance, dict)
            else {}
        )
        manifest = (
            dict(verification_manifest)
            if isinstance(verification_manifest, dict)
            else {}
        )
        run = (
            dict(run_evidence)
            if isinstance(run_evidence, dict)
            else {}
        )
        bound = (
            dict(manifest_binding)
            if isinstance(manifest_binding, dict)
            else {}
        )
        source = dict(report) if isinstance(report, dict) else {}

        if not self._valid_run_evidence(run):
            return self._audit_error(
                "TASK_PERSISTENCE_WORKFLOW_RUN_EVIDENCE_REQUIRED"
            )

        rebuilt_binding = self.bind_manifest(
            manifest,
            run,
        )
        if rebuilt_binding != bound:
            return self._audit_error(
                "TASK_PERSISTENCE_WORKFLOW_MANIFEST_BINDING_INVALID"
            )

        if (
            provenance.get("status")
            != "TASK_PERSISTENCE_VERIFICATION_MANIFEST_PROVENANCE_REPORT"
            or provenance.get("error") is not False
            or provenance.get("revision_id")
            != bound.get("revision_id")
            or provenance.get("verification_manifest_id")
            != bound.get("verification_manifest_id")
            or provenance.get("test_report_id")
            != bound.get("test_report_id")
            or provenance.get("test_suite_passed")
            is not bound.get("test_suite_passed")
        ):
            return self._audit_error(
                "TASK_PERSISTENCE_WORKFLOW_PROVENANCE_INVALID"
            )

        if not self._valid_report_shape(
            provenance,
            bound,
            run,
            source,
        ):
            return self._audit_error(
                "TASK_PERSISTENCE_WORKFLOW_REPORT_INVALID"
            )

        evidence = {
            "provenance_binding_id": source[
                "provenance_binding_id"
            ],
            "verification_binding_id": source[
                "verification_binding_id"
            ],
            "workflow_manifest_binding_id": source[
                "workflow_manifest_binding_id"
            ],
            "workflow_run_evidence_id": source[
                "workflow_run_evidence_id"
            ],
            "revision_id": source["revision_id"],
            "capability_manifest_id": source[
                "capability_manifest_id"
            ],
            "verification_manifest_id": source[
                "verification_manifest_id"
            ],
            "test_report_id": source["test_report_id"],
            "run_id": source["run_id"],
            "run_number": source["run_number"],
            "test_suite_passed": source["test_suite_passed"],
            "final_ci_run_success_reported": source[
                "final_ci_run_success_reported"
            ],
            "post_test_failure_possible": source[
                "post_test_failure_possible"
            ],
            "capabilities": list(source["capabilities"]),
            "externally_verified": False,
        }
        receipt_id = self._digest(
            "task-persistence-workflow-run-audit:",
            evidence,
        )

        return {
            "error": False,
            "status": (
                "TASK_PERSISTENCE_WORKFLOW_RUN_AUDIT_READY"
            ),
            "receipt_id": receipt_id,
            **evidence,
            "completed_workflow_run_bound": True,
            "network_fetch_performed": False,
            "externally_verified": False,
            "read_only": True,
            "executed": False,
        }

    def _valid_report_shape(
        self,
        provenance,
        manifest_binding,
        run,
        report,
    ):
        if (
            report.get("status")
            != "TASK_PERSISTENCE_WORKFLOW_RUN_PROVENANCE_REPORT"
            or report.get("error") is not False
            or report.get("revision_id")
            != provenance.get("revision_id")
            or report.get("verification_manifest_id")
            != provenance.get("verification_manifest_id")
            or report.get("capability_manifest_id")
            != provenance.get("capability_manifest_id")
            or report.get("test_report_id")
            != provenance.get("test_report_id")
            or report.get("verification_binding_id")
            != provenance.get("binding_id")
            or report.get("workflow_manifest_binding_id")
            != manifest_binding.get("binding_id")
            or report.get("workflow_run_evidence_id")
            != run.get("evidence_id")
            or report.get("run_id") != run.get("run_id")
            or report.get("run_number") != run.get("run_number")
            or report.get("workflow") != run.get("workflow")
            or report.get("event") != run.get("event")
            or report.get("run_status") != run.get("run_status")
            or report.get("run_conclusion") != run.get("conclusion")
            or report.get("test_suite_passed")
            is not manifest_binding.get("test_suite_passed")
            or report.get("final_ci_run_success_reported")
            is not manifest_binding.get(
                "final_ci_run_success_reported"
            )
            or report.get("post_test_failure_possible")
            is not manifest_binding.get(
                "post_test_failure_possible"
            )
            or report.get("completed_workflow_run_bound") is not True
            or report.get("verification_manifest_bound") is not True
            or report.get("ci_evidence_bound") is not False
            or report.get("active_probe_performed") is not False
            or report.get("network_fetch_performed") is not False
            or report.get("externally_verified") is not False
            or report.get("automatic_retry_allowed") is not False
            or report.get("automatic_lock_recovery_allowed") is not False
            or report.get("manual_lock_removal_allowed") is not False
            or report.get("business_execution_ready") is not False
            or report.get("mutation_ready") is not False
            or report.get("read_only") is not True
            or report.get("executed") is not False
        ):
            return False

        expected_capabilities = []
        for item in provenance.get("capabilities") or []:
            if not isinstance(item, dict):
                return False
            enriched = dict(item)
            enriched["completed_workflow_run_bound"] = True
            enriched["final_ci_run_success_reported"] = (
                manifest_binding[
                    "final_ci_run_success_reported"
                ]
            )
            enriched["externally_verified"] = False
            expected_capabilities.append(enriched)

        if report.get("capabilities") != expected_capabilities:
            return False

        evidence = {
            "revision_id": provenance["revision_id"],
            "capability_manifest_id": provenance[
                "capability_manifest_id"
            ],
            "verification_manifest_id": provenance[
                "verification_manifest_id"
            ],
            "test_report_id": provenance["test_report_id"],
            "verification_binding_id": provenance["binding_id"],
            "workflow_manifest_binding_id": manifest_binding[
                "binding_id"
            ],
            "workflow_run_evidence_id": run["evidence_id"],
            "run_id": run["run_id"],
            "run_number": run["run_number"],
            "test_suite_passed": provenance["test_suite_passed"],
            "final_ci_run_success_reported": manifest_binding[
                "final_ci_run_success_reported"
            ],
            "post_test_failure_possible": manifest_binding[
                "post_test_failure_possible"
            ],
            "capabilities": expected_capabilities,
        }
        return report.get(
            "provenance_binding_id"
        ) == self._digest(
            "task-persistence-workflow-provenance-binding:",
            evidence,
        )

    def _valid_run_evidence(self, value):
        if not (
            isinstance(value, dict)
            and value.get("status")
            == "TASK_PERSISTENCE_WORKFLOW_RUN_EVIDENCE_READY"
            and value.get("run_status") == "completed"
            and value.get("error") is False
            and self._sha(value.get("head_sha"))
            == value.get("head_sha")
            and value.get("workflow") == "Verify"
            and value.get("event") in self.ALLOWED_EVENTS
            and isinstance(value.get("run_id"), int)
            and not isinstance(value.get("run_id"), bool)
            and value.get("run_id") > 0
            and isinstance(value.get("run_number"), int)
            and not isinstance(value.get("run_number"), bool)
            and value.get("run_number") > 0
            and value.get("run_success")
            is (value.get("conclusion") == "success")
            and value.get("conclusion")
            in self.ALLOWED_CONCLUSIONS
            and value.get("evidence_source")
            == "CALLER_SUPPLIED_COMPLETED_WORKFLOW_RUN_METADATA"
            and value.get("network_fetch_performed") is False
            and value.get("externally_verified") is False
            and value.get("read_only") is True
            and value.get("executed") is False
        ):
            return False

        expected = {
            "head_sha": value["head_sha"],
            "workflow": value["workflow"],
            "event": value["event"],
            "run_id": value["run_id"],
            "run_number": value["run_number"],
            "run_status": "completed",
            "conclusion": value["conclusion"],
            "run_success": value["run_success"],
            "evidence_source": value["evidence_source"],
            "network_fetch_performed": False,
            "externally_verified": False,
        }
        return value.get("evidence_id") == self._digest(
            "task-persistence-workflow-run:",
            expected,
        )

    @staticmethod
    def _sha(value):
        text = str(value or "").strip().lower()
        if not re.fullmatch(r"[0-9a-f]{40}", text):
            return None
        return text

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
            "status": "TASK_PERSISTENCE_WORKFLOW_RUN_EVIDENCE_UNAVAILABLE",
            "completed_workflow_run_bound": False,
            "verification_manifest_bound": False,
            "ci_evidence_bound": False,
            "network_fetch_performed": False,
            "externally_verified": False,
            "business_execution_ready": False,
            "mutation_ready": False,
            "read_only": True,
            "executed": False,
        }

    @classmethod
    def _binding_error(cls, code):
        result = cls._error(code)
        result["status"] = (
            "TASK_PERSISTENCE_WORKFLOW_RUN_MANIFEST_BINDING_UNAVAILABLE"
        )
        return result

    @classmethod
    def _report_error(cls, code):
        result = cls._error(code)
        result["status"] = (
            "TASK_PERSISTENCE_WORKFLOW_RUN_PROVENANCE_REPORT"
        )
        return result

    @classmethod
    def _audit_error(cls, code):
        result = cls._error(code)
        result["status"] = (
            "TASK_PERSISTENCE_WORKFLOW_RUN_AUDIT_UNAVAILABLE"
        )
        return result
