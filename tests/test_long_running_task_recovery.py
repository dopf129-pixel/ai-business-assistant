from app.services.assistant_task_service import AssistantTaskService


USER_ID = 9001


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


def test_in_progress_task_recovers_after_service_restart(tmp_path):
    path = tmp_path / "tasks.json"
    original = AssistantTaskService(file_path=str(path))
    original.create_task(USER_ID, "Долгая задача", _actions())
    original.start_action(USER_ID, "Первый шаг")

    recovered = AssistantTaskService(file_path=str(path))

    task = recovered.get_task(USER_ID)["task"]
    current = recovered.get_current_action(USER_ID)["action"]

    assert task["task"] == "Долгая задача"
    assert task["status"] == "ACTIVE"
    assert task["pending_action"]["title"] == "Первый шаг"
    assert task["pending_action"]["status"] == "IN_PROGRESS"
    assert current["title"] == "Первый шаг"
    assert current["status"] == "IN_PROGRESS"


def test_paused_task_stays_paused_after_restart_and_can_resume(tmp_path):
    path = tmp_path / "tasks.json"
    original = AssistantTaskService(file_path=str(path))
    original.create_task(USER_ID, "Долгая задача", _actions())
    original.pause_task(USER_ID)

    recovered = AssistantTaskService(file_path=str(path))

    assert recovered.get_task(USER_ID)["task"]["status"] == "PAUSED"

    resumed = recovered.resume_task(USER_ID)
    restarted_again = AssistantTaskService(file_path=str(path))

    assert resumed["error"] is False
    assert resumed["status"] == "ACTIVE"
    assert restarted_again.get_task(USER_ID)["task"]["status"] == "ACTIVE"


def test_progress_survives_restart_and_next_unfinished_action_continues(tmp_path):
    path = tmp_path / "tasks.json"
    original = AssistantTaskService(file_path=str(path))
    original.create_task(USER_ID, "Долгая задача", _actions())
    original.start_action(USER_ID, "Первый шаг")
    original.complete_action(
        USER_ID,
        "Первый шаг",
        result={"message": "готово"},
    )

    recovered = AssistantTaskService(file_path=str(path))

    progress = recovered.get_task_progress(USER_ID)
    current = recovered.get_current_action(USER_ID)["action"]

    assert progress == {
        "error": False,
        "done": 1,
        "total": 2,
    }
    assert current["title"] == "Второй шаг"
    assert current["status"] == "NEW"


def test_recovery_does_not_execute_pending_action_implicitly(tmp_path):
    path = tmp_path / "tasks.json"
    original = AssistantTaskService(file_path=str(path))
    original.create_task(USER_ID, "Долгая задача", _actions())
    original.start_action(USER_ID, "Первый шаг")

    recovered = AssistantTaskService(file_path=str(path))
    task = recovered.get_task(USER_ID)["task"]

    assert task["actions"][0]["status"] == "IN_PROGRESS"
    assert task["actions"][1]["status"] == "NEW"
    assert recovered.get_task_progress(USER_ID)["done"] == 0
    assert recovered.is_task_completed(USER_ID)["completed"] is False
