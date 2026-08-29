import json

from app.core.task_states import TaskStatus
from app.services.assistant_action_execution_service import (
    AssistantActionExecutionService,
)
from app.services.assistant_task_service import (
    AssistantTaskService,
)


USER_ID = 9201


def _one_action():
    return [{
        "title": "Шаг",
        "type": "test",
        "status": "NEW",
        "priority": "HIGH",
    }]


def test_v256_final_completed_action_marks_task_done_and_persists(tmp_path):
    path = tmp_path / "tasks.json"
    service = AssistantTaskService(file_path=str(path))
    service.create_task(USER_ID, "Задача", _one_action())

    result = service.complete_action(
        USER_ID,
        "Шаг",
        result={"message": "готово"},
    )

    assert result["error"] is False
    assert service.get_task_status(USER_ID)["status"] == TaskStatus.DONE
    assert service.is_task_completed(USER_ID)["completed"] is True
    assert service.has_active_task(USER_ID)["active"] is False

    recovered = AssistantTaskService(file_path=str(path))
    assert recovered.get_task_status(USER_ID)["status"] == TaskStatus.DONE
    assert recovered.get_current_action(USER_ID)["action"] is None


def test_v257_final_skipped_action_marks_task_done(tmp_path):
    path = tmp_path / "tasks.json"
    service = AssistantTaskService(file_path=str(path))
    service.create_task(USER_ID, "Задача", _one_action())

    result = service.skip_action(USER_ID, "Шаг")

    assert result["error"] is False
    assert service.get_task_status(USER_ID)["status"] == TaskStatus.DONE
    assert service.get_task_progress(USER_ID) == {
        "error": False,
        "done": 1,
        "total": 1,
    }


def test_v258_condition_skip_of_last_action_finalizes_task(tmp_path):
    path = tmp_path / "tasks.json"
    service = AssistantTaskService(file_path=str(path))
    service.create_task(
        USER_ID,
        "Задача",
        [{
            "title": "Условный шаг",
            "type": "test",
            "status": "NEW",
            "condition": {"contains": "never-present"},
        }],
    )

    current = service.get_current_action(USER_ID)

    assert current["action"] is None
    task = service.get_task(USER_ID)["task"]
    assert task["actions"][0]["status"] == "SKIPPED"
    assert task["status"] == TaskStatus.DONE

    recovered = AssistantTaskService(file_path=str(path))
    assert recovered.get_task(USER_ID)["task"]["status"] == TaskStatus.DONE


def test_v259_legacy_active_completed_task_reconciles_on_load_without_execution(
    tmp_path,
):
    path = tmp_path / "tasks.json"
    payload = {
        str(USER_ID): {
            "task": "Старая задача",
            "status": TaskStatus.ACTIVE,
            "actions": [{
                "title": "Готовый шаг",
                "type": "test",
                "status": "DONE",
            }],
            "pending_action": None,
        }
    }
    path.write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )

    recovered = AssistantTaskService(file_path=str(path))

    assert recovered.get_task_status(USER_ID)["status"] == TaskStatus.DONE
    assert recovered.get_current_action(USER_ID)["action"] is None
    assert recovered.has_active_task(USER_ID)["active"] is False

    # Load reconciliation is in-memory and does not execute or rewrite.
    on_disk = json.loads(path.read_text(encoding="utf-8"))
    assert on_disk[str(USER_ID)]["status"] == TaskStatus.ACTIVE


def test_v260_cancelled_task_keeps_cancelled_precedence_on_recovery(tmp_path):
    path = tmp_path / "tasks.json"
    payload = {
        str(USER_ID): {
            "task": "Отменённая задача",
            "status": TaskStatus.CANCELLED,
            "actions": [{
                "title": "Старый шаг",
                "type": "test",
                "status": "DONE",
            }],
            "pending_action": None,
        }
    }
    path.write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )

    recovered = AssistantTaskService(file_path=str(path))

    assert recovered.get_task_status(USER_ID)["status"] == (
        TaskStatus.CANCELLED
    )
    assert recovered.has_active_task(USER_ID)["active"] is False


def test_v261_done_task_rejects_lifecycle_mutations(tmp_path):
    path = tmp_path / "tasks.json"
    service = AssistantTaskService(file_path=str(path))
    service.create_task(USER_ID, "Задача", _one_action())
    service.complete_action(USER_ID, "Шаг")

    checks = [
        service.start_action(USER_ID, "Шаг"),
        service.complete_action(USER_ID, "Шаг"),
        service.skip_action(USER_ID, "Шаг"),
        service.update_action_status(USER_ID, "Шаг", "NEW"),
        service.fail_action(USER_ID, "Шаг", "late failure"),
        service.prepare_retry_action(USER_ID, "Шаг", 2),
        service.apply_replan(
            USER_ID,
            [{
                "title": "Новый",
                "type": "test",
                "status": "NEW",
            }],
        ),
        service.request_replan(USER_ID, "late request"),
        service.set_pending_action(
            USER_ID,
            {
                "title": "Поддельный pending",
                "type": "test",
                "status": "IN_PROGRESS",
            },
        ),
    ]

    assert all(item["error"] is True for item in checks)
    assert all(item.get("status") == TaskStatus.DONE for item in checks)

    recovered = AssistantTaskService(file_path=str(path))
    task = recovered.get_task(USER_ID)["task"]
    assert task["status"] == TaskStatus.DONE
    assert task["actions"][0]["status"] == "DONE"


def test_v262_update_action_status_finalizes_when_all_actions_terminal(tmp_path):
    path = tmp_path / "tasks.json"
    service = AssistantTaskService(file_path=str(path))
    service.create_task(
        USER_ID,
        "Задача",
        [
            {
                "title": "Первый",
                "type": "test",
                "status": "NEW",
            },
            {
                "title": "Второй",
                "type": "test",
                "status": "NEW",
            },
        ],
    )

    service.update_action_status(USER_ID, "Первый", "DONE")
    assert service.get_task_status(USER_ID)["status"] == TaskStatus.ACTIVE

    service.update_action_status(USER_ID, "Второй", "SKIPPED")
    assert service.get_task_status(USER_ID)["status"] == TaskStatus.DONE


def test_v263_execution_result_and_persisted_task_agree_on_completion(tmp_path):
    path = tmp_path / "tasks.json"
    task_service = AssistantTaskService(file_path=str(path))
    task_service.create_task(USER_ID, "Задача", _one_action())

    execution = AssistantActionExecutionService(
        task_service=task_service,
    )
    result = execution.execute_current_action(USER_ID)

    assert result["error"] is False
    assert result["completed"] is True
    assert result["next_action"] is None
    assert result["progress"] == {
        "error": False,
        "done": 1,
        "total": 1,
    }
    assert task_service.get_task_status(USER_ID)["status"] == TaskStatus.DONE

    recovered = AssistantTaskService(file_path=str(path))
    assert recovered.get_task_status(USER_ID)["status"] == TaskStatus.DONE
    assert recovered.get_current_action(USER_ID)["action"] is None
