from services.assistant_entry_service import AssistantEntryService


class Runtime:
    def __init__(self, result): self.result = result; self.calls = []
    def handle_text(self, text):
        self.calls.append(text)
        return self.result


class MainFlow:
    def __init__(self): self.calls = []
    def process(self, *args):
        self.calls.append(args)
        return {"source": "main"}


class Provider:
    def build(self): return {}


class FinanceProvider:
    def build(self, data): return {}


def _entry(runtime):
    return AssistantEntryService(
        main_flow_service=MainFlow(),
        sales_context_provider=Provider(),
        stock_context_provider=Provider(),
        finance_context_provider=FinanceProvider(),
        period_profit_runtime_service=runtime,
    )


def test_profit_direct_route_bypasses_general_business_flow():
    runtime = Runtime({"error": False, "status": "PERIOD_PROFIT_QUERY_READY", "read_only": True, "executed": False})
    entry = _entry(runtime)
    result = entry.handle("прибыль за 7 дней")
    assert result["status"] == "PERIOD_PROFIT_QUERY_READY"
    assert entry.main_flow_service.calls == []


def test_non_profit_request_falls_through_to_existing_flow():
    runtime = Runtime(None)
    entry = _entry(runtime)
    result = entry.handle("что с остатками?")
    assert result == {"source": "main"}
    assert len(entry.main_flow_service.calls) == 1
