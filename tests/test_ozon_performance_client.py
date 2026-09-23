from api.ozon_performance_client import OzonPerformanceClient


class _Response:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def json(self):
        return self.payload


class _Session:
    def __init__(self):
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if url.endswith("/api/client/token"):
            return _Response({"access_token": "token", "expires_in": 1800})
        return _Response({"rows": []})


def test_token_is_cached_and_each_period_uses_one_statistics_call():
    session = _Session()
    client = OzonPerformanceClient("client", "secret", session=session)

    assert client.get_sku_expenses("2026-09-01", "2026-09-30") == {"rows": []}
    assert client.get_sku_expenses("2026-08-01", "2026-08-31") == {"rows": []}

    assert len(session.calls) == 3
    assert sum(url.endswith("/api/client/token") for url, _ in session.calls) == 1
    statistic_calls = [call for call in session.calls if call[0].endswith("/statistics/products/sku")]
    assert len(statistic_calls) == 2
    assert statistic_calls[0][1]["json"] == {
        "campaignIds": [],
        "dateFrom": "2026-09-01",
        "dateTo": "2026-09-30",
    }
