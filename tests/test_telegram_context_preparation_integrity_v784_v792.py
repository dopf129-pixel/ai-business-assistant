from services.assistant_button_handler_service import AssistantButtonHandlerService


class _Assistant:
    def __init__(self):
        self.calls = 0

    def ask(self, text, user_id=None):
        self.calls += 1
        return {"error": False, "message": "ok"}


class _UserContext:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = 0

    def update(self, user_id, key, value):
        self.calls += 1
        if self.error:
            raise self.error
        return self.result


class _TaskContext:
    def __init__(self, first_result=None, second_result=None, first_error=None, second_error=None):
        self.user_context_service = _UserContext(first_result, first_error)
        self.second_result = second_result
        self.second_error = second_error
        self.task_calls = 0

    def update_task(self, user_id, task):
        self.task_calls += 1
        if self.second_error:
            raise self.second_error
        return self.second_result


class _History:
    def __init__(self):
        self.calls = 0

    def add(self, user_id, event):
        self.calls += 1
        return {"error": False, "saved": True}


def _service(task_context):
    assistant = _Assistant()
    history = _History()
    service = AssistantButtonHandlerService(
        assistant,
        history_service=history,
        task_context_service=task_context,
    )
    return service, assistant, history


def test_v784_first_context_failure_stops_task_update_and_assistant():
    task_context = _TaskContext(
        first_result={"error": True, "message": "USER_CONTEXT_SAVE_FAILED"},
        second_result={"error": False, "updated": True},
    )
    service, assistant, history = _service(task_context)

    result = service.handle("analyze", user_id=1001)

    assert result["error"] is True
    assert result["message"] == "USER_CONTEXT_SAVE_FAILED"
    assert result["assistant_started"] is False
    assert task_context.user_context_service.calls == 1
    assert task_context.task_calls == 0
    assert assistant.calls == 0
    assert history.calls == 0


def test_v785_malformed_first_context_result_is_unknown_and_stops_flow():
    task_context = _TaskContext(
        first_result={"updated": True},
        second_result={"error": False, "updated": True},
    )
    service, assistant, history = _service(task_context)

    result = service.handle("plan", user_id=1001)

    assert result == {
        "error": True,
        "message": "INVALID_ASSISTANT_BUTTON_CONTEXT_RESULT",
        "assistant_started": False,
        "context_state_unknown": True,
    }
    assert task_context.task_calls == 0
    assert assistant.calls == 0
    assert history.calls == 0


def test_v786_first_context_exception_is_sanitized_without_retry():
    task_context = _TaskContext(
        first_error=TypeError("secret internal type error"),
        second_result={"error": False, "updated": True},
    )
    service, assistant, history = _service(task_context)

    result = service.handle("analyze", user_id=1001)

    assert result == {
        "error": True,
        "message": "ASSISTANT_BUTTON_CONTEXT_UPDATE_FAILED",
        "assistant_started": False,
        "context_state_unknown": True,
    }
    assert "secret" not in str(result)
    assert task_context.user_context_service.calls == 1
    assert task_context.task_calls == 0
    assert assistant.calls == 0
    assert history.calls == 0


def test_v787_second_context_failure_reports_partial_state_without_rollback():
    task_context = _TaskContext(
        first_result={"error": False, "updated": True},
        second_result={"error": True, "message": "CURRENT_TASK_SAVE_FAILED"},
    )
    service, assistant, history = _service(task_context)

    result = service.handle("plan", user_id=1001)

    assert result == {
        "error": True,
        "message": "CURRENT_TASK_SAVE_FAILED",
        "assistant_started": False,
        "context_partially_updated": True,
        "last_action_updated": True,
        "current_task_updated": False,
    }
    assert "rolled_back" not in result
    assert task_context.task_calls == 1
    assert assistant.calls == 0
    assert history.calls == 0


def test_v788_malformed_second_context_result_preserves_partial_unknown_state():
    task_context = _TaskContext(
        first_result={"error": False, "updated": True},
        second_result={"error": False},
    )
    service, assistant, history = _service(task_context)

    result = service.handle("analyze", user_id=1001)

    assert result["error"] is True
    assert result["message"] == "INVALID_ASSISTANT_BUTTON_CONTEXT_RESULT"
    assert result["assistant_started"] is False
    assert result["context_state_unknown"] is True
    assert result["context_partially_updated"] is True
    assert result["last_action_updated"] is True
    assert "rolled_back" not in result
    assert assistant.calls == 0
    assert history.calls == 0


def test_v789_second_context_exception_is_sanitized_and_partial():
    task_context = _TaskContext(
        first_result={"error": False, "updated": True},
        second_error=RuntimeError("secret persistence path"),
    )
    service, assistant, history = _service(task_context)

    result = service.handle("plan", user_id=1001)

    assert result == {
        "error": True,
        "message": "ASSISTANT_BUTTON_CONTEXT_UPDATE_FAILED",
        "assistant_started": False,
        "context_partially_updated": True,
        "last_action_updated": True,
        "current_task_state_unknown": True,
    }
    assert "secret" not in str(result)
    assert "rolled_back" not in result
    assert assistant.calls == 0
    assert history.calls == 0


def test_v790_valid_context_preparation_runs_assistant_and_history_once():
    task_context = _TaskContext(
        first_result={"error": False, "updated": True},
        second_result={"error": False, "updated": True},
    )
    service, assistant, history = _service(task_context)

    result = service.handle("analyze", user_id=1001)

    assert result["error"] is False
    assert task_context.user_context_service.calls == 1
    assert task_context.task_calls == 1
    assert assistant.calls == 1
    assert history.calls == 1


def test_v791_absent_context_service_preserves_optional_context_behavior():
    service, assistant, history = _service(None)

    result = service.handle("plan", user_id=1001)

    assert result["error"] is False
    assert assistant.calls == 1
    assert history.calls == 1


def test_v792_missing_user_id_does_not_attempt_context_persistence():
    task_context = _TaskContext(
        first_result={"error": False, "updated": True},
        second_result={"error": False, "updated": True},
    )
    service, assistant, history = _service(task_context)

    result = service.handle("analyze", user_id=None)

    assert result["error"] is False
    assert task_context.user_context_service.calls == 0
    assert task_context.task_calls == 0
    assert assistant.calls == 1
    assert history.calls == 0
