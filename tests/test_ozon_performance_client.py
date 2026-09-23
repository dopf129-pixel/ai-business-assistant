from api.ozon_performance_client import OzonPerformanceClient


class _Response:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def json(self):
        return self.payload


class _Session:
    def __init__(self, failures=None):
        self.calls = []
        self.failures = failures or {}

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if url.endswith("/api/client/token"):
            return _Response({"access_token": "token", "expires_in": 1800})
        dates = (kwargs["json"]["dateFrom"], kwargs["json"]["dateTo"])
        if dates in self.failures:
            return _Response({"message": "private"}, self.failures[dates])
        return _Response({"rows": [{"sku": "101", "expense": "2", "campaignId": dates[0]}]})


def _statistics(session):
    return [call for call in session.calls if call[0].endswith("/statistics/products/sku")]


def test_token_cached_and_month_uses_one_statistics_call():
    session = _Session()
    client = OzonPerformanceClient("client", "secret", session=session)
    assert len(client.get_sku_expenses("2026-09-01", "2026-09-30")["rows"]) == 1
    assert len(client.get_sku_expenses("2026-08-01", "2026-08-30")["rows"]) == 1
    assert sum(url.endswith("/api/client/token") for url, _ in session.calls) == 1
    assert len(_statistics(session)) == 2
    assert _statistics(session)[0][1]["json"] == {
        "campaignIds": [], "dateFrom": "2026-09-01", "dateTo": "2026-09-30"
    }


def test_long_period_is_partitioned_without_gaps_or_overlaps():
    session = _Session()
    result = OzonPerformanceClient("client", "secret", session=session).get_sku_expenses(
        "2026-05-03", "2026-09-23"
    )
    calls = _statistics(session)
    assert len(calls) == 5
    assert result["external_call_count"] == 5
    assert len(result["rows"]) == 5
    from datetime import date, timedelta
    windows = [(date.fromisoformat(x[1]["json"]["dateFrom"]),
                date.fromisoformat(x[1]["json"]["dateTo"])) for x in calls]
    assert windows[0][0] == date(2026, 5, 3)
    assert windows[-1][1] == date(2026, 9, 23)
    assert all((end - start).days < 30 for start, end in windows)
    assert all(windows[i][1] + timedelta(days=1) == windows[i+1][0]
               for i in range(len(windows)-1))


def test_failed_window_returns_error_without_partial_rows_or_private_body():
    session = _Session({("2026-06-02", "2026-07-01"): 400})
    result = OzonPerformanceClient("client", "secret", session=session).get_sku_expenses(
        "2026-05-03", "2026-07-01"
    )
    assert result == {"error": True, "code": "OZON_PERFORMANCE_HISTORICAL_SKU_UNAVAILABLE",
                      "status_code": 400, "failed_window_from": "2026-06-02",
                      "failed_window_to": "2026-07-01"}
    assert len(_statistics(session)) == 2


def test_invalid_dates_do_not_make_requests():
    session = _Session()
    client = OzonPerformanceClient("client", "secret", session=session)
    assert client.get_sku_expenses("2026-09-30", "2026-09-01")["error"] is True
    assert client.get_sku_expenses("invalid", "2026-09-01")["error"] is True
    assert session.calls == []
