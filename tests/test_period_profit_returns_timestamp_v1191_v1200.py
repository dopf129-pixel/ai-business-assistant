from api.ozon_client import OzonClient
from services.period_profit_return_evidence_service import (
    PeriodProfitReturnEvidenceService,
)


class CaptureClient(OzonClient):
    def __init__(self, response=None):
        super().__init__()
        self.response = {"returns": []} if response is None else response
        self.captured = None

    def _post(self, endpoint, data, timeout=20, max_attempts=3):
        self.captured = {
            "endpoint": endpoint,
            "data": data,
            "timeout": timeout,
            "max_attempts": max_attempts,
        }
        return self.response


def _period(client):
    return (
        client.captured["data"]["filter"]
        ["visual_status_change_moment"]
    )


def test_v1191_date_start_is_protobuf_timestamp():
    client = CaptureClient()
    client.get_returns(
        since="2026-05-01",
        to="2026-09-03",
    )
    assert (
        _period(client)["time_from"]
        == "2026-05-01T00:00:00Z"
    )


def test_v1192_date_end_includes_full_day():
    client = CaptureClient()
    client.get_returns(
        since="2026-05-01",
        to="2026-09-03",
    )
    assert (
        _period(client)["time_to"]
        == "2026-09-03T23:59:59.999999999Z"
    )


def test_v1193_full_rfc3339_values_are_preserved():
    client = CaptureClient()
    client.get_returns(
        since="2026-05-01T10:15:30Z",
        to="2026-09-03T20:45:10Z",
    )
    assert _period(client) == {
        "time_from": "2026-05-01T10:15:30Z",
        "time_to": "2026-09-03T20:45:10Z",
    }


def test_v1194_offset_timestamps_are_preserved():
    client = CaptureClient()
    client.get_returns(
        since="2026-05-01T10:15:30+03:00",
        to="2026-09-03T20:45:10+03:00",
    )
    assert (
        _period(client)["time_from"]
        == "2026-05-01T10:15:30+03:00"
    )
    assert (
        _period(client)["time_to"]
        == "2026-09-03T20:45:10+03:00"
    )


def test_v1195_returns_filter_and_transport_contract_stay_unchanged():
    client = CaptureClient()
    client.get_returns(
        offer_id="hook-2",
        return_schema="FBO",
        since="2026-05-01",
        to="2026-09-03",
        limit=500,
        last_id=0,
    )

    assert client.captured["endpoint"] == "/v1/returns/list"
    assert (
        client.captured["data"]["filter"]["offer_id"]
        == "hook-2"
    )
    assert (
        client.captured["data"]["filter"]["return_schema"]
        == "FBO"
    )
    assert client.captured["data"]["limit"] == 500
    assert client.captured["data"]["last_id"] == 0
    assert client.captured["timeout"] == 30
    assert client.captured["max_attempts"] == 3


def test_v1196_period_profit_return_evidence_uses_normalized_dates():
    client = CaptureClient()

    result = PeriodProfitReturnEvidenceService(
        client
    ).load(
        "2026-05-01",
        "2026-09-03",
    )

    assert result["error"] is False
    assert result["read_only"] is True
    assert result["executed"] is False
    assert (
        _period(client)["time_from"]
        == "2026-05-01T00:00:00Z"
    )
    assert (
        _period(client)["time_to"]
        == "2026-09-03T23:59:59.999999999Z"
    )


def test_v1197_timestamp_normalization_keeps_return_response_unchanged():
    source = {
        "returns": [
            {
                "id": 10,
                "offer_id": "hook-2",
            }
        ]
    }
    client = CaptureClient(
        response=source
    )

    result = client.get_returns(
        since="2026-05-01",
        to="2026-09-03",
    )

    assert result is source
    assert result["returns"][0]["id"] == 10
