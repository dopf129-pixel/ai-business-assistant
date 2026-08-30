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
            "issue_count": len(issues),
            "issues": issues,
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
