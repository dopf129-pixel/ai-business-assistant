from services.returns_finance_attribution_facts_source import (
    ReturnsFinanceAttributionFactsSource,
)


class StubReturnsFactsSource:
    def __init__(self, facts):
        self.facts = facts
        self.calls = []

    def get(self, **kwargs):
        self.calls.append(dict(kwargs))
        return dict(self.facts)


class FakeOzonClient:
    def __init__(self, responses):
        self.responses = dict(responses)
        self.calls = []

    def get_accruals_by_day(self, value):
        self.calls.append(value)
        return self.responses.get(value, {"accruals": []})


def _event(posting, category, quantity=1):
    return {
        "posting_number": posting,
        "category": category,
        "quantity": quantity,
    }


def _facts(events, ambiguous=0):
    return {
        "error": False,
        "postings_complete": True,
        "returns_complete": True,
        "ambiguous_cancelled_units": ambiguous,
        "delivered_units": 4580,
        "postings": [
            {
                "posting_number": "p-1",
                "status": "cancelled",
            },
            {
                "posting_number": "p-3",
                "status": "cancelled",
            },
        ],
        "return_events": events,
    }


def _posting_accrual(posting, sku, amount, services):
    return {
        "unit_number": posting,
        "total_amount": {"amount": str(amount)},
        "posting": {
            "products": [
                {
                    "sku": sku,
                    "delivery": {
                        "services": [
                            {
                                "type_id": type_id,
                                "accrued": {
                                    "amount": str(fee_amount)
                                },
                            }
                            for type_id, fee_amount in services
                        ]
                    },
                }
            ]
        },
        "item_fees": None,
    }


def _item_accrual(posting, sku, amount, fees):
    return {
        "unit_number": posting,
        "total_amount": {"amount": str(amount)},
        "posting": None,
        "item_fees": {
            "fees": [
                {
                    "sku": sku,
                    "fees": [
                        {
                            "type_id": type_id,
                            "accrued": {
                                "amount": str(fee_amount)
                            },
                        }
                        for type_id, fee_amount in fees
                    ],
                }
            ]
        },
    }


def test_matches_finance_rows_and_keeps_observed_metrics_explicit():
    facts = _facts([
        _event("p-1", "customer_non_buyout"),
        _event("p-2", "customer_return"),
        _event("p-3", "customer_non_buyout"),
    ])
    client = FakeOzonClient({
        "2026-08-01": {
            "accruals": [
                _posting_accrual(
                    "p-1",
                    42,
                    -18,
                    [(32, -10), (59, -8)],
                ),
                _item_accrual(
                    "p-2",
                    42,
                    1,
                    [(1, 1)],
                ),
            ]
        },
        "2026-08-02": {
            "accruals": [
                _posting_accrual(
                    "p-2",
                    42,
                    -20,
                    [(59, -9)],
                )
            ]
        },
    })
    source = ReturnsFinanceAttributionFactsSource(
        client,
        StubReturnsFactsSource(facts),
    )

    result = source.get(
        "hook-2",
        "42",
        "2026-08-01",
        "2026-08-02",
    )

    assert result["error"] is False
    assert result["delivered_units"] == 4580
    non_buyout = result["categories"]["customer_non_buyout"]
    assert non_buyout["event_posting_count"] == 2
    assert non_buyout["finance_matched_posting_count"] == 1
    assert non_buyout["finance_unmatched_posting_numbers"] == [
        "p-3"
    ]
    assert non_buyout["observed_net_amount_total"] == -18.0
    assert non_buyout["observed_net_amount_average"] == -18.0
    assert non_buyout["observed_fee_amount_total"] == -18.0
    assert non_buyout["observed_fee_amount_average"] == -18.0
    assert non_buyout["fees"]["32"]["observed_total"] == -10.0
    assert non_buyout["fees"]["59"]["observed_total"] == -8.0

    customer_return = result["categories"]["customer_return"]
    assert customer_return["event_posting_count"] == 1
    assert customer_return["observed_net_amount_total"] == -19.0
    assert customer_return["observed_fee_amount_total"] == -8.0
    assert customer_return["observed_fee_amount_average"] == -8.0
    assert customer_return["fees"]["1"]["observed_total"] == 1.0
    assert customer_return["fees"]["59"]["observed_total"] == -9.0

    assert result["classification_complete"] is True
    assert result["finance_complete"] is False
    assert result["complete"] is False
    assert result["missing_data"] == [
        "finance_postings_unmatched"
    ]
    assert client.calls == ["2026-08-01", "2026-08-02"]


def test_excludes_non_buyout_event_outside_cancelled_sample():
    facts = _facts([
        _event("outside", "customer_non_buyout"),
        _event("p-2", "customer_return"),
    ])
    source = ReturnsFinanceAttributionFactsSource(
        FakeOzonClient({}),
        StubReturnsFactsSource(facts),
    )

    result = source.get(
        "hook-2",
        "42",
        "2026-08-01",
        "2026-08-01",
    )

    assert (
        result["categories"]["customer_non_buyout"][
            "event_posting_count"
        ]
        == 0
    )
    assert (
        result["categories"]["customer_return"][
            "event_posting_count"
        ]
        == 1
    )


def test_marks_multi_product_accrual_as_non_attributable():
    facts = _facts([
        _event("p-1", "customer_non_buyout"),
    ])
    accrual = _posting_accrual(
        "p-1",
        42,
        -30,
        [(32, -10)],
    )
    accrual["posting"]["products"].append({
        "sku": 99,
        "delivery": {
            "services": [
                {
                    "type_id": 32,
                    "accrued": {"amount": "-20"},
                }
            ]
        },
    })
    source = ReturnsFinanceAttributionFactsSource(
        FakeOzonClient({
            "2026-08-01": {"accruals": [accrual]}
        }),
        StubReturnsFactsSource(facts),
    )

    result = source.get(
        "hook-2",
        "42",
        "2026-08-01",
        "2026-08-01",
    )

    category = result["categories"]["customer_non_buyout"]
    assert category["finance_matched_posting_count"] == 1
    assert category["non_attributable_posting_numbers"] == [
        "p-1"
    ]
    assert category["observed_posting_count"] == 0
    assert category["observed_net_amount_total"] is None
    assert category["observed_fee_amount_total"] is None
    assert "multi_product_accruals" in result["missing_data"]


def test_preserves_incomplete_classification_and_finance_days():
    facts = _facts([], ambiguous=1)
    source = ReturnsFinanceAttributionFactsSource(
        FakeOzonClient({
            "2026-08-01": {"error": True},
        }),
        StubReturnsFactsSource(facts),
    )

    result = source.get(
        "hook-2",
        "42",
        "2026-08-01",
        "2026-08-01",
    )

    assert result["classification_complete"] is False
    assert result["finance_complete"] is False
    assert result["complete"] is False
    assert result["missing_data"] == [
        "returns_classification_incomplete",
        "finance_days_unavailable",
    ]
    assert result["finance_error_dates"] == ["2026-08-01"]


def test_rejects_missing_sku_and_invalid_period():
    source = ReturnsFinanceAttributionFactsSource(
        FakeOzonClient({}),
        StubReturnsFactsSource({}),
    )

    missing = source.get(
        "",
        "42",
        "2026-08-01",
        "2026-08-02",
    )
    invalid = source.get(
        "hook-2",
        "42",
        "2026-08-03",
        "2026-08-02",
    )

    assert missing["code"] == "SKU_REQUIRED"
    assert invalid["code"] == "PERIOD_INVALID"
