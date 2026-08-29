from services.assistant_entry_service import AssistantEntryService


class _Runtime:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def handle_text(self, text):
        self.calls.append(text)
        return self.result


class _MainFlow:
    def __init__(self):
        self.called = False

    def process(self, text, report, context, user_id):
        self.called = True
        return {"fallback": True}


class _Provider:
    def build(self):
        return None


def _entry(runtime=None):
    main = _MainFlow()
    entry = AssistantEntryService(
        main_flow_service=main,
        sales_context_provider=_Provider(),
        stock_context_provider=_Provider(),
        finance_context_provider=_Provider(),
        freshness_operational_runtime_service=runtime,
    )
    return entry, main


def test_entry_returns_freshness_runtime_result_before_general_flow():
    runtime = _Runtime({"status": "FRESHNESS_OPERATIONAL_READINESS_SUMMARY", "read_only": True})
    entry, main = _entry(runtime)
    result = entry.handle("статус свежести")
    assert result["status"] == "FRESHNESS_OPERATIONAL_READINESS_SUMMARY"
    assert runtime.calls == ["статус свежести"]
    assert main.called is False


def test_entry_preserves_fallback_when_freshness_runtime_does_not_match():
    runtime = _Runtime(None)
    entry, main = _entry(runtime)
    result = entry.handle("обычный вопрос")
    assert result == {"fallback": True}
    assert main.called is True


def test_entry_is_backward_compatible_without_freshness_runtime():
    entry, main = _entry(None)
    result = entry.handle("обычный вопрос")
    assert result == {"fallback": True}
    assert main.called is True
