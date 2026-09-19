from api.base_ozon_client import OzonClient


class _Response:
    status_code = 200
    headers = {}

    def raise_for_status(self):
        return None

    def json(self):
        return {"ok": True}


class _Client(OzonClient):
    def __init__(self):
        self.base_url = "https://example.invalid"
        self.client_reads = 0
        self.key_reads = 0

    @property
    def client_id(self):
        self.client_reads += 1
        return "client"

    @property
    def api_key(self):
        self.key_reads += 1
        return "secret"


def test_post_snapshots_dynamic_credentials_once(monkeypatch):
    client = _Client()
    captured = {}

    def post(url, headers, json, timeout):
        captured["headers"] = headers
        return _Response()

    monkeypatch.setattr("api.base_ozon_client.requests.post", post)

    result = client._post("/read", {"x": 1})

    assert result == {"ok": True}
    assert client.client_reads == 1
    assert client.key_reads == 1
    assert captured["headers"]["Client-Id"] == "client"
    assert captured["headers"]["Api-Key"] == "secret"
