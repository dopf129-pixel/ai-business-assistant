from services.returns_buyout_facts_source import ReturnsBuyoutFactsSource


class FakeOzonClient:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def get_fbo_postings(self, **kwargs):
        self.calls.append(dict(kwargs))
        return self.response


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


def test_preserves_cancel_reason_as_fact_only():
    source = ReturnsBuyoutFactsSource(FakeOzonClient(_response()))

    result = source.get("hook-2", "2026-08-18", "2026-08-25")

    cancelled = result["postings"][1]
    assert cancelled["status"] == "cancelled"
    assert cancelled["cancel_reason_id"] == 123
    assert cancelled["cancel_reason"] == "unknown reason"
    assert result["customer_non_buyout_units"] is None


def test_returns_structured_error_when_api_is_unavailable():
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
