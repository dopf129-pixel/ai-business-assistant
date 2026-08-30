import json
import os
import stat

import pytest

from core.task_states import TaskStatus
from services.assistant_task_service import AssistantTaskService
from services.terminal_safe_assistant_task_service import TerminalSafeAssistantTaskService


USER_ID = 9801


def _action(title="Шаг"):
    return {
        "title": title,
        "type": "test",
        "status": "NEW",
        "priority": "HIGH",
    }


def _persisted_task():
    return {
        "task": "Исходная задача",
        "status": TaskStatus.ACTIVE,
        "actions": [_action()],
        "pending_action": None,
    }


def _write_store(path):
    path.write_text(
        json.dumps({str(USER_ID): _persisted_task()}, ensure_ascii=False, indent=4),
        encoding="utf-8",
    )


def test_v333_existing_write_lock_fails_closed_before_replace(tmp_path, monkeypatch):
    path = tmp_path / "tasks.json"
    _write_store(path)
    service = TerminalSafeAssistantTaskService(file_path=str(path))
    lock_path = tmp_path / "tasks.json.lock"
    lock_path.write_bytes(b"")

    replace_calls = []
    real_replace = os.replace

    def counted_replace(source, target):
        replace_calls.append((source, target))
        return real_replace(source, target)

    monkeypatch.setattr(os, "replace", counted_replace)

    with pytest.raises(RuntimeError, match="TASK_FILE_WRITE_LOCKED"):
        service.set_pending_action(USER_ID, {"title": "blocked"})

    assert replace_calls == []
    assert service.get_pending_action(USER_ID)["action"] is None
    diagnostics = service.get_persistence_diagnostics()
    assert diagnostics["last_save_issue"] == "TASK_FILE_WRITE_LOCKED"
    assert diagnostics["last_save_rolled_back"] is True


def test_v334_write_lock_is_exclusive_between_live_instances(tmp_path):
    path = tmp_path / "tasks.json"
    _write_store(path)
    first = TerminalSafeAssistantTaskService(file_path=str(path))
    second = TerminalSafeAssistantTaskService(file_path=str(path))

    first._acquire_write_lock()
    try:
        with pytest.raises(RuntimeError, match="TASK_FILE_WRITE_LOCKED"):
            second.set_pending_action(USER_ID, {"title": "second"})
    finally:
        first._release_write_lock()

    assert second.get_pending_action(USER_ID)["action"] is None


def test_v335_lock_file_is_private_and_contains_no_process_identity(tmp_path):
    path = tmp_path / "tasks.json"
    service = TerminalSafeAssistantTaskService(file_path=str(path))

    service._acquire_write_lock()
    lock_path = tmp_path / "tasks.json.lock"
    try:
        assert lock_path.read_bytes() == b""
        mode = stat.S_IMODE(lock_path.stat().st_mode)
        assert mode == 0o600
    finally:
        service._release_write_lock()


def test_v336_fingerprint_check_runs_while_write_lock_is_held(tmp_path, monkeypatch):
    path = tmp_path / "tasks.json"
    _write_store(path)
    service = TerminalSafeAssistantTaskService(file_path=str(path))
    real_check = service._current_file_fingerprint
    observed = []

    def guarded_check():
        observed.append((tmp_path / "tasks.json.lock").exists())
        return real_check()

    monkeypatch.setattr(service, "_current_file_fingerprint", guarded_check)

    service.set_pending_action(USER_ID, {"title": "safe"})

    assert observed == [True]
    assert not (tmp_path / "tasks.json.lock").exists()


def test_v337_serialization_failure_rolls_memory_back_to_durable_store(tmp_path):
    path = tmp_path / "tasks.json"
    _write_store(path)
    service = TerminalSafeAssistantTaskService(file_path=str(path))

    with pytest.raises(RuntimeError, match="TASK_FILE_SERIALIZATION_ERROR"):
        service.set_pending_action(USER_ID, {"bad": {1, 2, 3}})

    durable = json.loads(path.read_text(encoding="utf-8"))
    assert durable[str(USER_ID)]["pending_action"] is None
    assert service.get_pending_action(USER_ID)["action"] is None
    diagnostics = service.get_persistence_diagnostics()
    assert diagnostics["last_save_issue"] == "TASK_FILE_SERIALIZATION_ERROR"
    assert diagnostics["last_save_rolled_back"] is True
    assert not (tmp_path / "tasks.json.lock").exists()


def test_v338_lock_acquisition_error_is_stable_and_non_sensitive(tmp_path, monkeypatch):
    path = tmp_path / "tasks.json"
    _write_store(path)
    service = TerminalSafeAssistantTaskService(file_path=str(path))
    real_open = os.open

    def failing_open(target, flags, mode=0o777):
        if str(target).endswith(".lock"):
            raise PermissionError("sensitive lock detail")
        return real_open(target, flags, mode)

    monkeypatch.setattr(os, "open", failing_open)

    with pytest.raises(RuntimeError, match="TASK_FILE_WRITE_LOCK_ERROR"):
        service.set_pending_action(USER_ID, {"title": "blocked"})

    diagnostics = service.get_persistence_diagnostics()
    assert diagnostics["last_save_issue"] == "TASK_FILE_WRITE_LOCK_ERROR"
    assert "sensitive lock detail" not in repr(diagnostics)
    assert str(path) not in repr(diagnostics)


def test_v339_lock_release_error_does_not_turn_durable_success_into_failure(tmp_path, monkeypatch):
    path = tmp_path / "tasks.json"
    service = TerminalSafeAssistantTaskService(file_path=str(path))
    real_remove = os.remove

    def failing_remove(target):
        if str(target).endswith(".lock"):
            raise OSError("sensitive release detail")
        return real_remove(target)

    monkeypatch.setattr(os, "remove", failing_remove)

    result = service.create_task(USER_ID, "Сохранено", [_action()])

    assert result["saved"] is True
    durable = json.loads(path.read_text(encoding="utf-8"))
    assert durable[str(USER_ID)]["task"] == "Сохранено"
    diagnostics = service.get_persistence_diagnostics()
    assert diagnostics["last_save_state"] == "SUCCEEDED"
    assert diagnostics["last_lock_release_issue"] == "TASK_FILE_WRITE_LOCK_RELEASE_ERROR"
    assert "sensitive release detail" not in repr(diagnostics)


def test_v340_missing_lock_during_release_is_degraded_success_not_write_failure(tmp_path, monkeypatch):
    path = tmp_path / "tasks.json"
    service = TerminalSafeAssistantTaskService(file_path=str(path))
    real_remove = os.remove

    def missing_lock(target):
        if str(target).endswith(".lock"):
            raise FileNotFoundError(str(target))
        return real_remove(target)

    monkeypatch.setattr(os, "remove", missing_lock)

    result = service.create_task(USER_ID, "Сохранено", [_action()])

    assert result["saved"] is True
    diagnostics = service.get_persistence_diagnostics()
    assert diagnostics["last_save_state"] == "SUCCEEDED"
    assert diagnostics["last_lock_release_issue"] == "TASK_FILE_WRITE_LOCK_MISSING"


def test_v341_successful_save_removes_lock_and_keeps_guard_enabled(tmp_path):
    path = tmp_path / "tasks.json"
    service = TerminalSafeAssistantTaskService(file_path=str(path))

    service.create_task(USER_ID, "Новая", [_action()])

    assert not (tmp_path / "tasks.json.lock").exists()
    diagnostics = service.get_persistence_diagnostics()
    assert diagnostics["write_lock_guard"] is True
    assert diagnostics["last_lock_release_issue"] is None


def test_v342_lock_contention_never_claims_execution_or_retries_business_work(tmp_path):
    path = tmp_path / "tasks.json"
    _write_store(path)
    service = TerminalSafeAssistantTaskService(file_path=str(path))
    service._acquire_write_lock()
    try:
        with pytest.raises(RuntimeError, match="TASK_FILE_WRITE_LOCKED"):
            service.set_pending_action(USER_ID, {"title": "blocked"})
    finally:
        if (tmp_path / "tasks.json.lock").exists():
            service._release_write_lock()

    diagnostics = service.get_persistence_diagnostics()
    assert diagnostics["executed"] is False
    assert diagnostics["last_save_state"] == "FAILED"
