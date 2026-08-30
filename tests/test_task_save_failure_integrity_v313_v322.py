import json
import os
from copy import deepcopy

import pytest

from core.task_states import TaskStatus
from services.terminal_safe_assistant_task_service import (
    TerminalSafeAssistantTaskService,
)


USER_ID = 9601


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


def _fail_replace(monkeypatch):
    def boom(source, target):
        raise OSError("sensitive filesystem detail")

    monkeypatch.setattr(os, "replace", boom)


def test_v313_never_attempted_save_has_neutral_diagnostics(tmp_path):
    service = TerminalSafeAssistantTaskService(file_path=str(tmp_path / "tasks.json"))
    diagnostics = service.get_persistence_diagnostics()

    assert diagnostics["last_save_state"] == "NEVER_ATTEMPTED"
    assert diagnostics["last_save_issue"] is None
    assert diagnostics["last_save_rolled_back"] is False
    assert diagnostics["read_only"] is True
    assert diagnostics["executed"] is False


def test_v314_successful_save_records_success_without_execution_claim(tmp_path):
    service = TerminalSafeAssistantTaskService(file_path=str(tmp_path / "tasks.json"))

    result = service.create_task(USER_ID, "Новая задача", [_action()])

    assert result["saved"] is True
    diagnostics = service.get_persistence_diagnostics()
    assert diagnostics["last_save_state"] == "SUCCEEDED"
    assert diagnostics["last_save_issue"] is None
    assert diagnostics["last_save_rolled_back"] is False
    assert diagnostics["executed"] is False


def test_v315_failed_new_task_save_rolls_memory_back_to_absent_store(tmp_path, monkeypatch):
    path = tmp_path / "tasks.json"
    service = TerminalSafeAssistantTaskService(file_path=str(path))
    _fail_replace(monkeypatch)

    with pytest.raises(OSError):
        service.create_task(USER_ID, "Новая задача", [_action()])

    assert service.get_task(USER_ID)["task"] is None
    diagnostics = service.get_persistence_diagnostics()
    assert diagnostics["load_source_state"] == "ABSENT"
    assert diagnostics["last_save_state"] == "FAILED"
    assert diagnostics["last_save_issue"] == "TASK_FILE_WRITE_ERROR"
    assert diagnostics["last_save_rolled_back"] is True


def test_v316_failed_existing_task_mutation_restores_durable_record(tmp_path, monkeypatch):
    path = tmp_path / "tasks.json"
    path.write_text(json.dumps({str(USER_ID): _persisted_task()}, ensure_ascii=False), encoding="utf-8")
    service = TerminalSafeAssistantTaskService(file_path=str(path))
    before = deepcopy(service.get_task(USER_ID)["task"])
    _fail_replace(monkeypatch)

    with pytest.raises(OSError):
        service.set_pending_action(USER_ID, {"title": "новый pending"})

    assert service.get_task(USER_ID)["task"] == before
    assert service.get_pending_action(USER_ID)["action"] is None


def test_v317_failed_status_change_restores_durable_status(tmp_path, monkeypatch):
    path = tmp_path / "tasks.json"
    path.write_text(json.dumps({str(USER_ID): _persisted_task()}, ensure_ascii=False), encoding="utf-8")
    service = TerminalSafeAssistantTaskService(file_path=str(path))
    _fail_replace(monkeypatch)

    with pytest.raises(OSError):
        service.change_task_status(USER_ID, TaskStatus.PAUSED)

    assert service.get_task_status(USER_ID)["status"] == TaskStatus.ACTIVE
    assert service.get_persistence_diagnostics()["last_save_rolled_back"] is True


def test_v318_failed_save_does_not_replace_existing_file(tmp_path, monkeypatch):
    path = tmp_path / "tasks.json"
    original = json.dumps({str(USER_ID): _persisted_task()}, ensure_ascii=False, indent=2)
    path.write_text(original, encoding="utf-8")
    service = TerminalSafeAssistantTaskService(file_path=str(path))
    _fail_replace(monkeypatch)

    with pytest.raises(OSError):
        service.set_pending_action(USER_ID, {"title": "новый pending"})

    assert path.read_text(encoding="utf-8") == original


def test_v319_failed_save_cleans_temporary_file(tmp_path, monkeypatch):
    path = tmp_path / "tasks.json"
    service = TerminalSafeAssistantTaskService(file_path=str(path))
    _fail_replace(monkeypatch)

    with pytest.raises(OSError):
        service.create_task(USER_ID, "Новая задача", [_action()])

    assert not (tmp_path / "tasks.json.tmp").exists()


def test_v320_failure_diagnostics_do_not_expose_exception_path_or_task_content(tmp_path, monkeypatch):
    path = tmp_path / "private-tasks.json"
    service = TerminalSafeAssistantTaskService(file_path=str(path))
    _fail_replace(monkeypatch)

    with pytest.raises(OSError):
        service.create_task(USER_ID, "СЕКРЕТНАЯ ЗАДАЧА", [_action()])

    rendered = repr(service.get_persistence_diagnostics())
    assert "sensitive filesystem detail" not in rendered
    assert str(path) not in rendered
    assert "СЕКРЕТНАЯ ЗАДАЧА" not in rendered
    assert str(USER_ID) not in rendered


def test_v321_success_after_failure_replaces_failure_diagnostics(tmp_path, monkeypatch):
    path = tmp_path / "tasks.json"
    service = TerminalSafeAssistantTaskService(file_path=str(path))
    real_replace = os.replace
    _fail_replace(monkeypatch)

    with pytest.raises(OSError):
        service.create_task(USER_ID, "Первая", [_action()])

    monkeypatch.setattr(os, "replace", real_replace)
    result = service.create_task(USER_ID, "Вторая", [_action()])

    assert result["saved"] is True
    diagnostics = service.get_persistence_diagnostics()
    assert diagnostics["last_save_state"] == "SUCCEEDED"
    assert diagnostics["last_save_issue"] is None
    assert diagnostics["last_save_rolled_back"] is False


def test_v322_failed_save_never_returns_false_success(tmp_path, monkeypatch):
    service = TerminalSafeAssistantTaskService(file_path=str(tmp_path / "tasks.json"))
    _fail_replace(monkeypatch)

    with pytest.raises(OSError):
        service.create_task(USER_ID, "Новая задача", [_action()])

    assert service.get_persistence_diagnostics()["last_save_state"] == "FAILED"
