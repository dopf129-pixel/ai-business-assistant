from api.ozon_client import OzonClient


def test_analytics_data_client_sends_only_the_validated_read_request():
    client = OzonClient()
    calls = []

    def post(endpoint, payload, **kwargs):
        calls.append((endpoint, payload, kwargs))
        return {"error": False, "result": {"data": []}}

    client._post = post
    result = client.get_analytics_data(
        "2026-10-01",
        "2026-10-07",
        metrics=["ordered_units", "cancellations"],
        dimension=["day"],
        limit=1000,
        offset=0,
    )

    assert result["error"] is False
    assert calls == [(
        "/v1/analytics/data",
        {
            "date_from": "2026-10-01",
            "date_to": "2026-10-07",
            "metrics": ["ordered_units", "cancellations"],
            "dimension": ["day"],
            "limit": 1000,
            "offset": 0,
        },
        {"timeout": 30, "max_attempts": 3},
    )]


def test_analytics_data_client_rejects_invalid_ranges_and_page_limits_without_request():
    client = OzonClient()
    client._post = lambda *args, **kwargs: (_ for _ in ()).throw(
        AssertionError("invalid request reached Ozon")
    )

    for result in (
        client.get_analytics_data("2026-10-08", "2026-10-01", ["ordered_units"]),
        client.get_analytics_data("2026-10-01", "2026-10-08", ["ordered_units"], limit=1001),
    ):
        assert result["error"] is True
        assert result["code"] == "OZON_ANALYTICS_REQUEST_INVALID"
