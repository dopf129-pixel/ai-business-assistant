import sqlite3
import time

from api.base_ozon_client import OzonClient
from services.ozon_account_repository import OzonAccountRepository


class _Client(OzonClient):
    def __init__(self):
        self.base_url = "https://example.invalid"
        self.client_id = "client"
        self.api_key = "key"


def test_ozon_post_total_timeout_caps_single_attempt(monkeypatch):
    client = _Client()
    observed = {}

    def post(url, headers, json, timeout):
        observed["timeout"] = timeout
        raise __import__("requests").exceptions.Timeout()

    monkeypatch.setattr("api.base_ozon_client.requests.post", post)
    monkeypatch.setattr("api.base_ozon_client.time.sleep", lambda value: None)

    result = client._post(
        "/slow",
        {},
        timeout=30,
        max_attempts=1,
        total_timeout=0.25,
    )

    assert result["error"] is True
    assert observed["timeout"] <= 0.25


def test_account_repository_configures_short_sqlite_busy_timeout(tmp_path):
    repository = OzonAccountRepository(
        master_key=None,
        db_name=str(tmp_path / "accounts.db"),
    )

    conn = repository._connection()
    try:
        busy_timeout = conn.execute("PRAGMA busy_timeout").fetchone()[0]
    finally:
        conn.close()

    assert busy_timeout == 5000
