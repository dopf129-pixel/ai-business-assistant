import hashlib
import json


class TaskPersistenceVerificationManifestProvenanceService:
    """Bind validated CI test manifests to capability provenance without network I/O."""

    def __init__(
        self,
        capability_provenance_service,
        verification_manifest_service,
    ):
        self.capability_provenance_service = capability_provenance_service
        self.verification_manifest_service = verification_manifest_service

    def import_manifest(self, snapshot, manifest, revision_id):
        release = dict(snapshot) if isinstance(snapshot, dict) else {}
        source = dict(manifest) if isinstance(manifest, dict) else {}

        if not self.capability_provenance_service._valid_release_snapshot(
            release
        ):
            return self._error(
                "TASK_PERSISTENCE_VERIFICATION_RELEASE_SNAPSHOT_REQUIRED"
            )

        validation = self.verification_manifest_service.validate(source)
        if validation.get("error") is not False:
            return self._error(
                "TASK_PERSISTENCE_VERIFICATION_MANIFEST_INVALID"
            )

        revision = (
            self.capability_provenance_service
            ._normalize_revision(revision_id)
        )
        if revision is None:
            return self._error(
                "TASK_PERSISTENCE_VERIFICATION_REVISION_INVALID"
            )
        if validation.get("commit_sha") != revision:
            return self._error(
                "TASK_PERSISTENCE_VERIFICATION_MANIFEST_SHA_MISMATCH"
            )

        provenance = (
            self.capability_provenance_service
            .build_manifest(
                release,
                revision_id=revision,
            )
        )
        if provenance.get("error") is True:
            return self._error(
                "TASK_PERSISTENCE_CAPABILITY_MANIFEST_UNAVAILABLE"
            )

        test_suite_passed = source.get("status") == "passed"
        evidence = {
            "revision_id": revision,
            "capability_manifest_id": provenance["manifest_id"],
            "verification_manifest_id": source[
                "verification_manifest_id"
            ],
            "test_report_id": source["test_report_id"],
            "workflow": source["workflow"],
            "event": source["event"],
            "run_id": source["run_id"],
            "run_number": source["run_number"],
            "passed": source["passed"],
            "failed": source["failed"],
            "total": source["total"],
            "skipped": source["skipped"],
            "test_suite_passed": test_suite_passed,
            "final_ci_run_success_confirmed": False,
            "externally_verified": False,
        }
        import_id = self._digest(
            "task-persistence-verification-import:",
            evidence,
        )

        return {
            "error": False,
            "status": (
                "TASK_PERSISTENCE_VERIFICATION_MANIFEST_IMPORTED"
            ),
            "import_id": import_id,
            "revision_id": revision,
            "capability_manifest_id": provenance["manifest_id"],
            "verification_manifest_id": source[
                "verification_manifest_id"
            ],
            "test_report_id": source["test_report_id"],
            "workflow": source["workflow"],
            "event": source["event"],
            "run_id": source["run_id"],
            "run_number": source["run_number"],
            "passed": source["passed"],
            "failed": source["failed"],
            "total": source["total"],
            "skipped": source["skipped"],
            "test_suite_passed": test_suite_passed,
            "verification_manifest_bound": True,
            "ci_evidence_bound": False,
            "final_ci_run_success_confirmed": False,
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

    def build_binding(
        self,
        snapshot,
        provenance_manifest,
        verification_manifest,
        imported_evidence,
    ):
        release = dict(snapshot) if isinstance(snapshot, dict) else {}
        provenance = (
            dict(provenance_manifest)
            if isinstance(provenance_manifest, dict)
            else {}
        )
        verification = (
            dict(verification_manifest)
            if isinstance(verification_manifest, dict)
            else {}
        )
        imported = (
            dict(imported_evidence)
            if isinstance(imported_evidence, dict)
            else {}
        )

        if not self.capability_provenance_service._valid_release_snapshot(
            release
        ):
            return self._binding_error(
                "TASK_PERSISTENCE_VERIFICATION_RELEASE_SNAPSHOT_REQUIRED"
            )
        if not self.capability_provenance_service._valid_manifest(
            provenance
        ):
            return self._binding_error(
                "TASK_PERSISTENCE_CAPABILITY_MANIFEST_REQUIRED"
            )
        if not self.capability_provenance_service._manifest_matches_snapshot(
            release,
            provenance,
        ):
            return self._binding_error(
                "TASK_PERSISTENCE_CAPABILITY_MANIFEST_LINEAGE_MISMATCH"
            )
        if self.verification_manifest_service.validate(
            verification
        ).get("error") is not False:
            return self._binding_error(
                "TASK_PERSISTENCE_VERIFICATION_MANIFEST_INVALID"
            )
        if not self._valid_import(
            release,
            provenance,
            verification,
            imported,
        ):
            return self._binding_error(
                "TASK_PERSISTENCE_VERIFICATION_IMPORT_INVALID"
            )

        capabilities = []
        for item in provenance["capabilities"]:
            enriched = dict(item)
            enriched["verification_manifest_bound"] = True
            enriched["test_suite_manifest_passed"] = imported[
                "test_suite_passed"
            ]
            enriched["externally_verified"] = False
            capabilities.append(enriched)

        evidence = {
            "import_id": imported["import_id"],
            "revision_id": provenance["revision_id"],
            "capability_manifest_id": provenance["manifest_id"],
            "verification_manifest_id": verification[
                "verification_manifest_id"
            ],
            "test_report_id": verification["test_report_id"],
            "test_suite_passed": imported["test_suite_passed"],
            "capabilities": capabilities,
        }
        binding_id = self._digest(
            "task-persistence-verification-binding:",
            evidence,
        )

        return {
            "error": False,
            "status": (
                "TASK_PERSISTENCE_VERIFICATION_MANIFEST_PROVENANCE_BOUND"
            ),
            "binding_id": binding_id,
            "import_id": imported["import_id"],
            "revision_id": provenance["revision_id"],
            "capability_manifest_id": provenance["manifest_id"],
            "verification_manifest_id": verification[
                "verification_manifest_id"
            ],
            "test_report_id": verification["test_report_id"],
            "test_suite_passed": imported["test_suite_passed"],
            "verification_manifest_bound": True,
            "ci_evidence_bound": False,
            "final_ci_run_success_confirmed": False,
            "capabilities": capabilities,
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

    def build_audit_receipt(
        self,
        snapshot,
        provenance_manifest,
        verification_manifest,
        imported_evidence,
        binding,
    ):
        release = dict(snapshot) if isinstance(snapshot, dict) else {}
        provenance = (
            dict(provenance_manifest)
            if isinstance(provenance_manifest, dict)
            else {}
        )
        verification = (
            dict(verification_manifest)
            if isinstance(verification_manifest, dict)
            else {}
        )
        imported = (
            dict(imported_evidence)
            if isinstance(imported_evidence, dict)
            else {}
        )
        bound = dict(binding) if isinstance(binding, dict) else {}

        if not self._valid_binding(
            release,
            provenance,
            verification,
            imported,
            bound,
        ):
            return self._audit_error(
                "TASK_PERSISTENCE_VERIFICATION_BINDING_INVALID"
            )

        evidence = {
            "binding_id": bound["binding_id"],
            "import_id": imported["import_id"],
            "revision_id": bound["revision_id"],
            "capability_manifest_id": bound[
                "capability_manifest_id"
            ],
            "verification_manifest_id": bound[
                "verification_manifest_id"
            ],
            "test_report_id": bound["test_report_id"],
            "test_suite_passed": bound["test_suite_passed"],
            "capabilities": list(bound["capabilities"]),
            "final_ci_run_success_confirmed": False,
            "externally_verified": False,
        }
        receipt_id = self._digest(
            "task-persistence-verification-audit:",
            evidence,
        )

        return {
            "error": False,
            "status": (
                "TASK_PERSISTENCE_VERIFICATION_PROVENANCE_AUDIT_READY"
            ),
            "receipt_id": receipt_id,
            "binding_id": bound["binding_id"],
            "import_id": imported["import_id"],
            "revision_id": bound["revision_id"],
            "verification_manifest_id": bound[
                "verification_manifest_id"
            ],
            "test_report_id": bound["test_report_id"],
            "test_suite_passed": bound["test_suite_passed"],
            "verification_manifest_bound": True,
            "ci_evidence_bound": False,
            "final_ci_run_success_confirmed": False,
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

    def build_report(self, verification_manifest, revision_id):
        try:
            snapshot = (
                self.capability_provenance_service
                .release_observability_service
                .build_snapshot()
            )
        except Exception:
            return self._report_error(
                "TASK_PERSISTENCE_VERIFICATION_RELEASE_SNAPSHOT_UNAVAILABLE"
            )

        imported = self.import_manifest(
            snapshot,
            verification_manifest,
            revision_id,
        )
        if imported.get("error") is True:
            return imported

        provenance = (
            self.capability_provenance_service
            .build_manifest(
                snapshot,
                revision_id=imported["revision_id"],
            )
        )
        if provenance.get("error") is True:
            return provenance

        binding = self.build_binding(
            snapshot,
            provenance,
            verification_manifest,
            imported,
        )
        if binding.get("error") is True:
            return binding

        audit = self.build_audit_receipt(
            snapshot,
            provenance,
            verification_manifest,
            imported,
            binding,
        )
        if audit.get("error") is True:
            return audit

        return {
            "error": False,
            "status": (
                "TASK_PERSISTENCE_VERIFICATION_MANIFEST_PROVENANCE_REPORT"
            ),
            "revision_id": imported["revision_id"],
            "verification_manifest_id": imported[
                "verification_manifest_id"
            ],
            "test_report_id": imported["test_report_id"],
            "test_suite_passed": imported["test_suite_passed"],
            "verification_manifest_bound": True,
            "ci_evidence_bound": False,
            "final_ci_run_success_confirmed": False,
            "capability_manifest_id": provenance["manifest_id"],
            "binding_id": binding["binding_id"],
            "audit_receipt_id": audit["receipt_id"],
            "capabilities": list(binding["capabilities"]),
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

    def _valid_import(
        self,
        snapshot,
        provenance,
        verification,
        imported,
    ):
        validation = self.verification_manifest_service.validate(
            verification
        )
        if validation.get("error") is not False:
            return False
        if not self.capability_provenance_service._manifest_matches_snapshot(
            snapshot,
            provenance,
        ):
            return False
        if imported.get("status") != (
            "TASK_PERSISTENCE_VERIFICATION_MANIFEST_IMPORTED"
        ):
            return False
        if imported.get("error") is not False:
            return False
        if imported.get("revision_id") != provenance.get("revision_id"):
            return False
        if imported.get("revision_id") != validation.get("commit_sha"):
            return False
        if imported.get("capability_manifest_id") != provenance.get(
            "manifest_id"
        ):
            return False
        if imported.get("verification_manifest_id") != verification.get(
            "verification_manifest_id"
        ):
            return False
        if imported.get("test_report_id") != verification.get(
            "test_report_id"
        ):
            return False
        mirrored_fields = (
            "workflow",
            "event",
            "run_id",
            "run_number",
            "passed",
            "failed",
            "total",
            "skipped",
        )
        if any(
            imported.get(field) != verification.get(field)
            for field in mirrored_fields
        ):
            return False
        expected_passed = verification.get("status") == "passed"
        if imported.get("test_suite_passed") is not expected_passed:
            return False
        if (
            imported.get("verification_manifest_bound") is not True
            or imported.get("ci_evidence_bound") is not False
            or imported.get("final_ci_run_success_confirmed") is not False
            or imported.get("active_probe_performed") is not False
            or imported.get("network_fetch_performed") is not False
            or imported.get("externally_verified") is not False
            or imported.get("automatic_retry_allowed") is not False
            or imported.get("automatic_lock_recovery_allowed") is not False
            or imported.get("manual_lock_removal_allowed") is not False
            or imported.get("business_execution_ready") is not False
            or imported.get("mutation_ready") is not False
            or imported.get("read_only") is not True
            or imported.get("executed") is not False
        ):
            return False

        expected = {
            "revision_id": imported["revision_id"],
            "capability_manifest_id": provenance["manifest_id"],
            "verification_manifest_id": verification[
                "verification_manifest_id"
            ],
            "test_report_id": verification["test_report_id"],
            "workflow": verification["workflow"],
            "event": verification["event"],
            "run_id": verification["run_id"],
            "run_number": verification["run_number"],
            "passed": verification["passed"],
            "failed": verification["failed"],
            "total": verification["total"],
            "skipped": verification["skipped"],
            "test_suite_passed": expected_passed,
            "final_ci_run_success_confirmed": False,
            "externally_verified": False,
        }
        return imported.get("import_id") == self._digest(
            "task-persistence-verification-import:",
            expected,
        )

    def _valid_binding(
        self,
        snapshot,
        provenance,
        verification,
        imported,
        binding,
    ):
        if not self._valid_import(
            snapshot,
            provenance,
            verification,
            imported,
        ):
            return False
        if binding.get("status") != (
            "TASK_PERSISTENCE_VERIFICATION_MANIFEST_PROVENANCE_BOUND"
        ):
            return False
        if binding.get("error") is not False:
            return False
        if binding.get("import_id") != imported.get("import_id"):
            return False
        if binding.get("revision_id") != provenance.get("revision_id"):
            return False
        if binding.get("capability_manifest_id") != provenance.get(
            "manifest_id"
        ):
            return False
        if binding.get("verification_manifest_id") != verification.get(
            "verification_manifest_id"
        ):
            return False
        if binding.get("test_report_id") != verification.get(
            "test_report_id"
        ):
            return False
        if binding.get("test_suite_passed") is not imported.get(
            "test_suite_passed"
        ):
            return False
        if (
            binding.get("verification_manifest_bound") is not True
            or binding.get("ci_evidence_bound") is not False
            or binding.get("final_ci_run_success_confirmed") is not False
            or binding.get("active_probe_performed") is not False
            or binding.get("network_fetch_performed") is not False
            or binding.get("externally_verified") is not False
            or binding.get("automatic_retry_allowed") is not False
            or binding.get("automatic_lock_recovery_allowed") is not False
            or binding.get("manual_lock_removal_allowed") is not False
            or binding.get("business_execution_ready") is not False
            or binding.get("mutation_ready") is not False
            or binding.get("read_only") is not True
            or binding.get("executed") is not False
        ):
            return False

        expected_capabilities = []
        for item in provenance["capabilities"]:
            enriched = dict(item)
            enriched["verification_manifest_bound"] = True
            enriched["test_suite_manifest_passed"] = imported[
                "test_suite_passed"
            ]
            enriched["externally_verified"] = False
            expected_capabilities.append(enriched)
        if binding.get("capabilities") != expected_capabilities:
            return False

        evidence = {
            "import_id": imported["import_id"],
            "revision_id": provenance["revision_id"],
            "capability_manifest_id": provenance["manifest_id"],
            "verification_manifest_id": verification[
                "verification_manifest_id"
            ],
            "test_report_id": verification["test_report_id"],
            "test_suite_passed": imported["test_suite_passed"],
            "capabilities": expected_capabilities,
        }
        return binding.get("binding_id") == self._digest(
            "task-persistence-verification-binding:",
            evidence,
        )

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
            "status": (
                "TASK_PERSISTENCE_VERIFICATION_MANIFEST_PROVENANCE_UNAVAILABLE"
            ),
            "verification_manifest_bound": False,
            "ci_evidence_bound": False,
            "final_ci_run_success_confirmed": False,
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

    @classmethod
    def _binding_error(cls, code):
        result = cls._error(code)
        result["status"] = (
            "TASK_PERSISTENCE_VERIFICATION_MANIFEST_BINDING_UNAVAILABLE"
        )
        return result

    @classmethod
    def _audit_error(cls, code):
        result = cls._error(code)
        result["status"] = (
            "TASK_PERSISTENCE_VERIFICATION_PROVENANCE_AUDIT_UNAVAILABLE"
        )
        return result

    @classmethod
    def _report_error(cls, code):
        result = cls._error(code)
        result["status"] = (
            "TASK_PERSISTENCE_VERIFICATION_MANIFEST_PROVENANCE_REPORT"
        )
        return result
