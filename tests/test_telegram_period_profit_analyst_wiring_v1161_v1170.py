import telegram_core_factory as core_factory

from services.assistant_button_handler_service import (
    AssistantButtonHandlerService,
)
from services.assistant_keyboard_service import (
    AssistantKeyboardService,
)
from telegram_app_layer.telegram_response_formatter import (
    TelegramResponseFormatter,
)


class Runtime:
    def __init__(self, result=None, raises=False):
        self.result = result
        self.raises = raises
        self.calls = []

    def handle_callback(self, callback):
        self.calls.append(callback)
        if self.raises:
            raise RuntimeError("secret")
        return self.result


class Query:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def query(self, **kwargs):
        self.calls.append(kwargs)
        return dict(self.result)


def _handler(runtime):
    return AssistantButtonHandlerService(
        assistant=object(),
        keyboard_service=AssistantKeyboardService(),
        period_profit_runtime_service=runtime,
    )


def _ready_result(text="Прибыль за период"):
    return {
        "error": False,
        "status": "PERIOD_PROFIT_QUERY_READY",
        "text": text,
        "read_only": True,
        "executed": False,
    }


def test_v1161_main_keyboard_exposes_period_profit_analytics():
    keyboard = AssistantKeyboardService().build_main_keyboard()

    callbacks = [
        item["callback"]
        for item in keyboard["buttons"]
    ]

    assert "period_profit" in callbacks


def test_v1162_period_profit_keyboard_preserves_safe_callbacks():
    keyboard = AssistantKeyboardService().build_period_profit_keyboard([
        {
            "text": "28 дней",
            "callback_data": "period_profit:28D",
        }
    ])

    assert keyboard == {
        "error": False,
        "type": "inline_keyboard",
        "buttons": [{
            "text": "28 дней",
            "callback": "period_profit:28D",
        }],
    }


def test_v1163_period_profit_menu_is_read_only_and_non_executing():
    result = _handler(Runtime()).handle("period_profit")

    assert result["error"] is False
    assert result["read_only"] is True
    assert result["executed"] is False
    assert [
        item["callback"]
        for item in result["keyboard"]["buttons"]
    ] == [
        "period_profit:TODAY",
        "period_profit:7D",
        "period_profit:28D",
        "period_profit:56D",
        "period_profit:90D",
    ]


def test_v1164_period_profit_callback_delegates_to_read_only_runtime():
    runtime = Runtime(_ready_result("28 дней"))
    result = _handler(runtime).handle("period_profit:28D")

    assert runtime.calls == ["period_profit:28D"]
    assert result["text"] == "28 дней"
    assert result["read_only"] is True
    assert result["executed"] is False


def test_v1165_period_profit_callback_contains_runtime_exception():
    result = _handler(
        Runtime(raises=True)
    ).handle("period_profit:28D")

    assert result == {
        "error": True,
        "message": "PERIOD_PROFIT_TELEGRAM_QUERY_FAILED",
        "executed": False,
    }


def test_v1166_period_profit_callback_rejects_malformed_result():
    result = _handler(
        Runtime({"status": "PERIOD_PROFIT_QUERY_READY"})
    ).handle("period_profit:28D")

    assert result["error"] is True
    assert result["message"] == "INVALID_PERIOD_PROFIT_TELEGRAM_RESULT"
    assert result["executed"] is False


def test_v1167_period_profit_callback_rejects_execution_adjacent_success():
    unsafe = _ready_result()
    unsafe["read_only"] = False
    unsafe["executed"] = True

    result = _handler(
        Runtime(unsafe)
    ).handle("period_profit:28D")

    assert result["error"] is True
    assert result["message"] == "INVALID_PERIOD_PROFIT_TELEGRAM_RESULT"
    assert result["executed"] is False


def test_v1168_telegram_formatter_renders_analytical_text():
    result = _ready_result("Чистый аналитический ответ")

    assert (
        TelegramResponseFormatter().format(result)
        == "Чистый аналитический ответ"
    )


def test_v1169_telegram_core_wires_period_profit_runtime(monkeypatch):
    registry = object()
    query = Query(_ready_result())

    monkeypatch.setattr(
        core_factory,
        "create_period_profit_mapping_registry",
        lambda: registry,
    )
    monkeypatch.setattr(
        core_factory,
        "create_period_profit_query",
        lambda mapping_registry=None: (
            query
            if mapping_registry is registry
            else None
        ),
    )

    system = core_factory.create_telegram_core()

    runtime = system["period_profit_runtime_service"]
    entry = (
        system["core"]
        .orchestrator_service
        .entry_service
    )

    assert system["period_profit_query"] is query
    assert runtime.query_service is query
    assert entry.period_profit_runtime_service is runtime


def test_v1170_natural_language_profit_query_bypasses_execution_flow(monkeypatch):
    registry = object()
    query = Query(_ready_result("Прибыль за 7 дней"))

    monkeypatch.setattr(
        core_factory,
        "create_period_profit_mapping_registry",
        lambda: registry,
    )
    monkeypatch.setattr(
        core_factory,
        "create_period_profit_query",
        lambda mapping_registry=None: query,
    )

    system = core_factory.create_telegram_core()
    entry = (
        system["core"]
        .orchestrator_service
        .entry_service
    )

    result = entry.handle("прибыль за 7 дней")

    assert result["error"] is False
    assert result["read_only"] is True
    assert result["executed"] is False
    assert query.calls == [{
        "period_code": "7D",
        "compare_previous": True,
        "today": None,
    }]
