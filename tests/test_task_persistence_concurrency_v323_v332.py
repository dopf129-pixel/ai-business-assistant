import builtins
import json
import os

import pytest

from core.task_states import TaskStatus
from services.terminal_safe_assistant_task_service import TerminalSafeAssistantTaskService


USER_ID = 9701
OTHER_USER_ID = 9702


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


def test_v323_persistence_diagnostics_expose_guard_without_fingerprint(tmp_path):
    path = tmp_path / "tasks.json"
    _write_store(path)
    service = TerminalSafeAssistantTaskService(file_path=str(path))

    diagnostics = service.get_persistence_diagnostics()
    rendered = repr(diagnostics)

    assert diagnostics["optimistic_concurrency_guard"] is True
    assert "_source_fingerprint" not in diagnostics
    assert "sha256" not in rendered.lower()
    assert str(path) not in rendered


def test_v324_second_live_instance_cannot_overwrite_newer_durable_state(tmp_path):
    path = tmp_path / "tasks.json"
    _write_store(path)
    first = TerminalSafeAssistantTaskService(file_path=str(path))
    second = TerminalSafeAssistantTaskService(file_path=str(path))

    first.set_pending_action(USER_ID, {"title": "первый writer"})

    with pytest.raises(RuntimeError, match="TASK_FILE_STALE_WRITE"):
        second.set_pending_action(USER_ID, {"title": "второй writer"})

    durable = json.loads(path.read_text(encoding="utf-8"))
    assert durable[str(USER_ID)]["pending_action"] == {"title": "первый writer"}
    assert second.get_pending_action(USER_ID)["action"] == {"title": "первый writer"}
    assert second.get_persistence_diagnostics()["last_save_issue"] == "TASK_FILE_STALE_WRITE"
    assert second.get_persistence_diagnostics()["last_save_rolled_back"] is True


def test_v325_two_instances_loaded_from_absent_store_fail_closed_on_creation_race(tmp_path):
    path = tmp_path / "tasks.json"
    first = TerminalSafeAssistantTaskService(file_path=str(path))
    second = TerminalSafeAssistantTaskService(file_path=str(path))

    first.create_task(USER_ID, "Первая", [_action()])

    with pytest.raises(RuntimeError, match="TASK_FILE_STALE_WRITE"):
        second.create_task(OTHER_USER_ID, "Вторая", [_action("Другой шаг")])

    durable = json.loads(path.read_text(encoding="utf-8"))
    assert str(USER_ID) in durable
    assert str(OTHER_USER_ID) not in durable
    assert second.get_task(USER_ID)["task"]["task"] == "Первая"
    assert second.get_task(OTHER_USER_ID)["task"] is None


def test_v326_stale_writer_does_not_retry_or_reach_atomic_replace(tmp_path, monkeypatch):
    path = tmp_path / "tasks.json"
    _write_store(path)
    first = TerminalSafeAssistantTaskService(file_path=str(path))
    second = TerminalSafeAssistantTaskService(file_path=str(path))
    first.set_pending_action(USER_ID, {"title": "свежее"})

    calls = []
    real_replace = os.replace

    def counted_replace(source, target):
        calls.append((source, target))
        return real_replace(source, target)

    monkeypatch.setattr(os, "replace", counted_replace)

    with pytest.raises(RuntimeError, match="TASK_FILE_STALE_WRITE"):
        second.set_pending_action(USER_ID, {"title": "устаревшее"})

    assert calls == []


def test_v327_external_file_deletion_is_detected_as_stale_write(tmp_path):
    path = tmp_path / "tasks.json"
    _write_store(path)
    service = TerminalSafeAssistantTaskService(file_path=str(path))
    path.unlink()

    with pytest.raises(RuntimeError, match="TASK_FILE_STALE_WRITE"):
        service.set_pending_action(USER_ID, {"title": "не писать"})

    assert service.get_task(USER_ID)["task"] is None
    diagnostics = service.get_persistence_diagnostics()
    assert diagnostics["load_source_state"] == "ABSENT"
    assert diagnostics["last_save_issue"] == "TASK_FILE_STALE_WRITE"


def test_v328_external_corruption_is_detected_then_reloaded_fail_closed(tmp_path):
    path = tmp_path / "tasks.json"
    _write_store(path)
    service = TerminalSafeAssistantTaskService(file_path=str(path))
    path.write_bytes(b"{not-json")

    with pytest.raises(RuntimeError, match="TASK_FILE_STALE_WRITE"):
        service.set_pending_action(USER_ID, {"title": "не писать"})

    load = service.get_load_diagnostics()
    assert load["source_state"] == "UNREADABLE"
    assert load["issues"] == ["TASK_FILE_READ_ERROR"]
    assert service.get_task(USER_ID)["task"] is None


def test_v329_concurrency_check_read_failure_is_stable_and_non_sensitive(tmp_path, monkeypatch):
    path = tmp_path / "tasks.json"
    _write_store(path)
    service = TerminalSafeAssistantTaskService(file_path=str(path))
    real_open = builtins.open

    def failing_open(file, mode="r", *args, **kwargs):
        if str(file) == str(path) and "b" in mode:
            raise OSError("sensitive read detail")
        return real_open(file, mode, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", failing_open)

    with pytest.raises(RuntimeError, match="TASK_FILE_CONCURRENCY_CHECK_ERROR"):
        service.set_pending_action(USER_ID, {"title": "не писать"})

    diagnostics = service.get_persistence_diagnostics()
    assert diagnostics["last_save_issue"] == "TASK_FILE_CONCURRENCY_CHECK_ERROR"
    assert diagnostics["last_save_rolled_back"] is True
    rendered = repr(diagnostics)
    assert "sensitive read detail" not in rendered
    assert str(path) not in rendered


def test_v330_successful_write_refreshes_guard_for_next_same_instance_write(tmp_path):
    path = tmp_path / "tasks.json"
    _write_store(path)
    service = TerminalSafeAssistantTaskService(file_path=str(path))

    service.set_pending_action(USER_ID, {"title": "первое"})
    service.set_pending_action(USER_ID, {"title": "второе"})

    durable = json.loads(path.read_text(encoding="utf-8"))
    assert durable[str(USER_ID)]["pending_action"] == {"title": "второе"}
    assert service.get_persistence_diagnostics()["last_save_state"] == "SUCCEEDED"


def test_v331_fingerprint_value_never_appears_in_public_diagnostics(tmp_path):
    path = tmp_path / "tasks.json"
    _write_store(path)
    service = TerminalSafeAssistantTaskService(file_path=str(path))
    internal = service._source_fingerprint

    assert internal
    assert internal not in repr(service.get_load_diagnostics())
    assert internal not in repr(service.get_persistence_diagnostics())


def test_v332_concurrency_failure_never_claims_business_execution(tmp_path):
    path = tmp_path / "tasks.json"
    _write_store(path)
    first = TerminalSafeAssistantTaskService(file_path=str(path))
    second = TerminalSafeAssistantTaskService(file_path=str(path))
    first.set_pending_action(USER_ID, {"title": "свежее"})

    with pytest.raises(RuntimeError, match="TASK_FILE_STALE_WRITE"):
        second.set_pending_action(USER_ID, {"title": "устаревшее"})

    assert second.get_persistence_diagnostics()["executed"] is False
    assert second.get_load_diagnostics()["executed"] is False
