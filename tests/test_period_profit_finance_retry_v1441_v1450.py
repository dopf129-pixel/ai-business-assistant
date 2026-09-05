from api.ozon_client import OzonClient
from api.period_profit_ozon_client import PeriodProfitOzonClient


def test_reported_finance_day_retries_transient_503(monkeypatch):
    calls = []
    responses = [
        {"error": True, "status_code": 503, "message": "temporary"},
        {"error": False, "accruals": [], "last_id": ""},
    ]

    def fake_post(self, endpoint, data, timeout=20, max_attempts=3):
        calls.append((endpoint, data.get("date")))
        return responses.pop(0)

    monkeypatch.setattr(OzonClient, "_post", fake_post)
    monkeypatch.setattr("api.period_profit_ozon_client.time.sleep", lambda _: None)

    client = PeriodProfitOzonClient()
    result = client._post(
        "/v1/finance/accrual/by-day",
        {"date": "2026-08-30", "last_id": ""},
        timeout=30,
        max_attempts=3,
    )

    assert result == {"error": False, "accruals": [], "last_id": ""}
    assert calls == [
        ("/v1/finance/accrual/by-day", "2026-08-30"),
        ("/v1/finance/accrual/by-day", "2026-08-30"),
    ]


def test_transient_finance_failure_remains_unknown_after_retry_budget(monkeypatch):
    calls = []

    def fake_post(self, endpoint, data, timeout=20, max_attempts=3):
        calls.append(data.get("date"))
        return {"error": True, "status_code": 503, "message": "temporary"}

    monkeypatch.setattr(OzonClient, "_post", fake_post)
    monkeypatch.setattr("api.period_profit_ozon_client.time.sleep", lambda _: None)

    client = PeriodProfitOzonClient()
    result = client._post(
        "/v1/finance/accrual/by-day",
        {"date": "2026-08-30", "last_id": ""},
        max_attempts=3,
    )

    assert result["error"] is True
    assert result["status_code"] == 503
    assert calls == ["2026-08-30", "2026-08-30", "2026-08-30"]


def test_non_transient_finance_error_is_not_reinterpreted_as_zero(monkeypatch):
    calls = []

    def fake_post(self, endpoint, data, timeout=20, max_attempts=3):
        calls.append(data.get("date"))
        return {"error": True, "status_code": 400, "message": "bad request"}

    monkeypatch.setattr(OzonClient, "_post", fake_post)

    client = PeriodProfitOzonClient()
    result = client._post(
        "/v1/finance/accrual/by-day",
        {"date": "2026-08-30", "last_id": ""},
        max_attempts=3,
    )

    assert result == {"error": True, "status_code": 400, "message": "bad request"}
    assert calls == ["2026-08-30"]
