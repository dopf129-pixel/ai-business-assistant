import json
import os
import stat

from core.task_states import TaskStatus
from services.terminal_safe_assistant_task_service import TerminalSafeAssistantTaskService


USER_ID = 9901


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


def test_v343_successful_save_fsyncs_parent_directory(tmp_path, monkeypatch):
    path = tmp_path / "tasks.json"
    service = TerminalSafeAssistantTaskService(file_path=str(path))
    real_fsync = os.fsync
    directory_syncs = []

    def observed_fsync(fd):
        if stat.S_ISDIR(os.fstat(fd).st_mode):
            directory_syncs.append(fd)
        return real_fsync(fd)

    monkeypatch.setattr(os, "fsync", observed_fsync)

    service.create_task(USER_ID, "Новая", [_action()])

    assert directory_syncs


def test_v344_directory_fsync_runs_while_write_lock_is_held(tmp_path, monkeypatch):
    path = tmp_path / "tasks.json"
    service = TerminalSafeAssistantTaskService(file_path=str(path))
    observed = []

    def guarded_sync():
        observed.append(
            getattr(service, "_write_lock_fd", None) is not None
        )
        return None

    monkeypatch.setattr(service, "_sync_parent_directory", guarded_sync)

    service.create_task(USER_ID, "Новая", [_action()])

    assert observed == [True]


def test_v345_directory_fsync_warning_keeps_committed_write_successful(tmp_path, monkeypatch):
    path = tmp_path / "tasks.json"
    service = TerminalSafeAssistantTaskService(file_path=str(path))
    monkeypatch.setattr(service, "_sync_parent_directory", lambda: "TASK_DIRECTORY_FSYNC_ERROR")

    result = service.create_task(USER_ID, "Сохранено", [_action()])

    assert result["saved"] is True
    durable = json.loads(path.read_text(encoding="utf-8"))
    assert durable[str(USER_ID)]["task"] == "Сохранено"
    diagnostics = service.get_persistence_diagnostics()
    assert diagnostics["last_save_state"] == "SUCCEEDED_WITH_DURABILITY_WARNING"
    assert diagnostics["last_save_issue"] == "TASK_DIRECTORY_FSYNC_ERROR"


def test_v346_durability_warning_does_not_roll_memory_back(tmp_path, monkeypatch):
    path = tmp_path / "tasks.json"
    service = TerminalSafeAssistantTaskService(file_path=str(path))
    monkeypatch.setattr(service, "_sync_parent_directory", lambda: "TASK_DIRECTORY_FSYNC_ERROR")

    service.create_task(USER_ID, "Сохранено", [_action()])

    assert service.get_task(USER_ID)["task"]["task"] == "Сохранено"
    assert service.get_persistence_diagnostics()["last_save_rolled_back"] is False


def test_v347_same_instance_can_write_again_after_durability_warning(tmp_path, monkeypatch):
    path = tmp_path / "tasks.json"
    _write_store(path)
    service = TerminalSafeAssistantTaskService(file_path=str(path))
    calls = []

    def first_warning_then_ok():
        calls.append(1)
        return "TASK_DIRECTORY_FSYNC_ERROR" if len(calls) == 1 else None

    monkeypatch.setattr(service, "_sync_parent_directory", first_warning_then_ok)

    service.set_pending_action(USER_ID, {"title": "первое"})
    service.set_pending_action(USER_ID, {"title": "второе"})

    durable = json.loads(path.read_text(encoding="utf-8"))
    assert durable[str(USER_ID)]["pending_action"] == {"title": "второе"}
    assert service.get_persistence_diagnostics()["last_save_state"] == "SUCCEEDED"


def test_v348_directory_open_failure_is_non_sensitive_durability_warning(tmp_path, monkeypatch):
    path = tmp_path / "tasks.json"
    service = TerminalSafeAssistantTaskService(file_path=str(path))
    real_open = os.open

    def failing_open(target, flags, mode=0o777):
        if str(target) == str(tmp_path):
            raise PermissionError("sensitive directory detail")
        return real_open(target, flags, mode)

    monkeypatch.setattr(os, "open", failing_open)

    result = service.create_task(USER_ID, "Сохранено", [_action()])

    assert result["saved"] is True
    diagnostics = service.get_persistence_diagnostics()
    assert diagnostics["last_save_issue"] == "TASK_DIRECTORY_FSYNC_ERROR"
    rendered = repr(diagnostics)
    assert "sensitive directory detail" not in rendered
    assert str(path) not in rendered


def test_v349_directory_fsync_warning_still_releases_write_lock(tmp_path, monkeypatch):
    path = tmp_path / "tasks.json"
    service = TerminalSafeAssistantTaskService(file_path=str(path))
    monkeypatch.setattr(service, "_sync_parent_directory", lambda: "TASK_DIRECTORY_FSYNC_ERROR")

    service.create_task(USER_ID, "Сохранено", [_action()])

    lock = service.get_write_lock_diagnostics()
    assert lock["inspection_state"] == "NO_ACTIVE_LOCK_EVIDENCE"
    assert lock["coordination_file_present"] is True


def test_v350_durability_and_kernel_unlock_warnings_remain_distinct(tmp_path, monkeypatch):
    import services.terminal_safe_assistant_task_service as terminal_module

    path = tmp_path / "tasks.json"
    service = TerminalSafeAssistantTaskService(file_path=str(path))
    monkeypatch.setattr(service, "_sync_parent_directory", lambda: "TASK_DIRECTORY_FSYNC_ERROR")
    real_flock = terminal_module.fcntl.flock

    def failing_unlock(fd, operation):
        if operation == terminal_module.fcntl.LOCK_UN:
            raise OSError("sensitive lock release")
        return real_flock(fd, operation)

    monkeypatch.setattr(terminal_module.fcntl, "flock", failing_unlock)

    result = service.create_task(USER_ID, "Сохранено", [_action()])

    assert result["saved"] is True
    diagnostics = service.get_persistence_diagnostics()
    assert diagnostics["last_save_state"] == "SUCCEEDED_WITH_DURABILITY_WARNING"
    assert diagnostics["last_save_issue"] == "TASK_DIRECTORY_FSYNC_ERROR"
    assert diagnostics["last_lock_release_issue"] == "TASK_FILE_WRITE_LOCK_RELEASE_ERROR"


def test_v351_public_diagnostics_expose_requirement_not_directory_path(tmp_path):
    path = tmp_path / "nested" / "tasks.json"
    service = TerminalSafeAssistantTaskService(file_path=str(path))

    diagnostics = service.get_persistence_diagnostics()

    assert diagnostics["directory_fsync_required"] is True
    assert str(path) not in repr(diagnostics)
    assert str(path.parent) not in repr(diagnostics)


def test_v352_durability_warning_never_claims_business_execution(tmp_path, monkeypatch):
    path = tmp_path / "tasks.json"
    service = TerminalSafeAssistantTaskService(file_path=str(path))
    monkeypatch.setattr(service, "_sync_parent_directory", lambda: "TASK_DIRECTORY_FSYNC_ERROR")

    service.create_task(USER_ID, "Сохранено", [_action()])

    diagnostics = service.get_persistence_diagnostics()
    assert diagnostics["executed"] is False
    assert diagnostics["last_save_rolled_back"] is False
