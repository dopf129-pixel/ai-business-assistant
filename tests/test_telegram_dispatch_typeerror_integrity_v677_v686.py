import pytest

from telegram_app_layer.assistant_telegram_adapter import (
    AssistantTelegramAdapter,
)
from telegram_app_layer.telegram_bot_service import (
    TelegramBotService,
)
from telegram_app_layer.telegram_runner import (
    TelegramRunner,
)


class _Keyboard:

    def build_main_keyboard(
        self,
    ):
        return {}


class _Assistant:

    def ask(
        self,
        text,
        user_id=None,
    ):
        return {
            "error": False,
            "message": "ok",
        }


class _LegacyAdapter:

    def get_start_response(
        self,
    ):
        return {
            "kind": "start",
        }

    def handle_text(
        self,
        text,
    ):
        return {
            "kind": "text",
            "text": text,
        }

    def handle_button(
        self,
        callback,
    ):
        return {
            "kind": "callback",
            "callback": callback,
        }


class _RaisingAdapter:

    def __init__(
        self,
    ):
        self.start_calls = 0
        self.message_calls = 0
        self.callback_calls = 0

    def get_start_response(
        self,
        user_id=None,
    ):
        self.start_calls += 1
        raise TypeError(
            "internal start failure"
        )

    def handle_text(
        self,
        text,
        user_id=None,
    ):
        self.message_calls += 1
        raise TypeError(
            "internal message failure"
        )

    def handle_button(
        self,
        callback,
        user_id=None,
    ):
        self.callback_calls += 1
        raise TypeError(
            "internal callback failure"
        )


class _LegacyButtonHandler:

    def __init__(
        self,
    ):
        self.calls = 0

    def handle(
        self,
        callback,
    ):
        self.calls += 1
        return {
            "error": False,
            "callback": callback,
        }


class _RaisingButtonHandler:

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
        raise TypeError(
            "internal button failure"
        )


class _LegacyBot:

    def on_start(
        self,
    ):
        return {
            "kind": "start",
        }

    def on_message(
        self,
        text,
    ):
        return {
            "kind": "message",
            "text": text,
        }

    def on_callback(
        self,
        callback,
    ):
        return {
            "kind": "callback",
            "callback": callback,
        }


class _RaisingBot:

    def __init__(
        self,
    ):
        self.message_calls = 0
        self.callback_calls = 0

    def on_message(
        self,
        user_id,
        text,
    ):
        self.message_calls += 1
        raise TypeError(
            "internal bot message failure"
        )

    def on_callback(
        self,
        user_id,
        callback,
    ):
        self.callback_calls += 1
        raise TypeError(
            "internal bot callback failure"
        )


def test_v677_bot_start_preserves_legacy_arity_without_retry():

    service = TelegramBotService(
        _LegacyAdapter()
    )

    assert service.on_start(
        1001
    ) == {
        "kind": "start",
    }


def test_v678_bot_message_preserves_legacy_arity_without_retry():

    service = TelegramBotService(
        _LegacyAdapter()
    )

    assert service.on_message(
        1001,
        "hello",
    ) == {
        "kind": "text",
        "text": "hello",
    }


def test_v679_bot_callback_preserves_legacy_arity_without_retry():

    service = TelegramBotService(
        _LegacyAdapter()
    )

    assert service.on_callback(
        1001,
        "analyze",
    ) == {
        "kind": "callback",
        "callback": "analyze",
    }


def test_v680_internal_bot_message_typeerror_is_not_retried():

    adapter = _RaisingAdapter()
    service = TelegramBotService(
        adapter
    )

    with pytest.raises(
        TypeError,
        match="internal message failure",
    ):
        service.on_message(
            1001,
            "hello",
        )

    assert adapter.message_calls == 1


def test_v681_internal_bot_callback_typeerror_is_not_retried():

    adapter = _RaisingAdapter()
    service = TelegramBotService(
        adapter
    )

    with pytest.raises(
        TypeError,
        match="internal callback failure",
    ):
        service.on_callback(
            1001,
            "analyze",
        )

    assert adapter.callback_calls == 1


def test_v682_adapter_button_preserves_legacy_arity():

    handler = _LegacyButtonHandler()
    adapter = AssistantTelegramAdapter(
        _Assistant(),
        _Keyboard(),
        handler,
    )

    result = adapter.handle_button(
        "analyze",
        1001,
    )

    assert result["error"] is False
    assert handler.calls == 1


def test_v683_internal_button_typeerror_is_not_retried():

    handler = _RaisingButtonHandler()
    adapter = AssistantTelegramAdapter(
        _Assistant(),
        _Keyboard(),
        handler,
    )

    with pytest.raises(
        TypeError,
        match="internal button failure",
    ):
        adapter.handle_button(
            "analyze",
            1001,
        )

    assert handler.calls == 1


def test_v684_runner_start_preserves_legacy_arity():

    runner = TelegramRunner(
        _LegacyBot()
    )

    assert runner.start(
        1001
    ) == {
        "kind": "start",
    }


def test_v685_internal_runner_message_typeerror_is_not_retried():

    bot = _RaisingBot()
    runner = TelegramRunner(
        bot
    )

    with pytest.raises(
        TypeError,
        match="internal bot message failure",
    ):
        runner.receive_message(
            1001,
            "hello",
        )

    assert bot.message_calls == 1


def test_v686_internal_runner_callback_typeerror_is_not_retried():

    bot = _RaisingBot()
    runner = TelegramRunner(
        bot
    )

    with pytest.raises(
        TypeError,
        match="internal bot callback failure",
    ):
        runner.receive_callback(
            1001,
            "analyze",
        )

    assert bot.callback_calls == 1
