from telegram_app_layer.assistant_telegram_adapter import (
    AssistantTelegramAdapter,
)


class _Assistant:

    def __init__(
        self,
        result,
    ):
        self.result = result
        self.calls = 0

    def ask(
        self,
        text,
        user_id=None,
    ):
        self.calls += 1
        return self.result


class _Keyboard:

    def build_main_keyboard(
        self,
    ):
        return {
            "buttons": [],
        }


class _Button:

    def __init__(
        self,
        result,
    ):
        self.result = result
        self.calls = 0

    def handle(
        self,
        callback,
        user_id=None,
    ):
        self.calls += 1
        return self.result


class _MemoryCommand:

    def handle(
        self,
        user_id,
        text,
    ):
        return {
            "error": False,
            "handled": False,
        }


def _adapter(
    assistant_result=None,
    button_result=None,
):

    return AssistantTelegramAdapter(
        _Assistant(
            (
                {
                    "error": False,
                    "message": "ok",
                }
                if assistant_result is None
                else assistant_result
            )
        ),
        _Keyboard(),
        _Button(
            (
                {
                    "error": False,
                    "message": "button",
                }
                if button_result is None
                else button_result
            )
        ),
        memory_command_service=(
            _MemoryCommand()
        ),
    )


def test_v706_malformed_assistant_result_fails_closed():

    for malformed in (
        None,
        [],
        {},
        {
            "message": "ok",
        },
        {
            "error": "false",
            "message": "ok",
        },
    ):

        adapter = _adapter(
            assistant_result=malformed
        )

        result = adapter.handle_text(
            "hello"
        )

        assert result == {
            "error": True,
            "message":
                "INVALID_TELEGRAM_ASSISTANT_RESULT",
        }


def test_v707_explicit_assistant_failure_is_preserved():

    failure = {
        "error": True,
        "message":
            "ASSISTANT_DOWNSTREAM_FAILED",
        "details": {
            "safe": True,
        },
    }
    adapter = _adapter(
        assistant_result=failure
    )

    result = adapter.handle_text(
        "hello"
    )

    assert result is failure


def test_v708_valid_assistant_success_is_preserved():

    success = {
        "error": False,
        "message": "assistant ok",
        "actions": [],
    }
    adapter = _adapter(
        assistant_result=success
    )

    result = adapter.handle_text(
        "hello"
    )

    assert result is success


def test_v709_malformed_button_result_fails_closed():

    for malformed in (
        None,
        [],
        {},
        {
            "message": "button",
        },
        {
            "error": 0,
            "message": "button",
        },
    ):

        adapter = _adapter(
            button_result=malformed
        )

        result = adapter.handle_button(
            "analyze"
        )

        assert result == {
            "error": True,
            "message":
                "INVALID_TELEGRAM_BUTTON_RESULT",
        }


def test_v710_explicit_button_failure_is_preserved():

    failure = {
        "error": True,
        "message":
            "BUTTON_DOWNSTREAM_FAILED",
    }
    adapter = _adapter(
        button_result=failure
    )

    result = adapter.handle_button(
        "analyze"
    )

    assert result is failure


def test_v711_button_failure_is_not_freshness_enriched():

    failure = {
        "error": True,
        "message": "draft unavailable",
        "readiness_summary": {
            "freshness_counts": {
                "FRESH": 99,
            },
        },
    }
    adapter = _adapter(
        button_result=failure
    )

    result = adapter.handle_button(
        "product_action_task_drafts"
    )

    assert result is failure
    assert result[
        "message"
    ] == "draft unavailable"


def test_v712_valid_draft_button_success_keeps_freshness_enrichment():

    success = {
        "error": False,
        "message": "Черновики",
        "readiness_summary": {
            "freshness_counts": {
                "FRESH": 1,
                "STALE": 2,
                "UNKNOWN": 3,
            },
        },
    }
    adapter = _adapter(
        button_result=success
    )

    result = adapter.handle_button(
        "product_action_task_drafts"
    )

    assert result["error"] is False
    assert "Свежесть данных:" in result[
        "message"
    ]
    assert "Свежие: 1" in result[
        "message"
    ]


def test_v713_runtime_validation_does_not_rewrite_valid_payload():

    payload = {
        "error": False,
        "message": "same",
        "custom": {
            "value": 1,
        },
    }

    result = (
        AssistantTelegramAdapter
        ._validated_runtime_result(
            payload,
            "INVALID",
        )
    )

    assert result is payload
