from datetime import date, timedelta, timezone
from copy import deepcopy

import pytest

from services.cross_docking_supply_evidence_service import (
    CrossDockingSupplyEvidenceService,
)
from services.cross_docking_supply_source import OzonCrossDockingSupplySource


@pytest.fixture(autouse=True)
def _use_configured_moscow_timezone(monkeypatch):
    monkeypatch.setattr(
        CrossDockingSupplyEvidenceService,
        "resolve_timezone",
        classmethod(lambda cls: timezone(timedelta(hours=3))),
    )


class _FakeOzonSupplyClient:
    def __init__(self, *, pages, orders, summaries, products):
        self.pages = list(pages)
        self.orders = {str(key): value for key, value in orders.items()}
        self.summaries = {str(key): value for key, value in summaries.items()}
        self.products = {str(key): value for key, value in products.items()}
        self.calls = []

    def _record(self, call):
        self.calls.append(call)
        observer = call[-1].get("request_attempt_observer")
        if callable(observer):
            observer(call[0])

    def get_supply_orders_list(self, states, **options):
        self._record(("list", states, options))
        if not self.pages:
            return {"error": False, "order_ids": [], "last_id": None}
        return self.pages.pop(0)

    def get_supply_orders_details(self, order_ids, **options):
        self._record(("details", list(order_ids), options))
        return {
            "error": False,
            "orders": [
                self.orders[str(order_id)]
                for order_id in order_ids
                if str(order_id) in self.orders
            ],
        }

    def get_supply_act_summary(self, order_id, **options):
        self._record(("summary", str(order_id), options))
        return self.summaries.get(str(order_id), {"error": True})

    def get_supply_act_products(self, supply_id, **options):
        self._record(("products", str(supply_id), options))
        return self.products.get(str(supply_id), {"error": True})


def _fake_data():
    order = {
        "order_id": 1001,
        "state": "COMPLETED",
        "state_updated_date": "2026-09-29T09:22:15.203154Z",
        "supplies": [
            {"supply_id": 2001, "state": "COMPLETED", "is_crossdock": True}
        ],
    }
    summary = {
        "error": False,
        "supplies_acts": [
            {
                "supply_id": 2001,
                "is_agreement_completed": True,
                "supply_acts": [
                    {
                        "act_id": 3001,
                        "act_state": "ACCEPTED",
                        "type": "ACCEPTANCE",
                        "summary": {
                            "fact_quantity": 100,
                            "approved_quantity": 0,
                            "unidentified_quantity": 0,
                        },
                    }
                ],
            }
        ],
    }
    products = {
        "error": False,
        "supply_acts": [
            {
                "act_id": 3001,
                "type": "ACCEPTANCE",
                "items": [
                    {
                        "sku_info": {"sku": 3921245627},
                        "declared_quantity": 200,
                        "approved_quantity": 100,
                        "fact_quantity": 100,
                    }
                ],
            }
        ],
    }
    return (
        order,
        summary,
        products,
    )


def test_source_collects_completed_supply_and_exact_acceptance_act():
    order, summary, products = _fake_data()
    client = _FakeOzonSupplyClient(
        pages=[{"error": False, "order_ids": [1001], "last_id": None}],
        orders={1001: order},
        summaries={1001: summary},
        products={2001: products},
    )
    source = OzonCrossDockingSupplySource(client)

    result = source.collect_window(
        date_from=date(2026, 9, 1),
        date_to=date(2026, 9, 30),
    )

    assert result.evidence.status == "COMPLETE"
    assert result.evidence.units_by_sku == (("3921245627", 100),)
    assert result.request_count == 4
    assert [call[0] for call in client.calls] == [
        "list",
        "details",
        "summary",
        "products",
    ]
    list_call = client.calls[0]
    assert list_call[1] == ["COMPLETED"]
    assert list_call[2]["sort_by"] == "ORDER_STATE_UPDATED_AT"
    assert list_call[2]["sort_dir"] == "DESC"
    assert all(call[2]["max_attempts"] == 1 for call in client.calls)
    assert all(call[2]["total_timeout"] <= 10 for call in client.calls)
    evidence_supply = result.evidence.supplies[0]
    assert evidence_supply.identity_fingerprint != "1001"
    assert evidence_supply.identity_fingerprint != "2001"


def test_source_follows_cursor_until_final_short_page():
    first, first_summary, first_products = _fake_data()
    second = {
        **first,
        "order_id": 1002,
        "supplies": [{**first["supplies"][0], "supply_id": 2002}],
    }
    second_summary = deepcopy(first_summary)
    second_summary["supplies_acts"][0]["supply_id"] = 2002
    second_summary["supplies_acts"][0]["supply_acts"][0]["summary"][
        "fact_quantity"
    ] = 50
    second_products = {
        "error": False,
        "supply_acts": [
            {
                **first_products["supply_acts"][0],
                "items": [
                    {
                        **first_products["supply_acts"][0]["items"][0],
                        "fact_quantity": 50,
                    }
                ],
            }
        ],
    }
    client = _FakeOzonSupplyClient(
        pages=[
            {"error": False, "order_ids": [1001], "last_id": "cursor-1"},
            {"error": False, "order_ids": [1002], "last_id": None},
        ],
        orders={1001: first, 1002: second},
        summaries={1001: first_summary, 1002: second_summary},
        products={2001: first_products, 2002: second_products},
    )

    result = OzonCrossDockingSupplySource(client).collect_window(
        date_from=date(2026, 9, 1),
        date_to=date(2026, 9, 30),
    )

    assert result.evidence.status == "COMPLETE"
    assert result.evidence.total_units == 150
    assert result.request_count == 8
    assert [call[2].get("last_id") for call in client.calls if call[0] == "list"] == [
        None,
        "cursor-1",
    ]


def test_source_stops_after_fully_read_page_before_window():
    order, _, _ = _fake_data()
    order = {**order, "state_updated_date": "2026-08-31T20:00:00Z"}
    client = _FakeOzonSupplyClient(
        pages=[{"error": False, "order_ids": [1001], "last_id": "older-page"}],
        orders={1001: order},
        summaries={},
        products={},
    )

    result = OzonCrossDockingSupplySource(client).collect_window(
        date_from=date(2026, 9, 1),
        date_to=date(2026, 9, 30),
    )

    assert result.evidence.status == "NO_CROSSDOCK_SUPPLIES"
    assert result.evidence.total_units == 0
    assert result.request_count == 2
    assert [call[0] for call in client.calls] == ["list", "details"]


def test_source_request_budget_exhaustion_never_publishes_partial_total():
    order, summary, products = _fake_data()
    client = _FakeOzonSupplyClient(
        pages=[{"error": False, "order_ids": [1001], "last_id": None}],
        orders={1001: order},
        summaries={1001: summary},
        products={2001: products},
    )

    result = OzonCrossDockingSupplySource(client, max_requests=1).collect_window(
        date_from=date(2026, 9, 1),
        date_to=date(2026, 9, 30),
    )

    assert result.request_count == 1
    assert result.stopped_reason == "REQUEST_BUDGET_EXHAUSTED"
    assert result.evidence.status == "INCOMPLETE"
    assert result.evidence.total_units is None


def test_source_checkpoint_resumes_at_next_act_without_refetching_orders():
    order, summary, products = _fake_data()
    client = _FakeOzonSupplyClient(
        pages=[{"error": False, "order_ids": [1001], "last_id": None}],
        orders={1001: order},
        summaries={1001: summary},
        products={2001: products},
    )
    source = OzonCrossDockingSupplySource(client)

    first = source.collect_window(
        date_from=date(2026, 9, 1),
        date_to=date(2026, 9, 30),
        max_requests=2,
    )
    second = source.collect_window(
        date_from=date(2026, 9, 1),
        date_to=date(2026, 9, 30),
        checkpoint=first.checkpoint,
        max_requests=2,
    )

    assert first.evidence.status == "INCOMPLETE"
    assert first.evidence.total_units is None
    assert first.checkpoint is not None
    assert second.evidence.status == "COMPLETE"
    assert second.evidence.total_units == 100
    assert [call[0] for call in client.calls] == [
        "list",
        "details",
        "summary",
        "products",
    ]


def test_checkpoint_scope_mismatch_does_not_reuse_or_query_other_window():
    order, _, _ = _fake_data()
    client = _FakeOzonSupplyClient(
        pages=[{"error": False, "order_ids": [1001], "last_id": None}],
        orders={1001: order},
        summaries={},
        products={},
    )
    source = OzonCrossDockingSupplySource(client)
    initial = source.collect_window(
        date_from=date(2026, 9, 1),
        date_to=date(2026, 9, 30),
        max_requests=1,
    )

    mismatch = source.collect_window(
        date_from=date(2026, 8, 1),
        date_to=date(2026, 8, 31),
        checkpoint=initial.checkpoint,
    )

    assert mismatch.evidence.issue_codes == ("CHECKPOINT_SCOPE_MISMATCH",)
    assert mismatch.evidence.total_units is None
    assert len(client.calls) == 1


def test_source_invalid_window_does_not_call_api():
    client = _FakeOzonSupplyClient(pages=[], orders={}, summaries={}, products={})

    result = OzonCrossDockingSupplySource(client).collect_window(
        date_from=date(2026, 10, 1),
        date_to=date(2026, 9, 1),
    )

    assert result.request_count == 0
    assert result.evidence.status == "INCOMPLETE"
    assert "INVALID_DATE_WINDOW" in result.evidence.issue_codes
    assert client.calls == []


def test_source_missing_next_cursor_on_full_page_fails_closed():
    client = _FakeOzonSupplyClient(
        pages=[{"error": False, "order_ids": list(range(1, 101)), "last_id": None}],
        orders={},
        summaries={},
        products={},
    )

    result = OzonCrossDockingSupplySource(client).collect_window(
        date_from=date(2026, 9, 1),
        date_to=date(2026, 9, 30),
    )

    assert result.evidence.status == "INCOMPLETE"
    assert result.evidence.total_units is None
    assert result.stopped_reason == "SUPPLY_LIST_CURSOR_MISSING"


def test_source_invalid_cursor_fails_closed():
    client = _FakeOzonSupplyClient(
        pages=[{"error": False, "order_ids": [1001], "last_id": {"secret": 1}}],
        orders={},
        summaries={},
        products={},
    )

    result = OzonCrossDockingSupplySource(client).collect_window(
        date_from=date(2026, 9, 1),
        date_to=date(2026, 9, 30),
    )

    assert result.evidence.status == "INCOMPLETE"
    assert result.evidence.total_units is None
    assert result.stopped_reason == "SUPPLY_LIST_CURSOR_INVALID"
    assert len(client.calls) == 1


def test_source_api_error_does_not_expose_error_body():
    client = _FakeOzonSupplyClient(
        pages=[
            {
                "error": True,
                "code": "OZON_HTTP_ERROR",
                "raw_response": "private vendor response",
            }
        ],
        orders={},
        summaries={},
        products={},
    )

    result = OzonCrossDockingSupplySource(client).collect_window(
        date_from=date(2026, 9, 1),
        date_to=date(2026, 9, 30),
    )

    assert result.evidence.status == "INCOMPLETE"
    assert result.evidence.total_units is None
    assert result.stopped_reason == "SUPPLY_LIST_UNAVAILABLE"
    assert "private vendor response" not in repr(result)
