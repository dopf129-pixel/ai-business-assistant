import json

from core.task_states import TaskStatus
from services.terminal_safe_assistant_task_service import (
    TerminalSafeAssistantTaskService,
)


USER_ID = 9401


def _valid_task(**overrides):
    task = {
        "task": "Задача",
        "status": TaskStatus.ACTIVE,
        "actions": [{"title": "Шаг", "status": "NEW", "type": "test"}],
        "pending_action": None,
    }
    task.update(overrides)
    return task


def _write(path, payload):
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_v293_malformed_task_entry_is_dropped_in_memory_without_rewrite(tmp_path):
    path = tmp_path / "tasks.json"
    payload = {str(USER_ID): "broken"}
    _write(path, payload)
    before = path.read_text(encoding="utf-8")

    service = TerminalSafeAssistantTaskService(file_path=str(path))

    assert service.get_task(USER_ID)["task"] is None
    diagnostics = service.get_load_diagnostics()
    assert diagnostics["issues"] == ["MALFORMED_TASK"]
    assert diagnostics["loaded_task_count"] == 0
    assert path.read_text(encoding="utf-8") == before


def test_v294_unknown_task_status_is_rejected_fail_closed(tmp_path):
    path = tmp_path / "tasks.json"
    _write(path, {str(USER_ID): _valid_task(status="MAGIC")})

    service = TerminalSafeAssistantTaskService(file_path=str(path))

    assert service.has_active_task(USER_ID)["active"] is False
    assert service.get_load_diagnostics()["issues"] == ["INVALID_TASK_STATUS"]


def test_v295_non_list_actions_are_rejected_fail_closed(tmp_path):
    path = tmp_path / "tasks.json"
    _write(path, {str(USER_ID): _valid_task(actions={"title": "bad"})})

    service = TerminalSafeAssistantTaskService(file_path=str(path))

    assert service.get_task(USER_ID)["task"] is None
    assert service.get_load_diagnostics()["issues"] == ["INVALID_TASK_ACTIONS"]


def test_v296_non_dict_action_is_rejected_fail_closed(tmp_path):
    path = tmp_path / "tasks.json"
    _write(path, {str(USER_ID): _valid_task(actions=["bad-action"])})

    service = TerminalSafeAssistantTaskService(file_path=str(path))

    assert service.get_task(USER_ID)["task"] is None
    assert service.get_load_diagnostics()["issues"] == ["MALFORMED_TASK_ACTION"]


def test_v297_invalid_pending_action_is_normalized_without_execution(tmp_path):
    path = tmp_path / "tasks.json"
    _write(path, {str(USER_ID): _valid_task(pending_action="execute-me")})
    before = path.read_text(encoding="utf-8")

    service = TerminalSafeAssistantTaskService(file_path=str(path))

    assert service.get_pending_action(USER_ID)["action"] is None
    diagnostics = service.get_load_diagnostics()
    assert diagnostics["issues"] == ["INVALID_PENDING_ACTION_NORMALIZED"]
    assert diagnostics["executed"] is False
    assert path.read_text(encoding="utf-8") == before


def test_v298_valid_active_task_survives_validation_unchanged(tmp_path):
    path = tmp_path / "tasks.json"
    task = _valid_task()
    _write(path, {str(USER_ID): task})

    service = TerminalSafeAssistantTaskService(file_path=str(path))

    assert service.get_task(USER_ID)["task"] == task
    assert service.get_load_diagnostics()["issue_count"] == 0


def test_v299_missing_status_preserves_legacy_active_default(tmp_path):
    path = tmp_path / "tasks.json"
    task = _valid_task()
    task.pop("status")
    _write(path, {str(USER_ID): task})

    service = TerminalSafeAssistantTaskService(file_path=str(path))

    assert service.get_task(USER_ID)["task"] is not None
    assert service.has_active_task(USER_ID)["active"] is True
    assert service.get_load_diagnostics()["issue_count"] == 0


def test_v300_terminal_valid_task_is_sanitized_after_validation(tmp_path):
    path = tmp_path / "tasks.json"
    task = _valid_task(
        status=TaskStatus.CANCELLED,
        pending_action={"title": "stale"},
        replan_requested=True,
        replan_reason="stale",
    )
    _write(path, {str(USER_ID): task})

    service = TerminalSafeAssistantTaskService(file_path=str(path))
    recovered = service.get_task(USER_ID)["task"]

    assert recovered["status"] == TaskStatus.CANCELLED
    assert recovered["pending_action"] is None
    assert recovered["replan_requested"] is False
    assert recovered["replan_reason"] is None
    assert service.get_current_action(USER_ID)["action"] is None


def test_v301_multiple_bad_entries_do_not_hide_valid_task(tmp_path):
    path = tmp_path / "tasks.json"
    _write(path, {
        "bad-1": "broken",
        "bad-2": _valid_task(status="UNKNOWN"),
        str(USER_ID): _valid_task(),
    })

    service = TerminalSafeAssistantTaskService(file_path=str(path))

    assert service.get_task(USER_ID)["task"] is not None
    diagnostics = service.get_load_diagnostics()
    assert diagnostics["issue_count"] == 2
    assert diagnostics["loaded_task_count"] == 1


def test_v302_diagnostics_are_read_only_and_contain_no_user_identifiers(tmp_path):
    path = tmp_path / "tasks.json"
    _write(path, {str(USER_ID): "broken"})

    service = TerminalSafeAssistantTaskService(file_path=str(path))
    diagnostics = service.get_load_diagnostics()

    assert diagnostics["read_only"] is True
    assert diagnostics["executed"] is False
    assert str(USER_ID) not in repr(diagnostics)
