from services.assistant_entry_service import AssistantEntryService
from services.assistant_button_handler_service import AssistantButtonHandlerService
from services.assistant_keyboard_service import AssistantKeyboardService
from services.assistant_period_profit_runtime_service import (
    AssistantPeriodProfitRuntimeService,
)
from services.assistant_core_service import AssistantCoreService
from telegram_app_layer.assistant_telegram_adapter import AssistantTelegramAdapter
from telegram_app_layer.telegram_bot_service import TelegramBotService
from telegram_app_layer.telegram_response_formatter import TelegramResponseFormatter


class Query:
    def __init__(self):
        self.calls = []

    def query(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "error": False,
            "status": "PERIOD_PROFIT_QUERY_READY",
            "text": "ok",
            "read_only": True,
            "executed": False,
        }


class MainFlow:
    def __init__(self):
        self.calls = []

    def process(self, *args):
        self.calls.append(args)
        return {
            "error": False,
            "source": "main",
        }


class Provider:
    def build(self):
        return {}


class FinanceProvider:
    def build(self, data):
        return {}


def _service():
    query = Query()
    return AssistantPeriodProfitRuntimeService(query), query


def test_v1171_localized_custom_period_routes_as_iso():
    service, query = _service()

    result = service.handle_text(
        "прибыль 01.05.2026 - 03.09.2026"
    )

    assert result["error"] is False
    assert query.calls == [{
        "date_from": "2026-05-01",
        "date_to": "2026-09-03",
        "compare_previous": True,
        "today": None,
    }]


def test_v1172_localized_custom_period_accepts_en_dash():
    service, query = _service()

    service.handle_text(
        "прибыль 01.05.2026 – 03.09.2026"
    )

    assert query.calls[0]["date_from"] == "2026-05-01"
    assert query.calls[0]["date_to"] == "2026-09-03"


def test_v1173_localized_custom_period_accepts_em_dash():
    service, query = _service()

    service.handle_text(
        "прибыль 01.05.2026 — 03.09.2026"
    )

    assert query.calls[0]["date_from"] == "2026-05-01"
    assert query.calls[0]["date_to"] == "2026-09-03"


def test_v1174_localized_custom_period_accepts_single_digit_day_month():
    service, query = _service()

    service.handle_text(
        "прибыль 1.5.2026 - 3.9.2026"
    )

    assert query.calls[0]["date_from"] == "2026-05-01"
    assert query.calls[0]["date_to"] == "2026-09-03"


def test_v1175_existing_iso_custom_period_remains_supported():
    service, query = _service()

    service.handle_text(
        "прибыль 2026-05-01 - 2026-09-03"
    )

    assert query.calls[0]["date_from"] == "2026-05-01"
    assert query.calls[0]["date_to"] == "2026-09-03"


def test_v1176_mixed_supported_date_formats_normalize_consistently():
    service, query = _service()

    service.handle_text(
        "profit 01.05.2026 - 2026-09-03"
    )

    assert query.calls[0]["date_from"] == "2026-05-01"
    assert query.calls[0]["date_to"] == "2026-09-03"


def test_v1177_invalid_calendar_date_fails_closed_without_query():
    service, query = _service()

    result = service.handle_text(
        "прибыль 31.02.2026 - 03.09.2026"
    )

    assert result["error"] is True
    assert result["code"] == "PERIOD_PROFIT_CUSTOM_PERIOD_INVALID"
    assert result["read_only"] is True
    assert result["executed"] is False
    assert query.calls == []


def test_v1178_single_custom_date_fails_closed_without_query():
    service, query = _service()

    result = service.handle_text(
        "прибыль с 01.05.2026"
    )

    assert result["error"] is True
    assert result["code"] == "PERIOD_PROFIT_CUSTOM_PERIOD_INVALID"
    assert result["executed"] is False
    assert query.calls == []


def test_v1179_missing_period_prompt_uses_localized_date_example():
    service, _ = _service()

    result = service.handle_text(
        "покажи прибыль"
    )

    assert result["error"] is True
    assert result["code"] == "PERIOD_PROFIT_PERIOD_REQUIRED"
    assert "ДД.ММ.ГГГГ" in result["message"]
    assert "01.05.2026 - 03.09.2026" in result["message"]
    assert result["executed"] is False


def test_v1180_localized_period_bypasses_general_execution_flow():
    query = Query()
    runtime = AssistantPeriodProfitRuntimeService(query)
    main_flow = MainFlow()
    entry = AssistantEntryService(
        main_flow_service=main_flow,
        sales_context_provider=Provider(),
        stock_context_provider=Provider(),
        finance_context_provider=FinanceProvider(),
        period_profit_runtime_service=runtime,
    )

    result = entry.handle(
        "прибыль 01.05.2026 - 03.09.2026"
    )

    assert result["error"] is False
    assert result["read_only"] is True
    assert result["executed"] is False
    assert main_flow.calls == []
    assert query.calls[0]["date_from"] == "2026-05-01"
    assert query.calls[0]["date_to"] == "2026-09-03"


def test_period_profit_menu_exposes_custom_period_button():
    runtime, _query = _service()
    handler = AssistantButtonHandlerService(
        object(),
        keyboard_service=AssistantKeyboardService(),
        period_profit_runtime_service=runtime,
    )

    menu = handler.handle("period_profit", "seller-1")

    assert {
        "text": "📅 Указать период",
        "callback": "period_profit:custom",
    } in menu["keyboard"]["buttons"]


def test_custom_period_button_accepts_date_only_for_same_user():
    runtime, query = _service()
    handler = AssistantButtonHandlerService(
        object(),
        keyboard_service=AssistantKeyboardService(),
        period_profit_runtime_service=runtime,
    )

    prompt = handler.handle("period_profit:custom", "seller-1")
    unrelated = runtime.handle_text(
        "01.01.2026-02.02.2026", user_id="seller-2"
    )
    result = runtime.handle_text(
        "01.01.2026-02.02.2026", user_id="seller-1"
    )

    assert prompt["message"] == (
        "Введите период в формате 01.01.2026-02.02.2026"
    )
    assert unrelated is None
    assert result["error"] is False
    assert query.calls == [{
        "date_from": "2026-01-01",
        "date_to": "2026-02-02",
        "compare_previous": True,
        "today": None,
    }]


def test_general_period_prompt_replaces_abandoned_selected_sku_prompt():
    class SkuRuntime:
        def __init__(self):
            self.calls = []

        def handle_custom_period(self, *args):
            self.calls.append(args)
            return {
                "error": True,
                "code": "PERIOD_PROFIT_SKU_ADVERTISING_MAPPING_REQUIRED",
            }

    runtime, query = _service()
    sku_runtime = SkuRuntime()
    runtime.sku_runtime_service = sku_runtime

    runtime.begin_custom_sku_period("seller-1", "3921245627")
    runtime.begin_custom_period("seller-1")
    result = runtime.handle_text(
        "01.08.2026 - 31.08.2026",
        user_id="seller-1",
    )

    assert result["error"] is False
    assert result["text"] == "ok"
    assert query.calls == [{
        "date_from": "2026-08-01",
        "date_to": "2026-08-31",
        "compare_previous": True,
        "today": None,
    }]
    assert sku_runtime.calls == []


def test_selected_sku_prompt_replaces_abandoned_general_period_prompt():
    class SkuRuntime:
        def __init__(self):
            self.calls = []

        def handle_custom_period(self, *args):
            self.calls.append(args)
            return {
                "error": True,
                "code": "PERIOD_PROFIT_SKU_ADVERTISING_MAPPING_REQUIRED",
            }

    runtime, query = _service()
    sku_runtime = SkuRuntime()
    runtime.sku_runtime_service = sku_runtime

    runtime.begin_custom_period("seller-1")
    runtime.begin_custom_sku_period("seller-1", "3921245627")
    result = runtime.handle_text(
        "01.08.2026 - 31.08.2026",
        user_id="seller-1",
    )

    assert result["code"] == "PERIOD_PROFIT_SKU_ADVERTISING_MAPPING_REQUIRED"
    assert sku_runtime.calls == [(
        "3921245627",
        "2026-08-01",
        "2026-08-31",
    )]
    assert query.calls == []


def test_general_custom_button_navigation_replaces_pending_sku_prompt():
    class SkuRuntime:
        def __init__(self):
            self.calls = []

        def handle_custom_period(self, *args):
            self.calls.append(args)
            return {"error": True, "code": "SKU_PATH_USED"}

        def open_sku_menu(self):
            return {"error": False, "message": "Выберите SKU"}

    runtime, query = _service()
    sku_runtime = SkuRuntime()
    runtime.sku_runtime_service = sku_runtime
    handler = AssistantButtonHandlerService(
        object(),
        keyboard_service=AssistantKeyboardService(),
        period_profit_runtime_service=runtime,
        period_profit_sku_runtime_service=sku_runtime,
    )

    handler.handle("period_profit_sku:3921245627:custom", "seller-1")
    handler.handle("period_profit", "seller-1")
    handler.handle("period_profit:custom", "seller-1")
    result = runtime.handle_text(
        "01.08.2026 - 31.08.2026",
        user_id="seller-1",
    )

    assert result["error"] is False
    assert query.calls == [{
        "date_from": "2026-08-01",
        "date_to": "2026-08-31",
        "compare_previous": True,
        "today": None,
    }]
    assert sku_runtime.calls == []


def test_bot_general_period_dates_stay_on_general_path_after_sku_flow():
    class SkuRuntime:
        def __init__(self):
            self.calls = []

        def handle_custom_period(self, *args):
            self.calls.append(args)
            return {"error": True, "code": "SKU_PATH_USED"}

        def open_sku_menu(self):
            return {"error": False, "message": "Выберите SKU"}

    class Orchestrator:
        def __init__(self, entry):
            self.entry = entry

        def process(self, text, context, user_id):
            return self.entry.handle(text, context, user_id)

    class Profiles:
        def create_user(self, user_id):
            return {"error": False, "user": {"user_id": str(user_id)}}

    runtime, query = _service()
    sku_runtime = SkuRuntime()
    runtime.sku_runtime_service = sku_runtime
    keyboard = AssistantKeyboardService()
    handler = AssistantButtonHandlerService(
        object(),
        keyboard_service=keyboard,
        period_profit_runtime_service=runtime,
        period_profit_sku_runtime_service=sku_runtime,
    )
    entry = AssistantEntryService(
        main_flow_service=MainFlow(),
        sales_context_provider=Provider(),
        stock_context_provider=Provider(),
        finance_context_provider=FinanceProvider(),
        period_profit_runtime_service=runtime,
    )
    core = AssistantCoreService(Orchestrator(entry))
    adapter = AssistantTelegramAdapter(
        core,
        keyboard,
        handler,
        Profiles(),
    )
    bot = TelegramBotService(adapter)

    bot.on_callback(
        "seller-1", "period_profit_sku:3921245627:custom"
    )
    bot.on_callback("seller-1", "period_profit")
    bot.on_callback("seller-1", "period_profit:custom")
    result = bot.on_message("seller-1", "01.08.2026 - 31.08.2026")

    assert result["error"] is False
    assert TelegramResponseFormatter().format(result) == "ok"
    assert query.calls == [{
        "date_from": "2026-08-01",
        "date_to": "2026-08-31",
        "compare_previous": True,
        "today": None,
    }]
    assert sku_runtime.calls == []


def test_invalid_custom_period_keeps_prompt_active_until_valid_input():
    runtime, query = _service()
    runtime.begin_custom_period("seller-1")

    invalid_format = runtime.handle_text(
        "2026-01-01 - 2026-02-02", user_id="seller-1"
    )
    invalid_date = runtime.handle_text(
        "31.02.2026-02.03.2026", user_id="seller-1"
    )
    valid = runtime.handle_text(
        "01.02.2026-02.03.2026", user_id="seller-1"
    )

    assert invalid_format["code"] == "PERIOD_PROFIT_CUSTOM_PERIOD_INPUT_INVALID"
    assert invalid_date["code"] == "PERIOD_PROFIT_CUSTOM_PERIOD_INPUT_INVALID"
    assert valid["error"] is False
    assert len(query.calls) == 1


def test_custom_period_pending_state_can_be_cancelled_per_user():
    runtime, query = _service()
    runtime.begin_custom_period("seller-1")

    cancelled = runtime.handle_text("отмена", user_id="seller-1")
    after_cancel = runtime.handle_text(
        "01.01.2026-02.02.2026", user_id="seller-1"
    )

    assert cancelled["status"] == "PERIOD_PROFIT_CUSTOM_PERIOD_CANCELLED"
    assert after_cancel is None
    assert query.calls == []
