import hashlib
import json
import os
from copy import deepcopy

from core.task_states import TaskStatus
from services.assistant_task_service import AssistantTaskService


class TerminalSafeAssistantTaskService(AssistantTaskService):
    """Production task owner that keeps recovered and terminal task state safe."""

    TERMINAL_STATUSES = {
        TaskStatus.DONE,
        TaskStatus.SKIPPED,
        TaskStatus.CANCELLED,
    }

    @staticmethod
    def _fingerprint(raw):
        if raw is None:
            return None
        return hashlib.sha256(raw).hexdigest()

    def _current_file_fingerprint(self):
        if not os.path.exists(self.file_path):
            return None
        with open(self.file_path, "rb") as file:
            return self._fingerprint(file.read())

    def load(self):
        self.tasks = {}
        self._load_issues = ()
        self._load_source_state = "ABSENT"
        self._source_fingerprint = None

        if not os.path.exists(self.file_path):
            return

        try:
            with open(self.file_path, "rb") as file:
                raw = file.read()
            self._source_fingerprint = self._fingerprint(raw)
            loaded = json.loads(raw.decode("utf-8"))
        except Exception:
            self._load_source_state = "UNREADABLE"
            self._load_issues = ("TASK_FILE_READ_ERROR",)
            return

        if not isinstance(loaded, dict):
            self._load_source_state = "INVALID_ROOT"
            self._load_issues = ("INVALID_TASK_FILE_ROOT",)
            return

        self.tasks = loaded
        self._load_source_state = "LOADED"
        self._reconcile_loaded_tasks()

    def _rollback_after_save_failure(self, issue):
        self._last_save_state = "FAILED"
        self._last_save_issue = issue
        self.load()
        self._last_save_rolled_back = True

    def save(self):
        try:
            current_fingerprint = self._current_file_fingerprint()
        except Exception:
            self._rollback_after_save_failure("TASK_FILE_CONCURRENCY_CHECK_ERROR")
            raise RuntimeError("TASK_FILE_CONCURRENCY_CHECK_ERROR") from None

        if current_fingerprint != getattr(self, "_source_fingerprint", None):
            self._rollback_after_save_failure("TASK_FILE_STALE_WRITE")
            raise RuntimeError("TASK_FILE_STALE_WRITE")

        expected_raw = json.dumps(
            self.tasks,
            ensure_ascii=False,
            indent=4,
        ).encode("utf-8")
        expected_fingerprint = self._fingerprint(expected_raw)

        try:
            super().save()
        except Exception:
            self._rollback_after_save_failure("TASK_FILE_WRITE_ERROR")
            raise

        self._source_fingerprint = expected_fingerprint
        self._load_source_state = "LOADED"
        self._load_issues = ()
        self._last_save_state = "SUCCEEDED"
        self._last_save_issue = None
        self._last_save_rolled_back = False

    def _validate_loaded_task(self, task):
        if not isinstance(task, dict):
            return "MALFORMED_TASK"

        if task.get("status", TaskStatus.ACTIVE) not in TaskStatus.all():
            return "INVALID_TASK_STATUS"

        actions = task.get("actions", [])
        if not isinstance(actions, list):
            return "INVALID_TASK_ACTIONS"

        if any(not isinstance(action, dict) for action in actions):
            return "MALFORMED_TASK_ACTION"

        return None

    def _normalize_loaded_pending_action(self, task):
        pending = task.get("pending_action")
        if pending is None or isinstance(pending, dict):
            return False

        task["pending_action"] = None
        return True

    def _sanitize_terminal_task(self, task):
        if not isinstance(task, dict) or task.get("status") not in self.TERMINAL_STATUSES:
            return False

        changed = False
        expected = {
            "pending_action": None,
            "replan_requested": False,
            "replan_reason": None,
        }
        for field, value in expected.items():
            if task.get(field) != value:
                task[field] = deepcopy(value)
                changed = True

        return changed

    def _finalize_if_complete(self, task):
        changed = super()._finalize_if_complete(task)
        sanitized = self._sanitize_terminal_task(task)
        return changed or sanitized

    def _reconcile_loaded_tasks(self):
        issues = []
        valid_tasks = {}

        for key, task in self.tasks.items():
            error = self._validate_loaded_task(task)
            if error is not None:
                issues.append(error)
                continue

            if self._normalize_loaded_pending_action(task):
                issues.append("INVALID_PENDING_ACTION_NORMALIZED")

            valid_tasks[key] = task

        self.tasks = valid_tasks
        super()._reconcile_loaded_tasks()

        for task in self.tasks.values():
            self._sanitize_terminal_task(task)

        self._load_issues = tuple(issues)

    def get_load_diagnostics(self):
        issues = list(getattr(self, "_load_issues", ()))
        return {
            "error": False,
            "status": "TASK_PERSISTENCE_LOAD_DIAGNOSTICS",
            "source_state": getattr(self, "_load_source_state", "UNKNOWN"),
            "issue_count": len(issues),
            "issues": issues,
            "loaded_task_count": len(self.tasks),
            "read_only": True,
            "executed": False,
        }

    def get_persistence_diagnostics(self):
        return {
            "error": False,
            "status": "TASK_PERSISTENCE_DIAGNOSTICS",
            "load_source_state": getattr(self, "_load_source_state", "UNKNOWN"),
            "last_save_state": getattr(self, "_last_save_state", "NEVER_ATTEMPTED"),
            "last_save_issue": getattr(self, "_last_save_issue", None),
            "last_save_rolled_back": getattr(self, "_last_save_rolled_back", False),
            "optimistic_concurrency_guard": True,
            "loaded_task_count": len(self.tasks),
            "read_only": True,
            "executed": False,
        }

    def change_task_status(self, user_id, new_status):
        result = super().change_task_status(user_id, new_status)
        if result.get("error"):
            return result

        task = self.tasks.get(str(user_id))
        if self._sanitize_terminal_task(task):
            self.save()

        return result

    def clear_pending_action(self, user_id):
        task = self.tasks.get(str(user_id))
        if task is not None and self._task_is_terminal(task):
            return self._terminal_task_error(task)
        return super().clear_pending_action(user_id)
