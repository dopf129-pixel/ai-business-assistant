from services.returns_buyout_facts_source import ReturnsBuyoutFactsSource


class FakeOzonClient:
    def __init__(self, response, returns_response=None):
        self.response = response
        self.returns_response = (
            returns_response
            if returns_response is not None
            else {"error": True}
        )
        self.calls = []
        self.return_calls = []

    def get_fbo_postings(self, **kwargs):
        self.calls.append(dict(kwargs))
        return self.response

    def get_returns(self, **kwargs):
        self.return_calls.append(dict(kwargs))
        return self.returns_response


def _response():
    return {
        "result": {
            "postings": [
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
        }
    }


def _returns_response():
    def item(posting, event_type, reason, quantity=1):
        return {
            "posting_number": posting,
            "type": event_type,
            "return_reason_name": reason,
            "product": {
                "offer_id": "hook-2",
                "sku": 3921245627,
                "quantity": quantity,
            },
        }

    return {
        "returns": [
            item(
                "r-1",
                "Cancellation",
                "Покупатель отказался при вручении: товар не подошел",
                2,
            ),
            item(
                "r-2",
                "Cancellation",
                "Покупатель отменил заказ: нашел дешевле",
            ),
            item(
                "r-3",
                "Cancellation",
                "Не удалось доставить заказ",
            ),
            item(
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
    assert len(result["postings"]) == 2


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
    assert result["customer_non_buyout_units"] is None


def test_classifies_real_ozon_returns_reasons_without_mixing_categories():
    source = ReturnsBuyoutFactsSource(
        FakeOzonClient(
            _response(),
            returns_response=_returns_response(),
        )
    )

    result = source.get("hook-2", "2026-08-01", "2026-08-25")

    assert result["returns_available"] is True
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


def test_returns_api_is_queried_by_offer_id_and_fbo_schema():
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
            "limit": 100,
            "last_id": 0,
        }
    ]


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
