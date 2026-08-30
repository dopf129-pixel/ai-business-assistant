import hashlib
import json
import re


class TaskPersistenceCapabilityProvenanceService:
    """Read-only provenance over persistence capabilities and explicit CI metadata."""

    CAPABILITY_CATALOG = (
        {
            "capability": "optimistic_concurrency_guard",
            "evidence_mode": "IMPLEMENTATION_CONTRACT",
            "implementation_source": (
                "services.terminal_safe_assistant_task_service."
                "TerminalSafeAssistantTaskService.save"
            ),
            "focused_test_file": (
                "tests/test_task_persistence_concurrency_v323_v332.py"
            ),
            "project_doc": "project_brain/TASK_PERSISTENCE_CONCURRENCY_V1.md",
        },
        {
            "capability": "kernel_lock_guard",
            "evidence_mode": "RUNTIME_DIAGNOSTIC",
            "implementation_source": (
                "services.terminal_safe_assistant_task_service."
                "TerminalSafeAssistantTaskService._acquire_write_lock"
            ),
            "focused_test_file": (
                "tests/test_task_persistence_kernel_lock_v378_v387.py"
            ),
            "project_doc": "project_brain/TASK_PERSISTENCE_KERNEL_LOCK_V2.md",
        },
        {
            "capability": "atomic_replace_required",
            "evidence_mode": "IMPLEMENTATION_CONTRACT",
            "implementation_source": (
                "services.assistant_task_service.AssistantTaskService.save"
            ),
            "focused_test_file": (
                "tests/test_task_persistence_integrity_v248_v255.py"
            ),
            "project_doc": "project_brain/TASK_PERSISTENCE_INTEGRITY_V1.md",
        },
        {
            "capability": "file_fsync_required",
            "evidence_mode": "IMPLEMENTATION_CONTRACT",
            "implementation_source": (
                "services.assistant_task_service.AssistantTaskService.save"
            ),
            "focused_test_file": (
                "tests/test_task_persistence_integrity_v248_v255.py"
            ),
            "project_doc": "project_brain/TASK_PERSISTENCE_INTEGRITY_V1.md",
        },
        {
            "capability": "directory_fsync_required",
            "evidence_mode": "IMPLEMENTATION_CONTRACT",
            "implementation_source": (
                "services.terminal_safe_assistant_task_service."
                "TerminalSafeAssistantTaskService._sync_parent_directory"
            ),
            "focused_test_file": (
                "tests/test_task_persistence_crash_durability_v343_v352.py"
            ),
            "project_doc": (
                "project_brain/TASK_PERSISTENCE_CRASH_DURABILITY_V1.md"
            ),
        },
        {
            "capability": "coordination_file_ownership_neutral",
            "evidence_mode": "IMPLEMENTATION_CONTRACT",
            "implementation_source": (
                "services.terminal_safe_assistant_task_service."
                "TerminalSafeAssistantTaskService._acquire_write_lock"
            ),
            "focused_test_file": (
                "tests/test_task_persistence_kernel_lock_v378_v387.py"
            ),
            "project_doc": "project_brain/TASK_PERSISTENCE_KERNEL_LOCK_V2.md",
        },
    )

    def __init__(
        self,
        release_observability_service,
        revision_id=None,
        ci_evidence=None,
    ):
        self.release_observability_service = release_observability_service
        self.revision_id = self._normalize_revision(revision_id)
        self.ci_evidence = ci_evidence

    def build_manifest(self, snapshot, revision_id=None):
        source = dict(snapshot) if isinstance(snapshot, dict) else {}
        if not self._valid_release_snapshot(source):
            return self._error(
                "TASK_PERSISTENCE_CAPABILITY_RELEASE_SNAPSHOT_REQUIRED"
            )

        revision = (
            self._normalize_revision(revision_id)
            if revision_id is not None
            else self.revision_id
        )
        if revision_id is not None and revision is None:
            return self._error(
                "TASK_PERSISTENCE_CAPABILITY_REVISION_INVALID"
            )

        capabilities = source["capabilities"]
        items = []
        for row in self.CAPABILITY_CATALOG:
            capability = row["capability"]
            mode = row["evidence_mode"]
            items.append({
                "capability": capability,
                "required": True,
                "enabled": capabilities[capability],
                "evidence_mode": mode,
                "runtime_observed": mode == "RUNTIME_DIAGNOSTIC",
                "implementation_contract_claimed": True,
                "implementation_source": row["implementation_source"],
                "focused_test_file": row["focused_test_file"],
                "project_doc": row["project_doc"],
                "ci_evidence_bound": False,
                "externally_verified": False,
            })

        evidence = {
            "revision_id": revision,
            "release_ready": source["release_ready"],
            "capabilities": items,
            "active_probe_performed": False,
            "ci_evidence_bound": False,
            "externally_verified": False,
        }
        manifest_id = self._digest(
            "task-persistence-capability-manifest:",
            evidence,
        )

        return {
            "error": False,
            "status": "TASK_PERSISTENCE_CAPABILITY_PROVENANCE_READY",
            "manifest_id": manifest_id,
            "revision_id": revision,
            "revision_declared": revision is not None,
            "release_ready": source["release_ready"],
            "capability_count": len(items),
            "capabilities": items,
            "implementation_contract_count": sum(
                item["evidence_mode"] == "IMPLEMENTATION_CONTRACT"
                for item in items
            ),
            "runtime_observation_count": sum(
                item["evidence_mode"] == "RUNTIME_DIAGNOSTIC"
                for item in items
            ),
            "active_probe_performed": False,
            "ci_evidence_bound": False,
            "externally_verified": False,
            "automatic_retry_allowed": False,
            "automatic_lock_recovery_allowed": False,
            "manual_lock_removal_allowed": False,
            "business_execution_ready": False,
            "mutation_ready": False,
            "read_only": True,
            "executed": False,
        }

    def build_ci_verification_evidence(self, value):
        source = dict(value) if isinstance(value, dict) else {}
        target_sha = self._normalize_revision(source.get("target_sha"))

        if (
            target_sha is None
            or source.get("workflow") != "Verify"
            or source.get("event") not in {"push", "pull_request"}
            or isinstance(source.get("run_number"), bool)
            or not isinstance(source.get("run_number"), int)
            or source.get("run_number") <= 0
            or isinstance(source.get("passed"), bool)
            or not isinstance(source.get("passed"), int)
            or source.get("passed") < 0
            or isinstance(source.get("failed"), bool)
            or not isinstance(source.get("failed"), int)
            or source.get("failed") < 0
            or source.get("conclusion") != "success"
            or source.get("failed") != 0
            or source.get("exact_sha_bound") is not True
        ):
            return self._ci_error(
                "TASK_PERSISTENCE_CI_VERIFICATION_EVIDENCE_INVALID"
            )

        evidence = {
            "target_sha": target_sha,
            "workflow": "Verify",
            "event": source["event"],
            "run_number": source["run_number"],
            "passed": source["passed"],
            "failed": 0,
            "conclusion": "success",
            "exact_sha_bound": True,
        }

        return {
            "error": False,
            "status": "TASK_PERSISTENCE_CI_VERIFICATION_EVIDENCE_READY",
            **evidence,
            "evidence_source": "CALLER_SUPPLIED_CI_METADATA",
            "evidence_structurally_valid": True,
            "ci_success_claim_consistent": True,
            "externally_verified": False,
            "read_only": True,
            "executed": False,
        }

    def bind_ci_evidence(self, manifest, ci_evidence):
        source = dict(manifest) if isinstance(manifest, dict) else {}
        verification = (
            dict(ci_evidence)
            if isinstance(ci_evidence, dict)
            else {}
        )

        if not self._valid_manifest(source):
            return self._binding_error(
                "TASK_PERSISTENCE_CAPABILITY_MANIFEST_REQUIRED"
            )
        if not self._valid_ci_evidence(verification):
            return self._binding_error(
                "TASK_PERSISTENCE_CI_VERIFICATION_EVIDENCE_REQUIRED"
            )
        if source.get("revision_id") is None:
            return self._binding_error(
                "TASK_PERSISTENCE_CAPABILITY_REVISION_UNBOUND"
            )
        if source["revision_id"] != verification["target_sha"]:
            return self._binding_error(
                "TASK_PERSISTENCE_CAPABILITY_CI_SHA_MISMATCH"
            )

        items = []
        for item in source["capabilities"]:
            enriched = dict(item)
            enriched["ci_evidence_bound"] = True
            enriched["externally_verified"] = False
            items.append(enriched)

        evidence = {
            "manifest_id": source["manifest_id"],
            "revision_id": source["revision_id"],
            "ci_target_sha": verification["target_sha"],
            "ci_run_number": verification["run_number"],
            "ci_passed": verification["passed"],
            "ci_failed": verification["failed"],
            "capabilities": items,
        }
        binding_id = self._digest(
            "task-persistence-capability-ci-binding:",
            evidence,
        )

        return {
            "error": False,
            "status": "TASK_PERSISTENCE_CAPABILITY_CI_BOUND",
            "binding_id": binding_id,
            "manifest_id": source["manifest_id"],
            "revision_id": source["revision_id"],
            "ci_target_sha": verification["target_sha"],
            "ci_run_number": verification["run_number"],
            "ci_passed": verification["passed"],
            "ci_failed": verification["failed"],
            "ci_conclusion": verification["conclusion"],
            "ci_sha_match": True,
            "ci_evidence_bound": True,
            "capabilities": items,
            "active_probe_performed": False,
            "externally_verified": False,
            "automatic_retry_allowed": False,
            "automatic_lock_recovery_allowed": False,
            "manual_lock_removal_allowed": False,
            "business_execution_ready": False,
            "mutation_ready": False,
            "read_only": True,
            "executed": False,
        }

    def build_audit_receipt(self, manifest, binding=None):
        source = dict(manifest) if isinstance(manifest, dict) else {}
        if not self._valid_manifest(source):
            return self._audit_error(
                "TASK_PERSISTENCE_CAPABILITY_MANIFEST_REQUIRED"
            )

        bound = dict(binding) if isinstance(binding, dict) else {}
        if bound:
            if not self._valid_binding(bound, source):
                return self._audit_error(
                    "TASK_PERSISTENCE_CAPABILITY_CI_BINDING_INVALID"
                )
            ci_state = {
                "ci_evidence_bound": True,
                "binding_id": bound["binding_id"],
                "ci_target_sha": bound["ci_target_sha"],
                "ci_run_number": bound["ci_run_number"],
                "ci_passed": bound["ci_passed"],
                "ci_failed": bound["ci_failed"],
            }
        else:
            ci_state = {
                "ci_evidence_bound": False,
                "binding_id": None,
                "ci_target_sha": None,
                "ci_run_number": None,
                "ci_passed": None,
                "ci_failed": None,
            }

        evidence = {
            "manifest_id": source["manifest_id"],
            "revision_id": source["revision_id"],
            "release_ready": source["release_ready"],
            "capabilities": list(source["capabilities"]),
            **ci_state,
            "active_probe_performed": False,
            "externally_verified": False,
        }
        receipt_id = self._digest(
            "task-persistence-capability-audit:",
            evidence,
        )

        return {
            "error": False,
            "status": "TASK_PERSISTENCE_CAPABILITY_AUDIT_READY",
            "receipt_id": receipt_id,
            "manifest_id": source["manifest_id"],
            "revision_id": source["revision_id"],
            **ci_state,
            "active_probe_performed": False,
            "externally_verified": False,
            "automatic_retry_allowed": False,
            "automatic_lock_recovery_allowed": False,
            "manual_lock_removal_allowed": False,
            "business_execution_ready": False,
            "mutation_ready": False,
            "read_only": True,
            "executed": False,
        }

    def build_report(self):
        try:
            snapshot = self.release_observability_service.build_snapshot()
        except Exception:
            return self._report_error(
                "TASK_PERSISTENCE_CAPABILITY_RELEASE_SNAPSHOT_UNAVAILABLE"
            )

        manifest = self.build_manifest(snapshot)
        if manifest.get("error") is True:
            return manifest

        binding = None
        ci_state = "UNBOUND"

        if self.ci_evidence is not None:
            evidence = self.build_ci_verification_evidence(
                self.ci_evidence
            )
            if evidence.get("error") is True:
                return evidence
            binding = self.bind_ci_evidence(manifest, evidence)
            if binding.get("error") is True:
                return binding
            ci_state = "BOUND"

        audit = self.build_audit_receipt(manifest, binding)
        if audit.get("error") is True:
            return audit

        return {
            "error": False,
            "status": "TASK_PERSISTENCE_CAPABILITY_PROVENANCE_REPORT",
            "manifest_id": manifest["manifest_id"],
            "audit_receipt_id": audit["receipt_id"],
            "revision_id": manifest["revision_id"],
            "revision_declared": manifest["revision_declared"],
            "release_ready": manifest["release_ready"],
            "capability_count": manifest["capability_count"],
            "capabilities": list(manifest["capabilities"]),
            "implementation_contract_count": manifest[
                "implementation_contract_count"
            ],
            "runtime_observation_count": manifest[
                "runtime_observation_count"
            ],
            "ci_evidence_state": ci_state,
            "ci_evidence_bound": binding is not None,
            "ci_run_number": (
                binding["ci_run_number"]
                if binding is not None
                else None
            ),
            "ci_passed": (
                binding["ci_passed"]
                if binding is not None
                else None
            ),
            "active_probe_performed": False,
            "externally_verified": False,
            "automatic_retry_allowed": False,
            "automatic_lock_recovery_allowed": False,
            "manual_lock_removal_allowed": False,
            "business_execution_ready": False,
            "mutation_ready": False,
            "read_only": True,
            "executed": False,
        }

    @classmethod
    def _valid_release_snapshot(cls, value):
        expected = {
            row["capability"]
            for row in cls.CAPABILITY_CATALOG
        }
        capabilities = value.get("capabilities")
        return (
            isinstance(value, dict)
            and value.get("status") == (
                "TASK_PERSISTENCE_RELEASE_SNAPSHOT_READY"
            )
            and value.get("error") is False
            and isinstance(value.get("release_ready"), bool)
            and isinstance(capabilities, dict)
            and set(capabilities) == expected
            and all(
                isinstance(capabilities[name], bool)
                for name in expected
            )
            and value.get("active_probe_performed", False) is False
            and value.get("automatic_retry_allowed") is False
            and value.get("automatic_lock_recovery_allowed") is False
            and value.get("manual_lock_removal_allowed") is False
            and value.get("business_execution_ready") is False
            and value.get("mutation_ready") is False
            and value.get("read_only") is True
            and value.get("executed") is False
        )

    @classmethod
    def _valid_manifest(cls, value):
        if not (
            isinstance(value, dict)
            and value.get("status") == (
                "TASK_PERSISTENCE_CAPABILITY_PROVENANCE_READY"
            )
            and value.get("error") is False
            and isinstance(value.get("manifest_id"), str)
            and value.get("manifest_id")
            .startswith("task-persistence-capability-manifest:")
            and isinstance(value.get("release_ready"), bool)
            and isinstance(value.get("capabilities"), list)
            and value.get("capability_count")
            == len(cls.CAPABILITY_CATALOG)
            == len(value.get("capabilities"))
            and value.get("active_probe_performed") is False
            and value.get("ci_evidence_bound") is False
            and value.get("externally_verified") is False
            and value.get("automatic_retry_allowed") is False
            and value.get("automatic_lock_recovery_allowed") is False
            and value.get("manual_lock_removal_allowed") is False
            and value.get("business_execution_ready") is False
            and value.get("mutation_ready") is False
            and value.get("read_only") is True
            and value.get("executed") is False
        ):
            return False

        revision = value.get("revision_id")
        if revision is not None and cls._normalize_revision(revision) != revision:
            return False
        if value.get("revision_declared") != (revision is not None):
            return False

        expected_items = []
        enabled_by_name = {}
        for item in value["capabilities"]:
            if not isinstance(item, dict):
                return False
            capability = item.get("capability")
            if capability in enabled_by_name:
                return False
            enabled_by_name[capability] = item.get("enabled")

        for row in cls.CAPABILITY_CATALOG:
            capability = row["capability"]
            if capability not in enabled_by_name:
                return False
            expected_items.append({
                "capability": capability,
                "required": True,
                "enabled": enabled_by_name[capability],
                "evidence_mode": row["evidence_mode"],
                "runtime_observed": (
                    row["evidence_mode"] == "RUNTIME_DIAGNOSTIC"
                ),
                "implementation_contract_claimed": True,
                "implementation_source": row["implementation_source"],
                "focused_test_file": row["focused_test_file"],
                "project_doc": row["project_doc"],
                "ci_evidence_bound": False,
                "externally_verified": False,
            })

        if not all(
            isinstance(item["enabled"], bool)
            for item in expected_items
        ):
            return False
        if value["capabilities"] != expected_items:
            return False
        if value.get("implementation_contract_count") != sum(
            item["evidence_mode"] == "IMPLEMENTATION_CONTRACT"
            for item in expected_items
        ):
            return False
        if value.get("runtime_observation_count") != sum(
            item["evidence_mode"] == "RUNTIME_DIAGNOSTIC"
            for item in expected_items
        ):
            return False

        evidence = {
            "revision_id": revision,
            "release_ready": value["release_ready"],
            "capabilities": expected_items,
            "active_probe_performed": False,
            "ci_evidence_bound": False,
            "externally_verified": False,
        }
        return value["manifest_id"] == cls._digest(
            "task-persistence-capability-manifest:",
            evidence,
        )

    @classmethod
    def _valid_ci_evidence(cls, value):
        return (
            isinstance(value, dict)
            and value.get("status") == (
                "TASK_PERSISTENCE_CI_VERIFICATION_EVIDENCE_READY"
            )
            and value.get("error") is False
            and cls._normalize_revision(value.get("target_sha"))
            == value.get("target_sha")
            and value.get("workflow") == "Verify"
            and value.get("event") in {"push", "pull_request"}
            and isinstance(value.get("run_number"), int)
            and not isinstance(value.get("run_number"), bool)
            and value.get("run_number") > 0
            and isinstance(value.get("passed"), int)
            and not isinstance(value.get("passed"), bool)
            and value.get("passed") >= 0
            and value.get("failed") == 0
            and value.get("conclusion") == "success"
            and value.get("exact_sha_bound") is True
            and value.get("evidence_source")
            == "CALLER_SUPPLIED_CI_METADATA"
            and value.get("evidence_structurally_valid") is True
            and value.get("ci_success_claim_consistent") is True
            and value.get("externally_verified") is False
            and value.get("read_only") is True
            and value.get("executed") is False
        )

    @classmethod
    def _valid_binding(cls, value, manifest):
        if not (
            isinstance(value, dict)
            and value.get("status") == (
                "TASK_PERSISTENCE_CAPABILITY_CI_BOUND"
            )
            and value.get("error") is False
            and value.get("manifest_id") == manifest.get("manifest_id")
            and value.get("revision_id") == manifest.get("revision_id")
            and value.get("ci_target_sha") == manifest.get("revision_id")
            and value.get("ci_sha_match") is True
            and value.get("ci_evidence_bound") is True
            and value.get("active_probe_performed") is False
            and value.get("externally_verified") is False
            and value.get("automatic_retry_allowed") is False
            and value.get("automatic_lock_recovery_allowed") is False
            and value.get("manual_lock_removal_allowed") is False
            and value.get("business_execution_ready") is False
            and value.get("mutation_ready") is False
            and value.get("read_only") is True
            and value.get("executed") is False
            and isinstance(value.get("capabilities"), list)
        ):
            return False

        expected = []
        for item in manifest["capabilities"]:
            row = dict(item)
            row["ci_evidence_bound"] = True
            row["externally_verified"] = False
            expected.append(row)

        if value["capabilities"] != expected:
            return False

        evidence = {
            "manifest_id": manifest["manifest_id"],
            "revision_id": manifest["revision_id"],
            "ci_target_sha": value["ci_target_sha"],
            "ci_run_number": value["ci_run_number"],
            "ci_passed": value["ci_passed"],
            "ci_failed": value["ci_failed"],
            "capabilities": expected,
        }
        return value.get("binding_id") == cls._digest(
            "task-persistence-capability-ci-binding:",
            evidence,
        )

    @staticmethod
    def _normalize_revision(value):
        if value is None:
            return None
        if not isinstance(value, str):
            return None
        normalized = value.strip().lower()
        if not re.fullmatch(r"[0-9a-f]{40}", normalized):
            return None
        return normalized

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
            "status": "TASK_PERSISTENCE_CAPABILITY_PROVENANCE_UNAVAILABLE",
            "active_probe_performed": False,
            "externally_verified": False,
            "automatic_retry_allowed": False,
            "automatic_lock_recovery_allowed": False,
            "manual_lock_removal_allowed": False,
            "business_execution_ready": False,
            "mutation_ready": False,
            "read_only": True,
            "executed": False,
        }

    @classmethod
    def _ci_error(cls, code):
        result = cls._error(code)
        result["status"] = "TASK_PERSISTENCE_CI_VERIFICATION_EVIDENCE_UNAVAILABLE"
        return result

    @classmethod
    def _binding_error(cls, code):
        result = cls._error(code)
        result["status"] = "TASK_PERSISTENCE_CAPABILITY_CI_BINDING_UNAVAILABLE"
        return result

    @classmethod
    def _audit_error(cls, code):
        result = cls._error(code)
        result["status"] = "TASK_PERSISTENCE_CAPABILITY_AUDIT_UNAVAILABLE"
        return result

    @classmethod
    def _report_error(cls, code):
        result = cls._error(code)
        result["status"] = "TASK_PERSISTENCE_CAPABILITY_PROVENANCE_REPORT"
        return result
