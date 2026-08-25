from services.returns_buyout_facts_source import ReturnsBuyoutFactsSource


class FakeOzonClient:
    def __init__(self, response, returns_response=None, returns_pages=None):
        self.response = response
        self.returns_response = (
            returns_response
            if returns_response is not None
            else {"error": True}
        )
        self.returns_pages = list(returns_pages or [])
        self.calls = []
        self.return_calls = []

    def get_fbo_postings(self, **kwargs):
        self.calls.append(dict(kwargs))
        return self.response

    def get_returns(self, **kwargs):
        self.return_calls.append(dict(kwargs))
        if self.returns_pages:
            return self.returns_pages.pop(0)
        return self.returns_response


def _posting_items():
    return [
        {
            "posting_number": "p-1",
            "status": "delivered",
            "products": [
                {
                    "offer_id": "hook-2",
                    "sku": 3921245627,
                    "quantity": 2,
                }
            ],
        },
        {
            "posting_number": "p-2",
            "status": "cancelled",
            "cancellation": {
                "cancel_reason_id": 123,
                "cancel_reason": "unknown reason",
                "cancellation_type": "client_initiated",
            },
            "products": [
                {
                    "offer_id": "hook-2",
                    "sku": 3921245627,
                    "quantity": 1,
                }
            ],
        },
        {
            "posting_number": "other",
            "status": "delivered",
            "products": [
                {
                    "offer_id": "other",
                    "sku": 100,
                    "quantity": 5,
                }
            ],
        },
    ]


def _response():
    return {
        "result": {
            "postings": _posting_items()
        }
    }


def _real_response_shape():
    return {
        "result": _posting_items()
    }


def _return_item(item_id, posting, event_type, reason, quantity=1):
    return {
        "id": str(item_id),
        "posting_number": posting,
        "type": event_type,
        "return_reason_name": reason,
        "product": {
            "offer_id": "hook-2",
            "sku": 3921245627,
            "quantity": quantity,
        },
    }


def _returns_response():
    return {
        "returns": [
            _return_item(
                1,
                "r-1",
                "Cancellation",
                "Покупатель отказался при вручении: товар не подошел",
                2,
            ),
            _return_item(
                2,
                "r-2",
                "Cancellation",
                "Покупатель отменил заказ: нашел дешевле",
            ),
            _return_item(
                3,
                "r-3",
                "Cancellation",
                "Не удалось доставить заказ",
            ),
            _return_item(
                4,
                "r-4",
                "ClientReturn",
                "Покупатель передумал",
            ),
        ],
        "has_next": False,
    }


def test_prepares_product_posting_counts_without_inventing_non_buyouts():
    client = FakeOzonClient(_response())
    source = ReturnsBuyoutFactsSource(client)

    result = source.get(
        sku="hook-2",
        since="2026-08-18T00:00:00Z",
        to="2026-08-25T00:00:00Z",
    )

    assert result["error"] is False
    assert result["posting_count"] == 2
    assert result["total_units"] == 3
    assert result["delivered_units"] == 2
    assert result["cancelled_units"] == 1
    assert result["ambiguous_cancelled_units"] == 1
    assert result["customer_non_buyout_units"] is None
    assert result["customer_return_units"] is None
    assert result["returns_available"] is False
    assert result["postings_complete"] is True
    assert len(result["postings"]) == 2


def test_accepts_real_fbo_result_list_shape():
    source = ReturnsBuyoutFactsSource(FakeOzonClient(_real_response_shape()))

    result = source.get("hook-2", "2026-08-18", "2026-08-25")

    assert result["posting_count"] == 2
    assert result["delivered_units"] == 2
    assert result["cancelled_units"] == 1


def test_accepts_internal_ozon_sku_as_identifier():
    source = ReturnsBuyoutFactsSource(FakeOzonClient(_response()))

    result = source.get(
        sku="3921245627",
        since="2026-08-18",
        to="2026-08-25",
    )

    assert result["total_units"] == 3
    assert result["delivered_units"] == 2


def test_preserves_cancel_reason_as_fact_only_when_returns_api_unavailable():
    source = ReturnsBuyoutFactsSource(FakeOzonClient(_response()))

    result = source.get("hook-2", "2026-08-18", "2026-08-25")

    cancelled = result["postings"][1]
    assert cancelled["status"] == "cancelled"
    assert cancelled["cancel_reason_id"] == 123
    assert cancelled["cancel_reason"] == "unknown reason"
    assert cancelled["cancellation_type"] == "client_initiated"
    assert result["customer_non_buyout_units"] is None


def test_preserves_top_level_fbo_cancellation_metadata():
    response = _response()
    cancelled = response["result"]["postings"][1]
    cancelled.pop("cancellation")
    cancelled["cancel_reason_id"] = 504
    cancelled["cancel_reason"] = "top-level reason"
    cancelled["cancellation_type"] = "top-level type"

    result = ReturnsBuyoutFactsSource(FakeOzonClient(response)).get(
        "hook-2",
        "2026-08-01",
        "2026-08-25",
    )

    item = result["ambiguous_cancelled_postings"][0]
    assert item["cancel_reason_id"] == 504
    assert item["cancel_reason"] == "top-level reason"
    assert item["cancellation_type"] == "top-level type"


def test_classifies_real_ozon_returns_reasons_without_mixing_categories():
    source = ReturnsBuyoutFactsSource(
        FakeOzonClient(
            _response(),
            returns_response=_returns_response(),
        )
    )

    result = source.get("hook-2", "2026-08-01", "2026-08-25")

    assert result["returns_available"] is True
    assert result["returns_complete"] is True
    assert result["customer_non_buyout_units"] == 2
    assert result["customer_return_units"] == 1
    assert result["customer_cancelled_units"] == 1
    assert result["delivery_failure_units"] == 1
    assert result["unknown_return_units"] == 0

    categories = [item["category"] for item in result["return_events"]]
    assert categories == [
        "customer_non_buyout",
        "customer_cancel",
        "delivery_failure",
        "customer_return",
    ]


def test_classifies_confirmed_uncollected_order_as_non_buyout():
    returns_response = {
        "returns": [
            _return_item(
                9,
                "p-2",
                "Cancellation",
                "Покупатель не забрал заказ",
            )
        ],
        "has_next": False,
    }
    source = ReturnsBuyoutFactsSource(
        FakeOzonClient(_response(), returns_response=returns_response)
    )

    result = source.get("hook-2", "2026-08-01", "2026-08-25")

    assert result["customer_non_buyout_units"] == 1
    assert result["ambiguous_cancelled_units"] == 0
    assert result["return_events"][0]["category"] == "customer_non_buyout"


def test_ambiguous_cancelled_is_matched_by_posting_number():
    returns_response = {
        "returns": [
            _return_item(
                10,
                "p-2",
                "Cancellation",
                "Покупатель отказался при вручении: товар не подошел",
            )
        ],
        "has_next": False,
    }
    source = ReturnsBuyoutFactsSource(
        FakeOzonClient(
            _response(),
            returns_response=returns_response,
        )
    )

    result = source.get("hook-2", "2026-08-01", "2026-08-25")

    assert result["customer_non_buyout_units"] == 1
    assert result["ambiguous_cancelled_units"] == 0
    assert result["ambiguous_cancelled_postings"] == []
    assert result["cancelled_diagnostics"] == {
        "cancelled_posting_count": 1,
        "matched_posting_count": 1,
        "unmatched_posting_count": 0,
        "unmatched_postings": [],
        "unclassified_matched_posting_count": 0,
        "unclassified_matched_postings": [],
        "fbo_reason_classified_posting_count": 0,
        "fbo_reason_classified_postings": [],
    }


def test_unmatched_cancelled_posting_remains_ambiguous():
    source = ReturnsBuyoutFactsSource(
        FakeOzonClient(
            _response(),
            returns_response=_returns_response(),
        )
    )

    result = source.get("hook-2", "2026-08-01", "2026-08-25")

    assert result["ambiguous_cancelled_units"] == 1
    assert [
        item["posting_number"]
        for item in result["ambiguous_cancelled_postings"]
    ] == ["p-2"]
    assert result["cancelled_diagnostics"] == {
        "cancelled_posting_count": 1,
        "matched_posting_count": 0,
        "unmatched_posting_count": 1,
        "unmatched_postings": [
            {
                "posting_number": "p-2",
                "status": "cancelled",
                "quantity": 1,
                "cancel_reason_id": 123,
                "cancel_reason": "unknown reason",
                "cancellation_type": "client_initiated",
            }
        ],
        "unclassified_matched_posting_count": 0,
        "unclassified_matched_postings": [],
        "fbo_reason_classified_posting_count": 0,
        "fbo_reason_classified_postings": [],
    }


def test_classifies_unmatched_posting_by_confirmed_fbo_reason_id():
    response = _response()
    cancelled = response["result"]["postings"][1]
    cancelled.pop("cancellation")
    cancelled["cancel_reason_id"] = 504
    source = ReturnsBuyoutFactsSource(
        FakeOzonClient(
            response,
            returns_response={"returns": [], "has_next": False},
        )
    )

    result = source.get("hook-2", "2026-08-01", "2026-08-25")

    assert result["customer_cancelled_units"] == 1
    assert result["ambiguous_cancelled_units"] == 0
    diagnostics = result["cancelled_diagnostics"]
    assert diagnostics["fbo_reason_classified_posting_count"] == 1
    classified = diagnostics["fbo_reason_classified_postings"][0]
    assert classified["posting_number"] == "p-2"
    assert classified["category"] == "customer_cancel"
    assert classified["classification_source"] == "fbo_cancel_reason_id"


def test_exposes_return_events_for_matched_but_unclassified_posting():
    returns_response = {
        "returns": [
            _return_item(
                11,
                "p-2",
                "Cancellation",
                "Другая причина Ozon",
            )
        ],
        "has_next": False,
    }
    source = ReturnsBuyoutFactsSource(
        FakeOzonClient(_response(), returns_response=returns_response)
    )

    result = source.get("hook-2", "2026-08-01", "2026-08-25")

    diagnostics = result["cancelled_diagnostics"]
    assert diagnostics["matched_posting_count"] == 1
    assert diagnostics["unmatched_posting_count"] == 0
    assert diagnostics["unclassified_matched_posting_count"] == 1
    item = diagnostics["unclassified_matched_postings"][0]
    assert item["posting_number"] == "p-2"
    assert item["return_events"] == [
        {
            "return_id": "11",
            "posting_number": "p-2",
            "type": "Cancellation",
            "reason": "Другая причина Ozon",
            "quantity": 1,
            "category": "unknown",
        }
    ]


def test_returns_api_is_period_scoped_and_uses_max_page_size():
    client = FakeOzonClient(
        _response(),
        returns_response=_returns_response(),
    )
    source = ReturnsBuyoutFactsSource(client)

    source.get("hook-2", "2026-08-01", "2026-08-25")

    assert client.return_calls == [
        {
            "offer_id": "hook-2",
            "return_schema": "FBO",
            "since": "2026-08-01",
            "to": "2026-08-25",
            "limit": 500,
            "last_id": 0,
        }
    ]


def test_returns_pagination_uses_last_return_id():
    first = {
        "returns": [
            _return_item(
                101,
                "r-101",
                "Cancellation",
                "Покупатель отказался при вручении: товар не подошел",
            )
        ],
        "has_next": True,
    }
    second = {
        "returns": [
            _return_item(
                102,
                "r-102",
                "ClientReturn",
                "Покупатель передумал",
            )
        ],
        "has_next": False,
    }
    client = FakeOzonClient(
        _response(),
        returns_pages=[first, second],
    )

    result = ReturnsBuyoutFactsSource(client).get(
        "hook-2",
        "2026-08-01",
        "2026-08-25",
    )

    assert result["returns_complete"] is True
    assert result["customer_non_buyout_units"] == 1
    assert result["customer_return_units"] == 1
    assert [call["last_id"] for call in client.return_calls] == [0, 101]


def test_returns_structured_error_when_postings_api_is_unavailable():
    source = ReturnsBuyoutFactsSource(
        FakeOzonClient({"error": True})
    )

    result = source.get("hook-2", "2026-08-18", "2026-08-25")

    assert result == {
        "error": True,
        "code": "FBO_POSTINGS_UNAVAILABLE",
        "sku": "hook-2",
        "message": "FBO postings недоступны",
    }


def test_requires_sku_before_calling_api():
    client = FakeOzonClient(_response())
    source = ReturnsBuyoutFactsSource(client)

    result = source.get("", "2026-08-18", "2026-08-25")

    assert result["error"] is True
    assert result["code"] == "SKU_REQUIRED"
    assert client.calls == []
    assert client.return_calls == []
