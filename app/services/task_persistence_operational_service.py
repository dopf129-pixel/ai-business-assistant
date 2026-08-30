class TaskPersistenceOperationalService:
    """Build a deterministic read-only operator projection for task persistence."""

    LOAD_BLOCKERS = {
        "UNREADABLE": "TASK_STORE_UNREADABLE",
        "INVALID_ROOT": "TASK_STORE_INVALID_ROOT",
    }

    def __init__(self, task_service):
        self.task_service = task_service

    def build_report(self):
        try:
            load = self.task_service.get_load_diagnostics()
            persistence = self.task_service.get_persistence_diagnostics()
            lock = self.task_service.get_write_lock_diagnostics()
        except Exception:
            return self._blocked("TASK_PERSISTENCE_DIAGNOSTICS_UNAVAILABLE")

        if not self._valid_load(load):
            return self._blocked("TASK_PERSISTENCE_LOAD_DIAGNOSTICS_INVALID")
        if not self._valid_persistence(persistence):
            return self._blocked("TASK_PERSISTENCE_DIAGNOSTICS_INVALID")
        if not self._valid_lock(lock):
            return self._blocked("TASK_WRITE_LOCK_DIAGNOSTICS_INVALID")

        blockers = []
        warnings = []

        load_state = load["source_state"]
        if load_state in self.LOAD_BLOCKERS:
            blockers.append(self.LOAD_BLOCKERS[load_state])
        elif load.get("issue_count", 0):
            warnings.append("TASK_STORE_RECONCILIATION_ISSUES")

        if lock["inspection_state"] == "CHECK_ERROR":
            blockers.append("TASK_WRITE_LOCK_INSPECTION_FAILED")
        elif lock["lock_present"]:
            blockers.append("TASK_WRITE_LOCK_PRESENT_UNOWNED")

        save_state = persistence["last_save_state"]
        save_issue = persistence.get("last_save_issue")
        if save_state == "FAILED":
            blockers.append(save_issue or "TASK_PERSISTENCE_LAST_SAVE_FAILED")
        elif save_state == "SUCCEEDED_WITH_DURABILITY_WARNING":
            warnings.append(save_issue or "TASK_PERSISTENCE_DURABILITY_WARNING")

        release_issue = persistence.get("last_lock_release_issue")
        if release_issue:
            warnings.append(release_issue)

        blockers = self._stable_unique(blockers)
        warnings = self._stable_unique(warnings)

        if blockers:
            operational_state = "BLOCKED"
        elif warnings:
            operational_state = "WARNING"
        else:
            operational_state = "READY"

        next_action = self._next_action(blockers, warnings)

        return {
            "error": False,
            "status": "TASK_PERSISTENCE_OPERATIONAL_READINESS",
            "operational_state": operational_state,
            "operator_attention_required": operational_state != "READY",
            "next_action": next_action,
            "blocker_count": len(blockers),
            "blockers": blockers,
            "warning_count": len(warnings),
            "warnings": warnings,
            "load_source_state": load_state,
            "loaded_task_count": load["loaded_task_count"],
            "write_lock_present": lock["lock_present"],
            "write_lock_ownership_state": lock["ownership_state"],
            "write_lock_stale_proven": False,
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

    @classmethod
    def _next_action(cls, blockers, warnings):
        if "TASK_WRITE_LOCK_PRESENT_UNOWNED" in blockers:
            return "VERIFY_WRITE_LOCK_OWNER_MANUALLY"
        if "TASK_WRITE_LOCK_INSPECTION_FAILED" in blockers:
            return "INSPECT_WRITE_LOCK_MANUALLY"
        if "TASK_STORE_UNREADABLE" in blockers:
            return "REPAIR_TASK_STORE_MANUALLY"
        if "TASK_STORE_INVALID_ROOT" in blockers:
            return "REPAIR_TASK_STORE_MANUALLY"
        if blockers:
            return "RELOAD_AND_REVIEW_PERSISTENCE_MANUALLY"
        if "TASK_DIRECTORY_FSYNC_ERROR" in warnings:
            return "CHECK_FILESYSTEM_DURABILITY"
        if warnings:
            return "REVIEW_PERSISTENCE_WARNINGS"
        return "NONE"

    @staticmethod
    def _valid_load(value):
        return (
            isinstance(value, dict)
            and value.get("status") == "TASK_PERSISTENCE_LOAD_DIAGNOSTICS"
            and value.get("read_only") is True
            and value.get("executed") is False
            and value.get("source_state") in {"ABSENT", "LOADED", "UNREADABLE", "INVALID_ROOT"}
            and isinstance(value.get("issue_count"), int)
            and value.get("issue_count") >= 0
            and isinstance(value.get("issues"), list)
            and value.get("issue_count") == len(value.get("issues"))
            and isinstance(value.get("loaded_task_count"), int)
            and value.get("loaded_task_count") >= 0
        )

    @staticmethod
    def _valid_persistence(value):
        return (
            isinstance(value, dict)
            and value.get("status") == "TASK_PERSISTENCE_DIAGNOSTICS"
            and value.get("read_only") is True
            and value.get("executed") is False
            and value.get("optimistic_concurrency_guard") is True
            and value.get("write_lock_guard") is True
            and value.get("directory_fsync_required") is True
            and value.get("last_save_state") in {
                "NEVER_ATTEMPTED",
                "SUCCEEDED",
                "SUCCEEDED_WITH_DURABILITY_WARNING",
                "FAILED",
            }
            and isinstance(value.get("loaded_task_count"), int)
            and value.get("loaded_task_count") >= 0
        )

    @staticmethod
    def _valid_lock(value):
        return (
            isinstance(value, dict)
            and value.get("status") == "TASK_WRITE_LOCK_DIAGNOSTICS"
            and value.get("read_only") is True
            and value.get("executed") is False
            and value.get("inspection_state") in {"ABSENT", "PRESENT", "CHECK_ERROR"}
            and isinstance(value.get("lock_present"), bool)
            and value.get("ownership_state") in {"NONE", "UNKNOWN"}
            and value.get("stale_proven") is False
            and value.get("automatic_recovery_allowed") is False
            and value.get("manual_lock_removal_allowed") is False
            and value.get("path_exposed") is False
        )

    @staticmethod
    def _blocked(code):
        return {
            "error": True,
            "code": code,
            "status": "TASK_PERSISTENCE_OPERATIONAL_READINESS",
            "operational_state": "BLOCKED",
            "operator_attention_required": True,
            "next_action": "INSPECT_TASK_PERSISTENCE_MANUALLY",
            "blocker_count": 1,
            "blockers": [code],
            "warning_count": 0,
            "warnings": [],
            "write_lock_stale_proven": False,
            "automatic_lock_recovery_allowed": False,
            "manual_lock_removal_allowed": False,
            "business_execution_ready": False,
            "mutation_ready": False,
            "read_only": True,
            "executed": False,
        }
