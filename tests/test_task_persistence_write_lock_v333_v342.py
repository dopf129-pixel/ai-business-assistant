import json
import os
import stat

import pytest

import services.terminal_safe_assistant_task_service as terminal_module
from core.task_states import TaskStatus
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


def test_v333_legacy_coordination_file_does_not_block_kernel_lock_write(tmp_path):
    path = tmp_path / "tasks.json"
    _write_store(path)
    lock_path = tmp_path / "tasks.json.lock"
    lock_path.write_bytes(b"")
    service = TerminalSafeAssistantTaskService(file_path=str(path))

    result = service.set_pending_action(USER_ID, {"title": "safe"})

    assert result["saved"] is True
    durable = json.loads(path.read_text(encoding="utf-8"))
    assert durable[str(USER_ID)]["pending_action"] == {"title": "safe"}
    diagnostics = service.get_write_lock_diagnostics()
    assert diagnostics["inspection_state"] == "NO_ACTIVE_LOCK_EVIDENCE"
    assert diagnostics["coordination_file_present"] is True
    assert diagnostics["orphan_file_blocks_writes"] is False


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
    diagnostics = second.get_persistence_diagnostics()
    assert diagnostics["last_save_issue"] == "TASK_FILE_WRITE_LOCKED"
    assert diagnostics["last_save_rolled_back"] is True


def test_v335_lock_file_is_private_empty_and_persistent_coordination_artifact(tmp_path):
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

    assert lock_path.exists()
    assert lock_path.read_bytes() == b""


def test_v336_fingerprint_check_runs_while_kernel_lock_is_held(tmp_path, monkeypatch):
    path = tmp_path / "tasks.json"
    _write_store(path)
    service = TerminalSafeAssistantTaskService(file_path=str(path))
    real_check = service._current_file_fingerprint
    observed = []

    def guarded_check():
        observed.append(getattr(service, "_write_lock_fd", None) is not None)
        return real_check()

    monkeypatch.setattr(service, "_current_file_fingerprint", guarded_check)

    service.set_pending_action(USER_ID, {"title": "safe"})

    assert observed == [True]
    assert service.get_write_lock_diagnostics()["inspection_state"] == "NO_ACTIVE_LOCK_EVIDENCE"


def test_v337_serialization_failure_rolls_memory_back_and_releases_kernel_lock(tmp_path):
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
    assert service.get_write_lock_diagnostics()["inspection_state"] == "NO_ACTIVE_LOCK_EVIDENCE"


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


def test_v339_kernel_unlock_error_does_not_turn_durable_success_into_failure(tmp_path, monkeypatch):
    path = tmp_path / "tasks.json"
    service = TerminalSafeAssistantTaskService(file_path=str(path))
    real_flock = terminal_module.fcntl.flock

    def failing_unlock(fd, operation):
        if operation == terminal_module.fcntl.LOCK_UN:
            raise OSError("sensitive release detail")
        return real_flock(fd, operation)

    monkeypatch.setattr(terminal_module.fcntl, "flock", failing_unlock)

    result = service.create_task(USER_ID, "Сохранено", [_action()])

    assert result["saved"] is True
    durable = json.loads(path.read_text(encoding="utf-8"))
    assert durable[str(USER_ID)]["task"] == "Сохранено"
    diagnostics = service.get_persistence_diagnostics()
    assert diagnostics["last_save_state"] == "SUCCEEDED"
    assert diagnostics["last_lock_release_issue"] == "TASK_FILE_WRITE_LOCK_RELEASE_ERROR"
    assert "sensitive release detail" not in repr(diagnostics)


def test_v340_release_without_owned_fd_is_degraded_diagnostic_only(tmp_path):
    service = TerminalSafeAssistantTaskService(
        file_path=str(tmp_path / "tasks.json")
    )

    service._release_write_lock()

    diagnostics = service.get_persistence_diagnostics()
    assert diagnostics["last_lock_release_issue"] == "TASK_FILE_WRITE_LOCK_MISSING"
    assert diagnostics["executed"] is False


def test_v341_successful_save_keeps_coordination_file_but_releases_active_lock(tmp_path):
    path = tmp_path / "tasks.json"
    service = TerminalSafeAssistantTaskService(file_path=str(path))

    service.create_task(USER_ID, "Новая", [_action()])

    assert (tmp_path / "tasks.json.lock").exists()
    lock = service.get_write_lock_diagnostics()
    assert lock["inspection_state"] == "NO_ACTIVE_LOCK_EVIDENCE"
    assert lock["lock_present"] is None
    assert lock["coordination_file_present"] is True
    assert lock["kernel_lock_guard"] is True
    assert lock["orphan_file_blocks_writes"] is False
    assert service.get_persistence_diagnostics()["last_lock_release_issue"] is None


def test_v342_kernel_lock_contention_never_claims_execution_or_retries_business_work(tmp_path):
    path = tmp_path / "tasks.json"
    _write_store(path)
    first = TerminalSafeAssistantTaskService(file_path=str(path))
    second = TerminalSafeAssistantTaskService(file_path=str(path))

    first._acquire_write_lock()
    try:
        with pytest.raises(RuntimeError, match="TASK_FILE_WRITE_LOCKED"):
            second.set_pending_action(USER_ID, {"title": "blocked"})
    finally:
        first._release_write_lock()

    diagnostics = second.get_persistence_diagnostics()
    assert diagnostics["executed"] is False
    assert diagnostics["last_save_state"] == "FAILED"
    assert diagnostics["last_save_issue"] == "TASK_FILE_WRITE_LOCKED"
