from telegram_app_layer.assistant_telegram_adapter import (
    AssistantTelegramAdapter,
)


class _Profile:

    def __init__(
        self,
        result=None,
        error=None,
    ):
        self.result = result
        self.error = error
        self.calls = 0

    def create_user(
        self,
        user_id,
    ):
        self.calls += 1

        if self.error:
            raise self.error

        return self.result


class _Keyboard:

    def __init__(
        self,
    ):
        self.calls = 0

    def build_main_keyboard(
        self,
    ):
        self.calls += 1
        return {
            "buttons": [],
        }


class _Assistant:

    def __init__(
        self,
    ):
        self.calls = 0

    def ask(
        self,
        text,
        user_id=None,
    ):
        self.calls += 1
        return {
            "error": False,
            "message": "ok",
        }


class _ButtonHandler:

    def __init__(
        self,
    ):
        self.calls = 0

    def handle(
        self,
        callback,
        user_id=None,
    ):
        self.calls += 1
        return {
            "error": False,
            "callback": callback,
        }


class _MemoryCommands:

    def __init__(
        self,
    ):
        self.calls = 0

    def handle(
        self,
        user_id,
        text,
    ):
        self.calls += 1
        return {
            "error": True,
            "message": "not memory",
        }


def _adapter(
    profile,
):
    keyboard = _Keyboard()
    assistant = _Assistant()
    button = _ButtonHandler()
    memory = _MemoryCommands()

    adapter = AssistantTelegramAdapter(
        assistant,
        keyboard,
        button,
        profile,
        memory,
    )

    return (
        adapter,
        keyboard,
        assistant,
        button,
        memory,
    )


def _valid_profile():
    return {
        "error": False,
        "user": {
            "user_id": "1001",
            "memory": {},
            "history": [],
        },
    }


def test_v687_start_profile_error_stops_before_success_ui():

    profile = _Profile(
        {
            "error": True,
            "message":
                "USER_STORAGE_LOAD_FAILED",
        }
    )
    (
        adapter,
        keyboard,
        assistant,
        button,
        memory,
    ) = _adapter(
        profile
    )

    result = adapter.get_start_response(
        1001
    )

    assert result["error"] is True
    assert result[
        "message"
    ] == "USER_STORAGE_LOAD_FAILED"
    assert result[
        "text"
    ] == "Профиль пользователя недоступен"
    assert keyboard.calls == 0
    assert assistant.calls == 0
    assert button.calls == 0
    assert memory.calls == 0


def test_v688_text_profile_error_stops_all_downstream_dispatch():

    profile = _Profile(
        {
            "error": True,
            "message":
                "USER_STORAGE_USER_INVALID",
        }
    )
    (
        adapter,
        keyboard,
        assistant,
        button,
        memory,
    ) = _adapter(
        profile
    )

    result = adapter.handle_text(
        "hello",
        1001,
    )

    assert result == {
        "error": True,
        "message":
            "USER_STORAGE_USER_INVALID",
    }
    assert memory.calls == 0
    assert assistant.calls == 0


def test_v689_button_profile_error_stops_button_handler():

    profile = _Profile(
        {
            "error": True,
            "message":
                "USER_STORAGE_SAVE_FAILED",
        }
    )
    (
        adapter,
        keyboard,
        assistant,
        button,
        memory,
    ) = _adapter(
        profile
    )

    result = adapter.handle_button(
        "analyze",
        1001,
    )

    assert result["error"] is True
    assert button.calls == 0


def test_v690_malformed_profile_result_fails_closed():

    for malformed in (
        None,
        [],
        {},
        {
            "error": False,
        },
        {
            "error": False,
            "user": [],
        },
        {
            "error": "false",
            "user": {},
        },
    ):

        profile = _Profile(
            malformed
        )
        (
            adapter,
            keyboard,
            assistant,
            button,
            memory,
        ) = _adapter(
            profile
        )

        result = adapter.handle_text(
            "hello",
            1001,
        )

        assert result == {
            "error": True,
            "message":
                "INVALID_TELEGRAM_USER_PROFILE_RESULT",
        }
        assert memory.calls == 0
        assert assistant.calls == 0


def test_v691_profile_exception_is_safe_and_non_secret():

    profile = _Profile(
        error=RuntimeError(
            "secret filesystem detail"
        )
    )
    (
        adapter,
        keyboard,
        assistant,
        button,
        memory,
    ) = _adapter(
        profile
    )

    result = adapter.handle_button(
        "analyze",
        1001,
    )

    assert result == {
        "error": True,
        "message":
            "TELEGRAM_USER_PROFILE_CREATE_FAILED",
    }
    assert "secret" not in result[
        "message"
    ]
    assert button.calls == 0


def test_v692_valid_profile_preserves_start_success():

    profile = _Profile(
        _valid_profile()
    )
    (
        adapter,
        keyboard,
        assistant,
        button,
        memory,
    ) = _adapter(
        profile
    )

    result = adapter.get_start_response(
        1001
    )

    assert "text" in result
    assert "keyboard" in result
    assert keyboard.calls == 1
    assert profile.calls == 1


def test_v693_valid_profile_preserves_text_dispatch():

    profile = _Profile(
        _valid_profile()
    )
    (
        adapter,
        keyboard,
        assistant,
        button,
        memory,
    ) = _adapter(
        profile
    )

    result = adapter.handle_text(
        "hello",
        1001,
    )

    assert result["error"] is False
    assert memory.calls == 1
    assert assistant.calls == 1


def test_v694_valid_profile_preserves_button_dispatch():

    profile = _Profile(
        _valid_profile()
    )
    (
        adapter,
        keyboard,
        assistant,
        button,
        memory,
    ) = _adapter(
        profile
    )

    result = adapter.handle_button(
        "analyze",
        1001,
    )

    assert result["error"] is False
    assert button.calls == 1


def test_v695_missing_user_id_preserves_legacy_no_profile_path():

    profile = _Profile(
        {
            "error": True,
            "message": "should not run",
        }
    )
    (
        adapter,
        keyboard,
        assistant,
        button,
        memory,
    ) = _adapter(
        profile
    )

    result = adapter.handle_text(
        "hello"
    )

    assert result["error"] is False
    assert profile.calls == 0
    assert memory.calls == 1
    assert assistant.calls == 1
