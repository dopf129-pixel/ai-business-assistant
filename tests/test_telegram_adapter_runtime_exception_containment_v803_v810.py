from app.telegram_app_layer.assistant_telegram_adapter import (
    AssistantTelegramAdapter,
)


class _Keyboard:
    def __init__(self, result=None, error=None):
        self.result = result or {
            "error": False,
            "type": "inline_keyboard",
            "buttons": [],
        }
        self.error = error
        self.calls = 0

    def build_main_keyboard(self):
        self.calls += 1
        if self.error:
            raise self.error
        return self.result


class _Assistant:
    def __init__(self, result=None, error=None):
        self.result = result or {
            "error": False,
            "message": "ok",
        }
        self.error = error
        self.calls = 0

    def ask(self, text, user_id=None):
        self.calls += 1
        if self.error:
            raise self.error
        return self.result


class _Button:
    def __init__(self, result=None, error=None):
        self.result = result or {
            "error": False,
            "message": "ok",
        }
        self.error = error
        self.calls = 0

    def handle(self, callback, user_id=None):
        self.calls += 1
        if self.error:
            raise self.error
        return self.result


class _LegacyButton:
    def __init__(self, error):
        self.error = error
        self.calls = 0

    def handle(self, callback):
        self.calls += 1
        raise self.error


def _adapter(assistant=None, button=None, keyboard=None):
    return AssistantTelegramAdapter(
        assistant=assistant or _Assistant(),
        keyboard_service=keyboard or _Keyboard(),
        button_handler=button or _Button(),
    )


def test_v803_assistant_exception_returns_stable_failure_once():
    assistant = _Assistant(
        error=RuntimeError("secret assistant detail")
    )
    adapter = _adapter(assistant=assistant)

    result = adapter.handle_text("hello", user_id=1001)

    assert result == {
        "error": True,
        "message": "TELEGRAM_ASSISTANT_DISPATCH_FAILED",
    }
    assert "secret" not in str(result)
    assert assistant.calls == 1


def test_v804_internal_assistant_typeerror_is_not_retried():
    assistant = _Assistant(
        error=TypeError("internal type error")
    )
    adapter = _adapter(assistant=assistant)

    result = adapter.handle_text("hello", user_id=1001)

    assert result["error"] is True
    assert result["message"] == "TELEGRAM_ASSISTANT_DISPATCH_FAILED"
    assert assistant.calls == 1


def test_v805_button_exception_returns_stable_failure_once():
    button = _Button(
        error=RuntimeError("secret button detail")
    )
    adapter = _adapter(button=button)

    result = adapter.handle_button("analyze", user_id=1001)

    assert result == {
        "error": True,
        "message": "TELEGRAM_BUTTON_DISPATCH_FAILED",
    }
    assert "secret" not in str(result)
    assert button.calls == 1


def test_v806_internal_button_typeerror_is_not_legacy_retry():
    button = _Button(
        error=TypeError("internal handler bug")
    )
    adapter = _adapter(button=button)

    result = adapter.handle_button("analyze", user_id=1001)

    assert result["error"] is True
    assert result["message"] == "TELEGRAM_BUTTON_DISPATCH_FAILED"
    assert button.calls == 1


def test_v807_legacy_arity_handler_exception_is_still_one_call():
    button = _LegacyButton(
        RuntimeError("legacy secret")
    )
    adapter = _adapter(button=button)

    result = adapter.handle_button("analyze", user_id=1001)

    assert result == {
        "error": True,
        "message": "TELEGRAM_BUTTON_DISPATCH_FAILED",
    }
    assert button.calls == 1


def test_v808_keyboard_exception_does_not_claim_start_success():
    keyboard = _Keyboard(
        error=RuntimeError("secret keyboard detail")
    )
    adapter = _adapter(keyboard=keyboard)

    result = adapter.get_start_response(user_id=1001)

    assert result == {
        "error": True,
        "message": "TELEGRAM_KEYBOARD_BUILD_FAILED",
    }
    assert "secret" not in str(result)
    assert keyboard.calls == 1


def test_v809_valid_runtime_results_are_unchanged():
    assistant_result = {
        "error": False,
        "message": "assistant",
    }
    button_result = {
        "error": False,
        "message": "button",
    }
    assistant = _Assistant(result=assistant_result)
    button = _Button(result=button_result)
    adapter = _adapter(
        assistant=assistant,
        button=button,
    )

    assert adapter.handle_text(
        "hello",
        user_id=1001,
    ) is assistant_result
    assert adapter.handle_button(
        "history",
        user_id=1001,
    ) is button_result
    assert assistant.calls == 1
    assert button.calls == 1


def test_v810_explicit_runtime_failures_remain_failures():
    assistant_failure = {
        "error": True,
        "message": "ASSISTANT_DOWNSTREAM_FAILED",
    }
    button_failure = {
        "error": True,
        "message": "BUTTON_DOWNSTREAM_FAILED",
    }
    adapter = _adapter(
        assistant=_Assistant(
            result=assistant_failure
        ),
        button=_Button(
            result=button_failure
        ),
    )

    assert adapter.handle_text(
        "hello",
        user_id=1001,
    ) is assistant_failure
    assert adapter.handle_button(
        "analyze",
        user_id=1001,
    ) is button_failure
