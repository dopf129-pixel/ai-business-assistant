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


def test_fbs_postings_fallback_uses_current_cursor_api_and_reads_all_pages():
    client = OzonClient()
    calls = []

    def post(endpoint, payload, **kwargs):
        calls.append((endpoint, payload, kwargs))
        if len(calls) == 1:
            return {
                "error": False,
                "postings": [{"status": "cancelled", "products": [{"quantity": 1}]}],
                "has_next": True,
                "cursor": "page-2",
            }
        return {
            "error": False,
            "postings": [{"status": "cancelled", "products": [{"quantity": 2}]}],
            "has_next": False,
        }

    client._post = post
    result = client.get_fbs_postings(
        "2026-10-01",
        "2026-10-02",
        status="cancelled",
    )

    assert result["error"] is False
    assert result["complete"] is True
    assert [row["products"][0]["quantity"] for row in result["postings"]] == [1, 2]
    assert [call[0] for call in calls] == [
        "/v4/posting/fbs/list",
        "/v4/posting/fbs/list",
    ]
    assert calls[0][1]["filter"] == {
        "since": "2026-10-01",
        "to": "2026-10-02",
        "status": ["cancelled"],
    }
    assert calls[0][1]["cursor"] == ""
    assert calls[1][1]["cursor"] == "page-2"
    assert calls[0][1]["sort_dir"] == "ASC"
    assert "sort_by" not in calls[0][1]
    assert all(call[2] == {"timeout": 30, "max_attempts": 3} for call in calls)


def test_fbs_postings_fallback_fails_closed_on_a_repeated_cursor():
    client = OzonClient()
    client._post = lambda *_args, **_kwargs: {
        "error": False,
        "postings": [],
        "has_next": True,
        "cursor": "same-page",
    }

    result = client.get_fbs_postings(
        "2026-10-01",
        "2026-10-02",
        status="cancelled",
    )

    assert result["error"] is True
    assert result["code"] == "OZON_FBS_POSTINGS_CURSOR_INVALID"

