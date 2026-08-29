import json

import pytest

from app.services.assistant_action_execution_service import (
    AssistantActionExecutionService,
)
from app.services.assistant_task_service import (
    AssistantTaskService,
)


USER_ID = 9101


def _actions():
    return [
        {
            "title": "Первый шаг",
            "type": "test",
            "status": "NEW",
            "priority": "HIGH",
        },
        {
            "title": "Второй шаг",
            "type": "test",
            "status": "NEW",
            "priority": "MEDIUM",
        },
    ]


class _Replanning:
    def replan(self, failed_action):
        return {
            "error": False,
            "plan": [
                {
                    "title": "Восстановленный шаг",
                    "type": "test",
                    "status": "NEW",
                    "priority": "HIGH",
                }
            ],
        }


def test_v248_atomic_save_replaces_complete_json_and_cleans_tmp(tmp_path):
    path = tmp_path / "tasks.json"
    service = AssistantTaskService(file_path=str(path))
    service.create_task(USER_ID, "Задача", _actions())

    assert path.exists()
    assert not (tmp_path / "tasks.json.tmp").exists()

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload[str(USER_ID)]["task"] == "Задача"
    assert payload[str(USER_ID)]["actions"][0]["status"] == "NEW"


def test_v248_failed_atomic_replace_preserves_previous_file(
    tmp_path,
    monkeypatch,
):
    path = tmp_path / "tasks.json"
    service = AssistantTaskService(file_path=str(path))
    service.create_task(USER_ID, "Исходная", _actions())
    original = path.read_text(encoding="utf-8")

    service.tasks[str(USER_ID)]["task"] = "Новое значение"

    def _broken_replace(source, target):
        raise OSError("replace failed")

    monkeypatch.setattr(
        "app.services.assistant_task_service.os.replace",
        _broken_replace,
    )

    with pytest.raises(OSError):
        service.save()

    assert path.read_text(encoding="utf-8") == original
    assert not (tmp_path / "tasks.json.tmp").exists()


def test_v249_failure_persists_and_clears_pending_after_restart(tmp_path):
    path = tmp_path / "tasks.json"
    service = AssistantTaskService(file_path=str(path))
    service.create_task(USER_ID, "Задача", _actions())
    service.start_action(USER_ID, "Первый шаг")

    failed = service.fail_action(
        USER_ID,
        "Первый шаг",
        "API unavailable",
    )

    assert failed["error"] is False
    assert service.get_pending_action(USER_ID)["action"] is None

    recovered = AssistantTaskService(file_path=str(path))
    task = recovered.get_task(USER_ID)["task"]

    assert task["actions"][0]["status"] == "FAILED"
    assert task["actions"][0]["error"] == "API unavailable"
    assert task["pending_action"] is None
    assert recovered.get_current_action(USER_ID)["action"]["title"] == (
        "Второй шаг"
    )


def test_v250_replan_request_survives_restart(tmp_path):
    path = tmp_path / "tasks.json"
    service = AssistantTaskService(file_path=str(path))
    service.create_task(USER_ID, "Задача", _actions())

    requested = service.request_replan(
        USER_ID,
        reason="Execution failed",
    )

    assert requested["error"] is False

    recovered = AssistantTaskService(file_path=str(path))
    task = recovered.get_task(USER_ID)["task"]

    assert task["replan_requested"] is True
    assert task["replan_reason"] == "Execution failed"


def test_v251_retry_preparation_survives_restart(tmp_path):
    path = tmp_path / "tasks.json"
    service = AssistantTaskService(file_path=str(path))
    service.create_task(USER_ID, "Задача", _actions())
    service.start_action(USER_ID, "Первый шаг")
    service.fail_action(USER_ID, "Первый шаг", "temporary")

    execution = AssistantActionExecutionService(
        task_service=service,
    )
    retried = execution.retry_action(USER_ID)

    assert retried["error"] is False
    assert retried["action"]["status"] == "NEW"
    assert retried["action"]["attempt"] == 2

    recovered = AssistantTaskService(file_path=str(path))
    task = recovered.get_task(USER_ID)["task"]

    assert task["actions"][0]["status"] == "NEW"
    assert task["actions"][0]["attempt"] == 2
    assert "error" not in task["actions"][0]
    assert task["pending_action"] is None


def test_v252_applied_replan_survives_restart(tmp_path):
    path = tmp_path / "tasks.json"
    service = AssistantTaskService(file_path=str(path))
    service.create_task(USER_ID, "Задача", _actions())
    service.start_action(USER_ID, "Первый шаг")
    service.fail_action(USER_ID, "Первый шаг", "API unavailable")
    service.request_replan(USER_ID, "API unavailable")

    execution = AssistantActionExecutionService(
        task_service=service,
        replanning_service=_Replanning(),
    )
    replanned = execution.replan_failed_action(USER_ID)

    assert replanned["error"] is False
    assert replanned["plan"][0]["title"] == "Восстановленный шаг"

    recovered = AssistantTaskService(file_path=str(path))
    task = recovered.get_task(USER_ID)["task"]

    assert task["replanned"] is True
    assert task["replan_requested"] is False
    assert task["replan_reason"] == "API unavailable"
    assert task["pending_action"] is None
    assert task["actions"] == [
        {
            "title": "Восстановленный шаг",
            "type": "test",
            "status": "NEW",
            "priority": "HIGH",
        }
    ]


def test_v253_non_mapping_persisted_payload_fails_closed(tmp_path):
    path = tmp_path / "tasks.json"
    path.write_text(
        json.dumps(["not", "a", "task", "mapping"]),
        encoding="utf-8",
    )

    recovered = AssistantTaskService(file_path=str(path))

    assert recovered.tasks == {}
    assert recovered.get_task(USER_ID)["task"] is None


def test_v254_recovered_failed_action_is_not_implicitly_executed(tmp_path):
    path = tmp_path / "tasks.json"
    service = AssistantTaskService(file_path=str(path))
    service.create_task(
        USER_ID,
        "Задача",
        [{
            "title": "Единственный шаг",
            "type": "test",
            "status": "NEW",
        }],
    )
    service.start_action(USER_ID, "Единственный шаг")
    service.fail_action(
        USER_ID,
        "Единственный шаг",
        "failure",
    )

    recovered = AssistantTaskService(file_path=str(path))
    task = recovered.get_task(USER_ID)["task"]

    assert task["actions"][0]["status"] == "FAILED"
    assert task["pending_action"] is None
    assert recovered.get_current_action(USER_ID)["action"] is None
    assert recovered.is_task_completed(USER_ID)["completed"] is False


def test_v255_owner_retry_rejects_non_failed_action_without_mutation(tmp_path):
    path = tmp_path / "tasks.json"
    service = AssistantTaskService(file_path=str(path))
    service.create_task(USER_ID, "Задача", _actions())

    result = service.prepare_retry_action(
        USER_ID,
        "Первый шаг",
        2,
    )

    assert result["error"] is True

    recovered = AssistantTaskService(file_path=str(path))
    task = recovered.get_task(USER_ID)["task"]
    assert task["actions"][0]["status"] == "NEW"
    assert "attempt" not in task["actions"][0]
