from api.ozon_client import OzonClient


class _RecordingClient(OzonClient):
    def __init__(self):
        self.calls = []

    def _post(self, endpoint, data, timeout=20, max_attempts=3):
        self.calls.append((endpoint, timeout, max_attempts))
        return {"postings": [], "cursor": ""}


def test_fbo_postings_accepts_period_profit_short_timeout_contract():
    client = _RecordingClient()

    result = client.get_fbo_postings(
        "2026-01-01T00:00:00Z",
        "2026-01-02T23:59:59Z",
        limit=1000,
        offset=0,
        direction="ASC",
        status="",
        request_timeout=6,
        request_max_attempts=1,
    )

    assert result.get("error") is False
    assert client.calls == [("/v3/posting/fbo/list", 6, 1)]
