from api.base_ozon_client import OzonClient


def test_product_stock_read_forwards_bounded_retry_options_and_observer():
    client = object.__new__(OzonClient)
    calls = []
    observer = lambda endpoint=None: None
    client._post = lambda endpoint, payload, **options: calls.append(
        (endpoint, payload, options)
    ) or {"items": [], "total_items": 0}

    response = client.get_product_stocks(
        101,
        limit=50,
        timeout=3,
        max_attempts=1,
        total_timeout=4,
        request_attempt_observer=observer,
    )

    assert response == {"items": [], "total_items": 0}
    assert len(calls) == 1
    endpoint, payload, options = calls[0]
    assert endpoint == "/v4/product/info/stocks"
    assert payload["filter"]["product_id"] == ["101"]
    assert payload["limit"] == 50
    assert options == {
        "timeout": 3,
        "max_attempts": 1,
        "total_timeout": 4,
        "request_attempt_observer": observer,
    }


def test_product_stock_read_rejects_invalid_page_limits_before_request():
    client = object.__new__(OzonClient)
    calls = []
    client._post = lambda *args, **kwargs: calls.append((args, kwargs))

    for invalid_limit in (0, 101, True, 1.5, "not-a-number"):
        result = client.get_product_stocks(101, limit=invalid_limit)
        assert result["error"] is True
        assert result["executed"] is False

    assert calls == []
