from api.base_ozon_client import OzonClient
from api.ozon_client import OzonClient as TenantOzonClient


class _Response:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self.headers = {"Retry-After": "0"}
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def test_returns_request_observer_counts_actual_http_retries(monkeypatch):
    responses = iter(
        [
            _Response(429, {"error": True}),
            _Response(
                200,
                {"error": False, "returns": [], "has_next": False},
            ),
        ]
    )
    requests_seen = []
    observed_attempts = []

    def post(url, headers, json, timeout):
        requests_seen.append((url, json, timeout))
        return next(responses)

    monkeypatch.setattr("api.base_ozon_client.requests.post", post)
    client = OzonClient()
    client.client_id = "test-client"
    client.api_key = "test-key"

    result = client.get_returns(
        return_schema="FBO",
        since="2026-08-01",
        to="2026-08-31",
        limit=500,
        last_id=0,
        timeout=1,
        max_attempts=2,
        total_timeout=5,
        request_attempt_observer=observed_attempts.append,
    )

    assert result == {"error": False, "returns": [], "has_next": False}
    assert len(requests_seen) == 2
    assert observed_attempts == ["/v1/returns/list", "/v1/returns/list"]
    assert requests_seen[0][0].endswith("/v1/returns/list")
    assert requests_seen[0][1]["filter"]["return_schema"] == "FBO"
    assert requests_seen[0][1]["limit"] == 500
    assert requests_seen[0][1]["last_id"] == 0


def test_analytics_request_observer_counts_actual_http_retries(monkeypatch):
    responses = iter(
        [
            _Response(429, {"error": True}),
            _Response(
                200,
                {"error": False, "result": {"data": [], "totals": [0]}},
            ),
        ]
    )
    requests_seen = []
    observed_attempts = []

    def post(url, headers, json, timeout):
        requests_seen.append((url, json, timeout))
        return next(responses)

    monkeypatch.setattr("api.base_ozon_client.requests.post", post)
    client = TenantOzonClient(client_id="test-client", api_key="test-key")

    result = client.get_analytics_data(
        "2026-08-01",
        "2026-08-31",
        metrics=["ordered_units"],
        dimension=["day"],
        timeout=1,
        max_attempts=2,
        total_timeout=5,
        request_attempt_observer=observed_attempts.append,
    )

    assert result == {
        "error": False,
        "result": {"data": [], "totals": [0]},
    }
    assert len(requests_seen) == 2
    assert observed_attempts == [
        "/v1/analytics/data",
        "/v1/analytics/data",
    ]
    assert requests_seen[0][0].endswith("/v1/analytics/data")
    assert requests_seen[0][1]["metrics"] == ["ordered_units"]
    assert requests_seen[0][1]["dimension"] == ["day"]
