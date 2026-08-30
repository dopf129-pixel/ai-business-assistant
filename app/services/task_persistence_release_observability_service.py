import hashlib
import json


class TaskPersistenceReleaseObservabilityService:
    """Read-only release readiness and incident audit for task persistence."""

    def __init__(self, task_service, operational_service):
        self.task_service = task_service
        self.operational_service = operational_service

    def build_snapshot(self):
        try:
            operational = self.operational_service.build_report()
            persistence = self.task_service.get_persistence_diagnostics()
            lock = self.task_service.get_write_lock_diagnostics()
        except Exception:
            return self._blocked("TASK_PERSISTENCE_RELEASE_DIAGNOSTICS_UNAVAILABLE")

        if not self._valid_operational(operational):
            return self._blocked("TASK_PERSISTENCE_RELEASE_OPERATIONAL_INVALID")
        if not self._valid_persistence(persistence):
            return self._blocked("TASK_PERSISTENCE_RELEASE_CAPABILITY_INVALID")
        if not self._valid_lock(lock):
            return self._blocked("TASK_PERSISTENCE_RELEASE_LOCK_INVALID")

        blockers = list(operational.get("blockers") or [])
        warnings = list(operational.get("warnings") or [])

        capabilities = {
            "optimistic_concurrency_guard": persistence["optimistic_concurrency_guard"],
            "kernel_lock_guard": lock["kernel_lock_guard"],
            "atomic_replace_required": persistence["atomic_replace_required"],
            "file_fsync_required": persistence["file_fsync_required"],
            "directory_fsync_required": persistence["directory_fsync_required"],
            "coordination_file_ownership_neutral": persistence[
                "coordination_file_ownership_neutral"
            ],
        }

        missing_capabilities = [
            name for name, enabled in capabilities.items() if enabled is not True
        ]
        for name in missing_capabilities:
            blockers.append("RELEASE_CAPABILITY_MISSING:" + name)

        blockers = self._stable_unique(blockers)
        warnings = self._stable_unique(warnings)
        release_ready = not blockers

        return {
            "error": False,
            "status": "TASK_PERSISTENCE_RELEASE_SNAPSHOT_READY",
            "release_ready": release_ready,
            "operational_state": operational["operational_state"],
            "blocker_count": len(blockers),
            "blockers": blockers,
            "warning_count": len(warnings),
            "warnings": warnings,
            "capabilities": capabilities,
            "missing_capabilities": missing_capabilities,
            "coordination_file_present": lock.get("coordination_file_present"),
            "lock_inspection_state": lock["inspection_state"],
            "last_save_state": persistence["last_save_state"],
            "last_save_issue": persistence.get("last_save_issue"),
            "last_lock_release_issue": persistence.get("last_lock_release_issue"),
            "automatic_retry_allowed": False,
            "automatic_lock_recovery_allowed": False,
            "manual_lock_removal_allowed": False,
            "business_execution_ready": False,
            "mutation_ready": False,
            "read_only": True,
            "executed": False,
        }

    def classify_incident(self, snapshot):
        source = dict(snapshot) if isinstance(snapshot, dict) else {}
        if not self._valid_snapshot(source):
            return self._incident_error("TASK_PERSISTENCE_RELEASE_SNAPSHOT_REQUIRED")

        categories = self._expected_incident_categories(source)
        blockers = list(source.get("blockers") or [])
        warnings = list(source.get("warnings") or [])
        incident_detected = bool(categories or blockers or warnings)

        return {
            "error": False,
            "status": "TASK_PERSISTENCE_RELEASE_INCIDENT_READY",
            "incident_detected": incident_detected,
            "incident_categories": categories,
            "release_ready": source["release_ready"],
            "blockers": list(source["blockers"]),
            "warnings": list(source["warnings"]),
            "human_review_required": bool(blockers or warnings),
            "automatic_retry_allowed": False,
            "automatic_lock_recovery_allowed": False,
            "manual_lock_removal_allowed": False,
            "business_execution_ready": False,
            "mutation_ready": False,
            "read_only": True,
            "executed": False,
        }

    def build_audit_receipt(self, snapshot, incident):
        source = dict(snapshot) if isinstance(snapshot, dict) else {}
        classification = dict(incident) if isinstance(incident, dict) else {}
        if not self._valid_snapshot(source):
            return self._audit_error("TASK_PERSISTENCE_RELEASE_SNAPSHOT_REQUIRED")
        if not self._valid_incident(classification, source):
            return self._audit_error("TASK_PERSISTENCE_RELEASE_INCIDENT_INVALID")

        evidence = {
            "release_ready": source["release_ready"],
            "operational_state": source["operational_state"],
            "blockers": list(source["blockers"]),
            "warnings": list(source["warnings"]),
            "capabilities": dict(source["capabilities"]),
            "coordination_file_present": source["coordination_file_present"],
            "lock_inspection_state": source["lock_inspection_state"],
            "last_save_state": source["last_save_state"],
            "last_save_issue": source["last_save_issue"],
            "last_lock_release_issue": source["last_lock_release_issue"],
            "incident_detected": classification["incident_detected"],
            "incident_categories": list(classification["incident_categories"]),
            "human_review_required": classification["human_review_required"],
        }
        canonical = json.dumps(
            evidence,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        receipt_id = "task-persistence-release:" + hashlib.sha256(canonical).hexdigest()

        return {
            "error": False,
            "status": "TASK_PERSISTENCE_RELEASE_AUDIT_READY",
            "receipt_id": receipt_id,
            "evidence": evidence,
            "automatic_retry_allowed": False,
            "automatic_lock_recovery_allowed": False,
            "manual_lock_removal_allowed": False,
            "business_execution_ready": False,
            "mutation_ready": False,
            "read_only": True,
            "executed": False,
        }

    def build_release_report(self):
        snapshot = self.build_snapshot()
        if snapshot.get("error") is True:
            return snapshot
        incident = self.classify_incident(snapshot)
        if incident.get("error") is True:
            return incident
        audit = self.build_audit_receipt(snapshot, incident)
        if audit.get("error") is True:
            return audit

        return {
            "error": False,
            "status": "TASK_PERSISTENCE_RELEASE_READINESS",
            "release_ready": snapshot["release_ready"],
            "operational_state": snapshot["operational_state"],
            "blockers": list(snapshot["blockers"]),
            "warnings": list(snapshot["warnings"]),
            "capabilities": dict(snapshot["capabilities"]),
            "incident_detected": incident["incident_detected"],
            "incident_categories": list(incident["incident_categories"]),
            "human_review_required": incident["human_review_required"],
            "audit_receipt_id": audit["receipt_id"],
            "automatic_retry_allowed": False,
            "automatic_lock_recovery_allowed": False,
            "manual_lock_removal_allowed": False,
            "business_execution_ready": False,
            "mutation_ready": False,
            "read_only": True,
            "executed": False,
        }

    @staticmethod
    def _stable_unique(values):
        result = []
        for value in values:
            if value not in result:
                result.append(value)
        return result

    @staticmethod
    def _valid_operational(value):
        return (
            isinstance(value, dict)
            and value.get("status") == "TASK_PERSISTENCE_OPERATIONAL_READINESS"
            and value.get("error") is False
            and value.get("operational_state") in {"READY", "WARNING", "BLOCKED"}
            and isinstance(value.get("blockers"), list)
            and isinstance(value.get("warnings"), list)
            and value.get("blocker_count") == len(value.get("blockers"))
            and value.get("warning_count") == len(value.get("warnings"))
            and value.get("automatic_lock_recovery_allowed") is False
            and value.get("manual_lock_removal_allowed") is False
            and value.get("business_execution_ready") is False
            and value.get("mutation_ready") is False
            and value.get("read_only") is True
            and value.get("executed") is False
        )

    @staticmethod
    def _valid_persistence(value):
        return (
            isinstance(value, dict)
            and value.get("status") == "TASK_PERSISTENCE_DIAGNOSTICS"
            and value.get("optimistic_concurrency_guard") is True
            and isinstance(value.get("atomic_replace_required"), bool)
            and isinstance(value.get("file_fsync_required"), bool)
            and isinstance(value.get("directory_fsync_required"), bool)
            and isinstance(value.get("coordination_file_ownership_neutral"), bool)
            and value.get("read_only") is True
            and value.get("executed") is False
        )

    @staticmethod
    def _valid_lock(value):
        return (
            isinstance(value, dict)
            and value.get("status") == "TASK_WRITE_LOCK_DIAGNOSTICS"
            and value.get("inspection_state") in {
                "NO_ACTIVE_LOCK_EVIDENCE",
                "SELF_HELD",
                "CHECK_ERROR",
            }
            and isinstance(value.get("kernel_lock_guard"), bool)
            and value.get("orphan_file_blocks_writes") is False
            and value.get("stale_proven") is False
            and value.get("automatic_recovery_allowed") is False
            and value.get("manual_lock_removal_allowed") is False
            and value.get("read_only") is True
            and value.get("executed") is False
        )

    @classmethod
    def _valid_snapshot(cls, value):
        if not (
            isinstance(value, dict)
            and value.get("status") == "TASK_PERSISTENCE_RELEASE_SNAPSHOT_READY"
            and value.get("error") is False
            and isinstance(value.get("release_ready"), bool)
            and value.get("operational_state") in {"READY", "WARNING", "BLOCKED"}
            and isinstance(value.get("blockers"), list)
            and isinstance(value.get("warnings"), list)
            and value.get("blocker_count") == len(value.get("blockers"))
            and value.get("warning_count") == len(value.get("warnings"))
            and isinstance(value.get("capabilities"), dict)
            and isinstance(value.get("missing_capabilities"), list)
            and value.get("automatic_retry_allowed") is False
            and value.get("automatic_lock_recovery_allowed") is False
            and value.get("manual_lock_removal_allowed") is False
            and value.get("business_execution_ready") is False
            and value.get("mutation_ready") is False
            and value.get("read_only") is True
            and value.get("executed") is False
        ):
            return False

        expected_keys = {
            "optimistic_concurrency_guard",
            "kernel_lock_guard",
            "atomic_replace_required",
            "file_fsync_required",
            "directory_fsync_required",
            "coordination_file_ownership_neutral",
        }
        capabilities = value["capabilities"]
        if set(capabilities) != expected_keys:
            return False
        if not all(isinstance(capabilities[key], bool) for key in expected_keys):
            return False

        expected_missing = [
            name for name, enabled in capabilities.items()
            if enabled is not True
        ]
        if value["missing_capabilities"] != expected_missing:
            return False

        expected_blockers = list(value["blockers"])
        for name in expected_missing:
            code = "RELEASE_CAPABILITY_MISSING:" + name
            if code not in expected_blockers:
                return False

        return value["release_ready"] == (not expected_blockers)

    @classmethod
    def _valid_incident(cls, value, snapshot):
        if not (
            isinstance(value, dict)
            and value.get("status") == "TASK_PERSISTENCE_RELEASE_INCIDENT_READY"
            and value.get("error") is False
            and isinstance(value.get("incident_detected"), bool)
            and isinstance(value.get("incident_categories"), list)
            and value.get("release_ready") == snapshot.get("release_ready")
            and value.get("blockers") == snapshot.get("blockers")
            and value.get("warnings") == snapshot.get("warnings")
            and value.get("human_review_required")
            == bool(snapshot.get("blockers") or snapshot.get("warnings"))
            and value.get("automatic_retry_allowed") is False
            and value.get("automatic_lock_recovery_allowed") is False
            and value.get("manual_lock_removal_allowed") is False
            and value.get("business_execution_ready") is False
            and value.get("mutation_ready") is False
            and value.get("read_only") is True
            and value.get("executed") is False
        ):
            return False

        expected_categories = cls._expected_incident_categories(snapshot)
        expected_detected = bool(
            expected_categories
            or snapshot.get("blockers")
            or snapshot.get("warnings")
        )
        return (
            value["incident_categories"] == expected_categories
            and value["incident_detected"] == expected_detected
        )

    @staticmethod
    def _expected_incident_categories(snapshot):
        blockers = set(snapshot.get("blockers") or [])
        warnings = set(snapshot.get("warnings") or [])
        categories = []

        if "TASK_FILE_WRITE_LOCKED" in blockers:
            categories.append("LOCK_CONTENTION")
        if "TASK_WRITE_LOCK_INSPECTION_FAILED" in blockers:
            categories.append("LOCK_INSPECTION")
        if blockers.intersection({"TASK_STORE_UNREADABLE", "TASK_STORE_INVALID_ROOT"}):
            categories.append("STORE_INTEGRITY")
        if any(
            value.startswith("RELEASE_CAPABILITY_MISSING:")
            for value in blockers
        ):
            categories.append("RELEASE_CAPABILITY")
        if "TASK_DIRECTORY_FSYNC_ERROR" in warnings:
            categories.append("DURABILITY")
        if "TASK_FILE_WRITE_LOCK_RELEASE_ERROR" in warnings:
            categories.append("LOCK_RELEASE")
        if "TASK_STORE_RECONCILIATION_ISSUES" in warnings:
            categories.append("STORE_RECONCILIATION")
        if snapshot.get("last_save_state") == "FAILED" and not categories:
            categories.append("SAVE_FAILURE")

        return categories

    @staticmethod
    def _blocked(code):
        return {
            "error": True,
            "code": code,
            "status": "TASK_PERSISTENCE_RELEASE_READINESS_BLOCKED",
            "release_ready": False,
            "human_review_required": True,
            "automatic_retry_allowed": False,
            "automatic_lock_recovery_allowed": False,
            "manual_lock_removal_allowed": False,
            "business_execution_ready": False,
            "mutation_ready": False,
            "read_only": True,
            "executed": False,
        }

    @staticmethod
    def _incident_error(code):
        result = TaskPersistenceReleaseObservabilityService._blocked(code)
        result["status"] = "TASK_PERSISTENCE_RELEASE_INCIDENT_UNAVAILABLE"
        return result

    @staticmethod
    def _audit_error(code):
        result = TaskPersistenceReleaseObservabilityService._blocked(code)
        result["status"] = "TASK_PERSISTENCE_RELEASE_AUDIT_UNAVAILABLE"
        return result
