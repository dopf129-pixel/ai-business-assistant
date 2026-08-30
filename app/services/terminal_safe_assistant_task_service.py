from copy import deepcopy

from core.task_states import TaskStatus
from services.assistant_task_service import AssistantTaskService


class TerminalSafeAssistantTaskService(AssistantTaskService):
    """Production task owner that keeps terminal task state free of live recovery intent."""

    TERMINAL_STATUSES = {
        TaskStatus.DONE,
        TaskStatus.SKIPPED,
        TaskStatus.CANCELLED,
    }

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
        super()._reconcile_loaded_tasks()
        for task in self.tasks.values():
            self._sanitize_terminal_task(task)

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
