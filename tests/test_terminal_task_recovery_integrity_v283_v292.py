import json

from core.task_states import TaskStatus
from services.terminal_safe_assistant_task_service import (
    TerminalSafeAssistantTaskService,
)
from telegram_core_factory import create_telegram_core


USER_ID = 9301


def _action(status="NEW"):
    return {
        "title": "Шаг",
        "type": "test",
        "status": status,
        "priority": "HIGH",
    }


def _terminal_task(status=TaskStatus.DONE):
    return {
        "task": "Задача",
        "status": status,
        "actions": [_action("DONE")],
        "pending_action": {"title": "stale"},
        "replan_requested": True,
        "replan_reason": "stale recovery intent",
    }


def test_v283_terminal_sanitizer_clears_only_live_recovery_intent(tmp_path):
    service = TerminalSafeAssistantTaskService(file_path=str(tmp_path / "tasks.json"))
    task = _terminal_task()
    task["historical_note"] = "keep"

    assert service._sanitize_terminal_task(task) is True
    assert task["pending_action"] is None
    assert task["replan_requested"] is False
    assert task["replan_reason"] is None
    assert task["historical_note"] == "keep"


def test_v284_active_task_is_not_sanitized(tmp_path):
    service = TerminalSafeAssistantTaskService(file_path=str(tmp_path / "tasks.json"))
    task = _terminal_task(TaskStatus.ACTIVE)

    assert service._sanitize_terminal_task(task) is False
    assert task["pending_action"] == {"title": "stale"}
    assert task["replan_requested"] is True


def test_v285_final_action_completion_sanitizes_replan_state(tmp_path):
    path = tmp_path / "tasks.json"
    service = TerminalSafeAssistantTaskService(file_path=str(path))
    service.create_task(USER_ID, "Задача", [_action()])
    task = service.get_task(USER_ID)["task"]
    task["replan_requested"] = True
    task["replan_reason"] = "failure"

    result = service.complete_action(USER_ID, "Шаг")

    assert result["error"] is False
    task = service.get_task(USER_ID)["task"]
    assert task["status"] == TaskStatus.DONE
    assert task["pending_action"] is None
    assert task["replan_requested"] is False
    assert task["replan_reason"] is None


def test_v286_explicit_terminal_status_sanitizes_before_next_read(tmp_path):
    path = tmp_path / "tasks.json"
    service = TerminalSafeAssistantTaskService(file_path=str(path))
    service.create_task(USER_ID, "Задача", [_action()])
    task = service.get_task(USER_ID)["task"]
    task["pending_action"] = {"title": "Шаг"}
    task["replan_requested"] = True
    task["replan_reason"] = "failure"

    result = service.change_task_status(USER_ID, TaskStatus.CANCELLED)

    assert result["error"] is False
    task = service.get_task(USER_ID)["task"]
    assert task["status"] == TaskStatus.CANCELLED
    assert task["pending_action"] is None
    assert task["replan_requested"] is False
    assert task["replan_reason"] is None


def test_v287_restart_sanitizes_terminal_memory_without_rewriting_file(tmp_path):
    path = tmp_path / "tasks.json"
    persisted = {str(USER_ID): _terminal_task(TaskStatus.CANCELLED)}
    path.write_text(json.dumps(persisted, ensure_ascii=False, indent=2), encoding="utf-8")
    before = path.read_text(encoding="utf-8")

    recovered = TerminalSafeAssistantTaskService(file_path=str(path))

    task = recovered.get_task(USER_ID)["task"]
    assert task["pending_action"] is None
    assert task["replan_requested"] is False
    assert task["replan_reason"] is None
    assert path.read_text(encoding="utf-8") == before


def test_v288_terminal_clear_pending_is_rejected_as_owner_mutation(tmp_path):
    path = tmp_path / "tasks.json"
    service = TerminalSafeAssistantTaskService(file_path=str(path))
    service.tasks[str(USER_ID)] = _terminal_task(TaskStatus.DONE)
    service._reconcile_loaded_tasks()

    result = service.clear_pending_action(USER_ID)

    assert result["error"] is True
    assert result["status"] == TaskStatus.DONE


def test_v289_nonterminal_clear_pending_remains_backward_compatible(tmp_path):
    path = tmp_path / "tasks.json"
    service = TerminalSafeAssistantTaskService(file_path=str(path))
    service.create_task(USER_ID, "Задача", [_action()])
    service.set_pending_action(USER_ID, {"title": "Шаг"})

    result = service.clear_pending_action(USER_ID)

    assert result == {"error": False}
    assert service.get_pending_action(USER_ID)["action"] is None


def test_v290_restart_of_all_done_active_task_derives_done_and_sanitizes(tmp_path):
    path = tmp_path / "tasks.json"
    persisted = {str(USER_ID): _terminal_task(TaskStatus.ACTIVE)}
    path.write_text(json.dumps(persisted, ensure_ascii=False), encoding="utf-8")

    recovered = TerminalSafeAssistantTaskService(file_path=str(path))
    task = recovered.get_task(USER_ID)["task"]

    assert task["status"] == TaskStatus.DONE
    assert task["pending_action"] is None
    assert task["replan_requested"] is False
    assert task["replan_reason"] is None
    assert recovered.has_active_task(USER_ID)["active"] is False


def test_v291_terminal_recovery_never_exposes_next_action(tmp_path):
    path = tmp_path / "tasks.json"
    service = TerminalSafeAssistantTaskService(file_path=str(path))
    service.tasks[str(USER_ID)] = _terminal_task(TaskStatus.SKIPPED)
    service._reconcile_loaded_tasks()

    assert service.get_current_action(USER_ID)["action"] is None
    assert service.get_next_action(USER_ID)["action"] is None


def test_v292_production_core_uses_terminal_safe_owner():
    core = create_telegram_core()
    assert isinstance(core["task_service"], TerminalSafeAssistantTaskService)
