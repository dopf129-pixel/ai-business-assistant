import json
import threading
from datetime import datetime, timezone

import pytest
import requests

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


def test_public_trace_summary_bounds_events_and_omits_raw_identifiers():
    class _Clock:
        now = 100.0

        def __call__(self):
            return self.now

    clock = _Clock()
    trace = PeriodProfitOperationTrace(
        "period_profit",
        clock=clock,
        utc_clock=lambda: datetime(2026, 10, 17, tzinfo=timezone.utc),
    )
    trace.update(
        "sku_probe",
        finance_sku="private-sku-123",
        catalog_sku="private-catalog-456",
        posting_number="private-posting-789",
        endpoint="/private?api_key=secret",
    )
    for index in range(300):
        trace.update("stage_" + str(index))

    summary = trace.public_summary()
    rendered = json.dumps(summary)

    assert len(trace.events) == trace.MAX_EVENTS == 256
    assert summary["events_total"] == 301
    assert summary["events_dropped"] == 45
    assert summary["operation_id"] == trace.operation_id
    assert summary["started_at_utc"] == "2026-10-17T00:00:00Z"
    assert summary["http_attempts"] == 0
    assert summary["rows_attempted"] == 0
    assert "private-sku-123" not in rendered
    assert "private-catalog-456" not in rendered
    assert "private-posting-789" not in rendered
    assert "api_key" not in rendered


def test_public_trace_summary_aggregates_child_attempts_and_posting_outcomes():
    parent = PeriodProfitOperationTrace(ozon_request_budget=1)
    child = PeriodProfitOperationTrace(parent=parent)

    child.record_posting("posting-secret")
    child.record_posting_result("completed")
    child.record_posting("posting-secret-2")
    child.record_posting_result("not-an-allowed-status")
    assert child.reserve_ozon_request("/safe") ["error"] is False
    assert child.reserve_ozon_request("/safe") ["code"] == (
        "OZON_OPERATION_API_CALL_BUDGET_EXHAUSTED"
    )

    summary = parent.public_summary()
    assert summary["http_attempts"] == 1
    assert summary["http_attempt_cap"] == 1
    assert summary["rows_attempted"] == 2
    assert summary["rows_completed"] == 1
    assert summary["rows_unknown"] == 1
    assert summary["budget_reason_code"] == "HTTP_ATTEMPT_BUDGET_EXHAUSTED"
    assert summary["events_total"] == parent.total_events
    assert "posting-secret" not in json.dumps(summary)


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


def test_child_trace_inherits_parent_deadline_and_shared_request_budget():
    class _Clock:
        now = 10.0

        def __call__(self):
            return self.now

    clock = _Clock()
    parent = PeriodProfitOperationTrace(
        "price_batch",
        time_budget_seconds=5,
        ozon_request_budget=5,
        clock=clock,
    )
    first = parent.reserve_ozon_request("/parent")
    child = PeriodProfitOperationTrace(
        "price_batch_row",
        time_budget_seconds=60,
        ozon_request_budget=64,
        parent=parent,
    )

    assert first["error"] is False
    assert child.remaining_seconds() == 5
    reserved = child.reserve_ozon_request("/child")
    assert reserved["error"] is False
    assert reserved["ozon_requests_reserved"] == 1
    assert reserved["operation_ozon_requests_reserved"] == 2
    assert parent.ozon_requests_reserved == 2

    clock.now = 14
    assert child.remaining_seconds() == 1
    clock.now = 15
    assert child.reserve_ozon_request("/after-deadline")["code"] == (
        "OZON_OPERATION_TIME_BUDGET_EXHAUSTED"
    )


def test_concurrent_child_reservations_cannot_exceed_parent_attempt_cap():
    from threading import Barrier, Lock, Thread

    parent = PeriodProfitOperationTrace(
        "price_batch",
        time_budget_seconds=30,
        ozon_request_budget=5,
    )
    for index in range(4):
        assert parent.reserve_ozon_request(f"/used/{index}")["error"] is False
    children = [
        PeriodProfitOperationTrace(
            f"row-{index}",
            time_budget_seconds=30,
            ozon_request_budget=64,
            parent=parent,
        )
        for index in range(2)
    ]
    barrier = Barrier(3)
    result_lock = Lock()
    results = []

    def reserve(trace):
        barrier.wait()
        result = trace.reserve_ozon_request("/race")
        with result_lock:
            results.append(result)

    threads = [Thread(target=reserve, args=(trace,)) for trace in children]
    for thread in threads:
        thread.start()
    barrier.wait()
    for thread in threads:
        thread.join(timeout=3)

    assert all(not thread.is_alive() for thread in threads)
    assert parent.ozon_requests_reserved == 5
    assert sum(result["error"] is False for result in results) == 1
    assert sum(
        result.get("code") == "OZON_OPERATION_API_CALL_BUDGET_EXHAUSTED"
        for result in results
    ) == 1


def test_child_cancellation_is_scoped_and_parent_cancellation_reaches_children():
    parent = PeriodProfitOperationTrace(
        "price_batch", time_budget_seconds=30, ozon_request_budget=5
    )
    child = PeriodProfitOperationTrace(
        "row", time_budget_seconds=20, ozon_request_budget=3, parent=parent
    )
    child.cancel()

    assert child.is_cancelled() is True
    assert parent.is_cancelled() is False
    assert child.reserve_ozon_request("/cancelled")["code"] == (
        "OZON_OPERATION_CANCELLED"
    )
    assert parent.reserve_ozon_request("/other-row")["error"] is False

    parent.cancel()
    sibling = PeriodProfitOperationTrace(
        "sibling", time_budget_seconds=30, ozon_request_budget=64, parent=parent
    )
    assert sibling.is_cancelled() is True
    assert sibling.reserve_ozon_request("/also-cancelled")["code"] == (
        "OZON_OPERATION_CANCELLED"
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


@pytest.mark.parametrize(
    ("failure", "expected_code"),
    [
        ("http_429", "OZON_RATE_LIMITED"),
        ("timeout", "OZON_API_TIMEOUT"),
    ],
)
def test_http_failure_trace_keeps_exact_attempt_and_excludes_private_details(
    monkeypatch, failure, expected_code
):
    class _Response:
        status_code = 429
        headers = {}

    class _Client(OzonClient):
        def __init__(self):
            self.base_url = "https://example.invalid"
            self.client_id = "private-client-id"
            self.api_key = "private-api-key"

    def post(*_args, **_kwargs):
        if failure == "timeout":
            raise requests.exceptions.Timeout("private timeout detail")
        return _Response()

    monkeypatch.setattr("api.base_ozon_client.requests.post", post)
    trace = PeriodProfitOperationTrace(
        "period_profit", time_budget_seconds=30, ozon_request_budget=4
    )
    token = activate_period_profit_trace(trace)
    try:
        result = _Client()._post(
            "/private?token=private-token", {}, max_attempts=1
        )
        public = trace.public_summary()
    finally:
        reset_period_profit_trace(token)

    assert result["code"] == expected_code
    assert public["http_attempts"] == 1
    assert public["http_attempt_cap"] == 4
    assert public["events_total"] == 1
    serialized = json.dumps(public)
    for secret in (
        "private-client-id",
        "private-api-key",
        "private-token",
        "private timeout detail",
        "example.invalid",
    ):
        assert secret not in serialized


def test_http_client_uses_parent_cap_inside_nested_source_trace(monkeypatch):
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

    parent = PeriodProfitOperationTrace(
        "price_batch", time_budget_seconds=10, ozon_request_budget=1
    )
    child = PeriodProfitOperationTrace(
        "price_batch_row",
        time_budget_seconds=60,
        ozon_request_budget=64,
        parent=parent,
    )
    requests_seen = []

    def post(*_args, **_kwargs):
        requests_seen.append(True)
        return _Response()

    monkeypatch.setattr("api.base_ozon_client.requests.post", post)
    token = activate_period_profit_trace(child)
    try:
        first = _Client()._post("/first", {}, max_attempts=1)
        second = _Client()._post("/second", {}, max_attempts=1)
    finally:
        reset_period_profit_trace(token)

    assert first == {"ok": True}
    assert second["code"] == "OZON_OPERATION_API_CALL_BUDGET_EXHAUSTED"
    assert len(requests_seen) == 1
    assert parent.ozon_requests_reserved == 1
    assert child.ozon_requests_reserved == 1
