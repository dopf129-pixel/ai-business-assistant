import json

from core.task_states import TaskStatus
from services.terminal_safe_assistant_task_service import (
    TerminalSafeAssistantTaskService,
)


USER_ID = 9501


def _valid_task():
    return {
        "task": "Задача",
        "status": TaskStatus.ACTIVE,
        "actions": [{"title": "Шаг", "status": "NEW", "type": "test"}],
        "pending_action": None,
    }


def test_v303_absent_task_file_is_clean_and_non_executing(tmp_path):
    path = tmp_path / "missing.json"
    service = TerminalSafeAssistantTaskService(file_path=str(path))

    diagnostics = service.get_load_diagnostics()
    assert diagnostics["source_state"] == "ABSENT"
    assert diagnostics["issue_count"] == 0
    assert diagnostics["loaded_task_count"] == 0
    assert diagnostics["executed"] is False
    assert not path.exists()


def test_v304_corrupt_json_is_reported_without_rewrite(tmp_path):
    path = tmp_path / "tasks.json"
    path.write_text("{not-json", encoding="utf-8")
    before = path.read_text(encoding="utf-8")

    service = TerminalSafeAssistantTaskService(file_path=str(path))

    diagnostics = service.get_load_diagnostics()
    assert diagnostics["source_state"] == "UNREADABLE"
    assert diagnostics["issues"] == ["TASK_FILE_READ_ERROR"]
    assert diagnostics["loaded_task_count"] == 0
    assert path.read_text(encoding="utf-8") == before


def test_v305_non_dict_root_is_reported_without_rewrite(tmp_path):
    path = tmp_path / "tasks.json"
    path.write_text(json.dumps([_valid_task()]), encoding="utf-8")
    before = path.read_text(encoding="utf-8")

    service = TerminalSafeAssistantTaskService(file_path=str(path))

    diagnostics = service.get_load_diagnostics()
    assert diagnostics["source_state"] == "INVALID_ROOT"
    assert diagnostics["issues"] == ["INVALID_TASK_FILE_ROOT"]
    assert path.read_text(encoding="utf-8") == before


def test_v306_empty_dict_is_valid_loaded_store(tmp_path):
    path = tmp_path / "tasks.json"
    path.write_text("{}", encoding="utf-8")

    service = TerminalSafeAssistantTaskService(file_path=str(path))

    diagnostics = service.get_load_diagnostics()
    assert diagnostics["source_state"] == "LOADED"
    assert diagnostics["issue_count"] == 0
    assert diagnostics["loaded_task_count"] == 0


def test_v307_valid_file_reports_loaded_and_preserves_task(tmp_path):
    path = tmp_path / "tasks.json"
    path.write_text(json.dumps({str(USER_ID): _valid_task()}), encoding="utf-8")

    service = TerminalSafeAssistantTaskService(file_path=str(path))

    diagnostics = service.get_load_diagnostics()
    assert diagnostics["source_state"] == "LOADED"
    assert diagnostics["issue_count"] == 0
    assert diagnostics["loaded_task_count"] == 1
    assert service.get_task(USER_ID)["task"] is not None


def test_v308_record_level_issue_keeps_loaded_source_state(tmp_path):
    path = tmp_path / "tasks.json"
    path.write_text(json.dumps({str(USER_ID): "broken"}), encoding="utf-8")

    service = TerminalSafeAssistantTaskService(file_path=str(path))

    diagnostics = service.get_load_diagnostics()
    assert diagnostics["source_state"] == "LOADED"
    assert diagnostics["issues"] == ["MALFORMED_TASK"]
    assert diagnostics["loaded_task_count"] == 0


def test_v309_read_error_diagnostics_do_not_expose_exception_or_file_contents(tmp_path):
    path = tmp_path / "tasks.json"
    secret_text = "{private-payload"
    path.write_text(secret_text, encoding="utf-8")

    service = TerminalSafeAssistantTaskService(file_path=str(path))
    diagnostics = service.get_load_diagnostics()

    rendered = repr(diagnostics)
    assert secret_text not in rendered
    assert str(path) not in rendered
    assert "JSONDecodeError" not in rendered


def test_v310_corrupt_store_can_recover_only_after_explicit_mutation(tmp_path):
    path = tmp_path / "tasks.json"
    path.write_text("{bad", encoding="utf-8")
    service = TerminalSafeAssistantTaskService(file_path=str(path))
    assert service.get_load_diagnostics()["source_state"] == "UNREADABLE"

    result = service.create_task(USER_ID, "Новая задача", [_valid_task()["actions"][0]])

    assert result["saved"] is True
    recovered = TerminalSafeAssistantTaskService(file_path=str(path))
    assert recovered.get_load_diagnostics()["source_state"] == "LOADED"
    assert recovered.get_task(USER_ID)["task"]["task"] == "Новая задача"


def test_v311_invalid_root_can_recover_only_after_explicit_mutation(tmp_path):
    path = tmp_path / "tasks.json"
    path.write_text("[]", encoding="utf-8")
    service = TerminalSafeAssistantTaskService(file_path=str(path))
    assert service.get_load_diagnostics()["source_state"] == "INVALID_ROOT"

    service.create_task(USER_ID, "Новая задача", [_valid_task()["actions"][0]])

    recovered = TerminalSafeAssistantTaskService(file_path=str(path))
    assert recovered.get_load_diagnostics()["source_state"] == "LOADED"
    assert recovered.get_load_diagnostics()["issue_count"] == 0


def test_v312_load_diagnostics_are_read_only_metadata(tmp_path):
    path = tmp_path / "tasks.json"
    path.write_text("{bad", encoding="utf-8")
    service = TerminalSafeAssistantTaskService(file_path=str(path))

    diagnostics = service.get_load_diagnostics()
    assert diagnostics["status"] == "TASK_PERSISTENCE_LOAD_DIAGNOSTICS"
    assert diagnostics["read_only"] is True
    assert diagnostics["executed"] is False
