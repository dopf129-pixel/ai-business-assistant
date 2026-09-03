from services.assistant_entry_service import AssistantEntryService
from services.assistant_period_profit_runtime_service import (
    AssistantPeriodProfitRuntimeService,
)


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
