import json
import threading

from api.base_ozon_client import OzonClient
from services.period_profit_operation_diagnostics import (
    PeriodProfitOperationTrace,
    activate_period_profit_trace,
    reset_period_profit_trace,
)


def test_long_running_trace_writes_secret_free_worker_snapshot(tmp_path):
    trace = PeriodProfitOperationTrace("selected_sku_profit")
    trace.worker_thread_id = threading.get_ident()
    trace.update(
        "posting_identity_probe",
        service="IdentityScope",
        method="recover",
        finance_sku="finance-1",
        catalog_sku="catalog-1",
        endpoint="/v2/posting/fbo/get",
    )
    trace.record_identity_stage(
        "finance_posting",
        sample_count=501,
        record_count=501,
        candidate_count=0,
        status="no_match",
        api_key="must-not-be-recorded",
    )
    target = tmp_path / "diagnostics.log"

    trace.dump_worker_stack(log_path=target)

    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["stage"] == "selected_identity_finance_posting"
    assert payload["finance_sku"] == "finance-1"
    assert payload["catalog_sku"] == "catalog-1"
    assert payload["identity_diagnostics"] == {
        "finance_posting": {
            "sample_count": 501,
            "record_count": 501,
            "candidate_count": 0,
            "status": "no_match",
        }
    }
    assert payload["worker_stack"]
    assert "api_key" not in target.read_text(encoding="utf-8").lower()


def test_trace_enforces_cooperative_time_and_api_request_budgets():
    class _Clock:
        now = 10.0

        def __call__(self):
            return self.now

    clock = _Clock()
    trace = PeriodProfitOperationTrace(
        "period_profit",
        time_budget_seconds=5,
        ozon_request_budget=1,
        clock=clock,
    )

    assert trace.reserve_ozon_request("/first")["remaining_seconds"] == 5
    assert trace.reserve_ozon_request("/second")["code"] == (
        "OZON_OPERATION_API_CALL_BUDGET_EXHAUSTED"
    )
    clock.now = 16
    assert trace.reserve_ozon_request("/third")["code"] == (
        "OZON_OPERATION_TIME_BUDGET_EXHAUSTED"
    )


def test_ozon_request_uses_remaining_operation_budget_and_stops_at_call_limit(
    monkeypatch,
):
    class _Clock:
        now = 10.0

        def __call__(self):
            return self.now

    class _Response:
        status_code = 200
        headers = {}

        @staticmethod
        def raise_for_status():
            return None

        @staticmethod
        def json():
            return {"ok": True}

    class _Client(OzonClient):
        def __init__(self):
            self.base_url = "https://example.invalid"
            self.client_id = "client"
            self.api_key = "key"

    clock = _Clock()
    trace = PeriodProfitOperationTrace(
        "period_profit",
        time_budget_seconds=5,
        ozon_request_budget=1,
        clock=clock,
    )
    observed_timeouts = []

    def post(_url, headers, json, timeout):
        assert headers["Client-Id"] == "client"
        assert json == {}
        observed_timeouts.append(timeout)
        return _Response()

    monkeypatch.setattr("api.base_ozon_client.time.monotonic", lambda: 100.0)
    monkeypatch.setattr("api.base_ozon_client.requests.post", post)
    token = activate_period_profit_trace(trace)
    try:
        first = _Client()._post("/first", {}, timeout=30, max_attempts=1)
        clock.now = 14.5
        second = _Client()._post("/second", {}, timeout=30, max_attempts=1)
    finally:
        reset_period_profit_trace(token)

    assert first == {"ok": True}
    assert observed_timeouts == [5.0]
    assert second["code"] == "OZON_OPERATION_API_CALL_BUDGET_EXHAUSTED"
