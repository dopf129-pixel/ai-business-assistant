from api.ozon_client import OzonClient


def test_finance_transaction_list_loads_every_page_with_bounded_date_filter():
    client = OzonClient()
    calls = []

    def post(endpoint, data, **kwargs):
        calls.append((endpoint, data, kwargs))
        page = data["page"]
        return {
            "result": {
                "operations": [{"fixture_page": page}],
                "page_count": 2,
            }
        }

    client._post = post

    result = client.get_finance_transactions("2026-08-01", "2026-08-28")

    assert result == {
        "error": False,
        "operations": [{"fixture_page": 1}, {"fixture_page": 2}],
        "pages_loaded": 2,
        "read_only": True,
        "executed": False,
    }
    assert [call[0] for call in calls] == [
        "/v3/finance/transaction/list",
        "/v3/finance/transaction/list",
    ]
    assert [call[1]["page"] for call in calls] == [1, 2]
    assert all(call[1]["page_size"] == 1000 for call in calls)
    assert all(
        call[1]["filter"]
        == {
            "date": {
                "from": "2026-08-01T00:00:00.000Z",
                "to": "2026-08-28T23:59:59.999Z",
            },
            "transaction_type": "all",
        }
        for call in calls
    )


def test_finance_transaction_list_fails_closed_on_invalid_pagination():
    client = OzonClient()
    client._post = lambda *_args, **_kwargs: {
        "result": {"operations": [], "page_count": "unknown"}
    }

    result = client.get_finance_transactions("2026-08-01", "2026-08-28")

    assert result["error"] is True
    assert result["code"] == "OZON_FINANCE_TRANSACTIONS_RESPONSE_INVALID"
    assert "operations" not in result


def test_finance_transaction_list_stops_when_page_limit_is_exceeded():
    client = OzonClient()
    client._post = lambda *_args, **_kwargs: {
        "result": {"operations": [{"fixture_page": 1}], "page_count": 2}
    }

    result = client.get_finance_transactions(
        "2026-08-01",
        "2026-08-28",
        max_pages=1,
    )

    assert result["error"] is True
    assert result["code"] == "OZON_FINANCE_TRANSACTIONS_PAGE_LIMIT_REACHED"


def test_finance_transaction_list_rejects_malformed_operation_rows():
    client = OzonClient()
    client._post = lambda *_args, **_kwargs: {
        "result": {
            "operations": [{"amount": "-10.00"}, None],
            "page_count": 1,
        }
    }

    result = client.get_finance_transactions("2026-08-01", "2026-08-28")

    assert result["error"] is True
    assert result["code"] == "OZON_FINANCE_TRANSACTIONS_RESPONSE_INVALID"
    assert "operations" not in result


def test_finance_transaction_list_rejects_changing_page_count():
    client = OzonClient()
    client._post = lambda _endpoint, data, **_kwargs: {
        "result": {
            "operations": [{"fixture_page": data["page"]}],
            "page_count": 2 if data["page"] == 1 else 3,
        }
    }

    result = client.get_finance_transactions("2026-08-01", "2026-08-28")

    assert result["error"] is True
    assert result["code"] == "OZON_FINANCE_TRANSACTIONS_RESPONSE_INVALID"
    assert "operations" not in result
