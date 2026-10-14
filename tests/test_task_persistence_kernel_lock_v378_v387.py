import json
import os
import stat
import subprocess
import sys
import time
from pathlib import Path

import pytest

import services.terminal_safe_assistant_task_service as terminal_module
from core.task_states import TaskStatus
from services.task_persistence_operational_service import TaskPersistenceOperationalService
from services.terminal_safe_assistant_task_service import TerminalSafeAssistantTaskService


USER_ID = 10001


def _action(title="Шаг"):
    return {
        "title": title,
        "type": "test",
        "status": "NEW",
        "priority": "HIGH",
    }


def _task():
    return {
        "task": "Исходная задача",
        "status": TaskStatus.ACTIVE,
        "actions": [_action()],
        "pending_action": None,
    }


def _write_store(path):
    path.write_text(
        json.dumps({str(USER_ID): _task()}, ensure_ascii=False, indent=4),
        encoding="utf-8",
    )


def test_v378_platform_kernel_lock_is_available_in_supported_runtime():
    assert terminal_module._kernel_lock_backend() in {"fcntl", "msvcrt"}


def test_v379_coordination_file_is_stable_private_and_not_ownership_evidence(tmp_path):
    path = tmp_path / "tasks.json"
    service = TerminalSafeAssistantTaskService(file_path=str(path))

    service.create_task(USER_ID, "Первая", [_action()])

    lock_path = tmp_path / "tasks.json.lock"
    assert lock_path.exists()
    assert lock_path.read_bytes() == b""
    if os.name == "posix":
        assert stat.S_IMODE(lock_path.stat().st_mode) == 0o600

    diagnostics = service.get_write_lock_diagnostics()
    assert diagnostics["inspection_state"] == "NO_ACTIVE_LOCK_EVIDENCE"
    assert diagnostics["coordination_file_present"] is True
    assert diagnostics["lock_present"] is None
    assert diagnostics["ownership_state"] == "UNKNOWN"
    assert diagnostics["stale_proven"] is False
    assert diagnostics["orphan_file_blocks_writes"] is False


def test_v380_live_kernel_lock_blocks_second_instance_before_task_write(tmp_path):
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

    durable = json.loads(path.read_text(encoding="utf-8"))
    assert durable[str(USER_ID)]["pending_action"] is None
    assert second.get_persistence_diagnostics()["last_save_issue"] == "TASK_FILE_WRITE_LOCKED"


def test_v381_fd_close_releases_kernel_lock_without_deleting_coordination_file(tmp_path):
    path = tmp_path / "tasks.json"
    _write_store(path)
    first = TerminalSafeAssistantTaskService(file_path=str(path))
    second = TerminalSafeAssistantTaskService(file_path=str(path))

    first._acquire_write_lock()
    fd = first._write_lock_fd
    os.close(fd)
    first._write_lock_fd = None

    second.set_pending_action(
        USER_ID,
        {"title": "after-crash-like-close"},
    )

    assert (tmp_path / "tasks.json.lock").exists()
    durable = json.loads(path.read_text(encoding="utf-8"))
    assert durable[str(USER_ID)]["pending_action"] == {
        "title": "after-crash-like-close"
    }


def test_v382_diagnostics_report_self_held_only_for_this_live_owner(tmp_path):
    path = tmp_path / "tasks.json"
    service = TerminalSafeAssistantTaskService(file_path=str(path))

    service._acquire_write_lock()
    try:
        diagnostics = service.get_write_lock_diagnostics()
        assert diagnostics["inspection_state"] == "SELF_HELD"
        assert diagnostics["lock_present"] is True
        assert diagnostics["ownership_state"] == "SELF"
        assert diagnostics["manual_intervention_required"] is False
    finally:
        service._release_write_lock()

    after = service.get_write_lock_diagnostics()
    assert after["inspection_state"] == "NO_ACTIVE_LOCK_EVIDENCE"
    assert after["lock_present"] is None
    assert after["ownership_state"] == "UNKNOWN"


def test_v383_legacy_orphan_coordination_file_never_requires_manual_deletion(tmp_path):
    path = tmp_path / "tasks.json"
    _write_store(path)
    lock_path = tmp_path / "tasks.json.lock"
    lock_path.write_bytes(b"")
    service = TerminalSafeAssistantTaskService(file_path=str(path))

    diagnostics = service.get_write_lock_diagnostics()
    assert diagnostics["coordination_file_present"] is True
    assert diagnostics["inspection_state"] == "NO_ACTIVE_LOCK_EVIDENCE"
    assert diagnostics["manual_intervention_required"] is False
    assert diagnostics["automatic_recovery_allowed"] is False
    assert diagnostics["manual_lock_removal_allowed"] is False

    service.set_pending_action(USER_ID, {"title": "safe"})
    durable = json.loads(path.read_text(encoding="utf-8"))
    assert durable[str(USER_ID)]["pending_action"] == {"title": "safe"}
    assert service.get_pending_action(USER_ID)["action"] == {"title": "safe"}


def test_v384_operational_blocker_comes_from_real_contention_evidence_not_file_presence(tmp_path):
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

    report = TaskPersistenceOperationalService(second).build_report()

    assert report["operational_state"] == "BLOCKED"
    assert report["blockers"] == ["TASK_FILE_WRITE_LOCKED"]
    assert report["next_action"] == "WAIT_FOR_ACTIVE_WRITER_AND_RETRY_MANUALLY"
    assert report["write_lock_stale_proven"] is False
    assert report["automatic_lock_recovery_allowed"] is False
    assert report["manual_lock_removal_allowed"] is False


def test_v385_missing_kernel_lock_support_fails_closed_without_task_write(tmp_path, monkeypatch):
    path = tmp_path / "tasks.json"
    _write_store(path)
    service = TerminalSafeAssistantTaskService(file_path=str(path))
    monkeypatch.setattr(terminal_module, "_kernel_lock_backend", lambda: None)

    with pytest.raises(RuntimeError, match="TASK_FILE_WRITE_LOCK_ERROR"):
        service.set_pending_action(USER_ID, {"title": "blocked"})

    durable = json.loads(path.read_text(encoding="utf-8"))
    assert durable[str(USER_ID)]["pending_action"] is None
    persistence = service.get_persistence_diagnostics()
    assert persistence["last_save_state"] == "FAILED"
    assert persistence["last_save_issue"] == "TASK_FILE_WRITE_LOCK_ERROR"

    lock = service.get_write_lock_diagnostics()
    assert lock["inspection_state"] == "CHECK_ERROR"
    assert lock["kernel_lock_guard"] is False
    assert lock["manual_intervention_required"] is True


def test_v386_unlock_error_still_closes_fd_and_releases_kernel_ownership(tmp_path, monkeypatch):
    path = tmp_path / "tasks.json"
    _write_store(path)
    first = TerminalSafeAssistantTaskService(file_path=str(path))
    second = TerminalSafeAssistantTaskService(file_path=str(path))
    real_unlock = terminal_module._release_kernel_file_lock

    def failing_unlock(fd):
        raise OSError("sensitive unlock detail")

    monkeypatch.setattr(terminal_module, "_release_kernel_file_lock", failing_unlock)

    first.set_pending_action(USER_ID, {"title": "first"})
    assert first.get_persistence_diagnostics()[
        "last_lock_release_issue"
    ] == "TASK_FILE_WRITE_LOCK_RELEASE_ERROR"

    monkeypatch.setattr(terminal_module, "_release_kernel_file_lock", real_unlock)
    second.load()
    second.set_pending_action(USER_ID, {"title": "second"})

    durable = json.loads(path.read_text(encoding="utf-8"))
    assert durable[str(USER_ID)]["pending_action"] == {"title": "second"}
    assert second.get_pending_action(USER_ID)["action"] == {"title": "second"}
    second_persistence = second.get_persistence_diagnostics()
    if os.name == "nt":
        assert second_persistence["last_save_state"] == (
            "SUCCEEDED_WITH_DURABILITY_WARNING"
        )
        assert second_persistence["last_save_issue"] == (
            "TASK_DIRECTORY_FSYNC_UNSUPPORTED"
        )
    else:
        assert second_persistence["last_save_state"] == "SUCCEEDED"


def test_v387_kernel_lock_hardening_never_enables_business_execution_or_lock_deletion(tmp_path):
    path = tmp_path / "tasks.json"
    service = TerminalSafeAssistantTaskService(file_path=str(path))

    service.create_task(USER_ID, "Новая", [_action()])
    report = TaskPersistenceOperationalService(service).build_report()

    assert report["business_execution_ready"] is False
    assert report["mutation_ready"] is False
    assert report["automatic_lock_recovery_allowed"] is False
    assert report["manual_lock_removal_allowed"] is False
    assert report["executed"] is False


def test_v388_independent_process_lock_blocks_writer_and_releases_on_exit(tmp_path):
    path = tmp_path / "tasks.json"
    _write_store(path)
    ready_path = tmp_path / "writer-ready"
    release_path = tmp_path / "writer-release"
    app_path = Path(__file__).resolve().parents[1] / "app"
    environment = os.environ.copy()
    existing_pythonpath = environment.get("PYTHONPATH", "")
    environment["PYTHONPATH"] = os.pathsep.join(
        item for item in (str(app_path), existing_pythonpath) if item
    )
    child_code = "\n".join(
        [
            "import pathlib, sys, time",
            "from services.terminal_safe_assistant_task_service import TerminalSafeAssistantTaskService",
            "service = TerminalSafeAssistantTaskService(file_path=sys.argv[1])",
            "service._acquire_write_lock()",
            "pathlib.Path(sys.argv[2]).write_text('ready')",
            "while not pathlib.Path(sys.argv[3]).exists(): time.sleep(0.01)",
            "service._release_write_lock()",
        ]
    )
    child = subprocess.Popen(
        [sys.executable, "-c", child_code, str(path), str(ready_path), str(release_path)],
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    contender = TerminalSafeAssistantTaskService(file_path=str(path))

    try:
        deadline = time.monotonic() + 10
        while not ready_path.exists() and child.poll() is None and time.monotonic() < deadline:
            time.sleep(0.01)

        assert ready_path.exists(), child.stderr.read() if child.poll() is not None else "writer did not acquire lock"
        with pytest.raises(FileExistsError, match="TASK_FILE_WRITE_LOCKED"):
            contender._acquire_write_lock()

        release_path.write_text("release")
        assert child.wait(timeout=10) == 0, child.stderr.read()

        contender._acquire_write_lock()
        contender._release_write_lock()
    finally:
        if child.poll() is None:
            release_path.write_text("release")
            child.wait(timeout=10)
        child.stderr.close()
