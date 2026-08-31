from services.assistant_button_handler_service import AssistantButtonHandlerService


class _Assistant:
    def ask(self, text, user_id=None):
        return {"error": False, "message": "ok"}


class _History:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = 0

    def get(self, user_id):
        self.calls += 1
        if self.error:
            raise self.error
        return self.result


class _Memory:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = 0

    def get_memory(self, user_id):
        self.calls += 1
        if self.error:
            raise self.error
        return self.result


def _service(history=None, memory=None):
    return AssistantButtonHandlerService(
        _Assistant(),
        memory_service=memory,
        history_service=history,
    )


def test_v774_missing_history_service_is_unavailable_not_empty_success():
    result = _service().handle("history", user_id=1001)
    assert result == {"error": True, "message": "TELEGRAM_HISTORY_UNAVAILABLE"}
    assert "history" not in result


def test_v775_missing_memory_service_is_unavailable_not_empty_success():
    result = _service().handle("memory", user_id=1001)
    assert result == {"error": True, "message": "TELEGRAM_MEMORY_UNAVAILABLE"}
    assert "memory" not in result


def test_v776_missing_user_context_is_not_clean_empty_data():
    history = _History({"error": False, "history": []})
    memory = _Memory({"error": False, "memory": {}})
    service = _service(history=history, memory=memory)

    assert service.handle("history", user_id=None) == {
        "error": True,
        "message": "TELEGRAM_USER_CONTEXT_REQUIRED",
    }
    assert service.handle("memory", user_id=None) == {
        "error": True,
        "message": "TELEGRAM_USER_CONTEXT_REQUIRED",
    }
    assert history.calls == 0
    assert memory.calls == 0


def test_v777_history_exception_is_sanitized():
    history = _History(error=RuntimeError("secret storage path"))
    result = _service(history=history).handle("history", user_id=1001)

    assert result == {"error": True, "message": "TELEGRAM_HISTORY_READ_FAILED"}
    assert "secret" not in str(result)
    assert history.calls == 1


def test_v778_memory_exception_is_sanitized():
    memory = _Memory(error=RuntimeError("secret storage path"))
    result = _service(memory=memory).handle("memory", user_id=1001)

    assert result == {"error": True, "message": "TELEGRAM_MEMORY_READ_FAILED"}
    assert "secret" not in str(result)
    assert memory.calls == 1


def test_v779_malformed_history_result_fails_closed():
    for malformed in (
        None,
        [],
        {},
        {"error": "false", "history": []},
        {"error": False},
        {"error": False, "history": None},
        {"error": False, "history": {}},
    ):
        history = _History(malformed)
        result = _service(history=history).handle("history", user_id=1001)
        assert result == {"error": True, "message": "INVALID_TELEGRAM_HISTORY_RESULT"}
        assert history.calls == 1


def test_v780_malformed_memory_result_fails_closed():
    for malformed in (
        None,
        [],
        {},
        {"error": 0, "memory": {}},
        {"error": False},
        {"error": False, "memory": None},
        {"error": False, "memory": []},
    ):
        memory = _Memory(malformed)
        result = _service(memory=memory).handle("memory", user_id=1001)
        assert result == {"error": True, "message": "INVALID_TELEGRAM_MEMORY_RESULT"}
        assert memory.calls == 1


def test_v781_explicit_history_failure_is_preserved():
    failure = {"error": True, "message": "USER_STORAGE_LOAD_FAILED"}
    history = _History(failure)
    assert _service(history=history).handle("history", user_id=1001) is failure
    assert history.calls == 1


def test_v782_explicit_memory_failure_is_preserved():
    failure = {"error": True, "message": "USER_STORAGE_LOAD_FAILED"}
    memory = _Memory(failure)
    assert _service(memory=memory).handle("memory", user_id=1001) is failure
    assert memory.calls == 1


def test_v783_legitimate_empty_and_nonempty_reads_remain_success():
    empty_history = {"error": False, "history": []}
    empty_memory = {"error": False, "memory": {}}
    assert _service(history=_History(empty_history)).handle(
        "history", user_id=1001
    ) is empty_history
    assert _service(memory=_Memory(empty_memory)).handle(
        "memory", user_id=1001
    ) is empty_memory

    history_result = {"error": False, "history": ["event"]}
    memory_result = {"error": False, "memory": {"name": "Alex"}}
    assert _service(history=_History(history_result)).handle(
        "history", user_id=1001
    ) is history_result
    assert _service(memory=_Memory(memory_result)).handle(
        "memory", user_id=1001
    ) is memory_result
