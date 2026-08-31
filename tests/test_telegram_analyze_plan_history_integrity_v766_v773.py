from services.assistant_button_handler_service import AssistantButtonHandlerService


class _Assistant:
    def __init__(self, result):
        self.result = result
        self.calls = 0

    def ask(self, text, user_id=None):
        self.calls += 1
        return self.result


class _History:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = []

    def add(self, user_id, event):
        self.calls.append((user_id, event))
        if self.error:
            raise self.error
        return self.result


def _service(result, history=None):
    assistant = _Assistant(result)
    return AssistantButtonHandlerService(
        assistant,
        history_service=history,
    ), assistant


def test_v766_analyze_failure_does_not_record_success_history():
    failure = {"error": True, "message": "ASSISTANT_DOWNSTREAM_FAILED"}
    history = _History({"error": False, "saved": True})
    service, assistant = _service(failure, history)

    assert service.handle("analyze", user_id=1001) is failure
    assert assistant.calls == 1
    assert history.calls == []


def test_v767_plan_failure_does_not_record_success_history():
    failure = {"error": True, "message": "PLANNING_DOWNSTREAM_FAILED"}
    history = _History({"error": False, "saved": True})
    service, assistant = _service(failure, history)

    assert service.handle("plan", user_id=1001) is failure
    assert assistant.calls == 1
    assert history.calls == []


def test_v768_malformed_assistant_result_fails_closed_before_history():
    for malformed in (None, [], {}, {"error": "false"}, {"error": 0}):
        history = _History({"error": False, "saved": True})
        service, assistant = _service(malformed, history)

        assert service.handle("analyze", user_id=1001) == {
            "error": True,
            "message": "INVALID_ASSISTANT_BUTTON_RESULT",
        }
        assert assistant.calls == 1
        assert history.calls == []


def test_v769_valid_success_records_exact_history_event_once():
    for button_id, event in (
        ("analyze", "Выполнен анализ"),
        ("plan", "Создан план действий"),
    ):
        success = {"error": False, "message": "ok"}
        history = _History({"error": False, "saved": True})
        service, assistant = _service(success, history)

        assert service.handle(button_id, user_id=1001) is success
        assert assistant.calls == 1
        assert history.calls == [(1001, event)]


def test_v770_explicit_history_failure_is_not_hidden_by_assistant_success():
    history = _History({
        "error": True,
        "message": "USER_STORAGE_SAVE_FAILED",
    })
    service, assistant = _service({"error": False, "message": "ok"}, history)

    assert service.handle("plan", user_id=1001) == {
        "error": True,
        "message": "USER_STORAGE_SAVE_FAILED",
        "assistant_completed": True,
        "history_recorded": False,
    }
    assert assistant.calls == 1
    assert len(history.calls) == 1


def test_v771_malformed_history_result_keeps_persistence_state_unknown():
    history = _History({"saved": True})
    service, assistant = _service({"error": False, "message": "ok"}, history)

    assert service.handle("analyze", user_id=1001) == {
        "error": True,
        "message": "INVALID_ASSISTANT_BUTTON_HISTORY_RESULT",
        "assistant_completed": True,
        "history_recorded": False,
        "persistence_state_unknown": True,
    }
    assert assistant.calls == 1
    assert len(history.calls) == 1


def test_v772_history_exception_is_sanitized_and_state_is_unknown():
    history = _History(error=RuntimeError("secret filesystem path"))
    service, assistant = _service({"error": False, "message": "ok"}, history)

    result = service.handle("analyze", user_id=1001)

    assert result == {
        "error": True,
        "message": "ASSISTANT_BUTTON_HISTORY_WRITE_FAILED",
        "assistant_completed": True,
        "history_recorded": False,
        "persistence_state_unknown": True,
    }
    assert "secret" not in str(result)
    assert assistant.calls == 1
    assert len(history.calls) == 1


def test_v773_history_is_optional_without_persistable_user_context():
    success = {"error": False, "message": "ok"}
    history = _History({"error": False, "saved": True})
    service, assistant = _service(success, history)

    assert service.handle("plan", user_id=None) is success
    assert assistant.calls == 1
    assert history.calls == []

    service, assistant = _service(success, None)
    assert service.handle("analyze", user_id=1001) is success
    assert assistant.calls == 1
