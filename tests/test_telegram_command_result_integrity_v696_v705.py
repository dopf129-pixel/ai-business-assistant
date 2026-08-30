from services.assistant_memory_command_service import (
    AssistantMemoryCommandService,
)
from telegram_app_layer.assistant_telegram_adapter import (
    AssistantTelegramAdapter,
)
from telegram_app_layer.telegram_bot_service import (
    TelegramBotService,
)


class _Memory:

    def __init__(
        self,
        result=None,
        error=None,
    ):
        self.result = result
        self.error = error
        self.calls = 0

    def remember(
        self,
        user_id,
        key,
        value,
    ):
        self.calls += 1

        if self.error:
            raise self.error

        return self.result


class _MemoryCommand:

    def __init__(
        self,
        result=None,
        error=None,
    ):
        self.result = result
        self.error = error
        self.calls = 0

    def handle(
        self,
        user_id,
        text,
    ):
        self.calls += 1

        if self.error:
            raise self.error

        return self.result


class _Profile:

    def create_user(
        self,
        user_id,
    ):
        return {
            "error": False,
            "user": {
                "user_id": str(
                    user_id
                ),
                "memory": {},
                "history": [],
            },
        }


class _Keyboard:

    def build_main_keyboard(
        self,
    ):
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
            "message": "assistant",
        }


class _Button:

    def handle(
        self,
        callback,
        user_id=None,
    ):
        return {
            "error": False,
        }


class _Command:

    def __init__(
        self,
        result=None,
        error=None,
    ):
        self.result = result
        self.error = error

    def handle(
        self,
        user_id,
        text,
    ):
        if self.error:
            raise self.error
        return self.result


class _Adapter:

    def __init__(
        self,
    ):
        self.text_calls = 0

    def get_start_response(
        self,
        user_id=None,
    ):
        return {
            "error": False,
            "text": "start",
        }

    def handle_text(
        self,
        text,
        user_id=None,
    ):
        self.text_calls += 1
        return {
            "error": False,
            "message": "fallback",
        }


def _adapter(
    memory_command,
):
    assistant = _Assistant()
    adapter = AssistantTelegramAdapter(
        assistant,
        _Keyboard(),
        _Button(),
        _Profile(),
        memory_command,
    )
    return adapter, assistant


def test_v696_memory_command_unrecognized_is_not_failure():

    memory = _Memory()
    service = AssistantMemoryCommandService(
        memory
    )

    assert service.handle(
        1001,
        "обычный текст",
    ) == {
        "error": False,
        "handled": False,
    }
    assert memory.calls == 0


def test_v697_memory_command_success_is_marked_handled():

    memory = _Memory(
        {
            "error": False,
            "saved": True,
        }
    )
    service = AssistantMemoryCommandService(
        memory
    )

    result = service.handle(
        1001,
        "запомни имя Алекс",
    )

    assert result["error"] is False
    assert result["handled"] is True
    assert result["saved"] is True


def test_v698_memory_storage_failure_remains_handled_error():

    memory = _Memory(
        {
            "error": True,
            "message":
                "USER_STORAGE_SAVE_FAILED",
        }
    )
    service = AssistantMemoryCommandService(
        memory
    )

    result = service.handle(
        1001,
        "запомни имя Алекс",
    )

    assert result["error"] is True
    assert result["handled"] is True
    assert result[
        "message"
    ] == "USER_STORAGE_SAVE_FAILED"


def test_v699_malformed_memory_result_fails_closed_as_handled():

    memory = _Memory(
        {
            "saved": True,
        }
    )
    service = AssistantMemoryCommandService(
        memory
    )

    assert service.handle(
        1001,
        "запомни имя Алекс",
    ) == {
        "error": True,
        "handled": True,
        "message":
            "INVALID_MEMORY_COMMAND_RESULT",
    }


def test_v700_adapter_does_not_send_memory_failure_to_assistant():

    memory_command = _MemoryCommand(
        {
            "error": True,
            "handled": True,
            "message":
                "USER_STORAGE_SAVE_FAILED",
        }
    )
    adapter, assistant = _adapter(
        memory_command
    )

    result = adapter.handle_text(
        "запомни имя Алекс",
        1001,
    )

    assert result["error"] is True
    assert result[
        "message"
    ] == "USER_STORAGE_SAVE_FAILED"
    assert assistant.calls == 0


def test_v701_adapter_falls_back_only_when_memory_command_unhandled():

    memory_command = _MemoryCommand(
        {
            "error": False,
            "handled": False,
        }
    )
    adapter, assistant = _adapter(
        memory_command
    )

    result = adapter.handle_text(
        "обычный текст",
        1001,
    )

    assert result["error"] is False
    assert result[
        "message"
    ] == "assistant"
    assert assistant.calls == 1


def test_v702_adapter_rejects_malformed_memory_command_result():

    memory_command = _MemoryCommand(
        {
            "error": False,
        }
    )
    adapter, assistant = _adapter(
        memory_command
    )

    assert adapter.handle_text(
        "hello",
        1001,
    ) == {
        "error": True,
        "message":
            "INVALID_TELEGRAM_MEMORY_COMMAND_RESULT",
    }
    assert assistant.calls == 0


def test_v703_bot_rejects_malformed_non_none_command_result():

    adapter = _Adapter()
    bot = TelegramBotService(
        adapter,
        _Command(
            [
                "bad",
            ]
        ),
    )

    assert bot.on_message(
        1001,
        "/help",
    ) == {
        "error": True,
        "message":
            "INVALID_TELEGRAM_COMMAND_RESULT",
    }
    assert adapter.text_calls == 0


def test_v704_bot_preserves_explicit_command_failure():

    adapter = _Adapter()
    failure = {
        "error": True,
        "message":
            "USER_STORAGE_LOAD_FAILED",
    }
    bot = TelegramBotService(
        adapter,
        _Command(
            failure
        ),
    )

    result = bot.on_message(
        1001,
        "/memory",
    )

    assert result is failure
    assert adapter.text_calls == 0


def test_v705_start_success_has_explicit_error_marker():

    adapter, assistant = _adapter(
        _MemoryCommand(
            {
                "error": False,
                "handled": False,
            }
        )
    )

    result = adapter.get_start_response(
        1001
    )

    assert result["error"] is False
    assert "text" in result
    assert "keyboard" in result
